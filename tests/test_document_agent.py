"""
DocumentAgent test suite.

Covers:
  1. Metadata       — zero tool calls, answered from JSON
  2. Single file    — one PDF / PPTX / DOCX / image
  3. Multiple files — explicit list, mixed types
  4. Folder input   — agent receives a directory path
  5. Labeled items  — find_in_pages, count_in_pages
  6. Content        — get_pages for chapters / slides / full files
  7. Complex        — multi-step, multi-part, multi-file requests
  8. Edge cases     — wrong tools, hallucination, not-found, ambiguity

All traces → .traces/test_suite_results.json (one file, suppresses per-test JSONs).
"""

import pytest
from conftest import BOOK, LEC_3, LEC_4, ALL_FILES, FOLDER

# ── File references inside the test folder ─────────────────────────────────────

PPTX        = f"{FOLDER}/Agentic_Web_Architecture.pptx"
IMAGE       = f"{FOLDER}/image_1.png"
DOCX        = f"{FOLDER}/IRS rebuttal letter.docx"
LEC_SCANNED = f"{FOLDER}/lecture_1.pdf"   # scanned PDF
LEC_DIGITAL = f"{FOLDER}/lecture_3.pdf"   # digital PDF

TIME = {
    "metadata":  15_000,   # ms — answered from JSON, no LLM tool call
    "one_tool":  60_000,   # ms — one LLM round + one tool (get_toc on 181 entries ~45s)
    "two_tools": 90_000,   # ms — two sequential tool calls
    "multi":    150_000,   # ms — multi-file or multi-step
}


def tools(agent) -> list[str]:
    """Ordered list of tool names from the last trace."""
    if agent.last_trace is None:
        return []
    return [tc.tool_name for tc in agent.last_trace.tool_calls]


def ms(agent) -> float:
    return agent.last_trace.total_elapsed_ms if agent.last_trace else 0


# ── 1. Metadata — zero tools ──────────────────────────────────────────────────

class TestMetadata:
    """
    Page count, file type, has_toc, is_scanned — all answerable from JSON metadata.
    Zero tool calls required. Any tool call here is a bug (slow + hallucination risk).
    """

    def test_page_count_single_file(self, agent):
        r = agent.extract([LEC_3], "How many pages does this file have?")
        assert tools(agent) == [], "Metadata question — no tools"
        assert "5" in r
        assert ms(agent) < TIME["metadata"]

    def test_page_count_multiple_files(self, agent):
        r = agent.extract(ALL_FILES, "How many pages are in the lectures?")
        assert tools(agent) == []
        assert "5" in r and "8" in r           # lecture_3=5, lecture_4=8
        assert "18" not in r and "22" not in r  # past hallucinated values
        assert ms(agent) < TIME["metadata"]

    def test_total_pages_math(self, agent):
        r = agent.extract(ALL_FILES, "How many pages do the lectures have in total?")
        assert tools(agent) == []
        assert "13" in r    # 5 + 8 = 13
        assert "40" not in r  # old hallucinated total
        assert ms(agent) < TIME["metadata"]

    def test_has_toc(self, agent):
        r = agent.extract(ALL_FILES, "Does the physics book have a table of contents?")
        assert tools(agent) == []
        assert any(w in r.lower() for w in ("yes", "true", "has a table"))
        assert ms(agent) < TIME["metadata"]

    def test_is_scanned(self, agent):
        agent.extract(ALL_FILES, "Are any of my files scanned?")
        assert tools(agent) == []
        assert ms(agent) < TIME["metadata"]

    def test_file_count(self, agent):
        r = agent.extract(ALL_FILES, "How many files did I upload?")
        assert tools(agent) == []
        assert "3" in r
        assert ms(agent) < TIME["metadata"]

    def test_file_types(self, agent):
        r = agent.extract(ALL_FILES, "What types of files do I have?")
        assert tools(agent) == []
        assert "pdf" in r.lower()
        assert ms(agent) < TIME["metadata"]


# ── 2. Single file ────────────────────────────────────────────────────────────

