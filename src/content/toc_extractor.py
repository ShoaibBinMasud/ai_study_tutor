"""
BookTOCExtractor — standalone table-of-contents extraction for PDF books.

Four clear phases (no vision, no RAG):

  Phase 1 — fitz built-in TOC        (PDF metadata, free + instant)
  Phase 2 — PyMuPDF font scan         (full book, no LLM, stable)
  Phase 3 — LLM judge + targeted fix  (1-2 cheap text calls only if needed)
  Phase 4 — LLM-guided search         (if < 3 chapters found after phases 1-3)

The LLM is NEVER used to extract content. It is used only as a:
  - Judge: "Is this TOC plausible?"
  - Guide: "Which page should I look at to find chapter X?"

PyMuPDF then confirms every LLM guess. If confirmation fails → "not found".

Results are cached as a .toc.json sidecar file next to the PDF.

Usage:
    from content.toc_extractor import BookTOCExtractor
    from utils.llm_client import LLMClient

    extractor = BookTOCExtractor(LLMClient())
    result = extractor.extract("physics_book.pdf")
    print(result.source)   # "fitz" | "font" | "font+fix" | "guided" | "none"
    for entry in result.entries:
        print(entry.level, entry.page, entry.title)
"""

import json
import logging
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TOCEntry:
    level: int    # 1 = chapter, 2 = section, 3 = subsection
    title: str
    page: int     # 1-indexed start page


@dataclass
class TOCResult:
    file_path: str
    total_pages: int
    source: str          # "fitz" | "font" | "font+fix" | "guided" | "none"
    entries: List[TOCEntry] = field(default_factory=list)
    elapsed_sec: float = 0.0
    notes: str = ""

    @property
    def chapters(self) -> List[TOCEntry]:
        return [e for e in self.entries if e.level == 1]

    @property
    def sections(self) -> List[TOCEntry]:
        return [e for e in self.entries if e.level == 2]

    def format_display(self) -> str:
        """Human-readable TOC string for UI display."""
        if not self.entries:
            return "No TOC found."
        lines = [
            f"**Source:** {self.source} | "
            f"**Entries:** {len(self.entries)} ({len(self.chapters)} chapters, {len(self.sections)} sections) | "
            f"**Time:** {self.elapsed_sec:.1f}s\n"
        ]
        for e in self.entries:
            indent = "  " * (e.level - 1)
            marker = "**" if e.level == 1 else ("  " if e.level == 2 else "    ")
            lines.append(f"{indent}{marker}p.{e.page:<4}  {e.title}")
        if self.notes:
            lines.append(f"\n*Notes: {self.notes}*")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 2 helper: font-size calibration (no LLM)
# ---------------------------------------------------------------------------

