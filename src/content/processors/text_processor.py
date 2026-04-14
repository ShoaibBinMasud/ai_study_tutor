"""
Text/Markdown Processor — plain text and Markdown files.

Parses headings (# for Markdown, ALL CAPS lines for plain text) to build TOC.
"""

import logging
import re
from pathlib import Path
from typing import List, Tuple

from models.data_models import ProcessedDocument, TOCEntry, Section

logger = logging.getLogger(__name__)


class TextProcessor:
    """Processes .txt and .md files into ProcessedDocument format."""

    def process(self, file_path: str) -> ProcessedDocument:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        label = path.stem.replace("_", " ").replace("-", " ").title()
        is_markdown = path.suffix.lower() == ".md"

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read()

        if is_markdown:
            toc_entries, sections = self._parse_markdown(raw_text, file_path)
        else:
            toc_entries, sections = self._parse_plain_text(raw_text, file_path)

        return ProcessedDocument(
            file_path=file_path,
            file_type="text",
            label=label,
            toc=toc_entries,
            sections=sections,
        )

    def _parse_markdown(self, text: str, source_file: str) -> Tuple[List[TOCEntry], List[Section]]:
        toc_entries = []
        sections = []
        current_heading = None
        current_lines = []
        pseudo_page = 1

        def flush():
            if current_heading is None:
                return
            title, level, section_id = current_heading
            content = "\n".join(current_lines).strip()
            toc_entries.append(TOCEntry(
                title=title, level=level, page_or_slide=pseudo_page,
                source_file=source_file, section_id=section_id,
            ))
            sections.append(Section(
                section_id=section_id, title=title, content=content,
                page_start=pseudo_page, page_end=pseudo_page,
                source_file=source_file,
            ))

        counter = 0
        for line in text.splitlines():
            h1 = re.match(r'^#\s+(.+)', line)
            h2 = re.match(r'^##\s+(.+)', line)
            h3 = re.match(r'^###\s+(.+)', line)

            if h1:
                flush()
                counter += 1
                pseudo_page += 1
                current_heading = (h1.group(1).strip(), 1, f"sec_{counter}")
                current_lines = []
            elif h2:
                flush()
                counter += 1
                pseudo_page += 1
                current_heading = (h2.group(1).strip(), 2, f"sec_{counter}")
                current_lines = []
            elif h3:
                current_lines.append(f"\n### {h3.group(1).strip()}")
            else:
                current_lines.append(line)

        flush()

        if not sections:
            toc_entries, sections = self._single_section(text, source_file)

        return toc_entries, sections

    def _parse_plain_text(self, text: str, source_file: str) -> Tuple[List[TOCEntry], List[Section]]:
        """Heuristic: short all-caps lines or lines ending with ':' are headings."""
        toc_entries = []
        sections = []
        current_heading = None
        current_lines = []
        pseudo_page = 1
        counter = 0

        def flush():
            if current_heading is None:
                return
            title, level, section_id = current_heading
            content = "\n".join(current_lines).strip()
            toc_entries.append(TOCEntry(
                title=title, level=level, page_or_slide=pseudo_page,
                source_file=source_file, section_id=section_id,
            ))
            sections.append(Section(
                section_id=section_id, title=title, content=content,
                page_start=pseudo_page, page_end=pseudo_page,
                source_file=source_file,
            ))

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                current_lines.append("")
                continue

            is_heading = (
                (stripped.isupper() and 3 < len(stripped) < 80)
                or re.match(r'^[A-Z][^.!?]*:\s*$', stripped)
            )

            if is_heading:
                flush()
                counter += 1
                pseudo_page += 1
                current_heading = (stripped.rstrip(":"), 2, f"sec_{counter}")
                current_lines = []
            else:
                current_lines.append(stripped)

        flush()

        if not sections:
            toc_entries, sections = self._single_section(text, source_file)

        return toc_entries, sections

    def _single_section(self, text: str, source_file: str) -> Tuple[List[TOCEntry], List[Section]]:
        label = Path(source_file).stem
        toc_entries = [TOCEntry(
            title=label, level=1, page_or_slide=1,
            source_file=source_file, section_id="full_doc",
        )]
        sections = [Section(
            section_id="full_doc", title=label, content=text.strip(),
            page_start=1, page_end=1, source_file=source_file,
        )]
        return toc_entries, sections
