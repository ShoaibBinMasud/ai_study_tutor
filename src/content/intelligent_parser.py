"""
IntelligentDocumentParser — Vision-based parsing for image-heavy PDFs.

For PDFs with minimal text (MIT slides, whiteboard photos, image-heavy notes),
uses vision LLM to extract real content. Only activates when needed;
textbook PDFs with built-in TOCs bypass this entirely (no vision LLM cost).

Three phases:
  1. Inspect: Sample + render page 1 (1 LLM call) → DocumentProfile
  2. Structure: Render all pages → LLM groups into sections with summaries
  3. Content: Lazy vision fallback for thin text sections on first access
"""

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import fitz

from models.data_models import ProcessedDocument, TOCEntry, Section
from utils.llm_client import LLMClient
from tools.pdf_extraction_tool import extract_pdf_pages

logger = logging.getLogger(__name__)


@dataclass
class DocumentProfile:
    """Profile of a PDF determined by the Inspect phase."""
    doc_type: str           # "slides" | "textbook" | "notes" | "image_heavy"
    total_pages: int
    needs_vision: bool
    has_builtin_toc: bool
    structure_hint: str
    sample_titles: List[str] = field(default_factory=list)
    suggested_file_type: str = "pdf_notes"


class IntelligentDocumentParser:
    """Vision-based parser for image-heavy PDFs."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def process(self, file_path: str) -> ProcessedDocument:
        """Entry point: inspect document, build structure."""
        doc = fitz.open(file_path)
        try:
            logger.info(f"IntelligentDocumentParser: Processing {Path(file_path).name}")
            profile = self._inspect_document(file_path, doc)
            logger.info(f"  Profile: {profile.doc_type}, needs_vision={profile.needs_vision}")

            toc_entries, sections = self._build_structure_from_profile(file_path, doc, profile)
            logger.info(f"  Built structure: {len(sections)} sections, {len(toc_entries)} TOC entries")

            return ProcessedDocument(
                file_path=file_path,
                file_type=profile.suggested_file_type,
                label=Path(file_path).name,
                toc=toc_entries,
                sections=sections,
            )
        finally:
            doc.close()

    def _inspect_document(self, file_path: str, doc: fitz.Document) -> DocumentProfile:
        """Phase 1: Sample text + render page 1 image, 1 LLM call → DocumentProfile."""
        total_pages = len(doc)

        # Sample pages for text analysis
        sample_page_indices = [0, 1, 2]  # pages 1-3 (0-indexed)
        if total_pages > 6:
            sample_page_indices.append(total_pages // 2)
        if total_pages > 2:
            sample_page_indices.append(total_pages - 1)

        # Extract text from samples
        sample_texts = []
        total_chars = 0
        for pnum in sample_page_indices:
            if pnum < total_pages:
                text = doc[pnum].get_text().strip()
                sample_texts.append(f"[Page {pnum+1}]: {text[:300]}")
                total_chars += len(text)

        avg_text = total_chars / max(len(sample_page_indices), 1)

        # Check built-in TOC
        raw_toc = doc.get_toc()
        has_builtin_toc = len(raw_toc) > 3

        # Render page 1 to base64
        page1_b64 = self.render_page_to_b64(doc, 0, dpi=100)

        prompt = f"""Analyze this PDF document:
- Filename: {Path(file_path).name}
- Total pages: {total_pages}
- Built-in TOC entries: {len(raw_toc)}
- Average text per page: {avg_text:.0f} chars

Sampled page text:
{chr(10).join(sample_texts[:4])}

The image shows page 1 of the document.

Respond with ONLY a JSON object:
{{
  "doc_type": "slides|textbook|notes|image_heavy",
  "needs_vision": true or false,
  "structure_hint": "brief description of structure",
  "sample_titles": ["inferred titles for first 5 sections"],
  "suggested_file_type": "pdf_slides|pdf_textbook|pdf_notes"
}}