class TestSingleFile:
    """One file at a time — correct tool selection per file type."""

    def test_book_chapter_content(self, agent):
        agent.extract([BOOK], "Give me the content of chapter 2.")
        assert "get_toc" in tools(agent), "Book needs TOC lookup for chapter range"
        assert "get_pages" in tools(agent), "Must extract actual content"
        assert ms(agent) < TIME["two_tools"]

    def test_lecture_full_content(self, agent):
        r = agent.extract([LEC_3], "Give me everything from this lecture.")
        assert "get_pages" in tools(agent)
        assert "get_toc" not in tools(agent), "No TOC in lecture — skip get_toc"
        assert any(kw in r for kw in ("8.701", "Nuclear", "MIT", "Physics", "Klute"))
        assert "[Title" not in r and "[specific" not in r
        assert ms(agent) < TIME["one_tool"]

    def test_pptx_overview(self, agent):
        agent.extract([PPTX], "What is this presentation about?")
        assert "peek_preview" in tools(agent) or "get_pages" in tools(agent), \
            "PPTX overview must sample the slides"
        assert ms(agent) < TIME["one_tool"]

    def test_pptx_first_slide(self, agent):
        agent.extract([PPTX], "Give me the content of the first slide.")
        assert "get_pages" in tools(agent)
        assert ms(agent) < TIME["one_tool"]

    def test_docx_content(self, agent):
        agent.extract([DOCX], "What does this document say?")
        assert len(tools(agent)) > 0, "Must use a tool to read DOCX content"
        assert ms(agent) < TIME["one_tool"]

    def test_image_description(self, agent):
        # peek_preview and get_pages both trigger vision for images — both are valid
        agent.extract([IMAGE], "What is shown in this image?")
        assert any(t in tools(agent) for t in ("get_pages", "peek_preview")), \
            "Image must use get_pages or peek_preview (both trigger vision)"
        assert ms(agent) < TIME["one_tool"]

    def test_scanned_pdf(self, agent):
        """Scanned PDF must not return empty text — agent should handle via vision."""
        agent.extract([LEC_SCANNED], "What does this lecture cover?")
        assert len(tools(agent)) > 0
        assert ms(agent) < TIME["one_tool"]

    def test_book_toc_listing(self, agent):
        agent.extract([BOOK], "Show me the table of contents.")
        assert "get_toc" in tools(agent)
        assert "find_in_pages" not in tools(agent)
        assert ms(agent) < TIME["one_tool"]


# ── 3. Multiple files (explicit list) ─────────────────────────────────────────

class TestMultipleFiles:
    """Explicit list of heterogeneous files — correct routing per file."""

    def test_book_and_lecture_overview(self, agent):
        agent.extract([BOOK, LEC_3], "Give me an overview of all my files.")
        assert len(tools(agent)) > 0
        assert ms(agent) < TIME["multi"]

    def test_book_chapter_plus_lecture_content(self, agent):
        agent.extract(
            [BOOK, LEC_3],
            "Give me chapter 2 from the physics book and all of lecture 3."
        )
        assert "get_toc" in tools(agent), "Needs TOC to locate chapter 2"
        assert "get_pages" in tools(agent), "Needs get_pages for both files"
        assert ms(agent) < TIME["multi"]

    def test_multiple_lectures_page_counts(self, agent):
        r = agent.extract(ALL_FILES, "How many pages are in each of the lectures?")
        assert tools(agent) == [], "Metadata only — no tools"
        assert "5" in r    # lecture_3
        assert "8" in r    # lecture_4

    def test_book_plus_image(self, agent):
        agent.extract(
            [BOOK, IMAGE],
            "What is the image about and what chapters does the book have?"
        )
        assert len(tools(agent)) > 0
        assert ms(agent) < TIME["multi"]

    def test_book_pdf_plus_pptx_plus_docx(self, agent):
        """Three different file types in one request."""
        agent.extract(
            [BOOK, PPTX, DOCX],
            "Give me an overview of each of these files."
        )
        assert len(tools(agent)) > 0
        assert ms(agent) < TIME["multi"]


# ── 4. Folder input ────────────────────────────────────────────────────────────

