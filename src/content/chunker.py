"""
ContentChunker — deterministic adaptive splitting of section content into TeachingUnits.

Replaces the rigid 3-part LLM split with structural analysis:
- Split at subsection boundaries (detected by headers)
- Split at example boundaries (EXAMPLE patterns)
- Split at equation group boundaries for large concept blocks
- Chunk size adapts to merit (AdaptationLevel)

No LLM calls — purely deterministic based on text structure.
"""

import re
import logging
from typing import List, Tuple

from models.data_models import AdaptationLevel, Section, TeachingUnit

logger = logging.getLogger(__name__)

# Patterns that signal a natural split point in the content
SUBSECTION_PATTERNS = [
    re.compile(r'^#{1,3}\s+(.+)$', re.MULTILINE),               # Markdown headings
    re.compile(r'^([A-Z][A-Za-z\s]{3,40})\s*$', re.MULTILINE),  # ALL CAPS or Title Case short lines
]

EXAMPLE_PATTERN = re.compile(
    r'(EXAMPLE|Example)\s+(\d+[-\.]\d*)',
    re.MULTILINE,
)

EQUATION_BLOCK_PATTERN = re.compile(
    r'(?:Eq(?:uation)?\.?\s*\(?\d+[-\.]\d*\)?|Eq\.\s*\d+)',
    re.IGNORECASE,
)


