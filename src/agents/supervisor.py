"""
Supervisor — LLM-based orchestrator that integrates all agents under one roof.

Architecture:
  - LLM agent (gpt-4o) with its own tool-calling loop
  - Routes student messages to the right agent via 5 tools
  - Sees structured summaries from each agent, never raw content
  - Manages the full pipeline: extract → plan → teach

Tools:
  extract_content(request)  → DocumentAgent extracts, returns summary
  create_plan()             → PlannerAgent builds plan, returns summary
  start_teaching()          → PlanDrivenTutor starts, returns welcome
  forward_to_tutor(message) → forwards to active tutor, returns response
  get_teaching_status()     → session progress from tutor registry

Usage:
    from agents.supervisor import Supervisor

    supervisor = Supervisor(llm_client, gemini_client, session_dir)
    welcome = supervisor.upload(file_paths)    # chains extract → plan → teach
    response = supervisor.chat(student_msg)    # routes to tutor or handles meta
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.document_agent import DocumentAgent
from agents.planner_agent import PlannerAgent
from agents.plan_driven_tutor import PlanDrivenTutor
from utils.llm_client import LLMClient
from utils.gemini_client import GeminiLLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Supervisor — the top-level orchestrator for an AI study tutor.

You manage a pipeline of specialized agents via tools. You NEVER teach directly.

## YOUR TOOLS

1. extract_content(request) — Have the Document Agent extract content from uploaded files.
   Pass the student's study request so extraction is targeted.

2. create_plan() — Have the Planner Agent build a structured teaching plan from extracted content.

3. start_teaching() — Initialize the teaching session. Shows the learning path to the student.

4. forward_to_tutor(message) — Forward a student message to the active tutor.
   Use for ALL lesson interactions.

5. get_teaching_status() — Check what's been taught, what's next, student performance.
   Use when the student asks about progress or when you need context for a decision.

## ROUTING RULES

**After file upload:**
Chain: extract_content → create_plan → start_teaching. Do all three in sequence.

**During active teaching (most messages):**
Call forward_to_tutor immediately. Do NOT interpret, summarize, or modify the student's message.
The tutor handles: teaching, problems, navigation between units, unit completion.

**Exceptions — handle yourself (don't forward):**
- "Upload new documents" / "add another file" → tell student to use the upload button
- "What have we covered?" / "How am I doing?" → call get_teaching_status, summarize for them
- "Start over" / "reset" → acknowledge, tell them to use the reset button
- "I'm done for today" → call get_teaching_status, give a session summary

**After all units complete:**
The forward_to_tutor result will include ALL_UNITS_COMPLETE. Summarize the full session and offer:
upload new docs, revisit any topic, or end.

## RESPONSE STYLE
- When forwarding to tutor: pass through the tutor's response WITHOUT adding your own commentary.
  The tutor's response IS the response to the student — do not wrap it, prefix it, or summarize it.
- When handling meta-requests yourself: be brief and helpful.
- Never teach, explain concepts, or answer subject questions yourself.
"""

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "extract_content",
            "description": (
                "Extract content from uploaded documents. "
                "Pass the student's study request so extraction is targeted. "
                "Returns a summary of what was extracted (file names, pages, char counts)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": (
                            "Student's study request, e.g. 'chapter 3', "
                            "'section 3-2', 'all lectures', 'everything'"
                        ),
                    }
                },
                "required": ["request"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_plan",
            "description": (
                "Build a teaching plan from extracted content. "
                "Returns plan summary: subject, unit titles, dependencies, teaching order."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_teaching",
            "description": (
                "Start the teaching session. Creates the tutor and returns "
                "the welcome message with the learning path for the student."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forward_to_tutor",
            "description": (
                "Forward a student message to the active teaching session. "
                "Returns the tutor's full response. Use for ALL lesson interactions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The student's message, forwarded exactly as-is",
                    }
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_teaching_status",
            "description": (
                "Get current teaching progress: units completed, current unit, "
                "student struggles, problems solved, what's next."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# ---------------------------------------------------------------------------
# Supervisor agent
# ---------------------------------------------------------------------------


class Supervisor:
    """
    LLM-based orchestrator. Routes student messages to DocumentAgent,
    PlannerAgent, or PlanDrivenTutor via tool calls. Holds structured
    summaries of each stage, never raw content.
    """

    MAX_ITERATIONS = 10

    def __init__(
        self,
        llm_client: LLMClient,
        gemini_client: GeminiLLMClient,
        session_dir: str,
        teaching_llm_client: Optional[LLMClient] = None,
    ):
        self.llm = llm_client
        self.teaching_llm = teaching_llm_client or llm_client  # separate model for teaching
        self.document_agent = DocumentAgent(llm_client)
        self.planner_agent = PlannerAgent(gemini_client)
        self.tutor: Optional[PlanDrivenTutor] = None

        self.session_dir = session_dir
        self.file_paths: List[str] = []
        self.user_request: str = ""
        self.content_json_path = os.path.join(session_dir, "content.json")
        self.plan_json_path = os.path.join(session_dir, "plan_output.json")

        # Supervisor's own conversation (system + routing turns)
        self.conversation: List[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        # Pipeline flags — no content, just booleans
        self.has_content = False
        self.has_plan = False
        self.teaching_active = False

        # Activity log — timestamped entries for UI inspection
        self.activity_log: List[str] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def upload(
        self,
        file_paths: List[str],
        request: str = "extract all content for studying",
    ) -> str:
        """
        Called by server on file upload. Injects context into supervisor
        conversation and runs the tool loop (extract → plan → start).
        """
        self.file_paths = file_paths
        file_names = [Path(p).name for p in file_paths]

        user_msg = (
            f"Student uploaded these files: {file_names}. "
            f'Their request: "{request}". '
            f"Start the pipeline: extract → plan → teach."
        )
        self.conversation.append({"role": "user", "content": user_msg})
        return self._run_loop()

    def chat(self, message: str) -> str:
        """Called by server on student chat message."""
        self.conversation.append({"role": "user", "content": message})
        self._trim_conversation()
        return self._run_loop()

    # ── Step-by-step pipeline (for UIs that want status updates) ─────────────

    def step_extract(self, file_paths: List[str], request: str) -> str:
        """Phase 1: extract → content.json. Returns summary."""
        self.file_paths = file_paths
        self.user_request = request  # persisted so step_plan can scope correctly
        self._log("Supervisor", "Pipeline phase 1 — extract", f"request: \"{request}\"")
        return self._tool_extract(request)

    def step_plan(self) -> str:
        """Phase 2: plan → plan_output.json. Returns summary."""
        self._log("Supervisor", "Pipeline phase 2 — plan")
        return self._tool_create_plan()

    def step_start_teaching(self) -> str:
        """Phase 3: start teaching. Returns welcome message."""
        self._log("Supervisor", "Pipeline phase 3 — start teaching")
        result = self._tool_start_teaching()
        prefix = "TEACHING_STARTED\n"
        return result[len(prefix):] if result.startswith(prefix) else result

    def reset(self):
        """Reset all state."""
        self.tutor = None
        self.has_content = False
        self.has_plan = False
        self.teaching_active = False
        self.file_paths = []
        self.user_request = ""
        self.conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.activity_log = []

    # ── Activity logging ──────────────────────────────────────────────────────

    def _log(self, agent: str, action: str, detail: str = "") -> None:
        """Append a timestamped entry to the activity log."""
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] **{agent}** — {action}"
        if detail:
            entry += f"\n    ↳ {detail}"
        self.activity_log.append(entry)
        logger.info(f"[LOG] {agent}: {action}")

    # ── Tool-calling loop ─────────────────────────────────────────────────────

    def _run_loop(self) -> str:
        """
        Standard tool-calling loop. LLM decides which tool to call,
        we execute it, feed the result back, repeat until text response.
        """
        for _ in range(self.MAX_ITERATIONS):
            t0 = time.time()
            response = self.llm.chat(
                self.conversation,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=4000,
                temperature=0.1,
            )
            elapsed = (time.time() - t0) * 1000
            msg = response["choices"][0]["message"]
            self.conversation.append(msg)

            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    self._log("Supervisor", f"Calling tool `{name}`", str(args)[:120])
                    t_tool = time.time()
                    result = self._execute_tool(name, args)
                    tool_ms = (time.time() - t_tool) * 1000
                    self._log("Supervisor", f"Tool `{name}` done ({tool_ms:.0f}ms)", str(result)[:200])

                    self.conversation.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": (
                                result
                                if isinstance(result, str)
                                else json.dumps(result)
                            ),
                        }
                    )
                continue

            # Text response — return to student
            return msg.get("content", "")

        return "Something went wrong with routing. Please try again."

    # ── Tool dispatch ─────────────────────────────────────────────────────────

    def _execute_tool(self, name: str, args: dict) -> str:
        dispatch = {
            "extract_content": self._tool_extract,
            "create_plan": self._tool_create_plan,
            "start_teaching": self._tool_start_teaching,
            "forward_to_tutor": self._tool_forward,
            "get_teaching_status": self._tool_get_status,
        }
        handler = dispatch.get(name)
        if not handler:
            return f"Unknown tool: {name}"
        try:
            return handler(**args)
        except Exception as e:
            logger.error(f"[SUPERVISOR] Tool {name} failed: {e}", exc_info=True)
            return f"Error in {name}: {e}"

    # ── Tool implementations ──────────────────────────────────────────────────

    def _tool_extract(self, request: str) -> str:
        """Run DocumentAgent. Save content.json. Return summary."""
        file_names = [Path(p).name for p in self.file_paths]
        self._log("DocumentAgent", f"Extracting content", f"files={file_names}, request=\"{request}\"")

        raw = self.document_agent.extract(self.file_paths, request)

        entries = self._parse_to_content_entries(raw)
        with open(self.content_json_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)

        # Build rich summary for supervisor awareness
        lines = [f'Extraction complete for request: "{request}"']
        for entry in entries:
            source = entry.get("source", "unknown")
            content = entry.get("content", "")
            char_count = len(content)
            page_range = self._detect_page_range(content)
            page_info = f", pages {page_range}" if page_range else ""
            lines.append(f"  - {source}{page_info}: {char_count:,} chars")
            self._log("DocumentAgent", f"Extracted {source}", f"{char_count:,} chars{page_info}")

        lines.append(f"Total: {len(entries)} source(s). Call create_plan next.")
        self._log("DocumentAgent", "Done", f"Saved → content.json ({len(entries)} source(s))")
        self.has_content = True
        return "\n".join(lines)

    def _tool_create_plan(self) -> str:
        """Run PlannerAgent. Save plan_output.json. Return summary."""
        if not self.has_content:
            return "Error: No content extracted yet. Call extract_content first."

        self._log("PlannerAgent", "Building teaching plan from content.json")
        plan = self.planner_agent.plan(self.content_json_path)
        if "error" in plan:
            self._log("PlannerAgent", "Failed", plan["error"])
            return f"Planning failed: {plan['error']}"

        with open(self.plan_json_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)

        # Build rich summary: subject, unit titles, deps, order
        overview = plan.get("student_overview", "")
        path = plan.get("final_learning_path", [])

        lines = [
            "Plan created successfully.",
            f"Overview: {overview}",
            f"Learning path ({len(path)} units):",
        ]

        for src in plan.get("sources", []):
            subject = src.get("subject", "Unknown")
            lines.append(f"\nSubject: {subject}")
            for unit in src.get("units", []):
                title = unit.get("title", "?")
                deps = unit.get("depends_on", [])
                subtopics = unit.get("subtopics", [])
                n_examples = len(unit.get("examples", []))
                n_practice = len(unit.get("practice_problems", []))
                dep_str = f" (requires: {deps})" if deps else ""
                lines.append(
                    f"  {unit.get('order_id', '?')}. {title}{dep_str} — "
                    f"{len(subtopics)} subtopics, "
                    f"{n_examples} examples, {n_practice} practice problems"
                )
                self._log("PlannerAgent", f"Unit: {title}", f"{len(subtopics)} subtopics, {n_examples} examples{dep_str}")

        lines.append(f"\nTeaching order: {' → '.join(path)}")
        lines.append("Call start_teaching next.")
        self._log("PlannerAgent", "Done", f"Saved → plan_output.json ({len(path)} units)")
        self.has_plan = True
        return "\n".join(lines)

    def _tool_start_teaching(self) -> str:
        """Create PlanDrivenTutor and return welcome message."""
        if not self.has_plan:
            return "Error: No plan created yet. Call create_plan first."

        self._log("PlanDrivenTutor", "Initialising — loading plan_output.json")
        self.tutor = PlanDrivenTutor(self.teaching_llm, self.plan_json_path)
        welcome = self.tutor.start()
        self.teaching_active = True
        self._log("PlanDrivenTutor", "Ready", f"Learning path: {self.tutor.learning_path}")
        return f"TEACHING_STARTED\n{welcome}"

    def _tool_forward(self, message: str) -> str:
        """Forward message to PlanDrivenTutor. Return response + progress."""
        if not self.tutor or not self.teaching_active:
            return "Error: No active teaching session. Upload documents first."

        current_idx = self.tutor.current_index
        total = len(self.tutor.learning_path)
        current_unit_id = self.tutor.learning_path[current_idx] if current_idx < total else "?"
        current_title = self.tutor.unit_map.get(current_unit_id, {}).get("title", "?")

        self._log("TeachingAgent", f"Responding to student", f"unit: {current_title}")
        response = self.tutor.chat(message)

        # Check completion
        if self.tutor.current_index >= len(self.tutor.learning_path):
            self.teaching_active = False
            self._log("PlanDrivenTutor", "All units complete — session done")
            session_summary = self._build_session_summary()
            return (
                f"ALL_UNITS_COMPLETE\n\n"
                f"Session summary:\n{session_summary}\n\n"
                f"Tutor's final message:\n{response}"
            )

        completed_count = len(self.tutor.taught_sections_registry)
        new_title = self.tutor.unit_map.get(
            self.tutor.learning_path[self.tutor.current_index], {}
        ).get("title", "?")
        if self.tutor.current_index != current_idx:
            self._log("PlanDrivenTutor", f"Advanced to unit {self.tutor.current_index + 1}", new_title)

        progress = (
            f"[Progress: {completed_count}/{total} complete, "
            f"current: {current_title}]"
        )
        return f"{progress}\n{response}"

    def _tool_get_status(self) -> str:
        """Return session progress from tutor's registry."""
        if not self.tutor:
            return "No teaching session active."
        self._log("Supervisor", "Status check requested")
        return self._build_session_summary()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_session_summary(self) -> str:
        """Build structured summary from PlanDrivenTutor's registry."""
        lines = []
        total = len(self.tutor.learning_path)
        completed = len(self.tutor.taught_sections_registry)
        current_idx = self.tutor.current_index

        lines.append(f"Progress: {completed}/{total} units completed")

        # Completed units with details
        if self.tutor.taught_sections_registry:
            lines.append("\nCompleted units:")
            for unit_id, reg in self.tutor.taught_sections_registry.items():
                title = reg.get("title", unit_id)
                summary = reg.get("summary", "")
                struggles = reg.get("struggles", "none")
                problems = reg.get("problems_solved", "none")
                tone = reg.get("tone", "unknown")
                lines.append(f"  ✓ {title}")
                if summary:
                    lines.append(f"    Summary: {summary}")
                if struggles and struggles != "none":
                    lines.append(f"    Struggles: {struggles}")
                if problems and problems != "none":
                    lines.append(f"    Problems solved: {problems}")
                lines.append(f"    Confidence: {tone}")

        # Remaining units
        remaining = self.tutor.learning_path[current_idx:]
        if remaining:
            lines.append("\nRemaining units:")
            for uid in remaining:
                title = self.tutor.unit_map.get(uid, {}).get("title", uid)
                lines.append(f"  ○ {title}")

        return "\n".join(lines)

    def _parse_to_content_entries(self, raw_text: str) -> List[dict]:
        """
        Parse DocumentAgent output into [{source, content}] for PlannerAgent.

        DocumentAgent labels sections with [SOURCE: filename | pages X-Y | type: pdf].
        Split on these markers. Fallback: treat entire output as single source.
        """
        pattern = r"\[SOURCE:\s*([^|\]]+?)(?:\s*\|[^\]]*)?\]"
        parts = re.split(pattern, raw_text)

        entries = []
        if len(parts) < 2:
            # No SOURCE markers — single source
            source_name = (
                Path(self.file_paths[0]).stem if self.file_paths else "document"
            )
            entries.append({"source": source_name, "content": raw_text.strip()})
        else:
            # parts[0] = text before first marker (usually empty)
            # parts[1] = source name, parts[2] = content, etc.
            for i in range(1, len(parts), 2):
                source = parts[i].strip()
                content = parts[i + 1].strip() if i + 1 < len(parts) else ""
                if content:
                    entries.append({"source": source, "content": content})

        return entries

    @staticmethod
    def _detect_page_range(content: str) -> str:
        """Try to detect page range from ## Page N markers in content."""
        pages = re.findall(r"## Page (\d+)", content)
        if pages:
            nums = sorted(set(int(p) for p in pages))
            return f"{nums[0]}-{nums[-1]}"
        return ""

    def _trim_conversation(self, max_turns: int = 50):
        """Keep system prompt + most recent turns."""
        if len(self.conversation) > max_turns + 1:
            self.conversation = (
                [self.conversation[0]] + self.conversation[-max_turns:]
            )