Set needs_vision = true if avg_text_per_page < 300 OR the image shows diagrams as primary content."""

        try:
            logger.debug("Calling inspect LLM with page 1 image")
            result = self._vision_json_call(
                images_b64=[page1_b64],
                prompt=prompt,
                max_tokens=600,
            )
            return DocumentProfile(
                doc_type=result.get("doc_type", "notes"),
                total_pages=total_pages,
                needs_vision=result.get("needs_vision", avg_text < 300),
                has_builtin_toc=has_builtin_toc,
                structure_hint=result.get("structure_hint", ""),
                sample_titles=result.get("sample_titles", []),
                suggested_file_type=result.get("suggested_file_type", "pdf_notes"),
            )
        except Exception as e:
            logger.warning(f"Inspect LLM call failed: {e}. Using heuristics.")
            return DocumentProfile(
                doc_type="slides" if avg_text < 300 else "textbook",
                total_pages=total_pages,
                needs_vision=avg_text < 300,
                has_builtin_toc=has_builtin_toc,
                structure_hint="Fallback (LLM failed)",
                sample_titles=[],
                suggested_file_type="pdf_slides" if avg_text < 300 else "pdf_textbook",
            )

    def _build_structure_from_profile(
        self, file_path: str, doc: fitz.Document, profile: DocumentProfile
    ) -> Tuple[List[TOCEntry], List[Section]]:
        """Route to vision or TOC-based structure builder based on profile."""
        if profile.has_builtin_toc and not profile.needs_vision:
            logger.info("Using TOC-based structure (textbook path)")
            return self._build_structure_from_toc(file_path, doc.get_toc(), profile.total_pages)
        elif profile.needs_vision or profile.doc_type in ("slides", "image_heavy"):
            logger.info("Using vision-based structure (slide/image-heavy path)")
            return self._build_structure_via_vision(file_path, doc, profile)
        else:
            logger.info("Using TOC-based structure (fallback)")
            return self._build_structure_from_toc(file_path, doc.get_toc(), profile.total_pages)

    def _build_structure_via_vision(
        self, file_path: str, doc: fitz.Document, profile: DocumentProfile
    ) -> Tuple[List[TOCEntry], List[Section]]:
        """Phase 2: Render pages, group into sections via LLM, pre-populate content."""
        total_pages = profile.total_pages

        # Cap images per call; sample evenly for large PDFs
        MAX_IMAGES = 20
        if total_pages <= MAX_IMAGES:
            page_indices = list(range(total_pages))
        else:
            # Sample MAX_IMAGES pages evenly
            step = total_pages / MAX_IMAGES
            page_indices = [int(i * step) for i in range(MAX_IMAGES)]

        logger.info(f"Rendering {len(page_indices)} pages for structure analysis")

        images_b64 = []
        page_nums = []
        for pidx in page_indices:
            b64 = self.render_page_to_b64(doc, pidx, dpi=100)
            images_b64.append(b64)
            page_nums.append(pidx + 1)

        prompt = f"""Analyze these {len(images_b64)} lecture slide pages (pages: {page_nums}).
Group them into logical teaching sections.

Respond with ONLY a JSON object:
{{
  "sections": [
    {{
      "section_id": "slide_1",
      "title": "descriptive title",
      "page_start": 1,
      "page_end": 2,
      "summary": "what this section teaches, what diagrams show, equations present"
    }}
  ]
}}