class TestFolderInput:
    """
    Agent receives a folder path. extract() must expand it to individual files,
    build metadata for all 6 files, and answer correctly.
    """

    def test_folder_file_count(self, agent):
        r = agent.extract([FOLDER], "How many files do I have?")
        assert tools(agent) == [], "Metadata from folder — no tools"
        assert "6" in r, "Folder has 6 files"
        assert ms(agent) < TIME["metadata"]

    def test_folder_file_types(self, agent):
        r = agent.extract([FOLDER], "What types of files are in my folder?")
        assert tools(agent) == []
        assert "pdf" in r.lower()
        assert any(w in r.lower() for w in ("pptx", "powerpoint", "presentation"))
        assert any(w in r.lower() for w in ("docx", "word", "document"))
        assert any(w in r.lower() for w in ("png", "image"))

    def test_folder_which_files_are_scanned(self, agent):
        r = agent.extract([FOLDER], "Which of my files are scanned?")
        assert tools(agent) == []
        assert any(name in r for name in ("lecture_1", "image_1"))

    def test_folder_overview_all_files(self, agent):
        agent.extract([FOLDER], "Give me a brief overview of each file.")
        assert len(tools(agent)) > 0, "Overview needs at least peek_preview calls"
        assert ms(agent) < TIME["multi"]

    def test_folder_book_chapter(self, agent):
        agent.extract([FOLDER], "Give me chapter 1 from the physics book.")
        assert "get_toc" in tools(agent)
        assert "get_pages" in tools(agent)
        assert ms(agent) < TIME["two_tools"]

    def test_folder_example_location(self, agent):
        r = agent.extract([FOLDER], "Where does Example 3-2 appear in the physics book?")
        assert "get_toc" in tools(agent)
        assert "find_in_pages" in tools(agent)
        assert "143" in r
        assert ms(agent) < TIME["two_tools"]

    def test_folder_image_question(self, agent):
        # peek_preview and get_pages both trigger vision for images — both are valid
        agent.extract([FOLDER], "What is shown in the image file?")
        assert any(t in tools(agent) for t in ("get_pages", "peek_preview")), \
            "Image must use get_pages or peek_preview (both trigger vision)"
        assert ms(agent) < TIME["one_tool"]

    def test_folder_lecture_content(self, agent):
        r = agent.extract([FOLDER], "Give me the content of lecture 3.")
        assert "get_pages" in tools(agent)
        assert "[Title" not in r and "[specific" not in r
        assert ms(agent) < TIME["one_tool"]


# ── 5. Labeled items ──────────────────────────────────────────────────────────

class TestLabeledItems:
    """
    Labeled items (Example, Figure, Theorem, etc.) need get_toc → find_in_pages.
    Section questions need get_toc only.
    These must never be confused.
    """

    def test_example_location(self, agent):
        r = agent.extract([BOOK], "Where does Example 3-2 appear?")
        assert tools(agent) == ["get_toc", "find_in_pages"]
        assert "143" in r
        assert ms(agent) < TIME["two_tools"]

    def test_section_location_no_find_in_pages(self, agent):
        r = agent.extract([BOOK], "Where does section 3-2 appear?")
        assert "find_in_pages" not in tools(agent), \
            "Section is in TOC — must NOT call find_in_pages"
        assert "get_toc" in tools(agent)
        assert "137" in r
        assert ms(agent) < TIME["one_tool"]

    def test_chapter_location_no_find_in_pages(self, agent):
        agent.extract([BOOK], "What page does chapter 3 start on?")
        assert "find_in_pages" not in tools(agent)
        assert "get_toc" in tools(agent)
        assert ms(agent) < TIME["one_tool"]

    def test_count_examples_in_section(self, agent):
        r = agent.extract([BOOK], "How many examples are in section 2-1?")
        assert "get_toc" in tools(agent)
        assert "count_in_pages" in tools(agent)
        assert "2" in r
        assert ms(agent) < TIME["two_tools"]

    def test_count_figures_in_chapter(self, agent):
        agent.extract([BOOK], "How many figures are in chapter 3?")
        assert "get_toc" in tools(agent)
        assert "count_in_pages" in tools(agent)
        assert ms(agent) < TIME["two_tools"]

    def test_figure_location(self, agent):
        agent.extract([BOOK], "What page is Figure 1-2?")
        assert "get_toc" in tools(agent)
        assert "find_in_pages" in tools(agent)
        assert ms(agent) < TIME["two_tools"]


# ── 6. Content extraction ─────────────────────────────────────────────────────

