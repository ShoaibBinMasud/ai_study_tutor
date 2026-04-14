"""
PlannerAgent — transforms pre-extracted content.json into a complete, self-contained
teaching blueprint for the teaching agent.

Input:  content.json — array of { "source": "<id>", "content": "<extracted text>" }
Output: {
    "student_overview": "...",
    "sources": [{ "source_id": "...", "subject": "...", "units": [...] }],
    "final_learning_path": ["unit_id_1", ...]
}

The teaching agent has NO access to raw source content — every unit must be fully
grounded and independently teachable.

Pipeline:
    Phase 1: process each source independently → structured units
    Phase 2: combine all sources → global learning path

Usage:
    from agents.planner_agent import PlannerAgent
    from utils.llm_client import LLMClient

    agent = PlannerAgent(LLMClient())
    plan = agent.plan("content.json")
    print(json.dumps(plan, indent=2))
"""

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import List

# Allow running from any working directory (e.g. python src/agents/planner_agent.py)
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.gemini_client import GeminiLLMClient
from utils.agent_tracer import AgentTracer
from utils.trace_logger import TraceLogger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — Phase 1: process a single source into teaching units
# ---------------------------------------------------------------------------

SOURCE_SYSTEM_PROMPT = """You are a STEM curriculum planner. Your job is to read raw extracted content from a single source and produce a compact teaching plan — a structured reference package for a teaching agent.

CRITICAL: You are NOT the teacher. Do not explain concepts, build intuition, or write teaching narratives. Extract and organize what is already in the source. The teaching agent will do the actual teaching from the content you provide.

---

## STEP 1: Identify logical sections using the markdown structure

The content uses page markers like "## Page N" or "# Page N: <title>" and sub-headings.

FIRST — skip these pages entirely, do not create units for them:
- Course title, institution name, term, instructor info, OpenCourseWare/license slides
- Table of contents, index, bibliography pages
- Any page whose entire content is administrative (not STEM subject matter)

THEN — group the remaining pages into units:
- Group consecutive pages that belong to the same topic into ONE unit.
- Sub-headings within a section → list them as subtopics[], NOT as separate units.
- Hard limit: never more than 1 unit per page. Never more than 5 units per source.
- For lecture slides (sparse pages with one concept per slide): these MUST be merged aggressively.
  Ask yourself: "are these slides all part of teaching the same big idea?" If yes → one unit.
  Example: slides on Force Particles, Matter Particles, Higgs Boson, Elementary Particle Overview, Standard Model Timeline → these are ALL about the Standard Model of particle physics → merge into ONE unit "Fundamental Particles and the Standard Model".
  Example: slides on Composite Particles, Hadrons, Mesons, Baryons, Nuclei → all about nuclear structure → merge into ONE unit "Composite Particles and Nuclear Structure".
  Result for a 9-page lecture: 2–3 units maximum, not 8.
- For textbook content (dense pages): target 1 unit per 2–4 pages.

## STEP 2: For each unit, extract — do not explain

### content field
- Copy key technical sentences verbatim or near-verbatim from the source.
- Include: definitions, equation context, experimental setups, key numerical values and constants.
- Do NOT write: intuitive hooks, analogies, "imagine that…", or any teaching narrative.
- Length: 300–600 words. Prioritize density over completeness.

### equations
- Extract every equation from the pages this unit covers.
- Define every variable with its physical meaning and units.

### figures
For each figure or diagram referenced in the content:
- Include the figure number/reference (e.g. "Figure 3-4")
- Include the full caption exactly as it appears in the source
- Include the full Image Description block if present — these contain axis labels, curve descriptions, and key observations that the teacher needs since they cannot see the actual image
- Format: "Figure 3-4: <caption> | Description: <image description text>"

### examples
For each worked example:
- Include the full example number and title (e.g. "Example 3-1: How Big Is a Star?")
- Copy the complete problem statement verbatim with all given values
- Copy the final answer verbatim with units
- Do not re-solve or summarise the steps — just problem + answer

### practice_problems
- Include the problem number and page reference (e.g. "Problem 3-13 (page 143)")
- Copy the problem statement verbatim if it appears in the content
- If only a reference exists, list it as-is

### subtopics
- List the sub-headings or distinct sub-concepts within this unit.
- These are what the teaching agent will cover within the lesson.

---

## OUTPUT FORMAT

Output ONLY a valid JSON object — no markdown fences, no explanation:

{
  "source_id": "<the source name provided>",
  "subject": "<STEM subject and sub-field, e.g. 'Modern Physics — Blackbody Radiation'>",
  "units": [
    {
      "order_id": <integer, 1-based position of this unit in the teaching sequence for this source>,
      "unit_id": "<snake_case section-level id — e.g. 'blackbody_radiation', NOT 'stefan_boltzmann_law'>",
      "title": "<section-level title covering all subtopics>",
      "depends_on": ["<unit_id of prerequisite unit, if any>"],
      "subtopics": ["<sub-heading or sub-concept within this unit>"],
      "page_range": [<start_page_int>, <end_page_int>],
      "equations": [
        {
          "latex": "<exact LaTeX from source>",
          "variables": { "<symbol>": "<meaning with units>" }
        }
      ],
      "figures": [
        {
          "ref": "<e.g. Figure 3-4>",
          "caption": "<full caption from source>",
          "description": "<full Image Description text — axes, curves, key observations>"
        }
      ],
      "examples": [
        {
          "ref": "<e.g. Example 3-1: How Big Is a Star?>",
          "problem": "<full problem statement verbatim with all given values>",
          "answer": "<final answer verbatim with units>"
        }
      ],
      "practice_problems": [
        {
          "ref": "<e.g. Problem 3-13 (page 143)>",
          "problem": "<problem statement verbatim if available in content, else omit this field>"
        }
      ],
      "content": "<300-600 words of verbatim/near-verbatim key technical content from the source — definitions, equation derivation context, experimental results, key constants. NO teaching narrative.>"
    }
  ]
}"""