Rules:
- Titles must be descriptive (NOT "Slide 3" — say WHAT is being taught)
- summary is what the student will learn from this section — be thorough about diagrams and equations
- ALL pages from 1 to {total_pages} must be covered (no gaps)
- This document has {total_pages} pages total"""

        try:
            logger.debug(f"Calling structure LLM with {len(images_b64)} page images")
            result = self._vision_json_call(
                images_b64=images_b64,
                prompt=prompt,
                max_tokens=3000,
            )
            raw_sections = result.get("sections", [])
            logger.info(f"LLM returned {len(raw_sections)} sections")
        except Exception as e:
            logger.warning(f"Vision structure call failed: {e}. Using page-per-section fallback.")
            raw_sections = [
                {
                    "section_id": f"slide_{i+1}",
                    "title": (profile.sample_titles[i] if i < len(profile.sample_titles) else "") or f"Slide {i+1}",
                    "page_start": i + 1,
                    "page_end": i + 1,
                    "summary": "",
                }
                for i in range(min(total_pages, 20))
            ]

        toc_entries = []
        sections = []
        for i, s in enumerate(raw_sections):
            sid = s.get("section_id", f"slide_{i+1}")
            title = s.get("title", f"Slide {i+1}")
            page_start = int(s.get("page_start", i + 1))
            page_end = int(s.get("page_end", page_start))
            summary = s.get("summary", "")

            toc_entries.append(TOCEntry(
                title=title,
                level=2,
                page_or_slide=page_start,
                source_file=file_path,
                section_id=sid,
            ))
            sections.append(Section(
                section_id=sid,
                title=title,
                content=summary,  # Pre-populated from LLM
                page_start=page_start,
                page_end=page_end,
                source_file=file_path,
            ))

        return toc_entries, sections

    def _build_structure_from_toc(
        self, file_path: str, raw_toc: list, total_pages: int
    ) -> Tuple[List[TOCEntry], List[Section]]:
        """Build structure from PDF's built-in TOC (for traditional textbooks)."""
        toc_entries = []
        sections = []

        for i, (level, title, page) in enumerate(raw_toc):
            # Determine page range: from this entry to before next entry
            if i + 1 < len(raw_toc):
                next_page = raw_toc[i + 1][2]
                page_end = max(page, next_page - 1)
            else:
                page_end = total_pages

            section_id = self._toc_to_section_id(title, level, i)

            toc_entries.append(TOCEntry(
                title=title,
                level=level,
                page_or_slide=page,
                source_file=file_path,
                section_id=section_id,
            ))

            # Only extract chapters and sections (not subsections)
            if level <= 2:
                sections.append(Section(
                    section_id=section_id,
                    title=title,
                    content="",  # Lazy loaded on access
                    page_start=page,
                    page_end=page_end,
                    source_file=file_path,
                ))

        return toc_entries, sections

    def _toc_to_section_id(self, title: str, level: int, index: int) -> str:
        """Convert a TOC title to a normalized section ID."""
        # Try to extract numbering like "1-2", "3.4", "Chapter 5", etc.
        m = re.match(r'(?:chapter|section|ch|sec)?\s*(\d+)[.\-\s](\d+)', title, re.IGNORECASE)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        m = re.match(r'(?:chapter|ch)?\s*(\d+)', title, re.IGNORECASE)
        if m:
            return f"ch{m.group(1)}" if level == 1 else f"sec{m.group(1)}"
        # Fallback: slug-ify title
        clean = re.sub(r'[^a-z0-9]', '_', title.lower())[:20].strip('_')
        return clean or f"entry_{index}"

    def get_section_content(self, section: Section) -> str:
        """Lazy: extract text, use vision fallback if thin."""
        try:
            text = extract_pdf_pages(section.source_file, section.page_start, section.page_end)
        except Exception as e:
            logger.error(f"Failed to extract pages: {e}")
            text = ""

        if self.is_content_thin(text):
            logger.info(f"Thin content ({section.section_id}) — using vision fallback")
            return self._vision_fallback(section)
        return text

    def _vision_fallback(self, section: Section) -> str:
        """Call vision_describe_page for each page in section range."""
        doc = fitz.open(section.source_file)
        try:
            pages = []
            for pnum in range(section.page_start, section.page_end + 1):
                if pnum - 1 < len(doc):
                    page_md = self.vision_describe_page(
                        doc=doc,
                        page_num=pnum - 1,  # 0-indexed
                        context=section.title,
                    )
                    pages.append(f"--- Page {pnum} ---\n{page_md}")
            return "\n\n".join(pages)
        finally:
            doc.close()

    def vision_describe_page(
        self, doc: fitz.Document, page_num: int, context: str = "", dpi: int = 150
    ) -> str:
        """Vision LLM: extract all teachable content from one page."""
        b64 = self.render_page_to_b64(doc, page_num, dpi=dpi)

        context_hint = f"Section context: {context}\n\n" if context else ""
        prompt = f"""{context_hint}Extract ALL teachable content from this slide page into markdown:
1. Text and bullet points verbatim
2. Diagrams: detailed paragraph describing what it shows and what concept it illustrates
3. Equations: transcribe in LaTeX ($...$ inline, $$...$$ display)
4. Graphs: axes, curve shape, key points, relationship shown
5. Tables: markdown format

Be thorough — a student will be taught from this."""

        try:
            return self.llm.get_vision_completion(
                image_b64=b64,
                prompt=prompt,
                max_tokens=2000,
                temperature=0.1,
            )
        except Exception as e:
            logger.error(f"vision_describe_page failed for page {page_num}: {e}")
            return f"[Page {page_num + 1} — vision extraction failed]"

    def render_page_to_b64(self, doc: fitz.Document, page_num: int, dpi: int = 150) -> str:
        """Render fitz page to base64 PNG."""
        page = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        return base64.b64encode(png_bytes).decode("ascii")

    def _vision_json_call(
        self, images_b64: List[str], prompt: str, max_tokens: int = 2000
    ) -> Dict[str, Any]:
        """Send multimodal message with images, expect JSON response."""
        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"}
            })

        messages = [{"role": "user", "content": content}]
        response = self.llm.chat(
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = response["choices"][0]["message"]["content"]
        return json.loads(raw)

    @staticmethod
    def is_content_thin(text: str, threshold: int = 200) -> bool:
        """Check if text is sparse (excluding boilerplate headers from extract_pdf_pages)."""
        if not text:
            return True

        # Strip boilerplate headers
        lines = text.split("\n")
        real_lines = [
            line for line in lines
            if line
            and not line.startswith("PDF:")
            and not line.startswith("Pages:")
            and not line.startswith("===")
            and not line.startswith("PAGE ")
            and not line.startswith("Chapter ")
            and not line.startswith("Section ")
            and not line.startswith("EXTRACTION COMPLETE")
        ]
        real_content = "\n".join(real_lines).strip()
        return len(real_content) < threshold