class TestContentExtraction:
    """get_pages must return real text — never a hallucinated description."""

    def test_lecture_page_1_real_content(self, agent):
        r = agent.extract([LEC_3], "Give me the content of page 1.")
        assert "get_pages" in tools(agent)
        assert any(kw in r for kw in ("8.701", "Nuclear", "MIT", "Klute", "Physics"))
        assert "[Title" not in r
        assert ms(agent) < TIME["one_tool"]

    def test_book_section_content(self, agent):
        agent.extract([BOOK], "Give me the content of section 2-1.")
        assert "get_toc" in tools(agent)
        assert "get_pages" in tools(agent)
        assert ms(agent) < TIME["two_tools"]

    def test_all_lectures_content(self, agent):
        agent.extract(ALL_FILES, "Get everything from both lectures.")
        assert "get_pages" in tools(agent)
        assert ms(agent) < TIME["multi"]

    def test_no_hallucination_in_content_response(self, agent):
        """LLM must not prepend a fake description after get_pages."""
        r = agent.extract([LEC_3], "Show me page 2 of lecture 3.")
        assert "get_pages" in tools(agent)
        assert "[Title" not in r
        assert "[specific topics" not in r
        assert "concepts of [" not in r


# ── 7. Complex multi-step / multi-part ────────────────────────────────────────

class TestComplex:
    """
    Multi-step requests across tools and files.
    Most likely to break: wrong file chosen, wrong tool order, partial answers.
    """

    def test_two_part_find_and_count(self, agent):
        """Find Example 3-2 AND count examples in section 2-1 in one request."""
        r = agent.extract(
            [BOOK],
            "Where does Example 3-2 appear, and how many examples are in section 2-1?"
        )
        assert "get_toc" in tools(agent)
        assert "find_in_pages" in tools(agent)
        assert "count_in_pages" in tools(agent)
        assert "143" in r   # Example 3-2 page
        assert "2" in r     # count in section 2-1
        assert ms(agent) < TIME["multi"]

    def test_book_chapter_plus_lecture_plus_image(self, agent):
        """Three-file: book chapter + digital lecture + image — correct routing per type."""
        agent.extract(
            [BOOK, LEC_DIGITAL, IMAGE],
            "Give me chapter 1 from the physics book, the full content of the digital "
            "lecture, and describe what's in the image."
        )
        assert "get_toc" in tools(agent), "Book needs TOC"
        assert "get_pages" in tools(agent), "Needs content extraction"
        assert ms(agent) < TIME["multi"]

    def test_overview_then_specific_chapter(self, agent):
        """Show available chapters, then extract one. Must not dump the full book."""
        agent.extract(
            [BOOK],
            "What chapters does the book have, and then give me the content of chapter 2."
        )
        assert "get_toc" in tools(agent)
        assert "get_pages" in tools(agent)
        assert ms(agent) < TIME["multi"]

    def test_folder_multi_type_extraction(self, agent):
        """From folder: book section + PPTX overview + DOCX content — 3 file types."""
        agent.extract(
            [FOLDER],
            "Give me section 2-1 from the physics book, an overview of the PowerPoint, "
            "and the content of the Word document."
        )
        assert "get_toc" in tools(agent)    # for book section
        assert "get_pages" in tools(agent)  # for content
        assert ms(agent) < TIME["multi"]

    def test_mixed_metadata_and_content(self, agent):
        """
        Metadata question + content request in one message.
        Note: the agent suppresses its LLM summary when get_pages is called (to prevent
        hallucination), so the metadata answer ("5 pages") may not appear in the raw
        extracted content. We only assert that get_pages was correctly called.
        """
        agent.extract(
            ALL_FILES,
            "How many pages does lecture 3 have, and also give me page 1 of lecture 3."
        )
        assert "get_pages" in tools(agent), "Must extract page 1 content"
        assert ms(agent) < TIME["multi"]

    def test_find_in_folder_plus_count(self, agent):
        """Folder: find a labeled item AND count items in a section."""
        r = agent.extract(
            [FOLDER],
            "Where does Example 3-2 appear in the physics book, "
            "and how many examples are there in section 2-1?"
        )
        assert "get_toc" in tools(agent)
        assert "find_in_pages" in tools(agent)
        assert "count_in_pages" in tools(agent)
        assert "143" in r
        assert ms(agent) < TIME["multi"]