# ---------------------------------------------------------------------------
# System prompt — Phase 2: combine all sources into final learning path
# ---------------------------------------------------------------------------

COMBINE_SYSTEM_PROMPT = """You are a STEM curriculum planner. You have received a list of unit IDs from multiple sources. Your job is to arrange them into a coherent global learning path and write a student overview.

## Rules

1. PRESERVE WITHIN-SOURCE ORDER
   Units from the same source must stay in their original order.

2. RESPECT CROSS-SOURCE DEPENDENCIES
   If a unit from source B depends on a unit from source A, source A's unit must come first.

3. GROUP BY SUBJECT
   Do not interleave units from unrelated STEM domains. Complete one subject domain before transitioning to another unless a dependency requires otherwise.

4. STUDENT OVERVIEW
   Write a clear, friendly 2-4 sentence paragraph: what subjects/topics will be covered, in what order, and why that order makes sense pedagogically.

## Output Format

Output ONLY a valid JSON object — no markdown fences, no explanation:

{
  "student_overview": "<2-4 sentence teaching roadmap for the student>",
  "final_learning_path": [
    "<unit_id>",
    "<unit_id>",
    ...
  ]
}

The final_learning_path must list ALL unit_ids across ALL sources in the correct teaching order."""

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class PlannerAgent:
    """
    Transforms pre-extracted content.json into a complete teaching blueprint.

    Two-phase pipeline:
      Phase 1: process each source independently → structured units (one LLM call per source)
      Phase 2: combine all sources → global learning path (one LLM call)
    """

    CONTENT_CAP = 80_000       # max chars of source content (Gemini 1M-token context)
    CHUNK_SIZE   = 20_000      # max chars per LLM call — Gemini handles large inputs well
    MAX_TOKENS_SOURCE = 16000  # units are compact now — no detailed_explanation bloat
    MAX_TOKENS_COMBINE = 65536 # combine needs full budget for large unit lists
    LLM_TIMEOUT  = 300         # seconds — Gemini can take longer for large outputs

    def __init__(self, llm_client: GeminiLLMClient):
        self.llm = llm_client
        self.tracer = AgentTracer()
        self.trace_logger = TraceLogger()

    # ── Public API ────────────────────────────────────────────────────────────

    def plan(self, content_json_path: str) -> dict:
        """
        Build a complete teaching plan from content.json.

        Args:
            content_json_path: Path to content.json file.
                               Each entry: { "source": "<id>", "content": "<text>" }

        Returns:
            Teaching plan as a JSON-serializable dict.
        """
        entries = self._load_content_json(content_json_path)
        if not entries:
            return {"error": "No content entries found in content.json."}

        logger.info(f"PlannerAgent.plan: processing {len(entries)} source(s)")
        self.tracer.start_turn(f"plan({content_json_path})")

        # Phase 1: process each source independently
        source_results = []
        for entry in entries:
            source_id = entry.get("source", f"source_{len(source_results) + 1}")
            content = entry.get("content", "")
            if not content.strip():
                logger.warning(f"Skipping empty source: {source_id}")
                continue
            result = self._process_source(source_id, content)
            if "error" not in result:
                source_results.append(result)
            else:
                logger.error(f"Failed to process source '{source_id}': {result}")

        if not source_results:
            trace = self.tracer.end_turn("error: all sources failed")
            self.trace_logger.save(trace)
            return {"error": "All sources failed to process."}

        # Phase 2: combine into final plan
        final_plan = self._combine_sources(source_results)

        trace = self.tracer.end_turn(json.dumps(final_plan)[:500])
        self.trace_logger.save(trace)

        return final_plan

    # ── Phase 1: per-source processing ───────────────────────────────────────

    def _process_source(self, source_id: str, content: str) -> dict:
        """
        Process a single source into structured teaching units.
        Splits large content into CHUNK_SIZE chunks so each LLM call
        stays well within the output token ceiling.
        Returns merged { source_id, subject, units: [...] }.
        """
        capped = self._sanitize_content(content[:self.CONTENT_CAP])
        chunks = self._split_chunks(capped)
        total_units: List[dict] = []
        subject = ""
        chunk_count = len(chunks)

        logger.info(
            f"  Processing source '{source_id}' "
            f"({len(capped)} chars, {chunk_count} chunk(s))"
        )

        for i, chunk in enumerate(chunks):
            chunk_label = f"chunk {i+1}/{chunk_count}"
            prior_ids = [u["unit_id"] for u in total_units]
            prior_note = (
                f"\nUnits extracted so far (for depends_on references): "
                f"{prior_ids}\n" if prior_ids else ""
            )

            user_message = (
                f"Source ID: {source_id} ({chunk_label})\n"
                f"{prior_note}"
                f"--- BEGIN CONTENT ---\n{chunk}\n--- END CONTENT ---\n\n"
                f"Extract all teaching units from this content chunk following the schema. "
                f"Process sequentially. Set depends_on using unit_ids listed above if applicable."
            )

            messages = [
                {"role": "system", "content": SOURCE_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]

            chunk_units = []
            for attempt in range(1, 3):  # up to 2 attempts per chunk
                t0 = time.time()
                try:
                    response = self.llm.chat(
                        messages=messages,
                        tools=None,
                        max_tokens=self.MAX_TOKENS_SOURCE,
                        temperature=0.1,
                        timeout=self.LLM_TIMEOUT,
                        response_format={"type": "json_object"},
                    )
                    elapsed_ms = (time.time() - t0) * 1000
                    raw = response["choices"][0]["message"].get("content", "")
                    result = self._parse_json(raw)

                    if "error" in result:
                        logger.warning(
                            f"  JSON parse failed for '{source_id}' {chunk_label} "
                            f"(attempt {attempt}/2). Raw: {raw[:100]}"
                        )
                        self.tracer.log_tool_call(
                            tool_name="process_source",
                            arguments={"source_id": source_id, "chunk": chunk_label,
                                       "attempt": attempt},
                            response=f"PARSE ERROR. Raw: {raw[:200]}",
                            elapsed_ms=elapsed_ms,
                        )
                        continue  # retry

                    chunk_units = result.get("units", [])
                    if not subject:
                        subject = result.get("subject", "")

                    self.tracer.log_tool_call(
                        tool_name="process_source",
                        arguments={"source_id": source_id, "chunk": chunk_label,
                                   "chars": len(chunk)},
                        response=f"{len(chunk_units)} unit(s). Preview: {raw[:200]}",
                        elapsed_ms=elapsed_ms,
                    )
                    logger.info(
                        f"  '{source_id}' {chunk_label}: "
                        f"{len(chunk_units)} unit(s) in {elapsed_ms:.0f}ms"
                    )
                    break  # success

                except Exception as e:
                    elapsed_ms = (time.time() - t0) * 1000
                    self.tracer.log_tool_call(
                        tool_name="process_source",
                        arguments={"source_id": source_id, "chunk": chunk_label,
                                   "attempt": attempt},
                        response=f"ERROR: {e}",
                        elapsed_ms=elapsed_ms,
                    )
                    logger.error(
                        f"  LLM call failed for '{source_id}' {chunk_label} "
                        f"(attempt {attempt}/2): {e}"
                    )

            total_units.extend(chunk_units)

        if not total_units:
            return {"error": f"No units extracted for source '{source_id}'"}

        # Reassign order_id sequentially across all chunks (each chunk restarts from 1)
        for i, unit in enumerate(total_units):
            unit["order_id"] = i + 1

        logger.info(f"  Source '{source_id}': {len(total_units)} total unit(s)")
        return {"source_id": source_id, "subject": subject, "units": total_units}

    # ── Phase 2: combine sources ──────────────────────────────────────────────

    def _combine_sources(self, source_results: List[dict]) -> dict:
        """
        Combine per-source results into a global learning path.
        One LLM call — COMBINE_SYSTEM_PROMPT + all source JSONs.
        """
        # Send only unit IDs per source — not the full unit data.
        # The LLM only needs to order IDs and write an overview; Python assembles the rest.
        sources_index = [
            {
                "source_id": s["source_id"],
                "subject": s["subject"],
                "unit_ids": [u["unit_id"] for u in s.get("units", [])],
            }
            for s in source_results
        ]
        sources_payload = json.dumps(sources_index, indent=2)

        user_message = (
            f"Here are the unit IDs from {len(source_results)} source(s):\n\n"
            f"{sources_payload}\n\n"
            f"Produce a student_overview and final_learning_path ordering all unit_ids correctly."
        )

        messages = [
            {"role": "system", "content": COMBINE_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        logger.info(f"  Combining {len(source_results)} source(s) into final plan")

        t0 = time.time()
        try:
            response = self.llm.chat(
                messages=messages,
                tools=None,
                max_tokens=4000,  # only overview + list of IDs needed
                temperature=0.1,
                timeout=self.LLM_TIMEOUT,
                response_format={"type": "json_object"},
            )
            elapsed_ms = (time.time() - t0) * 1000
            raw = response["choices"][0]["message"].get("content", "")
            llm_result = self._parse_json(raw)

            if "error" in llm_result:
                logger.error("  JSON parse failed for combine phase")
                self.tracer.log_tool_call(
                    tool_name="combine_sources",
                    arguments={"source_count": len(source_results)},
                    response=f"PARSE ERROR: {raw[:200]}",
                    elapsed_ms=elapsed_ms,
                )
                return llm_result

            # Assemble full plan in Python — don't ask the LLM to repeat the units
            final = {
                "student_overview": llm_result.get("student_overview", ""),
                "sources": source_results,
                "final_learning_path": llm_result.get("final_learning_path", []),
            }
            path_len = len(final["final_learning_path"])
            self.tracer.log_tool_call(
                tool_name="combine_sources",
                arguments={"source_count": len(source_results)},
                response=f"{path_len} unit(s) in final path. Preview: {raw[:300]}",
                elapsed_ms=elapsed_ms,
            )
            logger.info(f"  Final plan: {path_len} unit(s) in {elapsed_ms:.0f}ms")
            return final
        except Exception as e:
            elapsed_ms = (time.time() - t0) * 1000
            self.tracer.log_tool_call(
                tool_name="combine_sources",
                arguments={"source_count": len(source_results)},
                response=f"ERROR: {e}",
                elapsed_ms=elapsed_ms,
            )
            logger.error(f"  Combine LLM call failed: {e}")
            return {"error": str(e)}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_content(content: str) -> str:
        """
        Clean source content before sending to the LLM.

        Two problems in raw PDF/PPTX text that cause Gemini to produce invalid JSON:
        1. Control characters (\\x00-\\x1f except \\t and \\n) — e.g. \\x0c form-feeds
           from PDF page breaks. Gemini copies them into JSON strings verbatim,
           where they are illegal.
        2. Bare LaTeX backslashes (\\sigma, \\frac, \\lambda, etc.) — Gemini copies
           these into JSON strings as single backslashes, producing invalid \\escape
           sequences. Pre-doubling them (\\sigma → \\\\sigma) means Gemini sees and
           reproduces \\\\sigma, which is a valid JSON-escaped backslash + text.
        """
        import re as _re
        # Step 1: strip control chars except tab and newline
        content = _re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', ' ', content)
        # Step 2: double any backslash so Gemini reproduces it escaped in JSON
        content = content.replace('\\', '\\\\')
        return content

    def _split_chunks(self, content: str) -> List[str]:
        """
        Split content into chunks of at most CHUNK_SIZE chars, breaking at
        page boundaries (--- ## Page N ---) where possible.
        """
        if len(content) <= self.CHUNK_SIZE:
            return [content]

        # Split at page-boundary markers
        import re as _re
        parts = _re.split(r'(?=---\s*\n## Page \d+)', content)
        chunks, current = [], ""
        for part in parts:
            if len(current) + len(part) <= self.CHUNK_SIZE:
                current += part
            else:
                if current:
                    chunks.append(current)
                # If a single part exceeds CHUNK_SIZE, hard-split it
                while len(part) > self.CHUNK_SIZE:
                    chunks.append(part[:self.CHUNK_SIZE])
                    part = part[self.CHUNK_SIZE:]
                current = part
        if current:
            chunks.append(current)
        return chunks

    def _load_content_json(self, path: str) -> List[dict]:
        """Load and parse content.json. Returns list of {source, content} dicts."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                logger.error(f"content.json must be a JSON array, got {type(data)}")
                return []
            return data
        except FileNotFoundError:
            logger.error(f"content.json not found at: {path}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"content.json is not valid JSON: {e}")
            return []

    @staticmethod
    def _fix_latex_escapes(raw: str) -> str:
        """
        Fix unescaped LaTeX backslashes inside JSON string values.

        LLMs output LaTeX like \\sigma, \\frac, \\, inside JSON strings without
        doubling the backslash. This walks the raw text char-by-char, and within
        JSON string regions, replaces any \\ not followed by a valid JSON escape
        character with \\\\ (a proper JSON-escaped backslash).

        Valid JSON escapes after backslash: " \\ / b f n r t u
        """
        VALID_AFTER_BS = set('"\\/ bfnrtu')
        result = []
        i = 0
        n = len(raw)
        while i < n:
            ch = raw[i]
            if ch != '"':
                result.append(ch)
                i += 1
                continue
            # Entering a JSON string
            result.append('"')
            i += 1
            while i < n:
                c = raw[i]
                if c == '\\' and i + 1 < n:
                    nxt = raw[i + 1]
                    if nxt in VALID_AFTER_BS:
                        if nxt == 'u' and i + 5 < n and all(
                            h in '0123456789abcdefABCDEF' for h in raw[i+2:i+6]
                        ):
                            result.append(raw[i:i+6])
                            i += 6
                        else:
                            result.append(c)
                            result.append(nxt)
                            i += 2
                    else:
                        # Invalid escape — double the backslash
                        result.append('\\\\')
                        i += 1
                elif c == '"':
                    result.append('"')
                    i += 1
                    break
                else:
                    result.append(c)
                    i += 1
        return ''.join(result)

    def _parse_json(self, raw: str) -> dict:
        """Extract and parse JSON from LLM response. Falls back to error dict."""
        if not raw:
            return {"error": "Empty response from LLM."}

        # Try direct parse first (fastest path)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try strict=False to allow literal control characters (tabs/newlines in strings)
        try:
            return json.loads(raw, strict=False)
        except json.JSONDecodeError:
            pass

        # Fix unescaped LaTeX backslashes inside JSON string values and retry
        fixed = self._fix_latex_escapes(raw)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # Both fixes combined
        try:
            return json.loads(fixed, strict=False)
        except json.JSONDecodeError:
            pass
        except json.JSONDecodeError:
            pass

        # Try to strip markdown fences
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            try:
                return json.loads(self._fix_latex_escapes(match.group(1)))
            except json.JSONDecodeError:
                pass

        # Try first { ... } block
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(self._fix_latex_escapes(raw[start:end + 1]))
            except json.JSONDecodeError:
                pass

        # Log the error from the fixed attempt for diagnosis
        try:
            json.loads(self._fix_latex_escapes(raw))
        except json.JSONDecodeError as _e:
            fixed_tmp = self._fix_latex_escapes(raw)
            logger.error(
                f"Failed to parse JSON. Fix-pass error at char {_e.pos}: {_e.msg}. "
                f"Context: {repr(fixed_tmp[max(0,_e.pos-40):_e.pos+40])}"
            )
        else:
            logger.error(f"Failed to parse JSON. Raw (first 200 chars): {raw[:200]}")
        return {
            "error": "Could not parse JSON response.",
            "raw_response": raw[:500],
        }
