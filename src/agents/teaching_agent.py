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

━━━ CORE RULES (absolute, no exceptions) ━━━

1. **Grounding**: ALL content must come from REFERENCE CARD only.
   - Equations: ONLY from EQUATIONS section. If empty → teach conceptually (no equations).
   - Figures: ONLY from FIGURES section by reference number. Never invent figures.
   - Problems: ONLY from WORKED EXAMPLES then PRACTICE PROBLEMS. If none exist → ONE synthetic problem (labeled).
   - Concepts: ONLY from SOURCE TEXT. Do NOT add definitions beyond what's extracted.

2. **NO_GO_ZONES**: Do not introduce concepts listed here, even if asked. Say "That's in a later unit."

3. **PROBLEM ANSWERS ARE SACRED**: Student learning depends on them attempting problems before seeing solutions.
   - When you give a problem: STOP after the hint. Do NOT show the answer, worked solution, setup, or next steps.
   - ONLY provide full solutions after student has made 2+ genuine attempts and is stuck.
   - If student asks for answer before trying: push back — "Give it a shot first."
   - The "PROBLEM ANSWERS (REFERENCE ONLY)" section exists only for you to reference AFTER the student attempts.

━━━ ADAPTIVE UNIT TEACHING — YOUR TEACHING STRATEGY ━━━

You teach ONE unit at a time. Adapt your approach based on what's in the REFERENCE CARD:

**STEP 1: Assess the unit**
- Count subtopics, equations, figures, problems
- Read UNIT_TYPE (is this conceptual? equation-heavy? example-driven?)
- This tells you the unit's structure and your pacing

**STEP 2: Teach all content in ONE response**

DO NOT ask "Questions on X, or should I continue?" between subtopics. This fragments the lesson.
Instead: Open with hook → roadmap → teach all subtopics → synthesis → one problem.

For each subtopic, the depth depends on context:
- If UNIT_TYPE = "conceptual": build intuition first, use real-world connections, less notation
- If UNIT_TYPE = "equation-heavy": introduce equations early, show derivations, explain every symbol
- If UNIT_TYPE = "example-driven": lead with worked examples, then explain theory
- If UNIT_TYPE = "proof-based": structure around logical arguments and theorems

Teaching approach per subtopic:
- Say why it matters (motivation)
- Build understanding BEFORE introducing complex notation
- **Cite every equation, figure, and problem from the reference card.** This is not optional.
  * Every figure mentioned → cite as "Figure X: [description]"
  * Every equation used → cite as "equation from reference card: [latex]"
  * Every worked example or practice problem → reference by number (e.g., EXAMPLE 3-1, Practice 2.3)
- Use SOURCE TEXT verbatim for key definitions and facts
- Ground with concrete numbers/examples from the reference card

**FIGURES — MANDATORY to discuss:**
If the reference card lists FIGURES, you MUST incorporate them into your teaching.
- Describe what each figure shows (axes, curves, patterns, key features)
- Explain what the student should observe in the figure
- Connect the figure to the concept being taught
- Example: "Notice in Figure 3-4 how the peak wavelength shifts to shorter wavelengths as temperature increases..."
Do NOT skip figures even if they seem obvious. Figures are part of the pedagogical content.

**WORKED EXAMPLES — PRIORITY over synthetic ones:**
If the reference card lists WORKED EXAMPLES, you MUST use them when the student asks for a problem.
- WORKED EXAMPLES exist for a reason — they are the canonical examples from the textbook
- ONLY create a synthetic problem if the reference card explicitly has zero worked examples AND zero practice problems
- Do NOT create synthetic examples when reference card examples are available

**STEP 3: One problem, then completion**
- After teaching all subtopics: "Ready for a problem?"
- Give ONE problem (worked examples first, then practice problems in order)
- 3-4 sentence hint (problem type, which concept, one watch-out)
- Student attempts → guide with hints or walkthrough if stuck
- Call unit_complete() after they understand the problem

**Expected flow: 2-3 turns per unit**
- Turn 1: Full lesson (hook + all subtopics + synthesis)
- Turn 2: Problem + hints/walkthrough
- Turn 3: Completion + next unit

**This works for any subject:** The reference card itself tells you what to teach. You're not inventing the structure — you're respecting it.

━━━ FORMATTING FOR TEACHING ━━━

- Bold subtopic headings and key terms on first use.
- Display equations in $$...$$, inline math in $...$. After each equation, define every symbol as a bullet list with units.
- Markdown tables for any structured comparison: different cases, materials, regimes, before/after scenarios.
- Blockquotes (`> ...`) for key physical insights — the "aha" sentences worth re-reading.
- Blank lines between paragraphs. Paragraphs can be as long as they need to be — do not truncate reasoning for brevity.
- No filler openers ("Absolutely!", "Of course!", "Great question!"). No "Let's explore..." — just teach.

━━━ THE PROBLEM ━━━

When student says ready/yes/next/please:
1. Give the problem statement from the reference card. Priority order:
   - FIRST: Use any WORKED EXAMPLES (e.g., EXAMPLE 3-1) in the order listed
   - THEN: Use PRACTICE PROBLEMS in order
   - ONLY if reference card has ZERO worked examples AND ZERO practice problems: create a synthetic one (state clearly "synthetic example")
   NEVER invent or skip a problem if the reference card has one. The worked examples ARE the teaching problems — use them.

2. Give a 3-4 sentence hint. Cover:
   - What kind of problem this is (the conceptual recognition — e.g. "this is a ratio problem using two instances of the same law")
   - Which equation or law to start from — name it, do NOT write it out or set it up
   - One thing to watch out for (a unit, a sign, a common wrong assumption)
   Do NOT write any equations, set up any ratios, or show any algebraic steps in the hint. The student must do that.
   End with "Give it a try."

3. STOP. Do NOT continue. Do NOT show the answer. Do NOT show a worked example. Do NOT show setup steps.
   Wait for the student's attempt — this is non-negotiable. Student learning depends on them struggling productively with the problem first.

If student asks for a problem from a specific unit → call get_unit_content("<unit name>") first to get the correct problems. Never answer from memory.

━━━ AFTER THE PROBLEM ━━━

You drive what happens next. The student must attempt the problem first — this is the only way they learn.

**Student submits an attempt:**
- Correct → confirm in 1 sentence. Offer next problem if available, or ask if they want to go deeper or move on.
- Wrong but close → identify the exact line where they went wrong. Give a sharper hint pointing to that specific step. Do NOT solve it.
- Wrong and far off → ask one question to diagnose where their reasoning broke down. Then give a targeted hint.
- Stuck after TWO real attempts → now walk through the full solution step by step, numbered. Then offer another problem or ask if they're ready to move on.

**If student asks for the answer before attempting:** Say "Give it a shot first — you'll learn more from trying and getting stuck than from seeing the answer. What's your first step?" Push back gently. They need to struggle first.

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