class _FontAnalyzer:
    """Sample ~20 pages to calibrate heading font-size thresholds."""

    def __init__(self, doc: fitz.Document):
        self.doc = doc

    def analyze(self, sample_pages: int = 20) -> dict:
        total = len(self.doc)
        step = max(1, total // sample_pages)
        font_sizes: List[float] = []

        for idx in range(0, total, step):
            try:
                for block in self.doc[idx].get_text("dict")["blocks"]:
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            sz = span.get("size", 0)
                            if 8.0 <= sz <= 40.0:
                                font_sizes.append(sz)
            except Exception:
                pass

        if not font_sizes:
            return self._defaults()

        body_size = Counter(round(s, 1) for s in font_sizes).most_common(1)[0][0]
        return {
            "body_size":      body_size,
            "subsection_min": body_size * 1.1,
            "section_min":    body_size * 1.3,
            "section_max":    body_size * 2.2,
            "chapter_min":    body_size * 2.2,
        }

    @staticmethod
    def _defaults() -> dict:
        return {
            "body_size":      10.0,
            "subsection_min": 11.0,
            "section_min":    13.0,
            "section_max":    22.0,
            "chapter_min":    22.0,
        }


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

class BookTOCExtractor:
    """
    Extract a full table of contents from a PDF book.

    LLM is optional. Without it, only phases 1 and 2 run (pure PyMuPDF).
    With LLM: phase 3 validates/fixes, phase 4 handles total-failure fallback.
    """

    def __init__(self, llm_client=None):
        self.llm = llm_client

    # ── Public API ────────────────────────────────────────────────────────────

    def extract(self, file_path: str) -> TOCResult:
        """Extract TOC. Returns a TOCResult (cached on disk as .toc.json)."""
        t0 = time.time()
        file_path = str(file_path)

        cached = self._load_cache(file_path)
        if cached is not None:
            entries = [TOCEntry(**e) for e in cached["entries"]]
            return TOCResult(
                file_path=file_path,
                total_pages=cached.get("total_pages", 0),
                source=cached["source"] + " (cached)",
                entries=entries,
                elapsed_sec=0.0,
                notes=cached.get("notes", ""),
            )

        doc = fitz.open(file_path)
        total_pages = len(doc)
        try:
            entries, source, notes = self._run_cascade(doc, file_path, total_pages)
        finally:
            doc.close()

        result = TOCResult(
            file_path=file_path,
            total_pages=total_pages,
            source=source,
            entries=entries,
            elapsed_sec=time.time() - t0,
            notes=notes,
        )

        if entries:
            self._save_cache(file_path, result)

        return result

    # ── Cascade orchestration ─────────────────────────────────────────────────

    def _run_cascade(
        self, doc: fitz.Document, file_path: str, total_pages: int
    ) -> Tuple[List[TOCEntry], str, str]:
        """
        Returns (entries, source, notes).
        Each phase returns a list of TOCEntry; source tracks which phase succeeded.
        """

        # ── Phase 1: fitz built-in TOC (PDF metadata) ──────────────────────
        raw = doc.get_toc()
        if raw and len(raw) > 3:
            entries = [TOCEntry(level=lv, title=tt.strip(), page=pg) for lv, tt, pg in raw if tt.strip()]
            logger.info(f"TOC Phase 1 (fitz): {len(entries)} entries")
            return entries, "fitz", ""

        # ── Phase 2: PyMuPDF font scan (stable, no LLM) ────────────────────
        logger.info(f"TOC Phase 2: font scan on {total_pages} pages...")
        font_info = _FontAnalyzer(doc).analyze(sample_pages=20)
        raw_tuples = self._font_scan(doc, font_info, total_pages)
        logger.info(f"TOC Phase 2: found {len(raw_tuples)} heading(s)")

        # ── Phase 3: LLM judge + targeted fix (optional) ───────────────────
        notes = ""
        source = "font"
        if raw_tuples and self.llm is not None:
            raw_tuples, fix_notes = self._judge_and_fix(raw_tuples, total_pages, doc)
            if fix_notes:
                notes = fix_notes
                source = "font+fix"

        chapter_count = sum(1 for lv, _, _ in raw_tuples if lv == 1)

        # ── Phase 4: LLM-guided search (if < 3 chapters after phases 1-3) ──
        if chapter_count < 3 and self.llm is not None:
            logger.info("TOC Phase 4: fewer than 3 chapters — trying LLM-guided search")
            raw_tuples = self._guided_search(doc, raw_tuples, total_pages)
            source = "guided" if sum(1 for lv, _, _ in raw_tuples if lv == 1) >= 3 else "none"

        if not raw_tuples:
            logger.warning("TOC: extraction failed — no entries found")
            return [], "none", "TOC extraction failed; section lookup not available."

        entries = [TOCEntry(level=lv, title=tt, page=pg) for lv, tt, pg in raw_tuples]
        return entries, source, notes

    # ── Phase 2: PyMuPDF font scan ────────────────────────────────────────────

    def _font_scan(
        self, doc: fitz.Document, font_info: dict, total_pages: int
    ) -> List[Tuple[int, str, int]]:
        """
        Scan every page with PyMuPDF. Detect headings by:
          - Font size thresholds (calibrated by _FontAnalyzer)
          - Regex patterns for common textbook heading formats

        Returns list of (level, title, page_1indexed) — NOT sorted, order is natural.
        No LLM. Stable.
        """
        chapter_min = font_info["chapter_min"]
        section_min = font_info["section_min"]

        # Chapter-level patterns
        p_chapter = re.compile(r'^(?:CHAPTER|Chapter)\s+(\d+[\w]*)(.*)', re.I)
        p_unit    = re.compile(r'^(?:UNIT|Unit)\s+(\d+[\w]*)(.*)', re.I)
        p_pipe    = re.compile(r'^(\d{1,2})\s*[|]\s*(.{3,80})$')

        # Section-level patterns
        p_sec_num  = re.compile(r'^(\d+(?:[.\-]\d+){1,3})\s+([A-Z\w].{2,80})$')
        p_sec_bold = re.compile(r'^[A-Z][A-Za-z\s\-:]{4,80}$')

        headings: List[Tuple[int, str, int]] = []
        seen: set = set()

        for page_idx in range(total_pages):
            try:
                page_num = page_idx + 1  # 1-indexed throughout
                blocks = doc[page_idx].get_text("dict")["blocks"]

                for block in blocks:
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        text = ""
                        max_size = 0.0
                        is_bold = False

                        for span in line.get("spans", []):
                            t = span.get("text", "").strip()
                            if t:
                                text += t + " "
                            sz = span.get("size", 0)
                            if sz > max_size:
                                max_size = sz
                            if span.get("flags", 0) & (1 << 4):
                                is_bold = True

                        text = text.strip()
                        if not text or len(text) > 120:
                            continue

                        key = text[:60]
                        if key in seen:
                            continue

                        # ── Level 1: Chapter / Unit / Pipe / Bare number ──
                        if p_chapter.match(text) or p_unit.match(text):
                            seen.add(key)
                            headings.append((1, text, page_num))
                            continue

                        if max_size >= chapter_min and p_pipe.match(text):
                            seen.add(key)
                            headings.append((1, text, page_num))
                            continue

                        # Bare digit 1-20 at large font (Nelson Physics style: just "3")
                        if (max_size >= chapter_min
                                and re.match(r'^\d{1,2}$', text)
                                and not re.match(r'^(?:19|20)\d{2}$', text)):
                            seen.add(key)
                            headings.append((1, text, page_num))
                            continue

                        # ── Level 2: Numbered section or large bold title ──
                        if p_sec_num.match(text):
                            seen.add(key)
                            headings.append((2, text, page_num))
                            continue

                        if max_size >= section_min and is_bold and p_sec_bold.match(text):
                            seen.add(key)
                            headings.append((2, text, page_num))
                            continue

            except Exception as e:
                logger.debug(f"Page {page_idx} scan error: {e}")

        headings.sort(key=lambda h: h[2])
        return headings

    # ── Phase 3: LLM judge + targeted fix ────────────────────────────────────

    def _judge_and_fix(
        self, raw_toc: List[Tuple], total_pages: int, doc: fitz.Document
    ) -> Tuple[List[Tuple], str]:
        """
        Step A — LLM JUDGE (1 call):
          Feed the extracted TOC as plain text.
          Ask: "Which chapters span implausibly many pages?"
          → Returns list of suspect chapter titles.

        Step B — TARGETED FIX (1 call per suspect, max 3):
          For each suspect:
            1. Ask LLM: "Which page should I look at to find where this chapter ends?"
            2. PyMuPDF reads that page (and ±2 neighbours).
            3. PyMuPDF confirms whether a new chapter heading exists there.
            4. If confirmed → insert the correct boundary.

        If LLM judge says TOC is valid → return as-is (no fix needed).
        If any call fails → return original TOC silently.
        """
        threshold = max(30, int(total_pages * 0.25))

        # ── Step A: Judge ──────────────────────────────────────────────────
        toc_text = "\n".join(f"  L{lv} | p.{pg:>4} | {tt}" for lv, tt, pg in raw_toc)
        judge_prompt = (
            f"Extracted TOC from a {total_pages}-page textbook:\n\n"
            f"{toc_text}\n\n"
            f"A chapter spanning more than {threshold} pages in a {total_pages}-page book "
            f"is almost certainly a detection error (missed chapter heading).\n"
            f"Identify which chapter titles have implausible page spans.\n"
            f'Reply ONLY with JSON: {{"valid": true}} or {{"valid": false, "suspects": ["title1", "title2"]}}'
        )

        try:
            r = self.llm.chat(
                [{"role": "user", "content": judge_prompt}],
                max_tokens=300, temperature=0.0
            )
            content = r["choices"][0]["message"].get("content", "")
            m = re.search(r'\{.*\}', content, re.DOTALL)
            verdict = json.loads(m.group(0)) if m else {}
        except Exception as e:
            logger.debug(f"TOC judge call failed: {e}")
            return raw_toc, ""

        if verdict.get("valid", True) or not verdict.get("suspects"):
            logger.info("TOC judge: TOC is valid — no fix needed")
            return raw_toc, ""

        suspects = verdict["suspects"]
        logger.info(f"TOC judge: suspects = {suspects}")

        # ── Step B: Targeted fix ───────────────────────────────────────────
        fixed = list(raw_toc)
        fix_notes = []

        for title in suspects[:3]:  # cap at 3 to limit LLM calls
            idx = next((i for i, (_, t, _) in enumerate(fixed) if t == title), None)
            if idx is None:
                continue

            lv, tt, start_pg = fixed[idx]
            curr_end = fixed[idx + 1][2] if idx + 1 < len(fixed) else total_pages

            # Ask LLM: which page to look at for the boundary?
            fix_prompt = (
                f"In a {total_pages}-page textbook, chapter '{tt}' starts at p.{start_pg} "
                f"and currently appears to end at p.{curr_end} (likely wrong — too many pages).\n"
                f"Based on typical textbook structure, which page should I look at "
                f"to find where this chapter actually ends?\n"
                f'Reply ONLY with JSON: {{"check_page": N}}'
            )

            try:
                r2 = self.llm.chat(
                    [{"role": "user", "content": fix_prompt}],
                    max_tokens=80, temperature=0.0
                )
                c2 = r2["choices"][0]["message"].get("content", "")
                m2 = re.search(r'\{.*\}', c2, re.DOTALL)
                check_page = int(json.loads(m2.group(0)).get("check_page", 0)) if m2 else 0
            except Exception as e:
                logger.debug(f"TOC fix call failed for '{tt}': {e}")
                continue

            if not (start_pg < check_page <= total_pages):
                continue

            # PyMuPDF confirms: scan check_page ± 2 for a chapter heading
            confirmed_end = self._find_boundary_near(doc, check_page, total_pages)
            if confirmed_end and start_pg < confirmed_end <= total_pages:
                logger.info(f"TOC fix: '{tt}' — confirmed boundary at p.{confirmed_end}")
                # Insert a boundary marker so the next entry starts at the right place
                # (only if there's a large gap between confirmed_end and current next entry)
                if idx + 1 >= len(fixed) or fixed[idx + 1][2] > confirmed_end + 5:
                    fixed.insert(idx + 1, (1, f"[next chapter ~p.{confirmed_end}]", confirmed_end))
                fix_notes.append(f"'{tt}' boundary ~p.{confirmed_end}")

        return fixed, "; ".join(fix_notes)

    def _find_boundary_near(
        self, doc: fitz.Document, target_page: int, total_pages: int, window: int = 3
    ) -> Optional[int]:
        """
        Scan pages [target_page-window, target_page+window] with PyMuPDF.
        Return the page number where a chapter heading is found, or None.
        """
        p_chapter = re.compile(r'(?:chapter|unit)\s+\d+', re.I)
        p_bare_num = re.compile(r'^\s*\d{1,2}\s*$', re.M)

        for pg in range(max(0, target_page - window - 1), min(total_pages, target_page + window)):
            try:
                text = doc[pg].get_text("text").strip()
                if p_chapter.search(text[:300]) or p_bare_num.search(text[:100]):
                    return pg + 1  # 1-indexed
            except Exception:
                pass
        return None

    # ── Phase 4: LLM-guided search (fallback for < 3 chapters) ──────────────

    def _guided_search(
        self, doc: fitz.Document, raw_toc: List[Tuple], total_pages: int
    ) -> List[Tuple]:
        """
        When PyMuPDF font scan finds < 3 chapters (headings not in font data):
          1. LLM estimates chapter positions from a small text preview.
          2. PyMuPDF scans ±3 pages around each estimate to confirm.
          3. Only confirmed pages are kept. Unconfirmed → skipped (not guessed).

        If fewer than 3 are confirmed → return original raw_toc (honest about failure).
        """
        # Small text preview (first 3 pages + last 2 pages, ~300 chars each)
        preview_parts = []
        for pg_idx in list(range(min(3, total_pages))) + list(range(max(0, total_pages - 2), total_pages)):
            try:
                t = doc[pg_idx].get_text("text").strip()[:300]
                preview_parts.append(f"[p.{pg_idx+1}] {t}")
            except Exception:
                pass

        found_hint = (
            "\n".join(f"  p.{p}: {t}" for _, t, p in raw_toc[:10])
            if raw_toc else "  (nothing found by font scan)"
        )

        prompt = (
            f"PDF textbook: {total_pages} pages total.\n"
            f"Font scan found these possible headings:\n{found_hint}\n\n"
            f"Sample page content:\n" + "\n".join(preview_parts) + "\n\n"
            f"Estimate where each chapter starts. Typical textbooks have 8-15 chapters.\n"
            f'Reply ONLY with JSON: {{"chapters": [{{"title": "Chapter 1 Title", "start_page": N}}, ...]}}'
        )

        try:
            resp = self.llm.chat([{"role": "user", "content": prompt}], max_tokens=600, temperature=0.1)
            text = resp["choices"][0]["message"].get("content", "")
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if not m:
                return raw_toc
            estimates = json.loads(m.group(0)).get("chapters", [])
        except Exception as e:
            logger.debug(f"Guided search LLM call failed: {e}")
            return raw_toc

        confirmed = []
        for ch in estimates:
            est = int(ch.get("start_page", 0))
            title_hint = ch.get("title", f"Chapter ~p.{est}")
            if not (1 <= est <= total_pages):
                continue

            # PyMuPDF confirms: look ±3 pages around estimate
            confirmed_pg = self._find_boundary_near(doc, est, total_pages, window=3)
            if confirmed_pg:
                logger.info(f"Guided: confirmed '{title_hint}' at p.{confirmed_pg}")
                confirmed.append((1, title_hint, confirmed_pg))
            else:
                logger.debug(f"Guided: '{title_hint}' estimate p.{est} not confirmed — skipped")

        if len(confirmed) >= 3:
            # Merge with any sections already found by font scan
            merged = sorted(confirmed + [(lv, tt, pg) for lv, tt, pg in raw_toc if lv == 2], key=lambda x: x[2])
            return merged

        logger.warning(f"Guided search: only {len(confirmed)} confirmed — not enough, returning original")
        return raw_toc

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _save_cache(self, file_path: str, result: TOCResult):
        cache_path = file_path + ".toc.json"
        try:
            data = {
                "source": result.source,
                "total_pages": result.total_pages,
                "notes": result.notes,
                "extracted_at": datetime.now().isoformat(),
                "file_mtime": os.path.getmtime(file_path),
                "entries": [
                    {"level": e.level, "title": e.title, "page": e.page}
                    for e in result.entries
                ],
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"TOC cached → {cache_path}")
        except Exception as e:
            logger.debug(f"Cache save failed: {e}")

    def _load_cache(self, file_path: str) -> Optional[dict]:
        cache_path = file_path + ".toc.json"
        if not os.path.exists(cache_path):
            return None
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            # Invalidate if PDF was modified after cache was written
            if abs(data.get("file_mtime", 0) - os.path.getmtime(file_path)) > 1.0:
                logger.debug("TOC cache stale — re-extracting")
                return None
            logger.info(
                f"TOC loaded from cache: source={data['source']}, "
                f"{len(data.get('entries', []))} entries"
            )
            return data
        except Exception as e:
            logger.debug(f"Cache load failed: {e}")
            return None