class ContentChunker:
    """Splits a section's content into adaptive TeachingUnits."""

    def chunk(
        self,
        section: Section,
        adaptation: AdaptationLevel = AdaptationLevel.NORMAL,
    ) -> List[TeachingUnit]:
        """
        Split a section into TeachingUnits.

        Args:
            section: The section to chunk
            adaptation: Current merit adaptation level (controls target chunk size)

        Returns:
            Ordered list of TeachingUnits
        """
        target_words = adaptation.target_chunk_words
        raw_content = section.content

        if not raw_content.strip():
            return []

        # Step 1: Split at natural structural boundaries
        candidate_splits = self._find_split_points(raw_content)

        # Step 2: Merge very small splits, break very large ones
        chunks = self._balance_chunks(raw_content, candidate_splits, target_words)

        # Step 3: Convert to TeachingUnit objects with metadata
        units = []
        for i, (title, content) in enumerate(chunks):
            unit_id = f"{section.section_id}_u{i+1}"
            units.append(TeachingUnit(
                unit_id=unit_id,
                title=title or f"{section.title} — Part {i+1}",
                content=content.strip(),
                page_range=(section.page_start, section.page_end),
                content_type=self._classify_content(content),
                source_file=section.source_file,
                equations=self._extract_equation_refs(content),
                figures=self._extract_figure_refs(content),
                examples=self._extract_example_refs(content),
                difficulty=self._estimate_difficulty(content),
            ))

        logger.debug(
            f"Chunked '{section.title}' into {len(units)} units "
            f"(target: {target_words} words, adaptation: {adaptation.value})"
        )
        return units

    # ── Split Point Detection ────────────────────────────────────────────────

    def _find_split_points(self, content: str) -> List[Tuple[int, str]]:
        """
        Find natural split points in the content.

        Returns list of (char_offset, heading_title) tuples.
        """
        splits = [(0, "")]  # Always start at beginning

        lines = content.split('\n')
        offset = 0

        for line in lines:
            stripped = line.strip()

            # Markdown heading
            md_match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
            if md_match:
                splits.append((offset, md_match.group(2)))

            # Example boundary — always a split point
            ex_match = EXAMPLE_PATTERN.match(stripped)
            if ex_match:
                splits.append((offset, f"Example {ex_match.group(2)}"))

            # Numbered points/concepts (1., 2., 3., etc. at start of paragraph)
            numbered_match = re.match(r'^(\d+)\.\s+([A-Z].{10,})$', stripped)
            if numbered_match and offset > 50:  # Only after some content
                splits.append((offset, f"Point {numbered_match.group(1)}"))

            # Page marker from PDF extraction (=== PAGE N ===)
            if re.match(r'^={3,}\s*PAGE\s+\d+', stripped):
                splits.append((offset, ""))

            offset += len(line) + 1  # +1 for newline

        # Deduplicate adjacent splits at same offset
        seen = set()
        unique_splits = []
        for split in splits:
            if split[0] not in seen:
                seen.add(split[0])
                unique_splits.append(split)

        return unique_splits

    def _balance_chunks(
        self,
        content: str,
        split_points: List[Tuple[int, str]],
        target_words: int,
    ) -> List[Tuple[str, str]]:
        """
        Given split points, merge small chunks and break large ones
        to hit the target word count per chunk.
        """
        # If no split points found but content is large, force splits at paragraph level
        if len(split_points) <= 1:
            content_words = len(content.split())
            max_words = target_words * 2.0  # Max 2x target size

            if content_words > max_words:
                # Content is too large — break at paragraph boundaries even without markers
                return self._force_paragraph_split(content, target_words)
            else:
                return [("", content)]

        # Extract raw chunks from split points
        raw_chunks = []
        for i, (offset, title) in enumerate(split_points):
            end = split_points[i + 1][0] if i + 1 < len(split_points) else len(content)
            chunk_text = content[offset:end]
            raw_chunks.append((title, chunk_text))

        # Merge chunks that are too small (< 40% of target)
        min_words = target_words * 0.4
        merged = []
        buffer_title = ""
        buffer_text = ""

        for title, text in raw_chunks:
            words = len(text.split())
            if words < min_words and buffer_text:
                # Too small — merge with previous
                buffer_text += "\n" + text
            else:
                if buffer_text:
                    merged.append((buffer_title, buffer_text))
                buffer_title = title
                buffer_text = text

        if buffer_text:
            merged.append((buffer_title, buffer_text))

        # Break chunks that are too large (> 200% of target)
        max_words = target_words * 2.0
        final = []
        for title, text in merged:
            words = len(text.split())
            if words > max_words:
                # Break at equation boundaries or mid-paragraph
                sub_chunks = self._break_large_chunk(text, target_words)
                for j, sub in enumerate(sub_chunks):
                    sub_title = title if j == 0 else f"{title} (continued)"
                    final.append((sub_title, sub))
            else:
                final.append((title, text))

        return final if final else [("", content)]

    def _break_large_chunk(self, text: str, target_words: int) -> List[str]:
        """Break an oversized chunk at paragraph boundaries."""
        paragraphs = re.split(r'\n\n+', text)
        chunks = []
        current = []
        current_words = 0

        for para in paragraphs:
            para_words = len(para.split())
            if current_words + para_words > target_words * 1.5 and current:
                chunks.append("\n\n".join(current))
                current = [para]
                current_words = para_words
            else:
                current.append(para)
                current_words += para_words

        if current:
            chunks.append("\n\n".join(current))

        return chunks if chunks else [text]

    def _force_paragraph_split(self, text: str, target_words: int) -> List[Tuple[str, str]]:
        """
        Force split at paragraph boundaries when no structural markers found.
        Used for unstructured PDF content that's too large.
        """
        paragraphs = re.split(r'\n\n+', text)
        chunks = []
        current_title = ""
        current_text = []
        current_words = 0
        chunk_num = 1

        for para in paragraphs:
            para_words = len(para.split())

            # Start new chunk if we've hit the target size
            if current_words > target_words * 1.2 and current_text:
                chunks.append((current_title or f"Part {chunk_num}", "\n\n".join(current_text)))
                chunk_num += 1
                current_title = ""
                current_text = []
                current_words = 0

            current_text.append(para)
            current_words += para_words

        # Add remaining content
        if current_text:
            chunks.append((current_title or f"Part {chunk_num}", "\n\n".join(current_text)))

        return chunks if chunks else [("", text)]

    # ── Metadata Extraction ─────────────────────────────────────────────────

    def _extract_equation_refs(self, content: str) -> List[str]:
        refs = re.findall(r'(?:Eq(?:uation)?\.?\s*\(?)(\d+[-\.]\d+)\)?', content, re.IGNORECASE)
        return list(dict.fromkeys(refs))[:10]  # deduplicate, cap at 10

    def _extract_figure_refs(self, content: str) -> List[str]:
        refs = re.findall(r'(?:Fig(?:ure)?\.?\s*)(\d+[-\.]\d+)', content, re.IGNORECASE)
        return list(dict.fromkeys(refs))[:10]

    def _extract_example_refs(self, content: str) -> List[str]:
        refs = re.findall(r'(?:Example\s+)(\d+[-\.]\d*)', content, re.IGNORECASE)
        return list(dict.fromkeys(refs))[:10]

    def _classify_content(self, content: str) -> str:
        content_lower = content.lower()
        if EXAMPLE_PATTERN.search(content):
            return "example"
        if len(EQUATION_BLOCK_PATTERN.findall(content)) >= 3:
            return "equation_group"
        if any(w in content_lower for w in ["proof:", "theorem:", "lemma:", "definition:"]):
            return "theorem"
        if any(w in content_lower for w in ["reaction:", "mechanism:", "→", "⟶"]):
            return "reaction"
        if any(w in content_lower for w in ["derive", "derivation", "show that"]):
            return "derivation"
        return "concept"

    def _estimate_difficulty(self, content: str) -> str:
        eq_count = len(EQUATION_BLOCK_PATTERN.findall(content))
        ex_count = len(EXAMPLE_PATTERN.findall(content))
        word_count = len(content.split())

        score = 0
        if eq_count > 4:
            score += 2
        elif eq_count > 1:
            score += 1
        if ex_count > 2:
            score += 1
        if word_count > 1000:
            score += 1

        if score >= 3:
            return "high"
        elif score >= 1:
            return "medium"
        return "low"
