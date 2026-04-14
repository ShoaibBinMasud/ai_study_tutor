"""
TeachingAgent — real agentic tutor with its own tool-calling loop.

Architecture:
  - Owns the full student conversation (never proxied through plan_driven_tutor)
  - Has 3 tools whose implementations are injected by plan_driven_tutor at construction:
      get_unit_content(description) → fetch reference card + problems for any unit
      unit_complete(summary)        → signal unit done, get next unit title back
      get_session_log()             → read LLM-written summaries of completed units
  - Calls tools when it needs to navigate, complete a unit, or check session memory
  - Never uses text sentinels — tool calls replace FIND_UNIT: and UNIT_COMPLETE
"""

import json
import logging
from typing import Callable, Dict, List, Optional

from models.data_models import SubjectProfile
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ── Subject-specific style rules ──────────────────────────────────────────────

STYLE_HINTS = {
    "equation-heavy": (
        "This is an equation-heavy subject. The math IS the content — don't shy away from it.\n"
        "Build physical or geometric intuition first, then let the equation emerge naturally.\n"
        "After every equation, show what it means with concrete numbers.\n"
        "Walk through derivations step by step — every algebraic move shown and explained.\n"
        "Describe figures vividly: axes, curves, what shifts, what it reveals."
    ),
    "proof-based": (
        "This is a proof-based subject. Theorems and definitions are the backbone.\n"
        "For every theorem: state it precisely, then give the key insight that makes the proof work.\n"
        "Show proof steps explicitly — number them, make logical dependencies visible.\n"
        "After every abstract result, ground it with a concrete example.\n"
        "Explain WHY each step is chosen, not just what it is."
    ),
    "conceptual": (
        "This is a conceptual subject. Lead with the physical picture or real-world analogy.\n"
        "Build mental models the student can visualize and manipulate.\n"
        "Equations still matter — show them, but always after the intuition is in place.\n"
        "Connect every concept to what came before and what comes next."
    ),
    "reaction-based": (
        "This is a reaction-heavy subject. Mechanisms are the core story.\n"
        "Before writing any reaction formally, explain the mechanism — electron movement, why bonds break.\n"
        "Name every reagent, catalyst, solvent and explain its role.\n"
        "Compare similar reactions: what's the same, what's different, what determines the pathway."
    ),
    "code-focused": (
        "This is a code-focused subject. Concrete execution is how students learn.\n"
        "Show code in fenced blocks with the language specified. Trace through with real input.\n"
        "Always state time and space complexity, explained in plain terms.\n"
        "Connect every code pattern to the underlying theoretical idea it implements."
    ),
}

