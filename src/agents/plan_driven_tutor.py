"""
PlanDrivenTutor — curriculum manager. Responds to tool calls from TeachingAgent.

Architecture:
  - chat() just calls teaching_agent.chat() — no proxying, no interception
  - Owns: JSON unit map, session registry, unit state
  - Exposes 3 tool implementations injected into TeachingAgent at construction:
      get_unit_content(description) → reference card + problems for any unit(s)
      unit_complete(summary)        → write registry, advance index, return next title
      get_session_log()             → LLM-written summaries of completed units
  - Never sees the teaching conversation
"""

import json
import logging
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.teaching_agent import TeachingAgent
from models.data_models import SubjectProfile

logger = logging.getLogger(__name__)


class PlanDrivenTutor:
    """
    Curriculum manager for plan_output.json.
    Student messages go directly to TeachingAgent — this class only
    answers tool calls and manages session state.
    """

    def __init__(self, llm_client, plan_path: str):
        with open(plan_path, encoding="utf-8") as f:
            self.plan: dict = json.load(f)

        self.llm = llm_client

        # Build unit_map: {unit_id: unit_dict}
        self.unit_map: Dict[str, dict] = {}
        for source in self.plan.get("sources", []):
            source_id = source.get("source_id", "")
            for unit in source.get("units", []):
                unit.setdefault("source_id", source_id)
                self.unit_map[unit["unit_id"]] = unit

        self.learning_path: List[str] = self.plan.get("final_learning_path", [])
        self.current_index: int = 0

        # Registry: LLM-written summary per completed unit
        self.taught_sections_registry: Dict[str, dict] = {}

        self.subject_profile: Optional[SubjectProfile] = self._detect_subject_profile()

        # Wire tool implementations into TeachingAgent
        self.teaching_agent = TeachingAgent(
            llm_client=llm_client,
            tools={
                "get_unit_content": self._tool_get_unit_content,
                "unit_complete":    self._tool_unit_complete,
                "get_session_log":  self._tool_get_session_log,
            },
            subject_profile=self.subject_profile,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> str:
        """Welcome message + kick off first unit."""
        overview = self.plan.get("student_overview", "")
        n = len(self.learning_path)

        lines = [overview, "", f"Here's your learning path ({n} units):"]
        for i, unit_id in enumerate(self.learning_path, start=1):
            unit = self.unit_map.get(unit_id, {})
            title = unit.get("title", unit_id)
            source = unit.get("source_id", "")
            lines.append(f"  {i}. {title}  [{source}]")

        first_title = ""
        if self.learning_path:
            first_unit = self.unit_map.get(self.learning_path[0], {})
            first_title = first_unit.get("title", "")

        lines += ["", f"Let's start with **{first_title}** — are you ready?"]
        return "\n".join(lines)

    def chat(self, message: str) -> str:
        """
        All student messages go directly to TeachingAgent.
        plan_driven_tutor only answers tool calls — it never intercepts messages.
        """
        # First message (student said "ready" / "yes" to start): kick off the lesson.
        # Ignore what the student said — they confirmed they want to start, so start.
        if not self.teaching_agent.conversation_history:
            unit_id = self.learning_path[self.current_index]
            unit = self.unit_map[unit_id]
            reference_card = self._build_reference_card(unit)
            unit_index = self._build_unit_index()
            return self.teaching_agent.start(
                unit_title=unit.get("title", ""),
                reference_card=reference_card,
                unit_index=unit_index,
            )

        return self.teaching_agent.chat(message)

    # ── Tool implementations (called by TeachingAgent) ────────────────────────

    def _tool_get_unit_content(self, description: str) -> str:
        """
        Fetch curriculum content for any unit, or all problems from completed units.

        Two modes based on description:
        - "all completed" → problems + examples from every completed unit
        - Any topic name → reference card + problems for that specific unit
        """
        if description.strip().lower() == "all completed":
            return self._get_all_completed_problems()

        # Find matching unit
        target = self._find_unit_by_description(description)
        if target == -1:
            return f"No unit found matching '{description}' in the learning path."

        unit_id = self.learning_path[target]
        unit = self.unit_map[unit_id]
        self.current_index = target

        reference_card = self._build_reference_card(unit)
        unit_index = self._build_unit_index()
        already_taught = unit_id in self.taught_sections_registry

        # Update teaching agent's system prompt with the new unit's content
        self.teaching_agent.update_system_prompt(
            unit_title=unit.get("title", ""),
            reference_card=reference_card,
            unit_index=unit_index,
        )

        status = "REVISIT" if already_taught else "FRESH"
        registry_note = ""
        if already_taught:
            reg = self.taught_sections_registry[unit_id]
            registry_note = (
                f"\nPREVIOUS SESSION NOTE: {reg.get('summary', '')}"
                f"\nStudent struggled with: {reg.get('struggles', 'nothing noted')}"
                f"\nProblems solved: {reg.get('problems_solved', 'none')}"
                f"\nStudent confidence: {reg.get('tone', 'unknown')}"
                f"\nDo NOT re-teach the full lesson. Brief recap (1-2 sentences), "
                f"then ask what they want to clarify or practice."
            )

        # Always include raw problems so the LLM has actual text, not just metadata
        raw_problems = self._extract_raw_problems(unit)

        return (
            f"UNIT: {unit.get('title', '')}\n"
            f"STATUS: {status}{registry_note}\n\n"
            f"REFERENCE CARD:\n{reference_card}\n\n"
            f"RAW PROBLEMS (use these exact texts when giving problems to student):\n{raw_problems}"
        )

    def _tool_unit_complete(self, summary: str) -> str:
        """
        Mark current unit complete. Write LLM summary to registry. Advance index.
        Returns the next unit title so teaching agent can name it to the student.
        """
        done_id = (
            self.learning_path[self.current_index]
            if self.current_index < len(self.learning_path)
            else ""
        )

        if done_id and done_id not in self.taught_sections_registry:
            unit = self.unit_map.get(done_id, {})
            self.taught_sections_registry[done_id] = self._build_registry_entry(
                unit, summary
            )

        self.current_index += 1

        if self.current_index >= len(self.learning_path):
            return "ALL_UNITS_COMPLETE"

        next_unit = self.unit_map.get(self.learning_path[self.current_index], {})
        next_title = next_unit.get("title", "")

        # Pre-load next unit into teaching agent system prompt
        reference_card = self._build_reference_card(next_unit)
        unit_index = self._build_unit_index()
        self.teaching_agent.update_system_prompt(
            unit_title=next_title,
            reference_card=reference_card,
            unit_index=unit_index,
        )

        return f"NEXT_UNIT: {next_title}"

    def _tool_get_session_log(self) -> str:
        """Return LLM-written summaries of all completed units."""
        if not self.taught_sections_registry:
            return "No units completed yet this session."

        lines = ["SESSION LOG — units completed so far:"]
        for reg in self.taught_sections_registry.values():
            entry = f"\n✓ {reg['title']}"
            if reg.get("summary"):
                entry += f"\n  {reg['summary']}"
            if reg.get("struggles") and reg["struggles"] != "none":
                entry += f"\n  Student struggled with: {reg['struggles']}"
            if reg.get("problems_solved") and reg["problems_solved"] != "none":
                entry += f"\n  Problems solved: {reg['problems_solved']}"
            if reg.get("tone"):
                entry += f"\n  Confidence: {reg['tone']}"
            lines.append(entry)
        return "\n".join(lines)

    # ── Content helpers ───────────────────────────────────────────────────────

    def _extract_raw_problems(self, unit: dict) -> str:
        """
        Return the full verbatim text of every example and practice problem
        in a unit (WITHOUT answers). This is what the teaching agent uses when
        giving problems to the student — exact text from the book, no solutions.
        """
        lines = []
        examples = unit.get("examples", [])
        for ex in examples:
            lines.append(f"[Example {ex.get('ref', '')}]")
            if ex.get("problem"):
                lines.append(f"Problem: {ex['problem']}")
            # NOTE: Answers not included here to prevent premature disclosure
            lines.append("")

        practice = unit.get("practice_problems", [])
        for pp in practice:
            lines.append(f"[Practice {pp.get('ref', '')}]")
            if pp.get("problem"):
                lines.append(f"Problem: {pp['problem']}")
            # NOTE: Answers not included here to prevent premature disclosure
            lines.append("")

        return "\n".join(lines) if lines else "No problems in reference card for this unit."

    def _get_all_completed_problems(self) -> str:
        """Collect all examples and practice problems from completed units."""
        if not self.taught_sections_registry:
            return "No units completed yet — no practice problems available."

        lines = ["PRACTICE PROBLEMS from completed units:\n"]
        for unit_id in self.taught_sections_registry:
            unit = self.unit_map.get(unit_id, {})
            title = unit.get("title", unit_id)
            lines.append(f"━━ {title} ━━")
            lines.append(self._extract_raw_problems(unit))

        return "\n".join(lines)

    def _build_reference_card(self, unit: dict) -> str:
        """Format unit JSON into pedagogically ordered reference card."""
        sections: List[str] = []

        subtopics = unit.get("subtopics", [])
        if subtopics:
            lines = ["SUBTOPICS TO TEACH (work through these one at a time):"]
            for i, s in enumerate(subtopics, start=1):
                lines.append(f"  {i}. {s}")
            sections.append("\n".join(lines))

        equations = unit.get("equations", [])
        if equations:
            lines = [
                "EQUATIONS (introduce each ONLY after building intuition for its subtopic):"
            ]
            for eq in equations:
                latex = eq.get("latex", "")
                variables = eq.get("variables", {})
                lines.append(f"  - ${latex}$")
                if variables:
                    var_str = "; ".join(f"{sym}: {desc}" for sym, desc in variables.items())
                    lines.append(f"    Variables: {var_str}")
            sections.append("\n".join(lines))

        figures = unit.get("figures", [])
        if figures:
            lines = ["FIGURES (cite by reference number to build intuition):"]
            for fig in figures:
                lines.append(f"  - {fig.get('ref', '')}: {fig.get('caption', '')}")
                if fig.get("description"):
                    lines.append(f"    {fig['description']}")
            sections.append("\n".join(lines))

        examples = unit.get("examples", [])
        if examples:
            lines = ["WORKED EXAMPLES (show problem + hint, then wait for student attempt):"]
            for ex in examples:
                lines.append(f"  - {ex.get('ref', '')}")
                if ex.get("problem"):
                    lines.append(f"    Problem: {ex['problem']}")
                # NOTE: Answers are NOT shown here. See PROBLEM ANSWERS section below.
            sections.append("\n".join(lines))

        practice = unit.get("practice_problems", [])
        if practice:
            lines = ["PRACTICE PROBLEMS (show these, but only provide answers after student attempts):"]
            for pp in practice:
                entry = f"  - {pp.get('ref', '')}"
                if pp.get("problem"):
                    entry += f": {pp['problem']}"
                lines.append(entry)
            sections.append("\n".join(lines))

        takeaways = unit.get("key_takeaways", [])
        if takeaways:
            lines = ["KEY TAKEAWAYS (what the student must know after this unit):"]
            for t in takeaways:
                lines.append(f"  • {t}")
            sections.append("\n".join(lines))

        no_go = unit.get("no_go_zones", [])
        if no_go:
            lines = ["NO_GO_ZONES (do NOT introduce these — they belong to later units):"]
            for z in no_go:
                lines.append(f"  ✗ {z}")
            sections.append("\n".join(lines))

        # PROBLEM ANSWERS — for reference only after student attempts
        examples = unit.get("examples", [])
        practice = unit.get("practice_problems", [])
        has_answers = any(ex.get("answer") for ex in examples) or any(pp.get("answer") for pp in practice)

        if has_answers:
            lines = [
                "━━━ PROBLEM ANSWERS (REFERENCE ONLY) ━━━",
                "",
                "⚠️  DO NOT SHOW THESE UNLESS:",
                "  - Student has attempted the problem and is stuck after 2+ tries, OR",
                "  - Student explicitly asks for the full solution/walkthrough",
                "",
                "Show answers only to help, not to shortcut learning.",
                ""
            ]

            examples = unit.get("examples", [])
            if examples and any(ex.get("answer") for ex in examples):
                lines.append("WORKED EXAMPLE ANSWERS:")
                for ex in examples:
                    if ex.get("answer"):
                        lines.append(f"  [{ex.get('ref', '')}]")
                        lines.append(f"  {ex['answer']}")
                        lines.append("")

            practice = unit.get("practice_problems", [])
            if practice and any(pp.get("answer") for pp in practice):
                lines.append("PRACTICE PROBLEM ANSWERS:")
                for pp in practice:
                    if pp.get("answer"):
                        lines.append(f"  [{pp.get('ref', '')}]")
                        lines.append(f"  {pp['answer']}")
                        lines.append("")

            sections.append("\n".join(lines))

        content = unit.get("content", "").strip()
        if content:
            sections.append(
                "SOURCE TEXT (authoritative — draw from this for depth and exact wording):\n"
                + content
            )

        return "\n\n".join(sections)

    def _build_unit_index(self) -> str:
        """Learning path titles only — no raw content."""
        lines = []
        for i, unit_id in enumerate(self.learning_path, start=1):
            unit = self.unit_map.get(unit_id, {})
            title = unit.get("title", unit_id)
            done = " ✓" if unit_id in self.taught_sections_registry else ""
            current = " ← current" if i - 1 == self.current_index else ""
            lines.append(f"  {i}. {title}{done}{current}")
        return "\n".join(lines)

    def _build_registry_entry(self, unit: dict, summary: str) -> dict:
        """
        LLM call: read the teaching conversation and write a structured memory entry.
        The summary param is what the teaching agent wrote when it called unit_complete.
        We enrich it by reading the actual conversation.
        """
        title = unit.get("title", "")

        history = self.teaching_agent.conversation_history
        dialogue = "\n".join(
            f"{m['role'].upper()}: {m['content'][:400]}"
            for m in history
            if m.get("role") in ("user", "assistant") and m.get("content")
        )[-4000:]

        if not dialogue:
            return {
                "title": title,
                "summary": summary,
                "struggles": "none",
                "problems_solved": "none",
                "tone": "unknown",
            }

        prompt = f"""A tutoring session on "{title}" just ended.

Teaching agent's summary: {summary}

Conversation excerpt:
{dialogue}

Write a memory entry in this exact format:

SUMMARY: <2-3 sentences: what was taught, key equations or concepts covered>
STRUGGLES: <concepts the student found confusing, or "none">
PROBLEMS_SOLVED: <which problems were attempted and whether correct, or "none">
TONE: <student confidence: confident / uncertain / mixed>"""

        try:
            raw = self.llm.get_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.2,
            )
        except Exception as e:
            logger.warning(f"Registry LLM call failed: {e}")
            return {
                "title": title,
                "summary": summary,
                "struggles": "none",
                "problems_solved": "none",
                "tone": "unknown",
            }

        entry = {
            "title": title,
            "summary": summary,
            "struggles": "none",
            "problems_solved": "none",
            "tone": "unknown",
        }
        for line in raw.splitlines():
            if line.startswith("SUMMARY:"):
                entry["summary"] = line.replace("SUMMARY:", "").strip()
            elif line.startswith("STRUGGLES:"):
                entry["struggles"] = line.replace("STRUGGLES:", "").strip()
            elif line.startswith("PROBLEMS_SOLVED:"):
                entry["problems_solved"] = line.replace("PROBLEMS_SOLVED:", "").strip()
            elif line.startswith("TONE:"):
                entry["tone"] = line.replace("TONE:", "").strip()
        return entry

    def _find_unit_by_description(self, description: str) -> int:
        """Find best matching unit index (0-based). Returns -1 if no match."""
        desc_lower = description.lower()
        desc_words = [w for w in desc_lower.split() if len(w) > 3]

        best_idx = -1
        best_score = 0

        for i, unit_id in enumerate(self.learning_path):
            unit = self.unit_map.get(unit_id, {})
            title = unit.get("title", "").lower()

            if desc_lower == title:
                return i

            score = sum(1 for w in desc_words if w in title)
            if score > best_score:
                best_score = score
                best_idx = i

        return best_idx if best_score > 0 else -1

    def _detect_subject_profile(self) -> Optional[SubjectProfile]:
        sources = self.plan.get("sources", [])
        if not sources:
            return None
        subject_str = sources[0].get("subject", "")
        if not subject_str:
            return None

        parts = [p.strip() for p in subject_str.replace("\u2014", "-").split("-", 1)]
        subject = parts[0] if parts else subject_str
        sub_field = parts[1] if len(parts) > 1 else ""

        sl = subject.lower()
        if any(k in sl for k in ["physics", "mechanics", "quantum", "thermodynamics"]):
            style = "equation-heavy"
        elif any(k in sl for k in ["math", "algebra", "calculus", "analysis"]):
            style = "proof-based"
        elif any(k in sl for k in ["chemistry", "organic"]):
            style = "reaction-based"
        elif any(k in sl for k in ["computer", "algorithm", "programming"]):
            style = "code-focused"
        else:
            style = "conceptual"

        return SubjectProfile(
            subject=subject,
            sub_field=sub_field,
            level="intermediate",
            material_type="textbook",
            teaching_style_hints=style,
        )
