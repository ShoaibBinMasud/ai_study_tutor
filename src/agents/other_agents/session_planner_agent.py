"""
SessionPlannerAgent — builds a structured JSON teaching plan from uploaded documents.

This is Layer 3 of the document pipeline:
  Layer 1: DocumentScannerAgent  → classifies documents (type, subject, pages, etc.)
  Layer 2: DocumentAgent         → extracts content on demand
  Layer 3: SessionPlannerAgent   → produces a teaching plan (this)

The planner decides WHAT to teach, in WHAT ORDER, with WHAT metadata.
It does NOT teach — it only plans. The TutorAgent (or any caller) executes the plan.

Context window protection:
- Files are processed ONE AT A TIME (never all at once)
- Every tool response is capped at RESPONSE_CAP chars before entering message history
- Short docs (≤50 pages): read all content
- Long regular docs (>50 pages, not scanned): get TOC + targeted section
- Long scanned docs (>50 pages, scanned): metadata only (no usable text/TOC)

Usage:
    from agents.session_planner_agent import SessionPlannerAgent
    from utils.llm_client import LLMClient

    agent = SessionPlannerAgent(LLMClient())
    plan = agent.plan(
        file_paths=["physics.pdf", "lecture1.pdf", "notes.jpg"],
        request="help me prepare for the exam on chapter 3",
        student_context="knows calculus, merit score 6/10",
    )
    # plan is a dict — JSON-serializable SessionPlan
    print(json.dumps(plan, indent=2))
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from agents.document_scanner_agent import DocumentScannerAgent
from agents.document_agent import DocumentAgent
from models.data_models import DocumentScanEntry, DocumentScanReport
from utils.llm_client import LLMClient
from utils.agent_tracer import AgentTracer
from utils.trace_logger import TraceLogger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Session Planner for an AI study tutor.

Your ONLY job is to create a structured teaching plan from uploaded documents.
You do NOT teach — you build a plan that the teaching agent will follow later.

## Your tools
- scan_documents: Get metadata for ALL files at once (pages, type, subject, TOC, scanned).
  ALWAYS call this first before reading any file content.
- get_file_pages: Read a small range of pages (8-10 at a time) from any document.
  Use for short-to-medium documents (total_pages <= 50) to read page by page in order.
- get_file_toc: Get table of contents for a single file.
  Use ONLY for long non-scanned documents (total_pages > 50, is_scanned=False).
- get_file_section: Extract one specific SECTION (not a whole chapter) from a long document.
  Use ONLY after get_file_toc shows you the structure, for long non-scanned docs.
  Call once per section — NOT once per chapter.

---

## STEP 1: Reason before you read

After scan_documents returns, STOP and write your strategy explicitly before calling any other tool.

  "The student wants [X]. I have [N] files:
   - [file1]: textbook, 280 pages, has_toc=True — I'll get TOC, then read each relevant SECTION
   - [file2]: lecture slides, 30 pages, scanned — I'll read in 8-page chunks
   Request maps to: [chapter / section / topic cluster / all content]"

**For chapter requests on textbooks:**
1. Call get_file_toc first
2. Find the chapter in the TOC. List ALL its sections: "Chapter 3 has sections 3-1, 3-2, 3-3, 3-4"
3. Read EACH section individually: get_file_section(path, "section 3-1"), then "section 3-2", etc.
4. NEVER call get_file_section(path, "chapter 3") — a whole chapter is too large to process.

**For single-section requests:**
1. Call get_file_toc to confirm the section exists and find its page range
2. Call get_file_section(path, "section X-Y") for that section only

This reasoning step prevents wasted tool calls and keeps your plan coherent.

---

## STEP 2: Validate the request against what's available

1. Student asks for "chapter X" but ALL files are lecture_slides or short notes:
   → Slides don't have chapters. Set scope="lecture_content".
   → Plan based on topic clusters. Note mismatch in request_note.
   → Do NOT invent chapter numbers.

2. Student asks for "chapter X" and a textbook exists (has_toc=True):
   → FIRST: call get_file_toc(textbook) to verify the TOC has usable structure with chapter/section names
   → If TOC returns empty or has fewer than 3 entries: STOP — do NOT call get_file_section
   → If TOC is good: Plan chapter X from the textbook. Cross-reference lecture slides if uploaded.

3. Student asks for all content / full plan / "help me read everything":
   → Plan ALL chapters/sections across ALL uploaded files.
   → Group by file, then by chapter/section within each file.
   → Cross-reference where files cover the same topic.
   → IMPORTANT: For files with no usable TOC, use key_topics only (see STEP 3).

4. Always use the actual document structure — never invent sections or chapters.
   If a document doesn't have one, plan from what exists (key_topics from metadata).

---

## STEP 3: Read content — follow the right strategy per file

### Short docs (total_pages <= 50): read in 20-25 page batches
  get_file_pages(path, 1, 25) → get_file_pages(path, 26, 50) → ... until all pages read.
  Finish ALL batches of one file before moving to the next.
  Larger batches = fewer API calls = faster, fewer rate limit issues.

### Long textbooks (total_pages > 50, is_scanned=False): read section by section
  ① get_file_toc(path) — see chapter and section structure
  ② From the TOC, write out every section in the requested chapter:
     "Chapter 4 contains: section 4-1 (p.165), 4-2 (p.167), 4-3 (p.175), 4-4 (p.187), 4-5 (p.192)"
  ③ For EACH section, call get_file_section(path, "section X-Y") — one call per section.
     After each call, extract equations/figures/symbols/examples from that section.
     Do NOT call get_file_section(path, "chapter X") — that returns a huge blob
     that gets cut off and produces empty metadata.
  ④ After reading ALL sections, break each section into 2-5 teachable concepts.
     Result: 10-20 topics total for a chapter, not 4-5.

  Example for "chapter 4" with sections 4-1 through 4-5:
    get_file_toc("textbook.pdf")
    → Note: "Chapter 4 has sections 4-1, 4-2, 4-3, 4-4, 4-5 — I will read each one"
    get_file_section("textbook.pdf", "section 4-1")  → read → split into 2-3 concepts
    get_file_section("textbook.pdf", "section 4-2")  → read → split into 2-3 concepts
    get_file_section("textbook.pdf", "section 4-3")  → read → split into 3-4 concepts
    get_file_section("textbook.pdf", "section 4-4")  → read → split into 2-3 concepts
    get_file_section("textbook.pdf", "section 4-5")  → read → split into 2 concepts

### Long scanned PDFs (total_pages > 50, is_scanned=True):
  No readable text. Use key_topics and preview_summary from scan metadata only.
  Create plan topics noting that content will be read during teaching.

### Long non-scanned, TOC empty or unhelpful (CRITICAL):
  If get_file_toc returns "No readable TOC" or "TOC empty" or fewer than 3 entries:
  → DO NOT call get_file_section — you will trigger massive full-document extraction
  → Instead, use key_topics and preview_summary from scan metadata ONLY
  → Create plan topics from key_topics, with estimated_minutes and difficulty inferred
  → Set content_note in each topic: "Content will be extracted during teaching"

  DO NOT try to be clever and read random pages to find "chapter 2" — you will hit rate limits.
  The LLM teaching this will have access to the actual content during the session.

---

## STEP 4: Extract metadata — never leave fields empty

After reading each section or page chunk, extract every field you can find.

key_equations:
  Textbooks: numbered equations exactly as written — "Eq. 4-3: E_n = -13.6/n² eV (page 178)"
             Also important unnumbered equations.
  Slides: equations described by vision — "E = hf", "λ = h/mv"

symbols:
  Every defined symbol — "n = principal quantum number", "a₀ = Bohr radius = 0.529 Å"
  These are NOT equations — they are symbol definitions.

figures:
  Textbooks: "Figure 4-3: Rutherford scattering geometry showing impact parameter b (page 169)"
  Slides: "Slide 7: Energy level diagram for hydrogen showing n=1 to n=4 transitions"

examples:
  "Example 4-2: Calculate the radius of the first Bohr orbit (page 177)"

practice_problems:
  "Problems 4-1 to 4-5 (page 192)", "Problem 4-18"

If a field is truly absent from the content, set it to []. Do NOT leave it empty because
you forgot to look — scan the content carefully.

---

## STEP 5: Handle multiple files intelligently

When multiple files are uploaded:
- Process files ONE AT A TIME — finish all reads for one file before starting the next.
- After reading all files, note cross-references in teaching_notes:
  "Section 4-2 in textbook corresponds to slides 8-12 in lecture_slides.pdf"
- For topics covered by multiple sources, choose the richer source as source_file
  and mention the supporting source in the topic's key_concepts or teaching_notes.
- For a "how to read everything" or "full plan" request: create one topic per
  section/chapter across all files, ordered logically (not just file-by-file).

---

## STEP 5: Break every section into teachable concepts

A private tutor never teaches an entire section in one go. After reading a section,
identify 2–5 distinct concepts within it and make each one a separate topic entry.

Rules for splitting:
- Each topic = one concept a student can absorb in 5–15 minutes
- Follow the natural pedagogical order (concept A must come before concept B)
- Each topic gets its OWN equations, symbols, figures, examples from that concept's pages
- Do NOT lump everything into order=1 with all equations/figures mixed together
- A section with 4 key concepts → 4 topic entries, not 1

How to identify concepts:
- Look for sub-headings within the section
- Look for distinct named laws, models, or phenomena (each is its own topic)
- Look for the worked examples — each example usually belongs to one concept
- Look at which equations are introduced together vs separately

Example — section 3-2 "Blackbody Radiation" (pages 137-144) splits into:
  Topic 1: "What is a Blackbody?" — intro concept, pages 137-138, ~8 min
  Topic 2: "Stefan-Boltzmann Law" — P = σT⁴, pages 139-140, Figure 3-3, ~10 min
  Topic 3: "Wien's Displacement Law" — λ_max = b/T, pages 140-141, Figure 3-4, ~10 min
  Topic 4: "Blackbody Cavity and Spectral Distribution" — Figure 3-5, Example 3-1, pages 142-144, ~12 min

NOT acceptable: one topic "Blackbody Radiation" covering pages 137-144, all equations mixed.

---

## Output format

Once ALL files are processed, output ONLY a valid JSON object:

{
  "scope": "chapter" | "section" | "exam_prep" | "concept" | "lecture_content",
  "title": "Teaching Plan: <descriptive title>",
  "student_request": "<original request verbatim>",
  "request_note": "<if request didn't match documents or scope was adjusted, explain; else omit>",
  "estimated_duration": "<X-Y minutes>",
  "prerequisites": ["<global prereq>", ...],
  "sources": [
    {"file": "<filename>", "document_class": "<class>", "pages": "<range or all>"}
  ],
  "topics": [
    {
      "order": 1,
      "title": "<specific concept name, not the section title>",
      "source_file": "<filename>",
      "section": "<section ID, e.g. '3-2'>",
      "page_range": [<start>, <end>],
      "key_concepts": ["<concept>", ...],
      "key_equations": ["<equations belonging to THIS concept only>", ...],
      "symbols": ["<symbols introduced in THIS concept only>", ...],
      "figures": ["<figures belonging to THIS concept only>", ...],
      "examples": ["<examples belonging to THIS concept only>", ...],
      "practice_problems": ["<problem ref>", ...],
      "estimated_minutes": <int between 5 and 15>,
      "difficulty": "introductory" | "intermediate" | "advanced",
      "prerequisites": ["<what must be understood before this concept>", ...]
    }
  ],
  "quiz_coverage": ["<topic title>", ...],
  "teaching_notes": "<cross-references between files, style notes, any scope corrections>"
}

---

## Example: textbook only, student asks "teach me chapter 4"

scan_documents(["physics_book.pdf"])
→ physics_book.pdf: 350 pages, has_toc=True, is_scanned=False

REASONING: Student wants chapter 4. I'll get the TOC, list every section in chapter 4,
then read each section one by one. Each section will be split into 2-4 teachable concepts.
I will NOT call get_file_section("chapter 4") — too large, kills metadata extraction.

get_file_toc("physics_book.pdf")
→ Chapter 4: The Nuclear Atom (p.165-192)
   4-1: Atomic Spectra (p.165)
   4-2: Rutherford's Nuclear Model (p.167)
   4-3: The Bohr Model (p.175)
   4-4: X-Ray Spectra (p.187)
   4-5: The Franck-Hertz Experiment (p.192)

Chapter 4 has 5 sections. I will call get_file_section 5 times, then split into concepts.

get_file_section("physics_book.pdf", "section 4-1")  → Splits into 2 concepts
get_file_section("physics_book.pdf", "section 4-2")  → Splits into 3 concepts
get_file_section("physics_book.pdf", "section 4-3")  → Splits into 4 concepts (Bohr model is rich)
get_file_section("physics_book.pdf", "section 4-4")  → Splits into 2 concepts
get_file_section("physics_book.pdf", "section 4-5")  → Splits into 2 concepts

Output: JSON plan with ~13 topics total, all metadata populated.

---

## Example: textbook + slides, student asks "create a reading plan for everything"

scan_documents(["textbook.pdf", "lecture_slides.pdf"])
→ textbook.pdf: 350 pages, has_toc=True | lecture_slides.pdf: 45 pages, scanned

REASONING: Student wants a full plan across both files. I'll get the textbook TOC for
structure, read each chapter section by section, then read the lecture slides in chunks.
I'll cross-reference slides to textbook sections in teaching_notes.

get_file_toc("textbook.pdf") → chapters 1-6 found
get_file_section("textbook.pdf", "section 1-1") → ... extract ...
get_file_section("textbook.pdf", "section 1-2") → ... extract ...
[continue for all sections across all chapters]

get_file_pages("lecture_slides.pdf", 1, 8) → vision output → extract equations/figures
get_file_pages("lecture_slides.pdf", 9, 16) → ...
[continue until all 45 slides read]

Output: JSON plan ordering all content logically, cross-references in teaching_notes.
"""

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "scan_documents",
            "description": (
                "Scan all uploaded files to get metadata: page count, document type, "
                "subject, key topics, whether it's scanned, whether it has a TOC. "
                "ALWAYS call this first before reading any file. "
                "This is fast — no content is read."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of all uploaded file paths to scan."
                    }
                },
                "required": ["file_paths"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_pages",
            "description": (
                "Read a specific range of pages from a document. "
                "Use for short-to-medium documents (total_pages <= 50) to read in batches. "
                "Read 20-25 pages at a time to minimize API calls. "
                "Call repeatedly with successive page ranges to cover the whole document. "
                "Example: get_file_pages(path, 1, 25), then get_file_pages(path, 26, 50), etc. "
                "Works for all formats: PDF, PPTX (slides), DOCX, images."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the document."
                    },
                    "start_page": {
                        "type": "integer",
                        "description": "First page to read (1-indexed)."
                    },
                    "end_page": {
                        "type": "integer",
                        "description": "Last page to read (inclusive). Keep end_page - start_page <= 9."
                    }
                },
                "required": ["file_path", "start_page", "end_page"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_toc",
            "description": (
                "Get the table of contents for a single file. "
                "Use ONLY for long non-scanned documents (total_pages > 50, is_scanned=False). "
                "Do NOT use for short docs (use get_file_pages) or scanned PDFs (no readable TOC). "
                "Returns chapter/section titles, IDs, and page numbers. "
                "If TOC is empty or has fewer than 3 entries, the file has no usable structure — "
                "use key_topics from scan_documents instead, do NOT try get_file_section."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the document."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_section",
            "description": (
                "Extract ONE specific SECTION from a long document. "
                "Use ONLY after get_file_toc has shown the structure, "
                "and ONLY for long non-scanned documents (total_pages > 50, is_scanned=False). "
                "IMPORTANT: Query must be a SECTION (e.g. 'section 3-1', 'section 4-2'), "
                "NEVER a whole chapter (e.g. 'chapter 3'). "
                "Whole chapters are too large — always read one section at a time. "
                "For chapter 3 with sections 3-1 through 3-4: call this tool 4 times, once per section. "
                "query examples: 'section 3-1', 'section 4-2', 'section 2.4'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the document."
                    },
                    "query": {
                        "type": "string",
                        "description": "Section to extract. Must be a section, not a chapter. e.g. 'section 3-1'"
                    }
                },
                "required": ["file_path", "query"]
            }
        }
    },
]