# ── 8. Edge cases ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    """
    Scenarios most likely to produce wrong tools, hallucination, or wrong answers.
    Each test documents the specific failure mode it guards against.
    """

    def test_nonexistent_example_not_hallucinated(self, agent):
        """Example 99-99 doesn't exist — must search then report not found, never invent a page."""
        r = agent.extract([BOOK], "Where does Example 99-99 appear?")
        assert "find_in_pages" in tools(agent), "Must attempt the search"
        assert any(phrase in r.lower() for phrase in (
            "not found", "couldn't find", "could not find", "cannot find",
            "unable to locate", "does not appear", "not locate", "couldn't locate",
            "not exist", "does not exist", "no example", "not contain",
        )), f"Must report honestly that it was not found. Got: {r[:200]}"
        assert "page 99" not in r.lower()

    def test_nonexistent_section_in_toc(self, agent):
        """Section 99-99 is not in the TOC. Answer from get_toc alone — no find_in_pages."""
        r = agent.extract([BOOK], "Where is section 99-99?")
        assert "get_toc" in tools(agent)
        assert "find_in_pages" not in tools(agent)
        assert any(phrase in r.lower() for phrase in (
            "not found", "not listed", "doesn't appear", "does not appear",
            "no section", "couldn't find", "could not find", "not contain",
            "does not contain", "not exist", "does not exist", "may not exist",
        )), f"Must report section was not found. Got: {r[:200]}"

    def test_section_vs_example_disambiguation(self, agent):
        """
        '3-2' in 'section 3-2' must NOT trigger find_in_pages.
        '3-2' in 'Example 3-2' must trigger find_in_pages.
        Both checked in the same test to confirm the distinction holds.
        """
        agent.extract([BOOK], "Where is section 3-2?")
        assert "find_in_pages" not in tools(agent), "Section must not trigger find_in_pages"

        agent.extract([BOOK], "Where is Example 3-2?")
        assert "find_in_pages" in tools(agent), "Example must trigger find_in_pages"

    def test_example_does_not_return_section_range(self, agent):
        """
        Core hallucination guard: must not return section 3-2 page range (137-145)
        as the location of Example 3-2. The actual page is 143.
        """
        r = agent.extract([BOOK], "Where does Example 3-2 appear?")
        assert "find_in_pages" in tools(agent)
        assert "143" in r, "Must return the actual page from find_in_pages"

    def test_metadata_never_hallucinated(self, agent):
        """The old bug: agent returned 18/22 pages instead of 5/8."""
        r = agent.extract(ALL_FILES, "How many pages does each lecture have?")
        assert tools(agent) == []
        assert "5" in r and "8" in r
        assert "18" not in r and "22" not in r

    def test_no_content_hallucination_after_get_pages(self, agent):
        """After get_pages, the response must contain actual text, not a fake description."""
        r = agent.extract([LEC_3], "What's on the first page?")
        assert "get_pages" in tools(agent)
        assert "[Title" not in r
        assert "[specific" not in r
        assert any(kw in r for kw in ("8.701", "Nuclear", "MIT", "Klute", "Physics"))

    def test_book_overview_does_not_extract_all_pages(self, agent):
        """'What is this book about?' must not trigger get_pages on all 758 pages."""
        agent.extract([BOOK], "What is this book about?")
        large_extractions = [
            tc for tc in agent.last_trace.tool_calls
            if tc.tool_name == "get_pages" and tc.arguments.get("end_page", 0) > 50
        ]
        assert len(large_extractions) == 0, \
            "Must not extract hundreds of pages for an overview question"

    def test_folder_correct_file_count(self, agent):
        """Folder expansion must find all 6 files."""
        r = agent.extract([FOLDER], "How many files do I have?")
        assert tools(agent) == []
        assert "6" in r

    def test_ambiguous_request_uses_toc_file(self, agent):
        """'Give me section 4' with mixed files — agent must use the book (has_toc=True)."""
        agent.extract(ALL_FILES, "Give me section 4.")
        assert "get_toc" in tools(agent)
        assert ms(agent) < TIME["two_tools"]

    def test_scanned_lecture_handled_gracefully(self, agent):
        """Scanned PDF must not return empty or crash."""
        r = agent.extract([LEC_SCANNED], "What does this lecture cover?")
        assert r.strip() != "", "Must return something, not empty"
        assert ms(agent) < TIME["one_tool"]

    def test_zero_page_docx_handled(self, agent):
        """DOCX inspection returns 0 estimated pages — agent must still attempt extraction."""
        r = agent.extract([DOCX], "What does this document say?")
        assert r.strip() != ""
        assert ms(agent) < TIME["one_tool"]
