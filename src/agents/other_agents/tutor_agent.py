"""
TutorAgent — fully agentic STEM tutor.

One main agent that remembers everything and decides everything.
Delegates to focused subagents with clean isolated context.

Flow:
  user_message
      ↓
  TutorAgent LLM (full session context + tools)
      ↓ decides what to do
  Tool calls → subagents/content layer
      ↓ results feed back
  LLM decides next step
      ↓
  Response to student
"""

import json
import logging
from typing import Any, Dict, List, Optional

from agents.teaching_agent import TeachingAgent
# from agents.quiz_agent import QuizAgent
# from agents.merit_evaluator import MeritEvaluator
# from agents.diagnostic_agent import DiagnosticAgent
# from agents.visualization_agent import VisualizationAgent
from content.chunker import ContentChunker
from content.concept_mapper import ConceptMapper
from content.file_manager import FileManager
from models.data_models import AdaptationLevel, TeachingUnit
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ── Tool definitions (what the LLM can call) ─────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "show_toc",
            "description": "Show the table of contents of all loaded study materials. Use to understand what's available before teaching.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_chapter",
            "description": (
                "Use when student wants to learn a full chapter. "
                "Reads the table of contents to find all sections in the chapter — "
                "no page content is loaded yet. Builds a section queue and shows the student the plan. "
                "Teaching then proceeds section-by-section using the existing flow."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_id": {
                        "type": "string",
                        "description": "Chapter identifier e.g. '1', '2', 'chapter-3'",
                    }
                },
                "required": ["chapter_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_section",
            "description": (
                "Load a section from the study materials. Extracts the content, "
                "identifies key concepts and prerequisites, and prepares it for teaching. "
                "Always call this before teaching a section."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section_id": {
                        "type": "string",
                        "description": "Section identifier e.g. '1-2', 'ch3', '2.4'",
                    }
                },
                "required": ["section_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "teach_chunk",
            "description": (
                "Delegate teaching the current chunk to the teaching subagent. "
                "The subagent has clean focused context — only the chunk content. "
                "Call this to start teaching or move to the next chunk."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forward_to_teaching_agent",
            "description": (
                "Forward the student's response to the teaching subagent during an active teaching session. "
                "Use this whenever the student responds while teaching is in progress. "
                "The subagent maintains its own conversation and will signal CHUNK_COMPLETE when done."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_message": {
                        "type": "string",
                        "description": "The student's response",
                    }
                },
                "required": ["student_message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_quiz",
            "description": (
                "Generate and run a quiz on the section just taught. "
                "Call after all chunks are complete to assess understanding."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_diagnostic",
            "description": (
                "Run a diagnostic to assess what the student already knows. "
                "Use for exam prep or when student says they have a test soon."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Topics to assess",
                    }
                },
                "required": ["topics"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_topic",
            "description": "Search loaded materials for sections covering a specific concept or topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Concept or topic to find"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_progress",
            "description": "Get current session progress: merit score, sections covered, quiz results.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert STEM tutor with full memory of this session. You make all decisions — what to teach, when to check prerequisites, how to respond. You have a set of tools and use them intelligently based on context.

MATERIALS LOADED:
{materials_summary}

SESSION MEMORY:
{session_state}

━━━ TOOLS ━━━
- show_toc() — see what's in the uploaded materials
- load_chapter(chapter_id) — read chapter TOC, build section queue, no page content yet
- load_section(section_id) — extract content + reference card for a section
- teach_chunk() — hand off to teaching subagent to start/continue a lesson
- forward_to_teaching_agent(student_message) — forward student's reply during active teaching
- run_quiz() — generate quiz questions + show summary (chapter mode only; single-section quiz fires automatically)
- run_diagnostic(topics) — assess what student already knows
- search_topic(query) — find sections covering a concept
- get_progress() — current merit score, pace, sections done

━━━ HOW TO BEHAVE ━━━

You are a private tutor who remembers everything from this session. Use that memory:

SECTION ALREADY STUDIED: If the student asks for a section that's already in "Sections taught this session", don't re-teach it. Say something like "We already covered that — is there a part that wasn't clear, or a specific concept you want to revisit?" Only restart from scratch if they explicitly ask.

PREREQUISITE CHECK: After load_section(), always ask yourself: does this student need a background check before I start?
- Default is YES — ask one focused question ("Before we start, are you comfortable with X?")
- Skip ONLY when: it's mid-chapter (they just finished the previous section), or they explicitly said they know the material
- If they jumped from chapter 1 to chapter 5, or came back after a quiz, definitely ask
This makes the session feel like a real tutor, not a lecture machine.

TEACHING A SINGLE SECTION:
1. load_section()
2. Ask one prereq question (unless mid-chapter) — wait for the student's answer
3. Then call teach_chunk()
4. Quiz fires automatically after teaching ends — do NOT call run_quiz() yourself

TEACHING A WHOLE CHAPTER:
1. load_chapter() → confirm plan with student
2. load_section() → teach_chunk() for the first section
3. After UNIT_COMPLETE: announce section done, ask if ready for next
4. load_section() → teach_chunk() for next section — no prereq check between sections
5. After all sections: call run_quiz() for the chapter quiz

DURING ACTIVE TEACHING:
- forward_to_teaching_agent() handles all student replies — yes, no, questions, confusion
- UNIT_COMPLETE means the section is done
- For chapter mode: move to next section
- For single section: quiz fires automatically, nothing to do

QUESTIONS OUTSIDE TEACHING: Answer directly and concisely. Use what you know about the loaded material.

STUDENT WANTS A DIFFERENT SECTION (outside teaching): If the student asks to go to, practice, or get a problem from a section that is NOT the current one — call search_topic() to find it, then load_section() and teach_chunk(). Do NOT just answer from memory. Do NOT say "type start". Load it and teach it.

EXAM PREP / "I have a test": run_diagnostic() first, then build a teaching plan from the results.

FILES JUST UPLOADED (__FILES_LOADED__): Call show_toc(), then write a natural 2-3 sentence welcome. What subject, what level, what's covered. End with: what would you like to start with?

━━━ TONE ━━━
Direct. No filler phrases. Don't narrate your actions. Be the expert in the room.
"""

# ── Main Agent ────────────────────────────────────────────────────────────────

class TutorAgent:
    """
    Fully agentic STEM tutor.
    One agent with full memory. Delegates focused tasks to subagents.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.llm = LLMClient(api_key=api_key, model=model)

        # Content layer
        self.file_manager = FileManager(self.llm)
        self.concept_mapper = ConceptMapper(self.llm)
        self.chunker = ContentChunker()

        # Subagents — each gets clean isolated context
        self.teaching_agent = TeachingAgent(self.llm)
        self.quiz_agent = QuizAgent(self.llm)
        self.merit_evaluator = MeritEvaluator(self.llm)
        self.diagnostic_agent = DiagnosticAgent(self.llm)
        self.viz_agent = VisualizationAgent(self.llm)

        # Main agent conversation (full memory)
        self.history: List[Dict] = []
        self._pending_image: Optional[str] = None  # set by _tool_teach_chunk, read by chat()

        # Session state the main agent tracks
        self.session = {
            "loaded_section_id": None,
            "loaded_section": None,
            "chunks": [],
            "chunk_responses": [],  # pre-generated teaching content per chunk
            "chunk_images": [],     # optional visualization path per chunk (None if not applicable)
            "chunk_index": 0,
            "teaching_active": False,
            "all_chunks_done": False,
            "active_quiz": None,
            "quiz_question_index": 0,
            "quiz_ready": False,    # summary shown, waiting for student to say yes/skip
            "quiz_active": False,   # quiz running — all messages go direct to quiz handler
            "merit_score": 5.0,
            "adaptation": AdaptationLevel.NORMAL,
            "sections_completed": [],
            "last_taught_section_id": None,
            "diagnostic_active": False,
            "diagnostic_questions": [],
            "diagnostic_index": 0,
            "diagnostic_answers": [],
            # Chapter mode
            "chapter_mode": False,
            "chapter_id": None,
            "chapter_section_queue": [],        # section_ids remaining to teach
            "chapter_sections_done": [],        # section_ids already taught
            "chapter_reference_cards": {},      # section_id → reference_card (for chapter summary)
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def load_files(self, file_paths: List[str]) -> str:
        """Load study materials. Agent discovers content via tools and writes a natural welcome."""
        docs = self.file_manager.load_files(file_paths)
        if not docs:
            return "No files could be loaded."
        # Let the agent discover what was loaded by calling show_toc() itself,
        # then generate a natural welcome — not hardcoded string formatting.
        text, _ = self.chat("__FILES_LOADED__")
        return text

    _AFFIRMATIVES = frozenset({
        "yes", "y", "yep", "yea", "yeah", "got it", "ok", "okay",
        "continue", "next", "sure", "clear", "understood", "makes sense",
        "i see", "sounds good", "good", "great",
    })

    def _is_affirmative(self, msg: str) -> bool:
        return msg.lower().strip() in self._AFFIRMATIVES

    def chat(self, user_message: str):
        """Main entry point. Returns (text, image_path) where image_path may be None."""
        self.history.append({"role": "user", "content": user_message})
        self._pending_image = None

        # ── Fast path 1: teaching active ─────────────────────────────────────
        # ALL messages go straight to the teaching agent — no main LLM involved.
        if self.session["teaching_active"]:
            merit_type = "yes_clear" if self._is_affirmative(user_message) else "in_progress"
            self._run_merit_update(user_message, merit_type)

            # ── Python-level cross-unit detection (before asking the LLM) ────
            # If the student's message references a different section by title,
            # navigate immediately — don't trust the teaching LLM to detect it.
            cross_unit = self._detect_cross_unit_reference(user_message)
            if cross_unit:
                self.session["teaching_active"] = False
                result = self._handle_navigation(cross_unit, "")
                image = self._pending_image
                self._pending_image = None
                self.history.append({"role": "assistant", "content": result})
                return result, image

            result = self._tool_forward_to_teaching(user_message)
            image = self._pending_image
            self._pending_image = None

            # ── FIND_UNIT: teaching agent wants to navigate to a different unit ──
            if self.teaching_agent.is_find_unit_request(result):
                description = self.teaching_agent.get_find_unit_description(result)
                clean = self.teaching_agent.clean_response(result)
                self.session["teaching_active"] = False
                result = self._handle_navigation(description, clean)
                image = self._pending_image
                self._pending_image = None
                self.history.append({"role": "assistant", "content": result})
                return result, image

            if "UNIT_COMPLETE" in result or "ALL_CHUNKS_DONE" in result:
                for sig in ("UNIT_COMPLETE", "ALL_CHUNKS_DONE", "\n\nCHUNK_COMPLETE"):
                    result = result.replace(sig, "").strip()
                self.session["teaching_active"] = False
                self.session["all_chunks_done"] = True
                image = None

                done_id = self.session.get("loaded_section_id", "")
                # Track last taught section for adjacency-based prereq decisions
                self.session["last_taught_section_id"] = done_id
                if done_id and done_id not in self.session["sections_completed"]:
                    self.session["sections_completed"].append(done_id)

                # Chapter mode: record section done and announce what's next
                if self.session["chapter_mode"]:
                    if done_id and done_id not in self.session["chapter_sections_done"]:
                        self.session["chapter_sections_done"].append(done_id)
                    queue = self.session["chapter_section_queue"]
                    if queue and queue[0] == done_id:
                        queue.pop(0)

                    if queue:
                        next_id = queue[0]
                        done_count = len(self.session["chapter_sections_done"])
                        total = done_count + len(queue)
                        result += (
                            f"\n\n---\n✅ Section {done_id} complete ({done_count}/{total} done)."
                            f"\n\nNext up: **{next_id}**. Ready to continue, or do you need a break?"
                        )
                    else:
                        result += "\n\n---\n🎉 You've finished the whole chapter! Ready for the chapter quiz?"
                        self.session["chapter_mode"] = False
                else:
                    # Single section done — auto-trigger quiz immediately
                    quiz_result = self._tool_run_quiz()
                    result = result + "\n\n" + quiz_result if result else quiz_result

            self.history.append({"role": "assistant", "content": result})
            logger.info(f"[TEACHING PATH] {result[:150]}")
            return result, image

        # ── Fast path 2: quiz ready — waiting for yes/skip ────────────────────
        if self.session["quiz_ready"]:
            msg_lower = user_message.lower().strip()
            skip_words = {"no", "skip", "later", "nope", "not now", "n"}
            if self._is_affirmative(user_message) or "quiz" in msg_lower:
                self.session["quiz_ready"] = False
                self.session["quiz_active"] = True
                q = self.session["active_quiz"].questions[0]
                n = len(self.session["active_quiz"].questions)
                result = f"**Q1/{n}:**\n\n" + self.quiz_agent.format_question(q)
            elif msg_lower in skip_words or any(w in msg_lower for w in skip_words):
                self.session["quiz_ready"] = False
                result = "No problem. What would you like to do next?"
            else:
                # Treat anything else as a yes — don't let the student accidentally escape
                self.session["quiz_ready"] = False
                self.session["quiz_active"] = True
                q = self.session["active_quiz"].questions[0]
                n = len(self.session["active_quiz"].questions)
                result = f"**Q1/{n}:**\n\n" + self.quiz_agent.format_question(q)
            self.history.append({"role": "assistant", "content": result})
            return result, None

        # ── Fast path 3: quiz active — evaluate answer directly ───────────────
        if self.session["quiz_active"]:
            result = self._handle_quiz_answer(user_message)
            self.history.append({"role": "assistant", "content": result})
            logger.info(f"[QUIZ PATH] {result[:150]}")
            return result, None

        # ── Main agentic loop ─────────────────────────────────────────────────
        # LLM sees full history + session state, calls tools, decides everything.
        # history includes everything: user, assistant, tool_calls, tool results
        # so LLM always has full memory across turns
        max_rounds = 20
        for _ in range(max_rounds):
            # System prompt rebuilt each round so session state is always fresh
            messages = [
                {"role": "system", "content": self._build_system_prompt()},
            ] + self.history

            response = self.llm.chat(
                messages,
                max_tokens=1500,
                temperature=0.4,
                tools=TOOLS,
                tool_choice="auto",
            )
            msg = response["choices"][0]["message"]

            # Save assistant message (tool calls OR text) into persistent history
            self.history.append(msg)

            # If the LLM called tools, execute them and save results to history
            if msg.get("tool_calls"):
                direct_response = None  # teaching content to return immediately

                for tool_call in msg["tool_calls"]:
                    name = tool_call["function"]["name"]
                    args = json.loads(tool_call["function"]["arguments"])

                    logger.info(f"[TOOL CALL] {name}({args})")
                    result = self._execute_tool(name, args)
                    logger.info(f"[TOOL RESULT] {result[:300]}")

                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result,
                    })

                    # Teaching tools produce student-facing content — return directly.
                    if name in ("teach_chunk", "forward_to_teaching_agent"):
                        content = result
                        for signal in ("CHUNK_COMPLETE", "ALL_CHUNKS_DONE"):
                            if f"\n\n{signal}" in content:
                                content = content.split(f"\n\n{signal}")[0]
                        direct_response = content

                if direct_response is not None:
                    image = self._pending_image
                    self._pending_image = None
                    logger.info(f"[FINAL RESPONSE] {direct_response[:300]}")
                    return direct_response, image

                # Non-teaching tools — LLM sees results and decides next step
                continue

            # LLM responded to the user (no more tool calls)
            content = msg.get("content", "")
            logger.info(f"[FINAL RESPONSE] {content[:300]}")
            return content, None

        return "I got stuck thinking. Could you rephrase that?", None

    # ── Tool Implementations ──────────────────────────────────────────────────

    def _execute_tool(self, name: str, args: Dict) -> str:
        dispatch = {
            "show_toc":                  lambda: self._tool_show_toc(),
            "load_chapter":              lambda: self._tool_load_chapter(args["chapter_id"]),
            "load_section":              lambda: self._tool_load_section(args["section_id"]),
            "teach_chunk":               lambda: self._tool_teach_chunk(),
            "forward_to_teaching_agent": lambda: self._tool_forward_to_teaching(args["student_message"]),
            "run_quiz":                  lambda: self._tool_run_quiz(),
            "run_diagnostic":            lambda: self._tool_run_diagnostic(args["topics"]),
            "search_topic":              lambda: self._tool_search_topic(args["query"]),
            "get_progress":              lambda: self._tool_get_progress(),
        }
        fn = dispatch.get(name)
        if not fn:
            return f"Unknown tool: {name}"
        try:
            return fn()
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
            return f"Tool {name} failed: {e}"

    def _tool_show_toc(self) -> str:
        return self.file_manager.format_toc_display() or "No materials loaded."

    def _tool_load_chapter(self, chapter_id: str) -> str:
        """Read the TOC to find all sections in this chapter. No pages loaded yet."""
        toc_entries = self.file_manager.get_chapter_sections(chapter_id)
        if not toc_entries:
            # Fallback: search by query
            toc_entries = self.file_manager.find_toc_entries_by_query(chapter_id)

        if not toc_entries:
            available = self.file_manager.get_chapter_list()
            return f"Chapter '{chapter_id}' not found. Available chapters: {', '.join(available)}"

        section_ids = [e.section_id for e in toc_entries if hasattr(e, "section_id")]
        if not section_ids:
            # Build section_ids from toc entry titles if section_id not set
            section_ids = [e.title for e in toc_entries]

        # Set chapter mode
        self.session["chapter_mode"] = True
        self.session["chapter_id"] = chapter_id
        self.session["chapter_section_queue"] = list(section_ids)
        self.session["chapter_sections_done"] = []
        self.session["chapter_reference_cards"] = {}  # reset for fresh chapter

        # Build a readable plan from TOC (no LLM needed — just TOC data)
        lines = [f"Chapter {chapter_id} — {len(toc_entries)} sections:"]
        for i, entry in enumerate(toc_entries, 1):
            title = entry.title
            sid = getattr(entry, "section_id", title)
            lines.append(f"  {i}. {sid}: {title}")
        lines.append(f"\nI'll teach them in order. Want to skip any, or shall we start with section {section_ids[0]}?")

        return "\n".join(lines)

    def _tool_load_section(self, section_id: str) -> str:
        section = self.file_manager.get_section(section_id)
        if not section:
            candidates = self.file_manager.find_sections_by_query(section_id)
            if candidates:
                section = candidates[0]
                section_id = section.section_id
            else:
                available = [s.section_id for s in self.file_manager.get_all_sections()[:6]]
                return f"Section '{section_id}' not found. Available: {', '.join(available)}"

        # Map concepts (lazy) — find the document this section belongs to
        if not hasattr(self, "_concept_map"):
            self._concept_map = {}

        if section_id not in self._concept_map:
            try:
                subject_profile = self.file_manager.subject_profile
                subject = subject_profile.subject if subject_profile else "STEM"
                level = subject_profile.level if subject_profile else "intermediate"
                material_type = subject_profile.material_type if subject_profile else "textbook"
                concept = self.concept_mapper._map_section(section, subject, level, material_type)
                self._concept_map[section_id] = concept
            except Exception as e:
                logger.warning(f"Concept mapping failed: {e}")
                concept = None
        else:
            concept = self._concept_map.get(section_id)

        # Chunk the section
        chunks = self.chunker.chunk(section, adaptation=self.session["adaptation"])
        if not chunks:
            return f"Section '{section_id}' has no content to teach."

        # Pre-generate all chunk explanations now so "yes" responses are instant later
        subject_profile = self.file_manager.subject_profile
        subject_name = subject_profile.subject if subject_profile else "STEM"

        # Build a lightweight reference card from the extracted text (1 fast LLM call).
        # This replaces pre-generating full lessons — teaching happens on-demand.
        reference_card = self._extract_reference_card(section, subject_name)

        # Store in session — no pre-generated lessons, just the reference card
        self.session["loaded_section_id"] = section_id
        self.session["loaded_section"] = section
        self.session["reference_card"] = reference_card

        # Accumulate reference cards for chapter summary
        if self.session.get("chapter_mode"):
            self.session["chapter_reference_cards"][section_id] = (section.title, reference_card)
        self.session["chunks"] = chunks          # kept for chunking structure only
        self.session["chunk_responses"] = []     # no longer pre-generated
        self.session["chunk_images"] = []
        self.session["chunk_index"] = 0
        self.session["teaching_active"] = False
        self.session["all_chunks_done"] = False

        # Build summary for LLM
        lines = [
            f"Section loaded: {section.title} (pages {section.page_start}–{section.page_end})",
            f"Parts to teach: {len(chunks)}",
            f"Reference card ready (symbols, equations, topics extracted).",
        ]
        if concept:
            if concept.concepts:
                lines.append(f"Topics: {', '.join(concept.concepts[:5])}")
            if concept.prerequisites:
                lines.append(f"Prerequisites: {', '.join(concept.prerequisites[:3])}")

        # Tell the LLM to stop the tool loop and talk to the student first.
        # Do NOT call teach_chunk() yet — respond to the student with a prereq
        # question (or jump straight to teach_chunk() only if mid-chapter).
        if self.session.get("chapter_mode"):
            lines.append("NEXT ACTION: call teach_chunk() immediately — mid-chapter, no prereq check needed.")
        else:
            prereq_context = ""
            if concept and concept.prerequisites:
                prereq_context = f"Key prerequisites for this section: {', '.join(concept.prerequisites[:3])}."
            lines.append(
                f"NEXT ACTION: stop here and respond to the student with a prereq question. "
                f"Do NOT call teach_chunk() yet. {prereq_context} "
                f"Ask ONE focused question like: 'Before we dive in, are you comfortable with [key prereq]?' "
                f"Wait for their answer, then call teach_chunk()."
            )
        return "\n".join(lines)

    def _extract_reference_card(self, section, subject: str) -> str:
        """
        One fast LLM call: extract symbols, equation numbers, topics, and figures
        from the raw PDF text. Returns a compact reference card string.
        """
        # Strip boilerplate headers from extract_pdf_pages to measure real content
        raw = section.content or ""
        real_lines = [
            l for l in raw.splitlines()
            if l.strip()
            and not l.startswith("PDF:")
            and not l.startswith("Pages:")
            and not l.startswith("===")
            and not l.startswith("PAGE ")
            and not l.startswith("EXTRACTION COMPLETE")
        ]
        real_content = "\n".join(real_lines).strip()

        if len(real_content) < 80:
            logger.warning(
                f"Section '{section.section_id}' has no extractable text "
                f"({len(real_content)} chars) — returning empty reference card"
            )
            return ""  # TeachingAgent's guard will catch this

        prompt = f"""You are parsing a {subject} textbook section to create a reference card for a tutor.

Section: {section.title} (pages {section.page_start}–{section.page_end})

Raw text:
{real_content[:5000]}

Extract ONLY what actually appears in the text. Return this exact format:

TOPICS: <comma-separated list of the main topics covered, most important first>

EQUATIONS:
- Eq. X-Y: <brief description> (page N)
(list every numbered equation found)

SYMBOLS:
- <symbol> = <what it represents> (<units if applicable>)
(list every symbol defined in the text)

FIGURES:
- Figure X-Y: <what it shows> (page N)
(list every figure referenced)

KEY EXAMPLES:
- Example X-Y: <brief description> (page N)
(list worked examples if any, or write "none")

Be concise. This is a reference card, not a summary."""

        try:
            return self.llm.get_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.1,
            )
        except Exception as e:
            logger.error(f"Reference card extraction failed: {e}")
            return f"Section: {section.title}\nTopics: {section.title}"

    def _tool_teach_chunk(self, opening_message: str = "Begin the lesson.", preserve_history: bool = False) -> str:
        """Start a teaching session for the loaded section using the reference card."""
        section = self.session.get("loaded_section")
        if not section:
            return "No section loaded. Call load_section() first."

        if self.session.get("all_chunks_done"):
            return "ALL_CHUNKS_DONE — section already complete. Call run_quiz() now."

        subject_profile = self.file_manager.subject_profile
        reference_card = self.session.get("reference_card", "")

        # Build unit index and current unit number for navigation context
        all_sections = self.file_manager.get_all_sections()
        current_id = self.session.get("loaded_section_id", "")
        unit_index_lines = []
        current_unit_number = 1
        for i, s in enumerate(all_sections, 1):
            unit_index_lines.append(f"{i}. {s.title}")
            if s.section_id == current_id:
                current_unit_number = i
        unit_index = "\n".join(unit_index_lines)

        # Use a lightweight TeachingUnit wrapper for the section title
        from models.data_models import TeachingUnit
        unit = TeachingUnit(
            unit_id=self.session["loaded_section_id"],
            title=section.title,
            content="",          # not used — reference card is the guide
            page_range=(section.page_start, section.page_end),
            content_type="concept",
            source_file=section.source_file,
        )

        response = self.teaching_agent.start_unit_with_reference(
            unit=unit,
            subject_profile=subject_profile,
            reference_card=reference_card,
            opening_message=opening_message,
            student_initiated=True,
            is_backward_jump=not preserve_history,
            unit_index=unit_index,
            current_unit_number=current_unit_number,
        )

        # Generate visualization if warranted
        self._pending_image = None
        subject_name = subject_profile.subject if subject_profile else "STEM"
        if self.viz_agent.should_visualize(section.title + " " + response[:200]):
            self._pending_image = self.viz_agent.generate(
                concept=section.title,
                subject=subject_name,
                context=response[:300],
            )

        self.session["teaching_active"] = True
        return response

    def _tool_forward_to_teaching(self, student_message: str) -> str:
        if not self.session["teaching_active"]:
            return "No active teaching session. Call teach_chunk() first."

        response = self.teaching_agent.respond(student_message)

        if self.teaching_agent.is_unit_complete(response):
            response = self.teaching_agent.clean_response(response)
            self.session["teaching_active"] = False
            self.session["all_chunks_done"] = True
            self._run_merit_update(student_message, "yes_clear")
            return response + "\n\nUNIT_COMPLETE — section done. Call run_quiz() now."

        self._run_merit_update(student_message, "in_progress")
        return response

    def _tool_run_quiz(self) -> str:
        """
        Generate quiz questions, show the summary, and ask if student is ready.
        The actual Q1 is shown only after the student says yes (quiz_ready fast path).
        """
        section = self.session.get("loaded_section")
        if not section:
            return "No section loaded to quiz on."

        section_id = self.session.get("loaded_section_id", "")
        concept = getattr(self, "_concept_map", {}).get(section_id)
        subject_profile = self.file_manager.subject_profile

        # Chapter quiz uses all accumulated reference cards; section quiz uses just this one
        cards = self.session.get("chapter_reference_cards", {})
        chapter_done = (
            not self.session.get("chapter_mode")
            and self.session.get("chapter_id")
            and len(cards) > 1
        )
        summary_block = (
            self._generate_chapter_summary() if chapter_done
            else self._format_section_summary(self.session.get("reference_card", ""), section.title)
        )

        # Generate quiz questions grounded in what the teaching agent actually taught
        teaching_history = self.teaching_agent.conversation_history
        # Use teaching conversation as content sample — richer than raw PDF text
        taught_content = "\n".join(
            m["content"] for m in teaching_history
            if m.get("role") == "assistant" and m.get("content")
        )[:3000]

        try:
            quiz = self.quiz_agent.generate_quiz(
                section_title=section.title,
                section_concept=concept,
                content_sample=taught_content or section.content[:3000],
                merit_score=self.session["merit_score"],
                subject_profile=subject_profile,
            )
            self.session["active_quiz"] = quiz
            self.session["quiz_question_index"] = 0
            self.session["quiz_ready"] = True
            self.session["quiz_active"] = False

            if not quiz.questions:
                self.session["quiz_ready"] = False
                return summary_block + "\n\nCouldn't generate quiz questions. What would you like to do next?"

            n = len(quiz.questions)
            return (
                summary_block
                + f"\n\nThat covers **{section.title}**. Ready for a short quiz? ({n} questions) — Yes / Skip"
            )
        except Exception as e:
            logger.error(f"Quiz generation failed: {e}", exc_info=True)
            return summary_block + f"\n\nQuiz generation failed: {e}"

    def _handle_quiz_answer(self, student_answer: str) -> str:
        """
        Evaluate one quiz answer, show feedback, advance to next question or finish.
        Called directly from the quiz_active fast path — no LLM routing involved.
        """
        quiz = self.session.get("active_quiz")
        if not quiz:
            self.session["quiz_active"] = False
            return "No active quiz."

        idx = self.session["quiz_question_index"]
        if idx >= len(quiz.questions):
            self.session["quiz_active"] = False
            return "Quiz already complete. What would you like to do next?"

        subject = self.file_manager.subject_profile.subject if self.file_manager.subject_profile else "STEM"
        q = quiz.questions[idx]
        self.quiz_agent.evaluate_answer(q, student_answer, subject)

        icon = "✅" if q.is_correct else "❌"
        feedback = f"{icon} {q.feedback}\n\n"

        self.session["quiz_question_index"] += 1
        next_idx = idx + 1
        n = len(quiz.questions)

        if next_idx < n:
            next_q = quiz.questions[next_idx]
            return feedback + f"**Q{next_idx + 1}/{n}:**\n\n" + self.quiz_agent.format_question(next_q)
        else:
            # Quiz complete
            self.session["quiz_active"] = False
            self.quiz_agent.compute_quiz_result(quiz)
            correct = sum(1 for q in quiz.questions if q.is_correct)
            pct = int(correct / n * 100)

            # Mark section complete
            section_id = self.session.get("loaded_section_id", "")
            if section_id and section_id not in self.session["sections_completed"]:
                self.session["sections_completed"].append(section_id)

            if pct >= 80:
                verdict = "Excellent work! 🎉"
            elif pct >= 60:
                verdict = "Good effort — solid understanding."
            else:
                verdict = "Let's note the weaker areas for review."

            weak = [q.question_text[:60] for q in quiz.questions if not q.is_correct]
            weak_note = ""
            if weak:
                weak_note = "\n\n**To revisit:** " + "; ".join(weak)

            return (
                feedback
                + f"**Quiz done!** {correct}/{n} correct ({pct}%) — {verdict}"
                + weak_note
                + "\n\nWhat would you like to do next?"
            )

    def _tool_run_diagnostic(self, topics: List[str]) -> str:
        try:
            questions = self.diagnostic_agent.generate_questions(topics)
            self.session["diagnostic_active"] = True
            self.session["diagnostic_questions"] = questions
            self.session["diagnostic_index"] = 0
            self.session["diagnostic_answers"] = []

            if not questions:
                return "Could not generate diagnostic questions."

            q = questions[0]
            return (
                f"**Diagnostic Assessment** ({len(questions)} questions)\n\n"
                f"**Question 1/{len(questions)}:**\n{q['question']}"
            )
        except Exception as e:
            return f"Diagnostic failed: {e}"

    def _tool_search_topic(self, query: str) -> str:
        results = self.file_manager.find_sections_by_query(query)
        if not results:
            return f"No sections found for '{query}'."
        lines = [f"Found {len(results)} section(s) for '{query}':"]
        for s in results[:5]:
            lines.append(f"  • {s.section_id}: {s.title} (pages {s.page_start}–{s.page_end})")
        return "\n".join(lines)

    def _tool_get_progress(self) -> str:
        lines = [
            f"Merit score: {self.session['merit_score']:.1f}/10",
            f"Adaptation: {self.session['adaptation'].value}",
            f"Sections completed: {len(self.session['sections_completed'])}",
        ]
        if self.session["sections_completed"]:
            lines.append(f"  Completed: {', '.join(self.session['sections_completed'])}")
        if self.session["chunks"]:
            total = len(self.session["chunks"])
            done = self.session["chunk_index"]
            lines.append(f"Current section: {done}/{total} chunks taught")
        return "\n".join(lines)

    # ── Summary helpers ───────────────────────────────────────────────────────

    def _format_section_summary(self, reference_card: str, title: str) -> str:
        """
        One LLM call: generate a clean 'What We Covered' summary from the reference card.
        """
        if not reference_card:
            return f"---\n### 📚 What We Covered — {title}\n\n*(No reference card available)*\n\n---"

        subject_profile = self.file_manager.subject_profile
        subject = subject_profile.subject if subject_profile else "STEM"

        prompt = f"""A student just finished a {subject} lesson on "{title}".

Here is the reference card from that section:
{reference_card}

Write a concise "What We Covered" summary in this format:

### 📚 What We Covered — {title}

**Key Concepts:**
<bullet list of the main ideas taught, 3-6 items>

**Equations to Remember:**
<bullet list with equation numbers and brief descriptions, max 5>

**To Keep in Mind:**
<1-2 sentences on the most important takeaway or common mistake to avoid>

Be concise. Student is about to take a short quiz."""

        try:
            summary = self.llm.get_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=350,
                temperature=0.3,
            )
            return f"---\n\n{summary}\n\n---"
        except Exception as e:
            logger.error(f"Section summary failed: {e}")
            return f"---\n### 📚 What We Covered — {title}\n\n{reference_card[:400]}\n\n---"

    def _generate_chapter_summary(self) -> str:
        """
        One LLM call: synthesize all section reference cards into a chapter-wide summary.
        Called only when a full chapter is done, before the chapter quiz.
        """
        cards = self.session.get("chapter_reference_cards", {})
        chapter_id = self.session.get("chapter_id", "")
        subject_profile = self.file_manager.subject_profile
        subject = subject_profile.subject if subject_profile else "STEM"

        if not cards:
            return f"---\n### 📚 Chapter {chapter_id} — Summary\n\n*(No content available)*\n\n---"

        # Build the combined input
        sections_text = []
        for sid, (title, card) in cards.items():
            sections_text.append(f"Section {sid} — {title}:\n{card[:800]}")
        combined = "\n\n".join(sections_text)

        prompt = f"""A student just finished all sections of Chapter {chapter_id} in a {subject} textbook.

Here are the reference cards from each section they studied:

{combined}

Write a concise chapter summary in this exact format:

### 📚 Chapter {chapter_id} Summary

**The Big Picture:**
<2-3 sentences on what this chapter was fundamentally about and why it matters>

**Core Concepts:**
<bullet list of the 5-8 most important concepts across all sections>

**Key Equations:**
<bullet list of the most important equations (max 6), with their equation numbers>

**How It All Connects:**
<2-3 sentences on how the sections built on each other>

Be concise. Student is about to take a quiz."""

        try:
            summary = self.llm.get_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )
            return f"---\n\n{summary}\n\n---"
        except Exception as e:
            logger.error(f"Chapter summary failed: {e}")
            # Fall back to per-section summaries concatenated
            parts = ["---", f"### 📚 Chapter {chapter_id} — What We Covered", ""]
            for sid, (title, card) in cards.items():
                parts.append(f"**{sid}: {title}**")
                eq_lines = [l for l in card.splitlines() if l.strip().startswith("-") and "Eq." in l]
                for line in eq_lines[:3]:
                    parts.append(f"  {line.strip()}")
                parts.append("")
            parts.append("---")
            return "\n".join(parts)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        materials = self.file_manager.summary()

        completed = self.session["sections_completed"]
        last = self.session.get("last_taught_section_id")
        state_lines = [
            f"Merit score: {self.session['merit_score']:.1f}/10 ({self.session['adaptation'].value} pace)",
            f"Teaching active: {self.session['teaching_active']}",
            f"Quiz active: {self.session['quiz_active']} | Quiz ready (waiting for yes): {self.session['quiz_ready']}",
            f"Current section: {self.session.get('loaded_section_id') or 'none'}",
            f"Last taught section: {last or 'none'}",
            f"Sections already taught this session: {', '.join(completed) if completed else 'none'}",
        ]

        # Chapter mode — give the main agent the full picture so it knows what to do next
        if self.session.get("chapter_mode"):
            done = self.session["chapter_sections_done"]
            queue = self.session["chapter_section_queue"]
            next_up = queue[0] if queue else None
            state_lines += [
                f"CHAPTER MODE: chapter {self.session['chapter_id']}",
                f"  Sections done: {done or 'none'}",
                f"  Sections remaining: {queue or 'none'}",
                f"  Next section to teach: {next_up or 'all done'}",
            ]
            if next_up:
                state_lines.append(
                    f"  → When student says ready: call load_section('{next_up}') then teach_chunk()"
                )
            else:
                state_lines.append("  → Chapter complete. Call run_quiz() for chapter quiz.")

        return SYSTEM_PROMPT.format(
            materials_summary=materials,
            session_state="\n".join(state_lines),
        )

    def _detect_cross_unit_reference(self, user_message: str) -> str:
        """
        Check if the student's message references a section title that is NOT
        the currently active section. Returns the matched section title if found,
        or '' if the message is about the current unit (or nothing recognizable).

        This is a Python-level guard so backward/cross navigation is never
        dependent on the teaching LLM deciding to emit FIND_UNIT:.
        """
        current_id = self.session.get("loaded_section_id", "")
        msg_lower = user_message.lower()

        all_sections = self.file_manager.get_all_sections()
        best_match = ""
        best_score = 0

        for section in all_sections:
            # Skip the currently active section
            if section.section_id == current_id:
                continue

            title = section.title
            title_lower = title.lower()

            # Score: count how many significant words from the title appear in the message
            words = [w for w in title_lower.split() if len(w) > 3]
            if not words:
                continue
            matches = sum(1 for w in words if w in msg_lower)
            score = matches / len(words)

            if score > best_score and score >= 0.5:  # at least half the title words match
                best_score = score
                best_match = title

        return best_match

    def _handle_navigation(self, description: str, ack_text: str) -> str:
        """
        Handle a FIND_UNIT navigation request from the teaching agent.
        Searches for the target section, loads it, and starts teaching —
        exactly as the main agentic loop would, but triggered from the fast path.
        """
        # Search for matching sections
        candidates = self.file_manager.find_sections_by_query(description)
        if not candidates:
            return f"{ack_text}\n\nSorry, I couldn't find a section matching '{description}' in the loaded materials."

        section = candidates[0]
        section_id = section.section_id

        # Load the section (sets up reference card, chunks, session state)
        load_result = self._tool_load_section(section_id)
        logger.info(f"[NAV] Loaded section {section_id}: {load_result[:100]}")

        # Start teaching immediately (no prereq check for student-initiated jumps)
        teach_result = self._tool_teach_chunk()
        self.session["teaching_active"] = True

        # Prepend the ack so the student sees "Taking you there now." before the lesson
        if ack_text:
            return f"{ack_text}\n\n{teach_result}"
        return teach_result

    def _run_merit_update(self, student_message: str, response_type: str):
        try:
            unit = self.session["chunks"][self.session["chunk_index"] - 1] if self.session["chunk_index"] > 0 else None
            if not unit:
                return
            entry = self.merit_evaluator.evaluate(
                unit=unit,
                response_type=response_type,
                student_message=student_message,
                current_merit=self.session["merit_score"],
            )
            # EWMA update
            self.session["merit_score"] = 0.7 * self.session["merit_score"] + 0.3 * entry.score
        except Exception as e:
            logger.debug(f"Merit update failed (non-critical): {e}")

    def _update_adaptation(self):
        score = self.session["merit_score"]
        if score < 5.0:
            self.session["adaptation"] = AdaptationLevel.SLOWER
        elif score > 7.0:
            self.session["adaptation"] = AdaptationLevel.FASTER
        else:
            self.session["adaptation"] = AdaptationLevel.NORMAL