TOOL_NAMES = {"scan_documents", "get_file_pages", "get_file_toc", "get_file_section"}

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class SessionPlannerAgent:
    """
    Builds a structured teaching plan from uploaded documents.

    Uses DocumentScannerAgent for metadata and DocumentAgent for targeted
    content reads. Processes files one at a time to stay within context limits.
    """

    MAX_ITERATIONS = 60       # more iterations needed for per-section reads
    FULL_READ_PAGE_LIMIT = 50 # docs at or below this: use get_file_pages
    PAGE_CHUNK_SIZE = 25      # max pages per get_file_pages call — batch larger to reduce API calls
    RESPONSE_CAP = 8000       # chars per tool response kept in history

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self._scanner: Optional[DocumentScannerAgent] = None
        self._doc_agent: Optional[DocumentAgent] = None
        self._scan_report: Optional[DocumentScanReport] = None
        # Tracing (same pattern as DocumentAgent)
        self.tracer = AgentTracer()
        self.last_trace = None
        self.trace_logger = TraceLogger()

    # ── Public API ────────────────────────────────────────────────────────────

    def plan(
        self,
        file_paths: List[str],
        request: str,
        student_context: str = "",
    ) -> dict:
        """
        Build a teaching plan for the given files and request.

        Args:
            file_paths: Paths to uploaded documents.
            request: Student's learning request (e.g. "teach me chapter 3").
            student_context: Optional context about the student
                             (e.g. "merit score 6, knows calculus").

        Returns:
            SessionPlan as a JSON-serializable dict.
        """
        if not file_paths:
            return {"error": "No files provided."}

        self.tracer.start_turn(request)

        file_list = "\n".join(
            f"- {p} ({Path(p).suffix.upper().lstrip('.')})"
            for p in file_paths
        )
        context_line = f"\n\nStudent context: {student_context}" if student_context else ""
        user_message = (
            f"The student has uploaded these documents:\n{file_list}\n\n"
            f"Student request: {request}{context_line}\n\n"
            f"Build a complete teaching plan for this request."
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        logger.info(
            f"SessionPlannerAgent.plan: {len(file_paths)} file(s), request='{request[:60]}'"
        )

        raw = self._run_agent_loop(messages)

        # Parse the JSON plan from the LLM's final response
        result = self._parse_plan_json(raw)

        self.last_trace = self.tracer.end_turn(json.dumps(result, indent=2)[:1000])
        self.trace_logger.save(self.last_trace)

        return result

    # ── Agent loop ────────────────────────────────────────────────────────────

    def _run_agent_loop(self, messages: list) -> str:
        """Standard OpenAI tool-calling loop with response capping."""
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

            if message.get("content"):
                self.tracer.log_reasoning(message.get("content", ""))

            if choice["finish_reason"] == "stop":
                content = message.get("content", "")
                if not content or not content.strip().startswith("{"):
                    return self._request_final_plan(messages)
                # Don't accept the draft JSON directly — refine it
                return self._refine_plan(messages, content)

            tool_calls = message.get("tool_calls", [])
            if not tool_calls:
                content = message.get("content", "")
                if not content or not content.strip().startswith("{"):
                    return self._request_final_plan(messages)
                return self._refine_plan(messages, content)

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                logger.info(f"  [{iteration+1}] {tool_name}({self._fmt_args(args)})")

                t0 = time.time()
                result = self._call_tool(tool_name, args)
                elapsed_ms = (time.time() - t0) * 1000

                # Cap response before adding to history
                capped = result[:self.RESPONSE_CAP]
                if len(result) > self.RESPONSE_CAP:
                    capped += f"\n... [response capped at {self.RESPONSE_CAP} chars]"

                self.tracer.log_tool_call(tool_name, args, capped, elapsed_ms)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": capped,
                })

        logger.warning("SessionPlannerAgent reached max iterations — requesting final plan")
        return self._request_final_plan(messages)

    def _refine_plan(self, messages: list, draft_json: str) -> str:
        """
        Two-phase plan refinement:
        1. Ask LLM to extract every equation, figure, symbol, example from content it read
        2. Ask LLM to rebuild JSON with all extracted items assigned to correct topics
        """
        logger.info("Running _refine_plan: extraction + rebuild")

        # Phase 1: Extract everything from the content
        extract_messages = messages + [
            {"role": "assistant", "content": draft_json},
            {"role": "user", "content": (
                "Before I accept this plan, go back through ALL the section content you read above "
                "and list everything you can find:\n\n"
                "EQUATIONS: (list every numbered and unnumbered equation with page numbers)\n"
                "FIGURES: (list every figure with number, description, and page)\n"
                "SYMBOLS: (list every symbol definition with meaning)\n"
                "EXAMPLES: (list every worked example with number and page)\n"
                "PRACTICE PROBLEMS: (list any end-of-section or end-of-chapter problems)\n"
                "KEY CONCEPTS: (list the main concepts/definitions introduced)\n\n"
                "Be exhaustive. Scan the content line by line. Do not skip anything."
            )}
        ]

        try:
            extract_response = self.llm.chat(
                extract_messages, tools=None, max_tokens=2000, temperature=0.1
            )
            extraction = extract_response["choices"][0]["message"].get("content", "")
            self.tracer.log_reasoning(f"[EXTRACTION STEP]\n{extraction}")
        except Exception as e:
            logger.error(f"Extraction phase failed: {e}")
            return draft_json  # fall back to draft

        # Phase 2: Rebuild plan with extraction results
        rebuild_messages = extract_messages + [
            {"role": "assistant", "content": extraction},
            {"role": "user", "content": (
                "Now update the teaching plan JSON. Every equation, figure, symbol, and example "
                "you just listed MUST appear in the correct topic entry. "
                "Assign each item to the topic whose page_range covers it.\n"
                "Each section should be broken into 2-5 teachable concepts (5-15 min each).\n"
                "key_equations, figures, symbols, examples, practice_problems fields must be populated.\n"
                "Output ONLY the updated JSON — no explanation, no markdown fences."
            )}
        ]

        try:
            rebuild_response = self.llm.chat(
                rebuild_messages, tools=None, max_tokens=4000, temperature=0.1
            )
            refined = rebuild_response["choices"][0]["message"].get("content", "")
            self.tracer.log_reasoning(f"[REFINED PLAN]\n{refined[:500]}")

            # Validate it looks like JSON
            if refined and refined.strip().startswith("{"):
                return refined
            else:
                logger.warning("Refined plan doesn't look like JSON, falling back to draft")
                return draft_json
        except Exception as e:
            logger.error(f"Rebuild phase failed: {e}")
            return draft_json

    def _request_final_plan(self, messages: list) -> str:
        """
        Explicitly ask the LLM to produce the final consolidated JSON plan
        from everything it has read so far, then refine it.
        """
        messages_copy = messages + [{
            "role": "user",
            "content": (
                "You have now read all the documents. "
                "Based on everything you have gathered, produce the final consolidated "
                "teaching plan as a single valid JSON object. "
                "Do not call any more tools. Output ONLY the JSON."
            )
        }]
        try:
            response = self.llm.chat(
                messages=messages_copy,
                tools=None,
                max_tokens=4000,
                temperature=0.1,
            )
            content = response["choices"][0]["message"].get("content", "")

            # Route through refinement if we got JSON
            if content and content.strip().startswith("{"):
                return self._refine_plan(messages, content)
            return content
        except Exception as e:
            logger.error(f"Final plan request failed: {e}")
            return '{"error": "Failed to generate final plan."}'

    # ── Tool dispatch ─────────────────────────────────────────────────────────

    def _call_tool(self, name: str, args: dict) -> str:
        try:
            if name == "scan_documents":
                return self._tool_scan_documents(args.get("file_paths", []))
            elif name == "get_file_pages":
                return self._tool_get_file_pages(
                    args.get("file_path", ""),
                    args.get("start_page", 1),
                    args.get("end_page", 8),
                )
            elif name == "get_file_toc":
                return self._tool_get_file_toc(args.get("file_path", ""))
            elif name == "get_file_section":
                return self._tool_get_file_section(
                    args.get("file_path", ""), args.get("query", "")
                )
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return f"ERROR: {name} failed — {e}"

    # ── Tool implementations ──────────────────────────────────────────────────

    def _tool_scan_documents(self, file_paths: List[str]) -> str:
        """Scan all files and return metadata summary."""
        if not file_paths:
            return "No file paths provided."

        scanner = self._get_scanner()
        try:
            self._scan_report = scanner.scan(file_paths)
        except Exception as e:
            return f"Scan failed: {e}"

        # Format scan results for the LLM
        lines = [f"Scan complete — {len(self._scan_report.entries)} file(s):\n"]
        for e in self._scan_report.entries:
            lines.append(f"FILE: {e.file_name}")
            lines.append(f"  type: {e.file_type} | class: {e.document_class}")
            lines.append(f"  pages: {e.total_pages} | is_scanned: {e.is_scanned} | has_toc: {e.has_toc}")
            lines.append(f"  subject: {e.subject} {e.sub_field} ({e.level})")
            lines.append(f"  key_topics: {', '.join(e.key_topics)}")
            if e.preview_summary:
                lines.append(f"  summary: {e.preview_summary}")
            lines.append("")

        if self._scan_report.collection_summary:
            lines.append(f"Collection: {self._scan_report.collection_summary}")

        return "\n".join(lines)

    def _tool_get_file_pages(self, file_path: str, start_page: int, end_page: int) -> str:
        """Read a page range — for short/medium docs only."""
        pages = self._get_page_count(file_path)

        if pages is not None and pages > self.FULL_READ_PAGE_LIMIT:
            return (
                f"This file has {pages} pages — too large for get_file_pages. "
                f"Use get_file_toc first, then get_file_section for specific chapters."
            )

        # Clamp to actual page count
        if pages is not None:
            end_page = min(end_page, pages)

        # Enforce max chunk size to protect context window
        max_chunk = self.PAGE_CHUNK_SIZE
        if (end_page - start_page + 1) > max_chunk:
            end_page = start_page + max_chunk - 1
            note = f" [chunk capped to {max_chunk} pages]"
        else:
            note = ""

        doc_agent = self._get_doc_agent()
        result = doc_agent.extract(
            [file_path],
            f"get pages {start_page} to {end_page}"
        )
        return result + note

    def _tool_get_file_toc(self, file_path: str) -> str:
        """Get TOC — only for long non-scanned docs."""
        pages = self._get_page_count(file_path)
        is_scanned = self._is_scanned(file_path)

        if pages is not None and pages <= self.FULL_READ_PAGE_LIMIT:
            return (
                f"This file has only {pages} pages. "
                f"Use get_file_pages in 8-page chunks instead of get_file_toc."
            )
        if is_scanned:
            return (
                "This is a scanned PDF — no machine-readable TOC exists. "
                "Use the key_topics and preview_summary from scan_documents instead."
            )

        doc_agent = self._get_doc_agent()
        return doc_agent.extract([file_path], "get the table of contents")

    def _tool_get_file_section(self, file_path: str, query: str) -> str:
        """Get a specific section — only for long non-scanned docs."""
        pages = self._get_page_count(file_path)
        is_scanned = self._is_scanned(file_path)

        if pages is not None and pages <= self.FULL_READ_PAGE_LIMIT:
            return (
                f"This file has only {pages} pages. "
                f"Use get_file_pages in 8-page chunks to read it."
            )
        if is_scanned:
            return (
                "This is a scanned PDF. "
                "Use key_topics and preview_summary from scan_documents for planning."
            )

        doc_agent = self._get_doc_agent()
        return doc_agent.extract([file_path], f"get {query}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_scanner(self) -> DocumentScannerAgent:
        if self._scanner is None:
            self._scanner = DocumentScannerAgent(self.llm)
        return self._scanner

    def _get_doc_agent(self) -> DocumentAgent:
        if self._doc_agent is None:
            self._doc_agent = DocumentAgent(self.llm)
            # Share scan report with doc agent for faster inspect calls
            if self._scan_report:
                self._doc_agent.register_scan(self._scan_report)
        return self._doc_agent

    def _get_scan_entry(self, file_path: str) -> Optional[DocumentScanEntry]:
        if not self._scan_report:
            return None
        name = Path(file_path).name
        for entry in self._scan_report.entries:
            if entry.file_path == file_path or entry.file_name == name:
                return entry
        return None

    def _get_page_count(self, file_path: str) -> Optional[int]:
        entry = self._get_scan_entry(file_path)
        return entry.total_pages if entry else None

    def _is_scanned(self, file_path: str) -> bool:
        entry = self._get_scan_entry(file_path)
        return entry.is_scanned if entry else False

    def _parse_plan_json(self, raw: str) -> dict:
        """Extract and parse JSON from LLM response. Falls back to error dict."""
        if not raw:
            return {"error": "Empty response from planner."}

        # Try direct parse first
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON block from markdown-wrapped response
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find first { ... } block
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end+1])
            except json.JSONDecodeError:
                pass

        logger.error(f"Failed to parse plan JSON. Raw: {raw[:200]}")
        return {
            "error": "Could not parse plan JSON.",
            "raw_response": raw[:500],
        }

    @staticmethod
    def _fmt_args(args: dict) -> str:
        parts = []
        for k, v in args.items():
            val = str(v)
            if len(val) > 50:
                val = val[:50] + "..."
            parts.append(f"{k}={val!r}")
        return ", ".join(parts)