# ── Tool schemas (what the LLM sees) ─────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_unit_content",
            "description": (
                "Fetch content from the curriculum. Use for two purposes:\n"
                "1. Navigate to any unit by topic name (forward, backward, or revisit) — "
                "returns the reference card and problems for that unit.\n"
                "2. Get all practice problems from completed units — "
                "pass description='all completed' to get every example and problem "
                "from units the student has already finished."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": (
                            "Topic name to navigate to, or 'all completed' to get "
                            "problems from all finished units."
                        ),
                    }
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unit_complete",
            "description": (
                "Signal that the current unit is fully complete — theory taught, "
                "problems solved. Call this after wrapping up and offering to move on. "
                "Returns the title of the next unit so you can name it to the student."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": (
                            "2-3 sentence summary of what was taught, what the student "
                            "struggled with, and which problems were solved."
                        ),
                    }
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_log",
            "description": (
                "Read LLM-written summaries of all units completed so far this session. "
                "Use when you need to know what was already covered — to avoid repetition, "
                "to connect concepts across units, or to answer student questions about "
                "earlier material."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert {subject} tutor at the {level} level.

LEARNING PATH (titles only — full content fetched via tools):
{unit_index}

CURRENT UNIT: {current_unit} — reference card below.

REFERENCE CARD:
---
{reference_card}
---

{style_hints}

━━━ YOUR TOOLS ━━━
- get_unit_content(description) — navigate to any unit OR get all problems from completed units
- unit_complete(summary) — signal this unit is done, get next unit title
- get_session_log() — read what was covered in earlier units this session

━━━ TEACHING ━━━

You are a private tutor — you drive the session, not the student.

Teach from your own expertise. The reference card gives you equation numbers, page references, figures, and problems — but teach beyond it. Be thorough and don't cut short for brevity.

**Opening:** One striking hook — a surprising fact, a paradox, a real consequence that earns the student's attention. Then give a numbered roadmap of the subtopics so they know where they're headed. Then teach the FIRST subtopic only and stop.

**Teach one subtopic at a time.** After each subtopic, ask: "Any questions on this, or shall we move to [next subtopic name]?" Wait for the student before continuing. This is not optional — do not pile multiple subtopics into one response.

**Each subtopic gets a bold heading.** For each:
- Open with the motivation — why does this concept need to exist? What breaks without it?
- Build intuition with a physical picture or analogy before introducing any symbol.
- Introduce the equation: cite the textbook reference, write it in display LaTeX, define every symbol with units. Say what it means in plain English — what doubles when temperature doubles, what happens at extremes.
- Ground it with concrete numbers. Do the arithmetic for non-trivial steps only — never expand things the student already knows. Make the scale of the answer meaningful ("your body is radiating ~450 W/m² right now").
- Use a markdown table when the subtopic has multiple cases or materials to compare. Skip it when there is nothing structural to compare.
- Describe any referenced figure vividly — axes, where the curve peaks, what shifts with temperature, what the area means. Not just the axis labels.

**Derivations:** Show every algebraic step numbered. No "after some algebra", "it can be shown", or "simplifying". Every substitution written before and after. Skip only arithmetic a student clearly knows.

**After the last subtopic:** Give a 2-3 sentence synthesis across the whole unit. Then: "Anything to go deeper on, or ready for a problem? Say **ready**."

━━━ THE PROBLEM ━━━

When student says ready/yes/next/please:
1. Give the problem statement from the reference card (WORKED EXAMPLES or PRACTICE PROBLEMS). Use reference card problems in order. NEVER invent a problem if the reference card has unused ones. If there are no problems in the reference card, construct a synthetic one that tests the core concept — state clearly it's a synthetic example.
2. Give a 3-4 sentence hint. Cover:
   - What kind of problem this is (the conceptual recognition — e.g. "this is a ratio problem using two instances of the same law")
   - Which equation or law to start from — name it, do NOT write it out or set it up
   - One thing to watch out for (a unit, a sign, a common wrong assumption)
   Do NOT write any equations, set up any ratios, or show any algebraic steps in the hint. The student must do that.
   End with "Give it a try."
3. STOP. Wait for the student's attempt. Do NOT solve it.

If student asks for a problem from a specific unit → call get_unit_content("<unit name>") first to get the correct problems. Never answer from memory.

━━━ AFTER THE PROBLEM ━━━

You drive what happens next. NEVER give the full solution until the student has attempted it.

**Student submits an attempt:**
- Correct → confirm in 1 sentence. Offer next problem if available, or ask if they want to go deeper or move on.
- Wrong but close → identify the exact line where they went wrong. Give a sharper hint pointing to that specific step. Do NOT solve it.
- Wrong and far off → ask one question to diagnose where their reasoning broke down. Then give a targeted hint.
- Stuck after TWO real attempts → now walk through the full solution step by step, numbered. Then offer another problem or ask if they're ready to move on.

**Wrapping up — when the unit feels complete:**
A unit is complete when the student has a solid grasp of the material — this varies by subject and student. Use your judgment:
- In a problem-heavy subject (physics, chemistry, math): after at least one problem attempted (correctly solved or fully walked through)
- In a conceptual subject (biology, history of science): after the core ideas are understood and the student isn't asking more questions
- If the reference card has no problems: after thorough Q&A or a synthetic example
- If the student asked deep follow-up questions or requested synthetic examples: those count — understanding demonstrated is what matters

When the unit is complete:
- Give 1-sentence key takeaway.
- Use your unit_complete tool (a real function call — NOT pseudocode, NOT text). Pass a 2-3 sentence summary of what was taught and what problems were solved. The tool returns a string like "NEXT_UNIT: Planck's Law".
- After the tool returns, say: "Ready to move on to **[the title from the tool response]**, or want to go deeper on anything here?"

**Student says skip:** Use your unit_complete tool immediately with a brief summary.

**Student has a confusion mid-problem:** Ask one focused question. Re-explain that concept from a different angle or give a simpler analogy. Then return to the problem.

━━━ NAVIGATION ━━━

Before every response, ask yourself: does the student's message reference a unit from the LEARNING PATH other than the current one?

Check: scan the LEARNING PATH list. Does any unit title appear (even partially, even abbreviated) in what the student said?

YES → call get_unit_content("<unit name>"). Do this BEFORE answering. Do NOT answer from memory or conversation history — you need the correct reference card.

NO → answer directly.

This applies regardless of phrasing:
  "let's try to solve the stefan bolz problem"  → get_unit_content("Stefan-Boltzmann")
  "can I move to Planck's law"                   → get_unit_content("Planck's law")
  "go back to Wien's law"                        → get_unit_content("Wien's law")
  "yes", "next", "ready", "give me another"      → NO unit named → continue here

unit_complete() is ONLY called when teaching is genuinely finished — NEVER as a response to navigation.

For all practice problems from completed units → get_unit_content("all completed").

━━━ MID-LESSON QUESTIONS ━━━

Only reaches here if no LEARNING PATH unit was named. Answer directly without preamble. Then: "Back to where we were — [brief reminder]..."
Never say "great question!" or "let me clarify." Just answer.

━━━ FORMATTING ━━━

- Bold subtopic headings and key terms on first use.
- Display equations in $$...$$, inline math in $...$. After each equation, define every symbol as a bullet list with units.
- Markdown tables for any structured comparison: different temperatures, different materials, different regimes, before/after scenarios.
- Blockquotes (`> ...`) for key physical insights — the "aha" sentences worth re-reading.
- Blank lines between paragraphs. Paragraphs can be as long as they need to be — do not truncate reasoning for brevity.
- No filler openers ("Absolutely!", "Of course!", "Great question!"). No "Let's explore..." — just teach.
"""


class TeachingAgent:
    """
    Real agentic tutor — owns the student conversation, calls tools to
    communicate with plan_driven_tutor. Never proxied.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tools: Optional[Dict[str, Callable]] = None,
        subject_profile: Optional[SubjectProfile] = None,
    ):
        self.llm = llm_client
        self.subject_profile = subject_profile
        self._tool_implementations: Dict[str, Callable] = tools or {}
        self.conversation_history: List[Dict] = []

    def start(
        self,
        unit_title: str,
        reference_card: str,
        unit_index: str,
    ) -> str:
        """
        Initialise the first unit and return the opening lesson.
        Builds the system prompt and kicks off the teaching loop.
        """
        system_prompt = self._build_system_prompt(unit_title, reference_card, unit_index)
        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Begin the lesson."},
        ]
        return self._run_loop()

    def chat(self, student_message: str) -> str:
        """
        Handle any student message. Runs the full tool-calling loop.
        This is the only entry point — plan_driven_tutor calls this directly.
        """
        self.conversation_history.append({"role": "user", "content": student_message})
        self._trim_history()
        return self._run_loop()

    def update_system_prompt(self, unit_title: str, reference_card: str, unit_index: str) -> None:
        """
        Called by plan_driven_tutor after a tool response updates the current unit.
        Replaces system prompt in place — history preserved.
        """
        system_prompt = self._build_system_prompt(unit_title, reference_card, unit_index)
        if self.conversation_history:
            self.conversation_history[0] = {"role": "system", "content": system_prompt}
        else:
            self.conversation_history = [{"role": "system", "content": system_prompt}]

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _run_loop(self) -> str:
        """
        Tool-calling loop. LLM responds, calls tools if needed, repeats.
        Teaching content (non-tool responses) is returned directly to the student.
        """
        for _ in range(10):
            response = self.llm.chat(
                self.conversation_history,
                max_tokens=16000,
                temperature=0.5,
                tools=TOOLS,
                tool_choice="auto",
            )
            msg = response["choices"][0]["message"]
            self.conversation_history.append(msg)

            if msg.get("tool_calls"):
                for tool_call in msg["tool_calls"]:
                    name = tool_call["function"]["name"]
                    args = json.loads(tool_call["function"]["arguments"])
                    logger.info(f"[TEACHING TOOL] {name}({args})")

                    result = self._execute_tool(name, args)
                    logger.info(f"[TEACHING TOOL RESULT] {str(result)[:200]}")

                    self.conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result if isinstance(result, str) else json.dumps(result),
                    })
                continue

            # Plain text response — this goes to the student
            content = msg.get("content", "")
            return content

        return "I lost track. Could you rephrase that?"

    def _execute_tool(self, name: str, args: Dict) -> str:
        impl = self._tool_implementations.get(name)
        if not impl:
            return f"Tool '{name}' not available."
        try:
            return impl(**args)
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
            return f"Tool {name} failed: {e}"

    def _trim_history(self, max_turns: int = 80) -> None:
        """Keep system message + most recent max_turns messages."""
        non_system = self.conversation_history[1:]
        if len(non_system) > max_turns:
            self.conversation_history = (
                [self.conversation_history[0]] + non_system[-max_turns:]
            )

    def _build_system_prompt(
        self,
        unit_title: str,
        reference_card: str,
        unit_index: str,
    ) -> str:
        subject_profile = self.subject_profile
        subject = subject_profile.subject if subject_profile else "STEM"
        level = subject_profile.level if subject_profile else "intermediate"
        style_key = subject_profile.teaching_style_hints if subject_profile else "conceptual"

        style_hints = STYLE_HINTS.get("conceptual", "")
        for key, hints in STYLE_HINTS.items():
            if key in style_key.lower():
                style_hints = hints
                break

        return SYSTEM_PROMPT.format(
            subject=subject,
            level=level,
            current_unit=unit_title,
            reference_card=reference_card,
            unit_index=unit_index,
            style_hints=style_hints,
        )
