"""
DocumentAgent — Intelligent document content extraction agent.

This is Layer 2 of the document pipeline:
  Layer 1: DocumentScannerAgent  → classifies documents (type, subject, page count, etc.)
  Layer 2: DocumentAgent (this)  → extracts content on demand, guided by student requests

The agent decides HOW to extract based on:
- Document type (PDF, PPTX, DOCX, image, text)
- Document size (long vs short)
- Whether it's scanned/handwritten (vision vs text extraction)
- What the student asked for (chapter, section, example, everything)

This agent does NOT teach — it ONLY parses and returns raw content.
The TutorAgent calls this when it needs content to teach from.

Usage:
    from agents.document_agent import DocumentAgent
    from utils.llm_client import LLMClient

    agent = DocumentAgent(LLMClient())
    agent.register_scan(scan_report)      # from DocumentScannerAgent

    # Student asks for specific content
    content = agent.extract(
        file_paths=["physics.pdf", "lecture_notes.pptx", "my_notes.jpg"],
        request="teach me chapter 2 from the textbook"
    )
"""

import sys
from pathlib import Path as _P
if str(_P(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(_P(__file__).parent.parent))

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from content.document_content_tool import DocumentContentTool, DocumentTooLargeError
from content.file_inspection_tool import inspect as inspect_files
from models.data_models import DocumentScanEntry, DocumentScanReport
from utils.llm_client import LLMClient
from utils.agent_tracer import AgentTracer
from utils.trace_logger import TraceLogger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — Refactored for 3 tools + file metadata
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Document Agent — an intelligent content navigator for an AI study tutor.
You work across all subjects: physics, math, biology, chemistry, law, computer science, history, and more.

---

## STEP 0: Can I answer from metadata alone?

File metadata is provided as JSON at the start of each request. READ IT FIRST.
If the student's question is about file properties — answer directly from the JSON. Call NO tools.

**Read the exact numbers from the JSON. Never substitute values from training knowledge.**

Answerable from metadata (no tools):
- "How many pages is X?" → read "total_pages" for that file from the JSON
- "Does X have a table of contents?" → read "has_toc"
- "Is X scanned / handwritten?" → read "is_scanned"
- "How many files did I upload?" → count objects in the JSON
- "What types of files do I have?" → read "file_type" for each

The JSON is ground truth. If it says a file has 5 pages, say 5 — never adjust it.

---

## STEP 1: Identify the right file(s)

Multiple files may be uploaded. Use file_name and file_type to infer roles:
- Large PDF with has_toc=True → likely a textbook or structured reference book
- Short PDF (few pages) with has_toc=False → likely a lecture, handout, or notes
- PPTX → slides
- Image (PNG/JPG) → handwritten notes, diagrams, scanned pages
- DOCX/TXT → typed notes or readings

If the request is ambiguous ("find section 4"), look at file types to decide which file to use.
If still ambiguous after inspecting types, ask the student to clarify which document they mean.

---

## STEP 2: Classify the request

**A. Metadata question** → answered in Step 0, no tools needed.

**B. Section or chapter location**
The student asks where a section or chapter is: "where is section 3-2?", "what page does chapter 4 start?"

→ call get_toc → read the page number directly from the result → answer immediately.
→ Do NOT call find_in_pages. The TOC IS the answer for section/chapter location questions.

**C. Labeled item location or count**
The student asks for a specific labeled item by number — these are items printed inline in the text,
NOT headings, NOT sections: "where does Example 2-1 appear?", "what page is Figure 3-2?", "find Theorem 4.2",
"how many examples in section 2-1?", "list all figures in chapter 3"

Labeled items exist across all subjects. Common types by domain:
- General: Example, Figure, Table, Problem
- Math/CS: Theorem, Lemma, Corollary, Definition, Algorithm, Proposition
- Science: Equation, Protocol, Experiment
- Any numbered label printed inline in the text (NOT in the TOC)

→ call get_toc to get the chapter page range → then call find_in_pages or count_in_pages.
→ Do NOT answer from the TOC alone — section page ranges are not the item's location.

CRITICAL DISTINCTION — "Section 3-2" vs "Example 3-2":
Both contain "3-2" but they are completely independent numbering systems.
- "Section 3-2" is a chapter heading. Its page range IS in the TOC. Answer from get_toc directly.
- "Example 3-2" is a worked item printed inside the text. Its page is NOT in the TOC. Must use find_in_pages.
The same logic applies to all labeled items: Figure 3-2, Theorem 3.2, Algorithm 3.2, etc.

**C. Content needed for studying**
The student wants to read or study actual content: a chapter, section, all lectures, etc.
→ Use get_toc (for structured books) then get_pages, or get_pages directly for short files.

**D. Overview / orientation**
The student doesn't know what's in the file or what to study.
→ Use peek_preview or get_toc to show structure, then let the student choose.

---

## STEP 3: Plan and execute tool calls

**Planning rules:**
- Book (has_toc=True) + specific chapter/section → get_toc first → get_pages with that range
- Short file (has_toc=False, few pages) → get_pages(file, 1, total_pages) directly
- Image file → get_pages(file, 1, 1) triggers vision automatically
- Multiple independent files → call tools in parallel
- Sequential only when one result feeds the next (e.g., TOC → page range → extract)

**For section/chapter location questions — one step only:**
get_toc → read the page from the result → answer. No further tools needed.

**For labeled item questions — always two steps:**
1. get_toc → identify which chapter covers the item, read its start/end pages
2. find_in_pages(file, start, end, "Theorem 3.2") or count_in_pages(file, start, end, "theorem")

**For multi-part questions with multiple labeled items — each item gets its OWN chapter lookup:**
If the student asks two things at once (e.g., "find Example 3-2 AND count examples in section 2-1"),
treat each part independently:
- Example 3-2 → look up Chapter 3 page range from TOC → find_in_pages for Chapter 3 range
- Section 2-1 examples → look up Chapter 2 / Section 2-1 page range → count_in_pages for that range
Never reuse a chapter range computed for one part to answer a different part.
Each labeled item has its own chapter number — look it up separately.

---

## STEP 4: Read tool results critically — replan if needed

After each tool call, evaluate what came back before deciding what to do next.
Do not just proceed blindly — ask: "Did this give me what I need? Or do I need to adjust?"

### get_pages result
The ack tells you the quality: OK / SPARSE / EMPTY.

- Quality OK → content is stored, proceed to answer
- Quality SPARSE (< 150 chars/page) → the file is likely image-heavy or partially scanned.
  Replan: call get_pages again with is_scanned handling in mind, or note the limitation to the student.
- Quality EMPTY → no text extracted at all.
  Replan: the file is probably fully scanned. Use peek_preview to confirm, then tell the student
  that this file needs vision-based reading and may have limited extractable text.

### get_toc result
- TOC returned with entries → read page ranges, proceed to get_pages or find_in_pages
- TOC returned empty → the file has no embedded TOC despite has_toc=True.
  Replan: fall back to peek_preview to understand the structure, then get_pages on the full file.

### find_in_pages result
- Found → report the exact page and snippet to the student
- Not found in chapter range → do NOT stop here. Replan:
  1. Try the full document range (page 1 to total_pages) in case the item is in a different chapter
  2. If still not found → tell the student: "I searched the full document for [item] but couldn't
     locate it. It may use a different label format (e.g., 'Ex. 3-2' vs 'Example 3-2'), or it
     may not exist in this file."
  3. Never substitute a guess or report a section range as the item's location.

### count_in_pages result
- Returned a count → report it
- Returned 0 → the section may use a different label format. Mention this to the student.

---

## STEP 5: Verify before answering

Ask: "Is this answer coming from a confirmed tool result, or am I filling in from assumptions?"

- Tool returned the data → answer from it
- No tool called yet for a content question → do not guess, call the tool first
- "Pretty sure from training" → that is not evidence; verify with a tool

One common mistake to avoid: after get_toc, you have section page ranges — but that is
navigation data, not an answer. If the student asked where a labeled item appears, you still
need to call find_in_pages. get_toc tells you where to look; find_in_pages finds the actual item.

peek_preview is only for orientation ("what is this about?"). It never answers content or location questions.

Never silently skip a file or swallow an error — always tell the student what happened and why.

---

## Your 5 Tools

### peek_preview(file_path)
Samples strategic pages for a quick overview without full extraction.
Use when: student asks "what is this about?", "what's in this file?", or you need to orient yourself.

### get_toc(file_path)
Extracts chapters and sections with page numbers. Only useful when has_toc=True.
Use when: student wants a specific chapter/section (to get the page range), or wants to see what's available.
Always call this BEFORE find_in_pages or count_in_pages.

### find_in_pages(file_path, start_page, end_page, item_label)
Regex search for a specific labeled item within a page range. No LLM — no hallucination.
Works only on digital (non-scanned) PDFs. Stops at first match.
item_label: the exact label as the student stated it — e.g., "Example 3-2", "Theorem 4.2", "Algorithm 2.1"

### count_in_pages(file_path, start_page, end_page, item_type)
Counts all labeled items of a given type within a page range. Scans every page. No LLM.
item_type: any label keyword — "example", "theorem", "figure", "algorithm", "definition", etc.

### get_pages(file_path, start_page, end_page)
Universal extraction for any file type and page range.
- Digital PDF → text extraction
- Scanned PDF (is_scanned=True) → vision automatically
- PPTX → slides
- Image → full vision description (use start=1, end=1)
- DOCX/text → sliced content

---

## Scenarios

**"What is this about?" / "What's in these slides?"**
→ peek_preview each relevant file in parallel → summarize

**"What can I study?" / "Show me the chapters"**
→ Books: get_toc → list chapters → ask student to choose
→ Lectures/handouts: peek_preview each → describe what each covers

**"Teach me chapter 3" / "I want to study [topic]"**
→ If has_toc=True: get_toc → find chapter range → get_pages(file, start, end)
→ If no TOC: peek_preview to locate content → get_pages for that region

**"Where does section 3-2 appear?" / "What page does chapter 4 start?"**
→ get_toc → read the page number from the result → answer directly. Done.
→ Do NOT call find_in_pages. Sections and chapters are in the TOC.

**"Where does Example 3-2 appear?" / "What page is Figure 2-5?" / "Find Theorem 4.2"**
→ get_toc → get the chapter's start and end pages
→ find_in_pages(file, start, end, item_label) → report exact page
→ Works for any subject: Example, Theorem, Algorithm, Definition, Figure, Protocol, etc.
→ Do NOT answer from the TOC — those are section ranges, not item locations.

**"How many [items] are in [section/chapter]?"**
→ get_toc → get section/chapter page range
→ count_in_pages(file, start, end, item_type) → report count and list

**"Use the book and all the lectures"**
→ get_toc(book) → get chapter range → get_pages(book, start, end)
→ get_pages for each lecture using total_pages from metadata — run in parallel

---

## Output Format

Label extracted content clearly:
[SOURCE: filename | pages X-Y | type: pdf/pptx/image]

For multiple files, label each section separately.
After extracting, briefly note what was found and flag any gaps or issues.
"""

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "peek_preview",
            "description": (
                "Sample a small portion of a file to give a quick overview. "
                "Fast — returns 500-1500 chars without full extraction. "
                "Use when: student asks 'what is this about?', 'give me an overview', 'what's in this file?' "
                "For images: triggers vision call for 1-2 sentence description. "
                "For PDFs: samples first 2 pages if has_toc, else first + middle + last page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the document file."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_toc",
            "description": (
                "Extract the table of contents from a document — chapters AND sections with page numbers. "
                "Only useful for files with has_toc=True (books, structured PDFs). "
                "ALWAYS call this first before find_in_pages or count_in_pages to get the correct page range. "
                "Helps students who are unsure what to study by showing available chapters and sections."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the document file."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_in_pages",
            "description": (
                "Find a specific labeled item (Example, Figure, Table, Problem) within a page range. "
                "Pure Python regex — no LLM, no hallucination. Stops at first match. "
                "MUST call get_toc first to get chapter start/end pages, then call this tool. "
                "Use for: 'where does Example 3-2 appear?', 'what page is Figure 3-2?', 'find Problem 2-20'. "
                "WARNING: Do NOT confuse 'Section 3-2' (a chapter section, visible in TOC) with "
                "'Example 3-2' (a worked example inside the text, NOT in TOC). "
                "The TOC cannot tell you where Example 3-2 is — only this tool can."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the digital PDF file."
                    },
                    "start_page": {
                        "type": "integer",
                        "description": "First page to search (1-indexed, from get_toc result)."
                    },
                    "end_page": {
                        "type": "integer",
                        "description": "Last page to search (inclusive, from get_toc result)."
                    },
                    "item_label": {
                        "type": "string",
                        "description": "Item to find. E.g. 'Example 2-1', 'Figure 3-2', 'Problem 2-20'."
                    }
                },
                "required": ["file_path", "start_page", "end_page", "item_label"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "count_in_pages",
            "description": (
                "Count ALL labeled items of a given type within a page range. "
                "Pure Python regex — no LLM. Scans every page in range. "
                "MUST call get_toc first to get start_page and end_page. "
                "Use for: 'how many examples in section 2-1?', 'list all figures in chapter 3'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the digital PDF file."
                    },
                    "start_page": {
                        "type": "integer",
                        "description": "First page to scan (1-indexed, from get_toc result)."
                    },
                    "end_page": {
                        "type": "integer",
                        "description": "Last page to scan (inclusive, from get_toc result)."
                    },
                    "item_type": {
                        "type": "string",
                        "description": "Type to count: 'example', 'figure', 'table', 'problem', 'equation'. Plurals ok."
                    }
                },
                "required": ["file_path", "start_page", "end_page", "item_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pages",
            "description": (
                "Universal page/slide extraction for any file type. "
                "Works for: PDFs (text + scanned vision), PPTX, DOCX, images, text files. "
                "Always use total_pages from file metadata (already provided) when extracting everything. "
                "Examples: "
                "  - Full file: get_pages(file, 1, total_pages) "
                "  - Chapter range from TOC: get_pages(book.pdf, 45, 89) "
                "  - Image or single page: get_pages(file, 1, 1)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the document file."
                    },
                    "start_page": {
                        "type": "integer",
                        "description": "First page/slide number (1-indexed)."
                    },
                    "end_page": {
                        "type": "integer",
                        "description": "Last page/slide number (inclusive)."
                    }
                },
                "required": ["file_path", "start_page", "end_page"]
            }
        }
    }
]

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class DocumentAgent:
    """
    Intelligent document content extraction agent.

    Orchestrates DocumentContentTool using an LLM agent loop.
    The LLM decides which tools to call and in what order based on
    document metadata and the student's request.
    """

    MAX_ITERATIONS = 8  # extraction plans are typically 2-3 tool calls

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.tool = DocumentContentTool(llm_client)
        # Scan metadata from DocumentScannerAgent (optional but recommended)
        self._scan_entries: Dict[str, DocumentScanEntry] = {}
        # Tracer for debugging
        self.tracer = AgentTracer()
        self.last_trace = None
        # Trace persistence
        self.trace_logger = TraceLogger()

    # ── Public API ───────────────────────────────────────────────────────────

    def register_scan(self, scan_report: DocumentScanReport):
        """
        Load scan results from DocumentScannerAgent.

        When scan entries are registered, inspect_document calls are answered
        instantly from metadata rather than re-detecting from disk.
        """
        for entry in scan_report.entries:
            self._scan_entries[entry.file_path] = entry
            self._scan_entries[entry.file_name] = entry  # also index by name
        logger.info(f"DocumentAgent: registered {len(scan_report.entries)} scan entries")

    def extract(self, file_paths: List[str], request: str) -> str:
        """
        Extract content from documents based on a student request.

        Args:
            file_paths: List of paths to uploaded documents.
            request: What the student asked for (e.g. "teach me chapter 2",
                     "help me prepare for the exam", "find example 3-2").

        Returns:
            Raw extracted content, labeled by source. Ready for TutorAgent to teach from.
        """
        if not file_paths:
            return "No documents provided."

        # Expand any folder paths to individual files
        expanded: List[str] = []
        for p in file_paths:
            if Path(p).is_dir():
                from content.file_inspection_tool import _find_files_in_folder
                expanded.extend(_find_files_in_folder(Path(p)))
            else:
                expanded.append(p)
        file_paths = expanded or file_paths

        # Start tracing
        self.tracer.start_turn(request)

        # Inspect all files upfront — gives agent full metadata to make decisions
        inspected_raw = inspect_files(file_paths)
        # Normalize paths for lookup (Windows uses backslashes, but input may have forward slashes)
        inspected = {}
        for m in inspected_raw:
            if m:
                # Store by both forward and backslash versions for reliable lookup
                inspected[m["file_path"]] = m
                inspected[m["file_path"].replace("\\", "/")] = m
                inspected[Path(m["file_path"]).name] = m

        # Build metadata as JSON (LLMs parse JSON more reliably than plain text for exact numbers)
        metadata_list = []
        for p in file_paths:
            # Try multiple lookup strategies
            meta = (
                inspected.get(p)
                or inspected.get(p.replace("/", "\\"))
                or inspected.get(str(Path(p)))
                or inspected.get(Path(p).name)
                or None
            )
            if meta:
                metadata_list.append({
                    "file_path": p,
                    "file_name": Path(p).name,
                    "file_type": meta["file_type"],
                    "total_pages": meta["total_pages"],
                    "has_toc": meta["has_toc"],
                    "is_scanned": meta["is_scanned"],
                })
            else:
                metadata_list.append({
                    "file_path": p,
                    "file_name": Path(p).name,
                    "file_type": Path(p).suffix.upper().lstrip("."),
                    "total_pages": 0,
                    "has_toc": False,
                    "is_scanned": False,
                })

        user_message = (
            f"The student has uploaded these documents:\n\n```json\n{json.dumps(metadata_list, indent=2)}\n```\n\n"
            f"Student request: {request}"
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        logger.info(f"DocumentAgent.extract: {len(file_paths)} file(s), request='{request[:60]}'")
        result = self._run_agent_loop(messages)

        # End tracing and save to JSON
        self.last_trace = self.tracer.end_turn(result)
        self.trace_logger.save(self.last_trace)
        return result

    # ── Agent loop ───────────────────────────────────────────────────────────

    def _run_agent_loop(self, messages: list) -> str:
        """Standard OpenAI tool-calling loop.

        Key design: get_pages results are NOT fed back to the LLM — only a short
        confirmation is. The LLM only reads peek_preview and get_toc results.
        Full extracted content is collected separately and returned directly.
        """
        # Stores full content from get_pages calls — LLM never reads these
        extracted_content: List[str] = []

        for iteration in range(self.MAX_ITERATIONS):
            response = self.llm.chat(
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=4000,
                temperature=0.1,
            )

            choice = response["choices"][0]
            message = choice["message"]
            messages.append(message)

            # Log reasoning from assistant message content
            if message.get("content"):
                self.tracer.log_reasoning(message.get("content", ""))

            # Done
            if choice["finish_reason"] == "stop":
                llm_summary = message.get("content", "")
                if extracted_content:
                    # Return raw extracted content only — the LLM never read it so any
                    # summary it generates is hallucinated. Only prepend if it flagged
                    # an issue (SPARSE/EMPTY quality) which we relay as a brief warning.
                    parts = []
                    if llm_summary and any(
                        kw in llm_summary.upper()
                        for kw in ("SPARSE", "EMPTY", "SCANNED", "ERROR", "WARNING", "COULD NOT", "FAILED")
                    ):
                        parts.append(llm_summary)
                    parts.extend(extracted_content)
                    return "\n\n".join(parts)
                return llm_summary

            # Tool calls — execute in parallel for speed
            tool_calls = message.get("tool_calls", [])
            if not tool_calls:
                return message.get("content", "")

            # Parse all tool calls upfront
            parsed_tools = {}
            for tc in tool_calls:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}
                parsed_tools[tc["id"]] = {
                    "name": tc["function"]["name"],
                    "args": args,
                }

            # Execute all tool calls in parallel
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {}
                for tc_id, tool_info in parsed_tools.items():
                    tool_name = tool_info["name"]
                    args = tool_info["args"]
                    logger.info(f"  [{iteration+1}] {tool_name}({self._fmt_args(args)})")

                    # Submit task to executor
                    future = executor.submit(self._execute_tool_timed, tool_name, args)
                    futures[future] = tc_id

                # Collect results as they complete
                for future in as_completed(futures):
                    tc_id = futures[future]
                    try:
                        result, elapsed_ms = future.result()
                        tool_name = parsed_tools[tc_id]["name"]

                        # Log to tracer
                        self.tracer.log_tool_call(tool_name, parsed_tools[tc_id]["args"], result, elapsed_ms)

                        if tool_name == "get_pages":
                            # Store full content — LLM only gets a short ack with quality signal
                            extracted_content.append(result)
                            char_count = len(result)
                            args = parsed_tools[tc_id]["args"]
                            file_path = args.get("file_path", "?")
                            start = args.get("start_page", "?")
                            end = args.get("end_page", "?")
                            page_count = (end - start + 1) if isinstance(start, int) and isinstance(end, int) else "?"
                            chars_per_page = char_count // page_count if isinstance(page_count, int) and page_count > 0 else 0

                            if char_count == 0:
                                quality = "EMPTY — no text extracted. File may be fully scanned or corrupted."
                            elif isinstance(chars_per_page, int) and chars_per_page < 150:
                                quality = f"SPARSE ({chars_per_page} chars/page avg) — file may be partially scanned or image-heavy."
                            else:
                                quality = f"OK ({chars_per_page} chars/page avg)"

                            ack = (
                                f"Extracted {char_count:,} chars from {Path(file_path).name} "
                                f"(pages {start}-{end}). Quality: {quality}. "
                                f"Content is stored and will be returned directly to the student. "
                                f"Do NOT describe, paraphrase, or summarize this content — "
                                f"you have not read it. Just confirm extraction is done."
                            )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": ack,
                            })
                        else:
                            # peek_preview and get_toc: LLM reads these normally
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": str(result),
                            })
                    except Exception as e:
                        logger.error(f"Tool execution failed for {tc_id}: {e}")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": f"ERROR: {e}",
                        })

        logger.warning("DocumentAgent reached max iterations")
        return "Could not complete extraction within iteration limit."

    # ── Tool execution ────────────────────────────────────────────────────────

    def _execute_tool_timed(self, tool_name: str, args: dict) -> tuple:
        """Execute a tool call and return (result, elapsed_ms) for timing."""
        tool_start = time.time()
        result = self._call_tool(tool_name, args)
        elapsed_ms = (time.time() - tool_start) * 1000
        return result, elapsed_ms

    # ── Tool dispatch ────────────────────────────────────────────────────────

    def _call_tool(self, name: str, args: dict) -> str:
        """Dispatch tool calls. 5 tools: peek_preview, get_toc, find_in_pages, count_in_pages, get_pages."""
        file_path = args.get("file_path", "")
        scan_entry = self._get_scan_entry(file_path)

        dispatch = {
            "peek_preview":   self._tool_peek_preview,
            "get_toc":        self._tool_get_toc,
            "find_in_pages":  self._tool_find_in_pages,
            "count_in_pages": self._tool_count_in_pages,
            "get_pages":    self._tool_get_pages,
        }

        handler = dispatch.get(name)
        if not handler:
            return f"Unknown tool: {name}"

        try:
            return handler(file_path, args, scan_entry)
        except DocumentTooLargeError as e:
            return f"ERROR: {e}"
        except FileNotFoundError:
            return f"ERROR: File not found: {file_path}"
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return f"ERROR: {name} failed — {e}"

    def _tool_peek_preview(self, file_path: str, args: dict, scan_entry: Optional[DocumentScanEntry]) -> str:
        """Handle peek_preview tool — sample a small portion for overview."""
        return self.tool.peek_preview(file_path, scan_entry)

    def _tool_get_toc(self, file_path: str, args: dict, scan_entry: Optional[DocumentScanEntry]) -> str:
        """Handle get_toc tool — extract table of contents with formatting."""
        toc = self.tool.get_toc(file_path, scan_entry)
        if not toc:
            return "No table of contents found for this document."
        lines = [f"TOC for {Path(file_path).name} ({len(toc)} entries):"]
        for entry in toc[:200]:  # show chapters + sections (up to 200 entries)
            indent = "  " * (entry["level"] - 1)
            lines.append(f"{indent}[{entry['section_id']}] {entry['title']} (p.{entry['page_start']})")
        if len(toc) > 200:
            lines.append(f"  ... and {len(toc) - 200} more entries")
        return "\n".join(lines)

    def _tool_find_in_pages(self, file_path: str, args: dict, scan_entry: Optional[DocumentScanEntry]) -> str:
        """Handle find_in_pages — regex search for a labeled item within a known page range."""
        start = args.get("start_page")
        end = args.get("end_page")
        item_label = args.get("item_label", "").strip()
        if not item_label or start is None or end is None:
            return "ERROR: file_path, start_page, end_page, and item_label are all required."
        return self.tool.find_in_pages(file_path, int(start), int(end), item_label, scan_entry)

    def _tool_count_in_pages(self, file_path: str, args: dict, scan_entry: Optional[DocumentScanEntry]) -> str:
        """Handle count_in_pages — count all labeled items within a known page range."""
        start = args.get("start_page")
        end = args.get("end_page")
        item_type = args.get("item_type", "").strip()
        if not item_type or start is None or end is None:
            return "ERROR: file_path, start_page, end_page, and item_type are all required."
        return self.tool.count_in_pages(file_path, int(start), int(end), item_type, scan_entry)

    def _tool_get_pages(self, file_path: str, args: dict, scan_entry: Optional[DocumentScanEntry]) -> str:
        """Handle get_pages tool — universal extraction for any file type and page range."""
        start = args.get("start_page", 1)
        end = args.get("end_page", 1)
        return self.tool.get_pages(file_path, start, end, scan_entry)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_scan_entry(self, file_path: str) -> Optional[DocumentScanEntry]:
        """Look up scan entry by path or filename."""
        return (
            self._scan_entries.get(file_path)
            or self._scan_entries.get(Path(file_path).name)
        )

    @staticmethod
    def _fmt_args(args: dict) -> str:
        """Format tool args for logging."""
        parts = []
        for k, v in args.items():
            val = str(v)
            if len(val) > 40:
                val = val[:40] + "..."
            parts.append(f"{k}={val!r}")
        return ", ".join(parts)


# ── Test ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path as P

    # Add src to path
    sys.path.insert(0, str(P(__file__).parent.parent))

    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from utils.llm_client import LLMClient

    # ── Config ────────────────────────────────────────────────────────────────
    DEBUG = True   # set False to skip printing trace JSON

    TEST_FILES = [
        # "sample_pdfs/physics_book.pdf",
        # "sample_pdfs/physic_lecture/lecture_1.pdf",
        "sample_pdfs/test_folder",
    ]

    SCENARIOS = [
        # ("Find Example 3-2",   "where does section 3-2 appear in the physics book?"),
        # ("Count examples 2-1", "How many example problems are there in section 2-1 of the physics book?"),
        # ("Metadata",           "How many pages are there in the lectures?"),
        # ("Find Figure 1-2",   "what page is Figure 1-2 on in the physics book?"),
        # ("Chapters",    "What chapters are available in the physics book? Show me the table of contents."),
        ("All files",   "Give me an overview what inside of this folder"),
        # ("Mixed",       "I want chapter 2 from the book and everything from the lectures"),
        # ("Mixed",       "what lecture 1 is about"),
        # ("book",        "Where does Relativity chapter start and end in the book?"),
        # ("book",        "Where does chemistry of life chapter start and end in the book."),

    ]

    # ── Setup ─────────────────────────────────────────────────────────────────
    files = [f for f in TEST_FILES if P(f).exists()]
    if not files:
        print("No test files found. Edit TEST_FILES paths at the bottom of this file.")
        sys.exit(1)

    print(f"\nFound {len(files)} test file(s): {[P(f).name for f in files]}")

    agent = DocumentAgent(LLMClient())

    # ── Run scenarios ─────────────────────────────────────────────────────────
    for label, request in SCENARIOS:
        print(f"\n{'='*65}")
        print(f"SCENARIO : {label}")
        print(f"REQUEST  : {request}")
        print("="*65)

        try:
            result = agent.extract(file_paths=files, request=request)

            # Print result preview
            preview = result[:800] + ("..." if len(result) > 800 else "")
            print(f"\nRESULT:\n{preview}")

            # Save trace and show path
            trace = agent.last_trace
            if trace:
                saved_path = agent.trace_logger.save(trace)
                print(f"\nTrace saved -> {saved_path}")

                if DEBUG:
                    from utils.agent_tracer import AgentTracer
                    print("\n── DEBUG TRACE ──────────────────────────────────────")
                    print(f"  Request       : {trace.request}")
                    print(f"  Total time    : {trace.total_elapsed_ms:.0f}ms")
                    print(f"  Tool calls    : {len(trace.tool_calls)}")
                    print(f"  LLM reasoning : {trace.reasoning[:200] if trace.reasoning else '(none)'}")
                    print()
                    for tc in trace.tool_calls:
                        status = f"ERROR: {tc.error}" if tc.error else "OK"
                        print(f"  [{tc.iteration}] {tc.tool_name}({json.dumps(tc.arguments)})")
                        print(f"       → {status} | {tc.elapsed_ms:.0f}ms")
                        print(f"       Response: {tc.response[:150]}...")
                    print("────────────────────────────────────────────────────")

        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

    print("\nAll scenarios done. Check .traces/ for full JSON logs.")
