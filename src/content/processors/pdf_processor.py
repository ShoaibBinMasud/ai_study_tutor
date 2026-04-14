"""
PDF Processor — handles both textbook PDFs (with built-in TOC) and unstructured PDFs (no TOC).

TOC extraction strategy (in order):
  1. fitz.get_toc()  — free, instant, works for most digital PDFs
  2. Vision LLM on pages 1-25 — reads the printed TOC from scanned/image PDFs
  3. Font-based heuristic detection — last resort for truly unstructured docs

Produces a normalized ProcessedDocument that works with the rest of the tutor system.
"""

import base64
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import sys

# Add src to path so existing tools can be imported
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import fitz
from tools.pdf_extraction_tool import extract_pdf_pages
from models.data_models import ProcessedDocument, TOCEntry, Section
from utils.pdf_extractor_utils import FontAnalyzer

logger = logging.getLogger(__name__)


class TOCExtractor:
    """
    Extract a table of contents from any PDF using a three-step cascade:
      1. fitz built-in TOC (free)
      2. Vision LLM on the first N pages (cheap — one call)
      3. Font-based heading detection (heuristic fallback)
    """

    TOC_PAGES = 25  # how many front-matter pages to send to vision

    def __init__(self, llm_client=None):
        self.llm = llm_client

    def extract(self, file_path: str, doc: fitz.Document) -> Tuple[list, str]:
        """
        Returns (raw_toc, source) where raw_toc is [(level, title, page), ...]
        and source is one of 'fitz', 'vision', 'font', 'none'.
        """
        # 0. Check cache first
        cached = self._load_toc_cache(file_path)
        if cached:
            return cached["toc"], cached["source"]

        # 1. Try fitz built-in TOC
        raw_toc = doc.get_toc()
        if raw_toc and len(raw_toc) > 3:
            logger.info(f"TOC: fitz built-in ({len(raw_toc)} entries)")
            self._save_toc_cache(file_path, raw_toc, "fitz")
            return raw_toc, "fitz"

        # 2. Font-based scan — full PyMuPDF scan (fast, no LLM, no vision)
        logger.info("TOC: no structured TOC found — running font-based full scan")
        total_pages = len(doc)
        analyzer = FontAnalyzer(doc)
        font_info = analyzer.analyze(sample_pages=20)
        raw_toc = PDFProcessor()._detect_headings_full(doc, font_info, total_pages)
        logger.info(f"TOC: font scan found {len(raw_toc)} heading(s)")

        # 3. LLM text validation — 1-2 cheap TEXT calls to fix bad page boundaries
        if raw_toc and self.llm is not None:
            raw_toc = self._validate_and_fix_toc(raw_toc, total_pages, file_path, doc)

        # 4. Guided fallback — if <3 chapters found, LLM estimates + targeted reads
        chapter_count = sum(1 for level, _, _ in raw_toc if level == 1)
        if chapter_count < 3 and self.llm is not None:
            raw_toc = self._guided_chapter_search(doc, raw_toc, total_pages, file_path)

        if raw_toc:
            self._save_toc_cache(file_path, raw_toc, "font")
            return raw_toc, "font"

        return [], "none"

    def _save_toc_cache(self, file_path: str, raw_toc: list, source: str):
        """Save extracted TOC as a JSON sidecar file next to the document."""
        cache_path = file_path + ".toc.json"
        try:
            data = {
                "source": source,
                "extracted_at": datetime.now().isoformat(),
                "file_mtime": os.path.getmtime(file_path),
                "toc": raw_toc,
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"TOC cache saved: {cache_path}")
        except Exception as e:
            logger.debug(f"Failed to save TOC cache: {e}")

    def _load_toc_cache(self, file_path: str) -> Optional[dict]:
        """Load cached TOC if it exists and file hasn't changed."""
        cache_path = file_path + ".toc.json"
        if not os.path.exists(cache_path):
            return None
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            current_mtime = os.path.getmtime(file_path)
            if abs(data.get("file_mtime", 0) - current_mtime) > 1.0:
                logger.debug(f"TOC cache stale (file modified): {file_path}")
                return None
            logger.info(f"TOC: loaded from cache ({data['source']}, {len(data['toc'])} entries)")
            return data
        except Exception as e:
            logger.debug(f"Failed to load TOC cache: {e}")
            return None

    def _validate_and_fix_toc(
        self, raw_toc: list, total_pages: int, file_path: str, doc: fitz.Document
    ) -> list:
        """
        Two cheap text LLM calls to sanity-check and repair extracted TOC.

        Call 1: identify entries that span implausibly many pages.
        Call 2 (only if suspects found): read pages near the boundary and ask LLM
                to determine the correct end page.

        Falls back to original raw_toc silently on any error.
        """
        # Build page-range pairs (start page of entry i, start page of entry i+1)
        toc_with_ranges = []
        for i, (level, title, page) in enumerate(raw_toc):
            if i + 1 < len(raw_toc):
                end = raw_toc[i + 1][2] - 1
            else:
                end = total_pages
            toc_with_ranges.append((level, title, page, end))

        toc_text = "\n".join(
            f"  L{level} | p.{page}-{end} ({end - page + 1} pages) | {title}"
            for level, title, page, end in toc_with_ranges
        )
        threshold = int(total_pages * 0.25)

        call1_prompt = (
            f"This is a {total_pages}-page textbook. Here is its extracted TOC with page ranges:\n\n"
            f"{toc_text}\n\n"
            f"A chapter spanning more than {threshold} pages in a {total_pages}-page book "
            f"is almost certainly a detection error (missed the next chapter start).\n"
            f"List ONLY the titles of entries with suspicious spans (> {threshold} pages). "
            f"If all look plausible, reply with an empty JSON array: []\n"
            f'Reply with only: {{"suspects": ["title1", "title2"]}}'
        )
        try:
            r1 = self.llm.chat(
                [{"role": "user", "content": call1_prompt}],
                max_tokens=300, temperature=0.1,
            )
            c1_text = r1["choices"][0]["message"].get("content", "")
            m = re.search(r'\{.*\}', c1_text, re.DOTALL)
            suspects = json.loads(m.group(0)).get("suspects", []) if m else []
        except Exception as e:
            logger.debug(f"TOC validation call 1 failed: {e}")
            return raw_toc

        if not suspects:
            logger.info("TOC validation: all ranges plausible")
            return raw_toc

        logger.info(f"TOC validation: suspect entries — {suspects}")

        # Call 2: read a few pages around each suspect's boundary and ask LLM to fix
        fixed_toc = list(raw_toc)
        for suspect_title in suspects:
            # Find the suspect entry
            idx = next(
                (i for i, (_, t, _) in enumerate(fixed_toc) if t == suspect_title), None
            )
            if idx is None:
                continue

            level, title, start_page = fixed_toc[idx]
            # Determine rough end area: start of next chapter if exists, else 60% of book
            if idx + 1 < len(fixed_toc):
                approx_end = fixed_toc[idx + 1][2]
            else:
                approx_end = total_pages

            # Read a window of 8 pages around where the next chapter might start
            window_start = max(start_page + 5, approx_end - 4)
            window_end = min(approx_end + 4, total_pages)

            window_text_parts = []
            for pg in range(window_start - 1, window_end):  # 0-indexed
                try:
                    page_obj = doc[pg]
                    page_text = page_obj.get_text("text").strip()[:400]
                    window_text_parts.append(f"--- Page {pg + 1} ---\n{page_text}")
                except Exception:
                    pass

            window_text = "\n\n".join(window_text_parts)

            call2_prompt = (
                f"I'm looking for where '{title}' ends in this {total_pages}-page textbook.\n"
                f"The chapter starts around page {start_page}. Here are pages {window_start}-{window_end}:\n\n"
                f"{window_text}\n\n"
                f"Based on the content above, on which page does '{title}' likely end "
                f"(i.e., where does the next chapter begin)? "
                f'Reply with only: {{"end_page": N}}'
            )
            try:
                r2 = self.llm.chat(
                    [{"role": "user", "content": call2_prompt}],
                    max_tokens=100, temperature=0.1,
                )
                c2_text = r2["choices"][0]["message"].get("content", "")
                m2 = re.search(r'\{.*\}', c2_text, re.DOTALL)
                if m2:
                    end_page = int(json.loads(m2.group(0)).get("end_page", 0))
                    if start_page < end_page <= total_pages:
                        logger.info(f"TOC fix: '{title}' end_page corrected to {end_page}")
                        # Insert a synthetic boundary note (doesn't change the entry itself,
                        # but _build_toc_from_raw will use next entry's start page as end)
                        # So we insert a marker entry right after end_page if no real next entry
                        if idx + 1 >= len(fixed_toc) or fixed_toc[idx + 1][2] > end_page + 10:
                            fixed_toc.insert(idx + 1, (1, f"__boundary_{title}__", end_page + 1))
            except Exception as e:
                logger.debug(f"TOC validation call 2 failed for '{title}': {e}")
                continue

        # Remove synthetic boundary markers — they only existed to shift end-page computation
        return [(lv, tt, pg) for lv, tt, pg in fixed_toc if not tt.startswith("__boundary_")]

    def _guided_chapter_search(
        self, doc: fitz.Document, raw_toc: list, total_pages: int, file_path: str
    ) -> list:
        """
        When font-based detection found fewer than 3 chapters, ask LLM to estimate
        where chapters are based on document structure, then read targeted pages to confirm.

        Avoids a full-book read — uses one LLM estimation call + targeted PyMuPDF reads.
        """
        # Read first 3 and last 2 pages of text as context
        context_pages = []
        for pg in list(range(min(3, total_pages))) + list(range(max(0, total_pages - 2), total_pages)):
            try:
                context_pages.append(doc[pg].get_text("text").strip()[:300])
            except Exception:
                pass
        doc_preview = "\n---\n".join(context_pages)

        # Summarize what we already found
        found_summary = (
            "\n".join(f"  p.{p}: {t}" for _, t, p in raw_toc[:10])
            if raw_toc else "  (nothing found)"
        )

        prompt = (
            f"I'm analyzing a {total_pages}-page textbook PDF. My font-based heading detector "
            f"found fewer than 3 chapters. Here is what it found:\n{found_summary}\n\n"
            f"Here are sample pages from the beginning and end of the book:\n{doc_preview}\n\n"
            f"Based on typical textbook structure and the content above, estimate where "
            f"each chapter starts. A {total_pages}-page book typically has 8-15 chapters.\n"
            f'Reply ONLY with: {{"chapters": [{{"title": "Chapter 1 ...", "start_page": N}}, ...]}}'
        )
        try:
            resp = self.llm.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=600, temperature=0.1,
            )
            text = resp["choices"][0]["message"].get("content", "")
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if not m:
                return raw_toc
            chapters = json.loads(m.group(0)).get("chapters", [])
        except Exception as e:
            logger.debug(f"Guided chapter search failed: {e}")
            return raw_toc

        if not chapters:
            return raw_toc

        # For each estimated chapter start, verify by reading 3 pages around it
        confirmed = []
        for ch in chapters:
            est_page = int(ch.get("start_page", 0))
            title_hint = ch.get("title", "")
            if est_page < 1 or est_page > total_pages:
                continue

            # Scan ±3 pages around the estimate to find the real heading
            best_page = est_page
            for pg in range(max(0, est_page - 3), min(total_pages, est_page + 3)):
                try:
                    page_obj = doc[pg]
                    page_text = page_obj.get_text("text").strip()
                    # Check if page starts with a chapter-like heading
                    first_lines = page_text[:200]
                    if re.search(r'(?:chapter|unit)\s+\d+|^\d+\s*\n', first_lines, re.I | re.M):
                        best_page = pg + 1  # 1-indexed
                        break
                except Exception:
                    pass

            confirmed.append((1, title_hint, best_page))
            logger.info(f"Guided search: confirmed '{title_hint}' at page {best_page}")

        if len(confirmed) >= 3:
            logger.info(f"Guided chapter search found {len(confirmed)} chapters")
            return sorted(confirmed + raw_toc, key=lambda x: x[2])

        return raw_toc

    def _extract_via_vision(self, file_path: str, doc: fitz.Document) -> Optional[list]:
        """Render up to TOC_PAGES pages, call LLM to extract the printed TOC."""
        total_pages = len(doc)
        pages_to_render = min(self.TOC_PAGES, total_pages)

        images_b64 = []
        for i in range(pages_to_render):
            page = doc[i]
            mat = fitz.Matrix(100 / 72, 100 / 72)  # 100 DPI — readable, small payload
            pix = page.get_pixmap(matrix=mat)
            png_bytes = pix.tobytes("png")
            b64 = base64.b64encode(png_bytes).decode("ascii")
            images_b64.append(b64)

        prompt = f"""These are the first {pages_to_render} pages of a PDF document (total: {total_pages} pages).
Look for a Table of Contents page. If you find one, extract all entries from it.

Return ONLY a JSON object:
{{
  "found": true or false,
  "entries": [
    {{
      "level": 1,
      "title": "Chapter 1: Introduction",
      "page": 5
    }}
  ]
}}

Rules:
- level 1 = chapter, level 2 = section, level 3 = subsection
- "page" is the page number the entry POINTS TO (the actual content page), not the TOC page itself
- If no TOC page found, return {{"found": false, "entries": []}}
- Include ALL entries you see — do not summarize or skip any"""

        content: List[Dict] = [{"type": "text", "text": prompt}]
        for b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"}
            })

        messages = [{"role": "user", "content": content}]
        response = self.llm.chat(
            messages=messages,
            max_tokens=2000,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(response["choices"][0]["message"]["content"])

        if not result.get("found") or not result.get("entries"):
            return None

        # Convert to fitz raw_toc format: [(level, title, page), ...]
        raw_toc = []
        for entry in result["entries"]:
            level = int(entry.get("level", 2))
            title = str(entry.get("title", "")).strip()
            page = int(entry.get("page", 1))
            if title and page > 0:
                raw_toc.append((level, title, page))

        return raw_toc if raw_toc else None


class PDFProcessor:
    """Processes PDF files into ProcessedDocument format."""

    def __init__(self, llm_client=None):
        self._toc_extractor = TOCExtractor(llm_client)

    def process(self, file_path: str) -> ProcessedDocument:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")

        doc = fitz.open(file_path)
        total_pages = len(doc)

        raw_toc, toc_source = self._toc_extractor.extract(file_path, doc)
        doc.close()

        if raw_toc:
            logger.info(f"Building structure from TOC ({toc_source}): {len(raw_toc)} entries")
            return self._process_textbook(file_path, raw_toc, total_pages)
        else:
            logger.info("No TOC found — using font-based heading detection")
            return self._process_slides(file_path, total_pages)

    def _process_textbook(self, file_path: str, raw_toc: list, total_pages: int) -> ProcessedDocument:
        """PDF with a proper TOC — textbook, lecture notes, etc."""
        label = Path(file_path).stem.replace("_", " ").replace("-", " ").title()

        # Build TOC entries directly from fitz raw TOC (no string parsing)
        toc_entries = self._build_toc_from_raw(raw_toc, file_path, total_pages)

        # Extract sections (one per TOC entry at section level)
        sections = self._extract_sections(file_path, toc_entries, total_pages)

        return ProcessedDocument(
            file_path=file_path,
            file_type="pdf_textbook",
            label=label,
            toc=toc_entries,
            sections=sections,
        )

    def _build_toc_from_raw(
        self, raw_toc: list, source_file: str, total_pages: int
    ) -> List[TOCEntry]:
        """
        Build TOCEntry list directly from fitz.get_toc() output.

        raw_toc entries are: (level, title, page_num)
        This bypasses string-based parsing entirely.
        """
        entries = []
        for i, (level, title, page_num) in enumerate(raw_toc):
            title = title.strip()
            if not title:
                continue

            # Skip back-matter
            if any(word in title.lower() for word in ['answer', 'appendix', 'index', 'glossary', 'bibliography']):
                continue

            # Compute end page = start of next same-or-higher-level entry, or total_pages
            end_page = total_pages
            for j in range(i + 1, len(raw_toc)):
                next_level, _, next_page = raw_toc[j]
                if next_level <= level:
                    end_page = max(page_num, next_page - 1)
                    break

            # Derive a clean section_id from the title
            section_id = self._title_to_section_id(title)

            entries.append(TOCEntry(
                title=title,
                level=level,
                page_or_slide=page_num,
                source_file=source_file,
                section_id=section_id,
            ))

        return entries

    def _title_to_section_id(self, title: str) -> str:
        """
        Extract a normalized section ID from a TOC title.

        Examples:
          "1-2 Time and Clocks"  → "1-2"
          "Section 1.2 Velocity" → "1.2"
          "3-4-1 Sub subsection" → "3-4-1"
          "Chapter 1"            → "ch1"
          "CHAPTER 3"            → "ch3"
          "Introduction"         → "introduction"
        """
        title_clean = title.strip()

        # Match section number at start: "1-2", "3.4", "1-2-1"
        sec_match = re.match(r'^(\d+(?:[-\.]\d+)+)', title_clean)
        if sec_match:
            return sec_match.group(1)

        # Match "Section X.Y" or "Sec. X-Y"
        sec_word = re.match(r'^[Ss]ec(?:tion)?\.?\s+(\d+(?:[-\.]\d+)*)', title_clean)
        if sec_word:
            return sec_word.group(1)

        # Match "Chapter N" → "chN"
        ch_match = re.match(r'^(?:CHAPTER|Chapter|chapter)\s+(\d+)', title_clean)
        if ch_match:
            return f"ch{ch_match.group(1)}"

        # Fallback: slugify
        slug = re.sub(r'\W+', '_', title_clean.lower()).strip('_')
        return slug[:40]

    def _process_slides(self, file_path: str, total_pages: int) -> ProcessedDocument:
        """
        PDF without a built-in TOC — scan every page to synthesize one.

        For correctness we scan ALL pages (not sample), since missing a section
        heading breaks the entire structure. FontAnalyzer still uses sampling for
        threshold calibration only.
        """
        label = Path(file_path).stem.replace("_", " ").replace("-", " ").title()

        doc = fitz.open(file_path)
        analyzer = FontAnalyzer(doc)
        font_info = analyzer.analyze(sample_pages=20)

        # Full scan: every page — needed for correct section detection
        headings = self._detect_headings_full(doc, font_info, total_pages)
        doc.close()

        logger.info(f"Full scan: detected {len(headings)} heading(s) across {total_pages} pages")

        toc_entries = []
        sections = []
        file_type = "pdf_slides"

        section_headings = [h for h in headings if h[0] >= 2]
        chapter_headings = [h for h in headings if h[0] == 1]

        if section_headings:
            # Best case: chapters + sections
            logger.info(f"  {len(chapter_headings)} chapters, {len(section_headings)} sections")
            toc_entries = self._build_toc_from_raw(headings, file_path, total_pages)
            sections = self._extract_sections(file_path, toc_entries, total_pages)
            file_type = "pdf_notes"
        elif chapter_headings and len(chapter_headings) >= 2:
            # Chapter-only — treat each chapter as one teachable section
            logger.info(f"  Chapter-only structure: {len(chapter_headings)} chapters, no subsections")
            toc_entries = self._build_toc_from_raw(chapter_headings, file_path, total_pages)
            sections = self._extract_sections(file_path, toc_entries, total_pages)
            file_type = "pdf_notes"
        else:
            # No usable structure — page-per-section fallback
            logger.info(f"No clear heading structure — treating as slides ({total_pages} pages)")
            toc_entries, sections = self._build_page_sections(file_path, total_pages)
            file_type = "pdf_slides"

        return ProcessedDocument(
            file_path=file_path,
            file_type=file_type,
            label=label,
            toc=toc_entries,
            sections=sections,
        )

    def _detect_headings_full(
        self, doc: fitz.Document, font_info: Dict, total_pages: int
    ) -> List[Tuple[int, str, int]]:
        """
        Scan ALL pages to detect headings. Used for PDFs without a built-in TOC.

        Broader pattern coverage than the sampled version:
        - Numbered sections: "1.1", "2.3", "1-2", "1.1.1"
        - Chapter keywords: "Chapter N", "CHAPTER N"
        - Bold larger-than-body lines that look like titles (≥ 120% body size)
        """
        chapter_min = font_info["chapter_min"]
        section_min = font_info["section_min"]
        body_size = font_info["body_size"]

        # Compile patterns once
        # Level 1 — chapter patterns
        p_chapter = re.compile(r'^(?:CHAPTER|Chapter|chapter)\s+(\d+[\w]*)\b(.*)', re.I)
        p_unit   = re.compile(r'^(?:UNIT|Unit)\s+(\d+[\w]*)\b(.*)', re.I)
        p_pipe   = re.compile(r'^(\d+)\s*\|\s*(.{3,80})$')   # "3 | Motion and Force"

        # Level 2 — section patterns
        p_section_numbered = re.compile(
            r'^(\d+(?:[.\-]\d+){1,3})\s+([A-Z\w].{2,80})$'
        )
        p_section_bold_title = re.compile(r'^[A-Z][A-Za-z\s\-:]{4,80}$')

        headings: List[Tuple[int, str, int]] = []
        seen: set = set()

        for page_idx in range(total_pages):
            try:
                page = doc[page_idx]
                blocks = page.get_text("dict")["blocks"]

                for block in blocks:
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        line_text = ""
                        max_size = 0.0
                        is_bold = False

                        for span in line.get("spans", []):
                            t = span.get("text", "").strip()
                            if t:
                                line_text += t + " "
                                sz = span.get("size", 0)
                                if sz > max_size:
                                    max_size = sz
                                flags = span.get("flags", 0)
                                is_bold = is_bold or bool(flags & (1 << 4))

                        line_text = line_text.strip()
                        if not line_text or len(line_text) > 120:
                            continue

                        key = line_text[:60]
                        if key in seen:
                            continue

                        page_num = page_idx + 1  # 1-indexed

                        # Level 1: chapter / unit headings
                        if p_chapter.match(line_text) or p_unit.match(line_text):
                            seen.add(key)
                            headings.append((1, line_text, page_num))
                            continue

                        # Level 1: pipe format "3 | Motion" at large font
                        if max_size >= chapter_min and p_pipe.match(line_text):
                            seen.add(key)
                            headings.append((1, line_text, page_num))
                            continue

                        # Level 1: bare large number alone (e.g. Nelson Physics: just "3" at 32pt)
                        if (max_size >= chapter_min
                                and re.match(r'^\d{1,2}$', line_text)
                                and not re.match(r'^(?:19|20)\d{2}$', line_text)):  # skip years
                            seen.add(key)
                            headings.append((1, line_text, page_num))
                            continue

                        # Level 2: numbered sections (e.g. "2.3 Eigenvalues")
                        if p_section_numbered.match(line_text):
                            seen.add(key)
                            headings.append((2, line_text, page_num))
                            continue

                        # Level 2: large bold title-case lines
                        if (max_size >= section_min
                                and is_bold
                                and p_section_bold_title.match(line_text)):
                            seen.add(key)
                            headings.append((2, line_text, page_num))
                            continue

            except Exception as e:
                logger.debug(f"Page {page_idx} scan error: {e}")
                continue

        # Sort by page order (scan order should already be correct but be safe)
        headings.sort(key=lambda h: h[2])
        return headings

    def _detect_headings_smart(
        self, doc: fitz.Document, font_info: Dict, total_pages: int, sample_pages: int = 50
    ) -> List[Tuple[int, str, int]]:
        """
        Detect headings using intelligent pattern matching (with sampling for speed).

        Samples up to `sample_pages` across the document + scans first/last pages fully.
        Returns list of (level, title, page_num) tuples — same format as fitz.get_toc()
        """
        # Patterns from v1: match "1-2 Title", "Chapter 3", "1.1.1 Subtitle", etc.
        chapter_patterns = [
            r'^CHAPTER\s+(\d+)',
            r'^Chapter\s+(\d+)',
        ]
        section_patterns = [
            r'^(\d+[-.][\d]{1,2})\s+(.+)',  # "1-2 Title" or "1.2 Title"
            r'^(\d+)\s+([A-Z][a-zA-Z\s\-]+)$',  # "1 Introduction"
        ]
        subsection_patterns = [
            r'^(\d+[-.][\d]{1,2}[-.][\d]{1,2})\s+(.+)',  # "1.1.1 Title"
        ]

        chapter_min = font_info["chapter_min"]
        section_min = font_info["section_min"]
        subsection_min = font_info["subsection_min"]
        body_size = font_info["body_size"]

        headings: List[Tuple[int, str, int]] = []
        seen_headings = set()  # Avoid duplicates

        # Sample pages intelligently: first page + every Nth page + last page
        pages_to_scan = set([0, total_pages - 1])  # Always scan first and last
        if total_pages > sample_pages:
            step = max(1, total_pages // sample_pages)
            pages_to_scan.update(range(0, total_pages, step))
        else:
            pages_to_scan.update(range(total_pages))  # Scan all if small PDF

        for page_idx in sorted(pages_to_scan):
            try:
                page = doc[page_idx]
                blocks = page.get_text("dict")["blocks"]

                for block in blocks:
                    if block.get("type") != 0:  # Not text
                        continue

                    for line in block.get("lines", []):
                        # Extract text and font info from spans
                        line_text = ""
                        max_size = body_size
                        is_bold = False

                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                line_text += text + " "
                                size = span.get("size", body_size)
                                max_size = max(max_size, size)
                                flags = span.get("flags", 0)
                                is_bold = is_bold or bool(flags & (1 << 4))  # Bold flag

                        line_text = line_text.strip()
                        if not line_text or len(line_text) > 150:
                            continue

                        heading_key = (page_idx, line_text[:40])
                        if heading_key in seen_headings:
                            continue

                        # Detect chapter (largest fonts)
                        if max_size >= chapter_min:
                            for pattern in chapter_patterns:
                                match = re.match(pattern, line_text, re.I)
                                if match:
                                    seen_headings.add(heading_key)
                                    headings.append((1, line_text, page_idx + 1))
                                    break

                        # Detect section (medium fonts + numbered pattern)
                        elif max_size >= section_min and max_size < chapter_min:
                            for pattern in section_patterns:
                                match = re.match(pattern, line_text)
                                if match and len(line_text) < 100:
                                    seen_headings.add(heading_key)
                                    headings.append((2, line_text, page_idx + 1))
                                    break

                        # Detect subsection (slightly larger than body + bold or pattern)
                        elif max_size >= subsection_min and (is_bold or len(line_text) < 80):
                            for pattern in subsection_patterns:
                                match = re.match(pattern, line_text)
                                if match:
                                    seen_headings.add(heading_key)
                                    headings.append((3, line_text, page_idx + 1))
                                    break

            except Exception as e:
                logger.debug(f"Error processing page {page_idx}: {e}")
                continue

        return headings

    def _build_page_sections(self, file_path: str, total_pages: int):
        """Build one section per page (true slides fallback)."""
        toc_entries = []
        sections = []

        for page_num in range(1, total_pages + 1):
            content = extract_pdf_pages(file_path, page_num, page_num)
            title = f"Slide {page_num}"
            # Skip header boilerplate: "PDF: ...", "Pages: ...", "====", "PAGE N"
            for line in content.splitlines():
                line = line.strip()
                if (line
                        and not line.startswith("PDF:")
                        and not line.startswith("Pages:")
                        and not line.startswith("===")
                        and not line.startswith("PAGE ")
                        and len(line) > 3):
                    title = line[:80]
                    break

            section_id = f"slide_{page_num}"
            toc_entries.append(TOCEntry(
                title=title,
                level=2,
                page_or_slide=page_num,
                source_file=file_path,
                section_id=section_id,
            ))
            sections.append(Section(
                section_id=section_id,
                title=title,
                content=content,
                page_start=page_num,
                page_end=page_num,
                source_file=file_path,
            ))

        return toc_entries, sections

    # Numbered section pattern: "1-2", "1.2", "3-4-1", etc.
    _NUMBERED_ID = re.compile(r'^\d+[-\.]\d+')

    def _extract_sections(
        self, file_path: str, toc_entries: List[TOCEntry], total_pages: int
    ) -> List[Section]:
        """
        Create Section metadata WITHOUT extracting content (lazy loading).

        Priority order for choosing which entries become teachable sections:
        1. Entries whose section_id is a numbered section (e.g. "1-2", "3.4")
        2. Entries whose title starts with "Chapter N" (level 1 only)
        3. If neither exists, fall back to the deepest level present

        Content is loaded on-demand via FileManager when teaching begins.
        """
        # ── Priority 1: numbered sections (the ideal case) ────────────────────
        numbered = [e for e in toc_entries if self._NUMBERED_ID.match(e.section_id)]
        if numbered:
            return self._build_sections(numbered, toc_entries, total_pages, file_path)

        # ── Priority 2: chapter-level entries (no sub-sections in TOC) ────────
        chapters = [e for e in toc_entries if e.section_id.startswith("ch")]
        if chapters:
            return self._build_sections(chapters, toc_entries, total_pages, file_path)

        # ── Priority 3: deepest level present ─────────────────────────────────
        if toc_entries:
            max_level = max(e.level for e in toc_entries)
            deepest = [e for e in toc_entries if e.level == max_level]
            return self._build_sections(deepest, toc_entries, total_pages, file_path)

        return []

    def _build_sections(
        self,
        entries: List[TOCEntry],
        all_entries: List[TOCEntry],
        total_pages: int,
        file_path: str,
    ) -> List[Section]:
        """
        Build Section objects from the chosen TOC entries.
        End-page is computed from the next same-or-higher entry in the full list.
        """
        sections = []
        # Sort by page so end-page calculation is reliable
        entries = sorted(entries, key=lambda e: e.page_or_slide)
        all_sorted = sorted(all_entries, key=lambda e: e.page_or_slide)

        for entry in entries:
            start_page = entry.page_or_slide
            if start_page == 0:
                continue

            # Find end page: the next TOC entry at same or higher level that comes after
            end_page = total_pages
            for other in all_sorted:
                if other.page_or_slide > start_page and other.level <= entry.level:
                    end_page = other.page_or_slide - 1
                    break

            end_page = max(start_page, min(end_page, total_pages))

            sections.append(Section(
                section_id=entry.section_id,
                title=entry.title,
                content="",  # Lazy: loaded on-demand by FileManager
                page_start=start_page,
                page_end=end_page,
                source_file=file_path,
            ))

        return sections
