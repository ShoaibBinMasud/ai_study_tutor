"""
FileManager — manages all uploaded documents for a tutoring session.

Responsibilities:
- Accept files at startup or mid-session
- Route each file to DocumentProcessor
- Auto-detect subject from loaded materials
- Provide unified TOC view across all files
- Route content queries to the correct file
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models.data_models import (
    ProcessedDocument, SubjectProfile, TOCEntry, Section
)
from content.document_processor import DocumentProcessor
from utils.llm_client import LLMClient

# Lazy content loading: extract PDF pages on demand using the page range from the TOC
try:
    from tools.pdf_extraction_tool import extract_pdf_pages
    HAS_PDF_TOOLS = True
except ImportError:
    HAS_PDF_TOOLS = False

try:
    from content.intelligent_parser import IntelligentDocumentParser
    HAS_INTELLIGENT_PARSER = True
except ImportError:
    HAS_INTELLIGENT_PARSER = False

logger = logging.getLogger(__name__)

SUBJECT_DETECTION_PROMPT = """You are analyzing uploaded study materials.
Based on the table of contents and sample content below, determine:
1. The academic subject
2. The sub-field or specific topic area
3. The academic level
4. The type of material
5. The best teaching style for this subject

{toc_sample}

{content_sample}

Respond with ONLY a JSON object:
{{
  "subject": "e.g. Physics, Mathematics, Organic Chemistry, Computer Science",
  "sub_field": "e.g. Classical Mechanics, Linear Algebra, Reaction Mechanisms",
  "level": "introductory | intermediate | advanced | graduate",
  "material_type": "textbook | lecture_notes | problem_set | formula_sheet | exam_prep | mixed",
  "teaching_style_hints": "equation-heavy | proof-based | conceptual | reaction-based | code-focused | diagram-heavy"
}}"""


class FileManager:
    """Manages all uploaded documents for the current tutoring session."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.processor = DocumentProcessor(llm_client)
        self.documents: List[ProcessedDocument] = []
        self.subject_profile: Optional[SubjectProfile] = None
        # Index for fast lookup: section_id → ProcessedDocument
        self._section_index: Dict[str, ProcessedDocument] = {}

    # ── File Loading ────────────────────────────────────────────────────────

    def load_file(self, file_path: str) -> ProcessedDocument:
        """Process and register a new file. Can be called mid-session."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(f"Loading file: {path.name}")
        doc = self.processor.process(file_path)
        self.documents.append(doc)

        # Update section index
        for section in doc.sections:
            self._section_index[section.section_id] = doc

        # Log what sections were found
        section_ids = [s.section_id for s in doc.sections]
        logger.info(
            f"Loaded {path.name} ({doc.file_type}): {len(doc.sections)} sections\n"
            f"  Section IDs: {section_ids[:10]}"
            + (f" ... ({len(section_ids)} total)" if len(section_ids) > 10 else "")
        )

        # Re-detect subject now that we have more material
        self._detect_subject()
        return doc

    def load_files(self, file_paths: List[str]) -> List[ProcessedDocument]:
        """Load multiple files at once."""
        docs = []
        for fp in file_paths:
            try:
                docs.append(self.load_file(fp))
            except Exception as e:
                logger.error(f"Failed to load {fp}: {e}")
        return docs

    # ── Subject Detection ───────────────────────────────────────────────────

    def _detect_subject(self):
        """Auto-detect subject from all loaded documents (1 LLM call)."""
        if not self.documents:
            return

        # Build a compact sample: first 5 TOC entries + first 500 chars of first section
        toc_lines = []
        content_lines = []

        for doc in self.documents:
            toc_lines.append(f"[{doc.label}]")
            for entry in doc.toc[:8]:
                indent = "  " * (entry.level - 1)
                toc_lines.append(f"{indent}{entry.title}")

            if doc.sections:
                snippet = doc.sections[0].content[:400].strip()
                if snippet:
                    content_lines.append(f"[Sample from {doc.label}]:\n{snippet}")

        toc_sample = "TABLE OF CONTENTS:\n" + "\n".join(toc_lines)
        content_sample = "\n\n".join(content_lines) if content_lines else ""

        prompt = SUBJECT_DETECTION_PROMPT.format(
            toc_sample=toc_sample,
            content_sample=content_sample,
        )

        try:
            result = self.llm.get_json_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.1,
            )
            self.subject_profile = SubjectProfile(
                subject=result.get("subject", "Unknown"),
                sub_field=result.get("sub_field", ""),
                level=result.get("level", "intermediate"),
                material_type=result.get("material_type", "textbook"),
                teaching_style_hints=result.get("teaching_style_hints", "conceptual"),
            )
            logger.info(
                f"Subject detected: {self.subject_profile.subject} "
                f"({self.subject_profile.level}) — {self.subject_profile.teaching_style_hints}"
            )
        except Exception as e:
            logger.warning(f"Subject detection failed: {e}")
            self.subject_profile = SubjectProfile(
                subject="STEM", sub_field="", level="intermediate",
                material_type="textbook", teaching_style_hints="conceptual",
            )

    # ── Content Access ──────────────────────────────────────────────────────

    def get_unified_toc(self) -> List[TOCEntry]:
        """All TOC entries across all documents."""
        entries = []
        for doc in self.documents:
            entries.extend(doc.toc)
        return entries

    def get_all_section_ids(self) -> List[str]:
        return list(self._section_index.keys())

    def get_section(self, section_id: str) -> Optional[Section]:
        """
        Retrieve a section by ID. Lazily loads content if empty (on first access).

        Also handles section references like "1-2" when only chapters are in the TOC
        by resolving to the parent chapter (e.g. "ch1") and loading that.
        """
        # 1. Direct match
        doc = self._section_index.get(section_id)
        if doc:
            for section in doc.sections:
                if section.section_id == section_id:
                    if not section.content and HAS_PDF_TOOLS:
                        self._load_section_content(section)
                    return section

        # 2. Try resolving "X-Y" → parent chapter "chX"
        parent_id = self._resolve_to_parent_chapter(section_id)
        if parent_id and parent_id != section_id:
            doc = self._section_index.get(parent_id)
            if doc:
                for section in doc.sections:
                    if section.section_id == parent_id:
                        if not section.content and HAS_PDF_TOOLS:
                            self._load_section_content(section)
                        # Return a virtual section scoped to the chapter,
                        # but label it with the requested section_id
                        return Section(
                            section_id=section_id,
                            title=section.title,
                            content=section.content,
                            page_start=section.page_start,
                            page_end=section.page_end,
                            source_file=section.source_file,
                        )

        return None

    def _resolve_to_parent_chapter(self, section_id: str) -> Optional[str]:
        """
        If section_id looks like "1-2" or "1.2", return the parent chapter id "ch1".
        Used when the PDF TOC only has chapters, not individual sections.
        """
        # Match "1-2", "1.2", "1-2-3" — extract the first number as chapter
        match = re.match(r'^(\d+)[.\-]', section_id)
        if match:
            chapter_num = match.group(1)
            candidate = f"ch{chapter_num}"
            if candidate in self._section_index:
                return candidate
        return None

    def _load_section_content(self, section: Section):
        """
        Lazily extract pages for a section using the page range stored in the TOC.

        The section already has start/end page from the TOC — we just extract
        those pages on first access. Falls back to vision if text is thin.
        """
        if not HAS_PDF_TOOLS:
            logger.warning("extract_pdf_pages not available; cannot load content")
            return

        if section.page_start == 0:
            logger.warning(f"Section {section.section_id} has no page metadata, skipping")
            return

        try:
            section.content = extract_pdf_pages(
                section.source_file, section.page_start, section.page_end
            )
            logger.info(
                f"Lazy-loaded '{section.section_id}' — "
                f"pages {section.page_start}-{section.page_end} "
                f"({len(section.content)} chars)"
            )

            # Check if content is thin — use vision fallback if available
            if HAS_INTELLIGENT_PARSER and IntelligentDocumentParser.is_content_thin(section.content):
                logger.info(f"Thin content ({section.section_id}) — using vision fallback")
                parser = IntelligentDocumentParser(self.llm)
                section.content = parser.get_section_content(section)

        except Exception as e:
            logger.error(f"Failed to load section {section.section_id}: {e}")
            section.content = ""

    def get_all_sections(self) -> List[Section]:
        """Return all sections from all loaded documents."""
        result = []
        for doc in self.documents:
            result.extend(doc.sections)
        return result

    def find_sections_by_query(self, query: str) -> List[Section]:
        """Fuzzy search for sections matching a topic, title, or section ID query."""
        query_lower = query.lower().strip()
        clean_query = query_lower.replace("section", "").replace("chapter", "").strip()
        results = []
        for doc in self.documents:
            for section in doc.sections:
                sid = section.section_id.lower()
                title = section.title.lower()
                if (
                    clean_query in sid
                    or sid in clean_query
                    or clean_query in title
                    or query_lower in title
                ):
                    results.append(section)

        # If no direct match found, try chapter-based resolution for "X-Y" patterns
        if not results:
            section = self.get_section(query)
            if section:
                results.append(section)

        return results

    def get_sections_for_chapter(self, chapter_ref: str) -> List[Section]:
        """Get all sections belonging to a chapter (e.g., 'ch1', 'chapter 1', '1')."""
        ref = chapter_ref.lower().replace("chapter", "").replace("ch", "").strip()
        results = []
        for doc in self.documents:
            for section in doc.sections:
                # Match section IDs like "1-1", "1-2", "1.1", "1.2"
                if section.section_id.startswith(f"{ref}-") or \
                   section.section_id.startswith(f"{ref}."):
                    results.append(section)
        return results

    # ── Chapter Navigation ───────────────────────────────────────────────────

    def get_chapter_sections(self, chapter_id: str) -> List:
        """
        Return all TOCEntry items that belong to this chapter.
        Matches by: chapter number prefix in section_id, or by level-1 title.
        Returns entries at level >= 2 (sections, not the chapter heading itself).
        """
        chapter_id = chapter_id.strip().lstrip("0")  # normalize "01" → "1"
        results = []

        for doc in self.documents:
            inside_chapter = False
            for entry in doc.toc:
                # Detect chapter boundary: level-1 entry whose title or section_id matches
                if entry.level == 1:
                    sid = entry.section_id.strip()
                    title_lower = entry.title.lower()
                    # Match "Chapter 1", "1", "ch1", etc.
                    inside_chapter = (
                        sid == chapter_id
                        or sid == f"ch{chapter_id}"
                        or title_lower in (f"chapter {chapter_id}", f"ch{chapter_id}")
                        or title_lower.startswith(f"chapter {chapter_id} ")
                        or title_lower.startswith(f"chapter {chapter_id}:")
                        or (sid.startswith(chapter_id + "-") and "-" not in chapter_id)
                    )
                    continue  # don't include the chapter heading itself

                # Also match sections whose section_id starts with "chapter_id-"
                if not inside_chapter:
                    sid = entry.section_id or ""
                    if sid.startswith(f"{chapter_id}-"):
                        inside_chapter = True

                if inside_chapter:
                    if entry.level == 1:
                        # Hit the next chapter — stop
                        inside_chapter = False
                    elif entry.level >= 2 and entry.section_id:
                        results.append(entry)

        return results

    def find_toc_entries_by_query(self, query: str) -> List:
        """Fuzzy search TOC entries by title or section_id."""
        query_lower = query.lower().replace("chapter", "").strip()
        results = []
        for doc in self.documents:
            for entry in doc.toc:
                if (query_lower in entry.title.lower()
                        or query_lower in entry.section_id.lower()):
                    results.append(entry)
        return results

    def get_chapter_list(self) -> List[str]:
        """Return list of chapter identifiers from the TOC."""
        chapters = []
        for doc in self.documents:
            for entry in doc.toc:
                if entry.level == 1 and entry.section_id:
                    chapters.append(f"{entry.section_id} ({entry.title})")
        return chapters or ["(no chapters detected)"]

    def format_toc_display(self) -> str:
        """Human-readable unified TOC for showing to the student."""
        lines = []
        for doc in self.documents:
            lines.append(f"\n[{doc.label}]")
            for entry in doc.toc:
                indent = "  " * (entry.level - 1)
                lines.append(f"{indent}{entry.title}")
        return "\n".join(lines)

    # ── Status ──────────────────────────────────────────────────────────────

    def summary(self) -> str:
        if not self.documents:
            return "No documents loaded."
        parts = [f"{len(self.documents)} document(s) loaded:"]
        for doc in self.documents:
            parts.append(f"  • {doc.label} ({doc.file_type}, {len(doc.sections)} sections)")
        if self.subject_profile:
            sp = self.subject_profile
            parts.append(f"\nDetected subject: {sp.subject} — {sp.sub_field} ({sp.level})")
        return "\n".join(parts)

    def debug_toc_structure(self) -> str:
        """Show the raw TOC structure for debugging section ID issues."""
        if not self.documents:
            return "No documents loaded."

        lines = ["=== TOC Structure Debug ===\n"]
        for doc in self.documents:
            lines.append(f"Document: {doc.label}")
            lines.append(f"File type: {doc.file_type}")
            lines.append(f"\nRaw TOC Entries ({len(doc.toc)}):")
            for entry in doc.toc[:20]:
                indent = "  " * (entry.level - 1)
                lines.append(
                    f"{indent}[L{entry.level}] {entry.section_id:20s} | {entry.title} "
                    f"(page {entry.page_or_slide})"
                )
            if len(doc.toc) > 20:
                lines.append(f"  ... and {len(doc.toc) - 20} more entries")

            lines.append(f"\nExtracted Sections ({len(doc.sections)}):")
            for section in doc.sections[:10]:
                lines.append(
                    f"  {section.section_id:20s} | {section.title} "
                    f"(pages {section.page_start}-{section.page_end})"
                )
            if len(doc.sections) > 10:
                lines.append(f"  ... and {len(doc.sections) - 10} more sections")
            lines.append("")

        return "\n".join(lines)
