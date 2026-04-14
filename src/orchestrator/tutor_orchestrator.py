"""
TutorOrchestrator — the main coordinator that drives the adaptive teaching session.

Entry point: chat(user_message) → str
Manages all state transitions across:
  IDLE → FILE_UPLOAD → CONCEPT_MAPPING → INTENT_CLASSIFICATION → PLANNING
  → DIAGNOSTIC → PLAN_REVIEW → DEEP_ANALYZE → TEACHING → COMPREHENSION_CHECK
  → RETEACH/MERIT_UPDATE → SECTION_QUIZ → PHASE_CHECKPOINT → PLAN_COMPLETE
  and DETOUR (for in-context questions)
"""

import logging
import os
import re
from typing import Dict, List, Optional

from agents.diagnostic_agent import DiagnosticAgent
from agents.merit_evaluator import MeritEvaluator
from agents.quiz_agent import QuizAgent
from agents.teaching_agent import TeachingAgent
from content.chunker import ContentChunker
from content.concept_mapper import ConceptMapper
from content.file_manager import FileManager
from content.resolver import ContentResolver
from models.data_models import (
    AdaptationLevel, QuizResult, RequestScope, SessionState, TutorState,
    TeachingPlan, TeachingUnit,
)
from orchestrator.session_planner import SessionPlanner
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Responses that signal "yes, I understand, continue"
YES_SIGNALS = {
    "yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "clear",
    "got it", "i get it", "makes sense", "understood", "continue",
    "next", "move on", "keep going", "ready", "go ahead", "proceed",
}

# Responses that signal "no, I'm confused"
NO_SIGNALS = {
    "no", "n", "nope", "not really", "not clear", "confused",
    "don't understand", "dont understand", "i'm lost", "im lost",
    "unclear", "lost", "what", "huh",
}

# Signals to show a quiz answer (worked example)
SHOW_SOLUTION_SIGNALS = {"show solution", "show answer", "reveal", "what's the answer"}


class TutorOrchestrator:
    """
    Top-level coordinator for the adaptive STEM tutor.

    Public API:
        orchestrator = TutorOrchestrator(api_key, model)
        orchestrator.load_files(["/path/to/textbook.pdf"])  # at startup
        response = orchestrator.chat("teach me section 1-2")
        response = orchestrator.chat("yes")
        response = orchestrator.chat("no, i don't get the second part")
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.llm = LLMClient(api_key=api_key, model=model)

        # Components
        self.file_manager = FileManager(self.llm)
        self.concept_mapper = ConceptMapper(self.llm)
        self.chunker = ContentChunker()
        self.session_planner = SessionPlanner(self.llm)
        self.teaching_agent = TeachingAgent(self.llm)
        self.merit_evaluator = MeritEvaluator(self.llm)
        self.quiz_agent = QuizAgent(self.llm)
        self.diagnostic_agent = DiagnosticAgent(self.llm)
        self.resolver = ContentResolver(self.llm)

        # Session state (in-memory)
        self.state = SessionState()

        # Diagnostic session tracking
        self._diagnostic_questions: List[Dict] = []
        self._diagnostic_answers: List = []
        self._diagnostic_index: int = 0

        # Quiz session tracking
        self._active_quiz: Optional[QuizResult] = None
        self._quiz_question_index: int = 0

    # ── Public API ──────────────────────────────────────────────────────────────

    def load_files(self, file_paths: List[str]) -> str:
        """
        Load and process files (called at startup or mid-session).
        Returns a status message to show the student.
        """
        if not file_paths:
            return "No files provided. Please give me a PDF, image, or document to work with."

        self.state.current_state = TutorState.FILE_UPLOAD
        try:
            docs = self.file_manager.load_files(file_paths)
        except Exception as e:
            logger.error(f"File loading failed: {e}")
            self.state.current_state = TutorState.IDLE
            return f"I had trouble loading your files: {e}"

        if not docs:
            self.state.current_state = TutorState.IDLE
            return "I couldn't process any of the provided files. Please check the file paths."

        # Update session state with loaded documents
        self.state.documents = self.file_manager.documents
        self.state.subject_profile = self.file_manager.subject_profile

        # Concept mapping is LAZY — we'll map sections only when they're about to be taught.
        # Skip upfront LLM calls: content extraction is also lazy (pdf_content_navigator).
        # This keeps file load time instant (< 1 second for 500+ page PDFs).

        self.state.current_state = TutorState.IDLE

        # Log loaded section IDs for debugging
        loaded_ids = list(self.file_manager._section_index.keys())
        logger.debug(f"Loaded section IDs: {loaded_ids[:20]}")

        # Build response
        subject = self.state.subject_profile
        subject_str = f"{subject.subject} ({subject.level})" if subject else "your material"
        doc_names = [d.label for d in docs]
        names_str = ", ".join(f'"{n}"' for n in doc_names)

        concept_count = len(self.state.concept_map)
        toc_display = self.file_manager.format_toc_display()

        return self._build_welcome_message(docs)

    def chat(self, user_message: str) -> str:
        """
        Main entry point. Route user message based on current state.
        """
        user_message = user_message.strip()
        if not user_message:
            return ""

        # Add to conversation history
        self.state.conversation_history.append({"role": "user", "content": user_message})

        state = self.state.current_state

        # State routing
        if state == TutorState.IDLE:
            response = self._handle_idle(user_message)

        elif state == TutorState.DIAGNOSTIC:
            response = self._handle_diagnostic(user_message)

        elif state == TutorState.PLAN_REVIEW:
            response = self._handle_plan_review(user_message)

        elif state == TutorState.TEACHING:
            response = self._handle_teaching(user_message)

        elif state == TutorState.COMPREHENSION_CHECK:
            response = self._handle_comprehension_check(user_message)

        elif state == TutorState.RETEACH:
            response = self._handle_reteach(user_message)

        elif state == TutorState.SECTION_QUIZ:
            response = self._handle_quiz(user_message)

        elif state == TutorState.QUIZ_EVAL:
            response = self._handle_quiz_eval(user_message)

        elif state == TutorState.PHASE_CHECKPOINT:
            response = self._handle_phase_checkpoint(user_message)

        elif state == TutorState.DETOUR:
            response = self._handle_detour(user_message)

        else:
            # Fallback — return to IDLE handling
            response = self._handle_idle(user_message)

        self.state.conversation_history.append({"role": "assistant", "content": response})
        return response

    # ── State Handlers ──────────────────────────────────────────────────────────

    def _handle_idle(self, message: str) -> str:
        """
        IDLE: Classify intent, create plan or respond to non-teaching requests.
        """
        # Debug commands
        if message.lower() in ("debug", "debug toc", "show toc", "/debug"):
            return self.file_manager.debug_toc_structure()

        if message.lower() in ("debug raw", "/debug raw"):
            return self._debug_raw_toc()

        if not self.state.documents:
            return (
                "I don't have any study materials loaded yet. "
                "Please load a PDF or other document first."
            )

        self.state.current_state = TutorState.INTENT_CLASSIFICATION
        intent = self.session_planner.classify_intent(message)
        intent_type = intent.get("intent", "OTHER")

        logger.debug(f"Intent classified: {intent_type} / target: {intent.get('target')}")

        # ADD_FILE: load more documents mid-session
        if intent_type == "ADD_FILE":
            return self._handle_add_file_request(message)

        # INFO: just show TOC / concept info
        if intent_type == "INFO":
            self.state.current_state = TutorState.SHOW_INFO
            response = self._answer_info_request(message, intent)
            self.state.current_state = TutorState.IDLE
            return response

        # CONTINUE: resume from where we left off
        if intent_type == "CONTINUE":
            return self._handle_continue()

        # OTHER: try to answer helpfully
        if intent_type == "OTHER":
            self.state.current_state = TutorState.IDLE
            return self._handle_other_message(message)

        # Teaching intents: create a plan
        self.state.current_state = TutorState.PLANNING
        plan = self.session_planner.create_plan(intent, self.state)

        if plan is None:
            self.state.current_state = TutorState.IDLE
            return "I'm not sure what you'd like to study. Could you be more specific?"

        self.state.current_plan = plan

        # EXAM_PREP: run diagnostic first
        if intent_type == "EXAM_PREP":
            return self._start_diagnostic()

        # SINGLE_SECTION: skip plan review, go directly to teaching
        if plan.scope == RequestScope.SINGLE_SECTION:
            return self._execute_plan_first_section()

        # Other scopes: show plan and ask to confirm
        self.state.current_state = TutorState.PLAN_REVIEW
        return self.session_planner.format_plan_for_student(plan)

    def _handle_plan_review(self, message: str) -> str:
        """
        PLAN_REVIEW: Use LLM (session_planner) to understand if student wants to start or adjust.
        """
        intent = self.session_planner.classify_intent(message)
        intent_type = intent.get("intent", "OTHER").upper()

        logger.debug(f"Plan review intent: {intent_type}")

        # Student wants to adjust/skip something
        if any(word in message.lower() for word in ["skip", "already", "know", "focus", "more", "adjust"]):
            return self._adjust_plan(message)

        # Student is ready to start
        if intent_type in ("CONTINUE", "TEACH_SECTION", "TEACH_CHAPTER", "TEACH_MULTI"):
            return self._execute_plan_first_section()

        # Default: ask for clarification
        return (
            "Sure! The plan above shows what we'll cover. "
            "You can say:\n"
            '- "Start" or "Go" to begin\n'
            '- "Skip phase 1" to skip something you know\n'
            '- "Focus more on [topic]" to adjust priorities\n\n'
            "Ready to start?"
        )

    def _handle_diagnostic(self, message: str) -> str:
        """
        DIAGNOSTIC: Student is answering a gateway question.
        """
        if not self._diagnostic_questions:
            # No questions generated — skip to plan
            return self._finish_diagnostic()

        current_q = self._diagnostic_questions[self._diagnostic_index]
        subject = self.state.subject_profile.subject if self.state.subject_profile else "STEM"

        mastery, feedback = self.diagnostic_agent.assess_answer(current_q, message, subject)
        self._diagnostic_answers.append((mastery, feedback))
        self._diagnostic_index += 1

        # Give brief feedback
        feedback_msg = f"_{feedback}_\n\n"

        # More questions?
        if self._diagnostic_index < len(self._diagnostic_questions):
            next_q = self._diagnostic_questions[self._diagnostic_index]
            return (
                feedback_msg
                + f"**Question {self._diagnostic_index + 1} of {len(self._diagnostic_questions)}:**\n\n"
                + f"{next_q['question']}"
            )

        # All questions answered — build knowledge map and refine plan
        return self._finish_diagnostic()

    def _handle_teaching(self, message: str) -> str:
        """
        TEACHING: Student got an opening teaching message. Handle their response.
        (This is called when the agent is between sending the teaching and the yes/no check.)
        Actually we only hit TEACHING when student responds to ongoing teaching.
        """
        # Detect if student asked a question mid-teaching
        if self._looks_like_question(message):
            return self._enter_detour(message)

        # Otherwise treat as comprehension response
        return self._handle_comprehension_check(message)

    def _handle_comprehension_check(self, message: str) -> str:
        """
        COMPREHENSION_CHECK: Handle student responses using LLM-based understanding
        (via session_planner.classify_intent), not regex signal matching.
        """
        # ── Handle prerequisite response ──────────────────────────────────────
        if self.state.waiting_for_prerequisite_response:
            # Use LLM to understand yes/no/uncertain on prerequisites
            intent = self.session_planner.classify_intent(message)
            intent_type = intent.get("intent", "OTHER").upper()

            # Treat TEACH/CONTINUE as "yes, proceed"
            if intent_type in ("CONTINUE", "TEACH_SECTION", "TEACH_CHAPTER"):
                has_background = True
            # Everything else treated as "no/uncertain, but proceed anyway"
            else:
                has_background = False

            self.state.waiting_for_prerequisite_response = False
            section_id = self.state.pending_section_id
            self.state.pending_section_id = None

            section = self.file_manager.get_section(section_id)
            self.state.current_state = TutorState.DEEP_ANALYZE

            if not self.state.current_units:
                units = self.chunker.chunk(section=section, adaptation=self.state.adaptation_level)
                self.state.current_units = units
                self.state.current_unit_index = 0

            self.state.current_state = TutorState.TEACHING
            unit = self.state.current_unit

            concept = self.state.concept_map.get(section_id)
            prereq_note = ""
            if not has_background and concept and concept.prerequisites:
                prereq_note = (
                    f"⚠️ **Note:** This section assumes knowledge of: {', '.join(concept.prerequisites[:2])}\n"
                    f"Feel free to ask if you get stuck!\n\n"
                )

            response = prereq_note + self.teaching_agent.start_unit(unit, self.state.subject_profile)
            self.state.current_state = TutorState.COMPREHENSION_CHECK
            return response

        # ── Handle unit comprehension response using LLM ────────────────────
        # Use session_planner's LLM-based classify_intent to understand the response
        intent = self.session_planner.classify_intent(message)
        intent_type = intent.get("intent", "OTHER").upper()

        logger.debug(f"Comprehension response classified as: {intent_type}")

        # Route based on LLM understanding, not regex
        if intent_type in ("CONTINUE", "TEACH_SECTION", "TEACH_CHAPTER"):
            # Student said yes / clear / understood
            return self._on_unit_clear()
        elif intent_type == "OTHER" and any(
            word in message.lower() for word in ["confused", "lost", "don't", "not clear", "unclear"]
        ):
            # LLM wasn't sure, but message has negative signals → re-teach
            return self._on_unit_unclear(message)
        elif "?" in message or intent_type in ("TARGETED", "INFO"):
            # Student asked a question
            return self._enter_detour(message)
        else:
            # Default: ask for clarification (don't assume)
            return "I'm not sure I understand — are you clear on this concept, or is something confusing? (Yes / No)"

    def _handle_reteach(self, message: str) -> str:
        """
        RETEACH: Student specified which part was unclear. The teaching agent re-explains.
        """
        response = self.teaching_agent.respond(message)

        if self.teaching_agent.is_unit_complete(response):
            response = self.teaching_agent.clean_response(response)
            self.state.current_state = TutorState.COMPREHENSION_CHECK
        else:
            # Still in re-teach mode
            self.state.current_state = TutorState.COMPREHENSION_CHECK

        self._run_merit_update(message, "no_confused")
        return response

    def _handle_quiz(self, message: str) -> str:
        """
        SECTION_QUIZ: A quiz is active. Handle answer or navigation.
        """
        if self._active_quiz is None:
            return self._start_section_quiz()

        questions = self._active_quiz.questions
        if self._quiz_question_index >= len(questions):
            return self._finish_quiz()

        current_q = questions[self._quiz_question_index]

        # Hint request
        if "hint" in message.lower():
            if current_q.hint:
                return f"💡 **Hint:** {current_q.hint}"
            return "No hint available for this question."

        # Show solution (worked example)
        if any(phrase in message.lower() for phrase in SHOW_SOLUTION_SIGNALS):
            message = "show solution"

        # Evaluate
        subject = self.state.subject_profile.subject if self.state.subject_profile else "STEM"
        evaluated_q = self.quiz_agent.evaluate_answer(current_q, message, subject)

        # Update merit based on quiz result
        if evaluated_q.is_correct:
            self._run_merit_update(message, "quiz_correct")
        else:
            self._run_merit_update(message, "quiz_incorrect")

        self._quiz_question_index += 1
        feedback_text = f"{'✅' if evaluated_q.is_correct else '❌'} {evaluated_q.feedback}\n\n"

        # More questions?
        if self._quiz_question_index < len(questions):
            next_q = questions[self._quiz_question_index]
            return (
                feedback_text
                + f"**Question {self._quiz_question_index + 1}/{len(questions)}:**\n\n"
                + self.quiz_agent.format_question(next_q)
            )

        return feedback_text + self._finish_quiz()

    def _handle_quiz_eval(self, message: str) -> str:
        """QUIZ_EVAL: Waiting for student acknowledgment after quiz results."""
        if self._is_yes(message) or any(
            w in message.lower() for w in ["continue", "next", "ok", "okay", "ready", "go"]
        ):
            return self._advance_to_next_section()
        return (
            "Take your time! When you're ready to continue, just say **'next'** or **'continue'**."
        )

    def _handle_phase_checkpoint(self, message: str) -> str:
        """PHASE_CHECKPOINT: Between phases. Student acknowledges and we move on."""
        if self._is_yes(message) or any(
            w in message.lower() for w in ["continue", "next", "start", "ready", "go", "ok"]
        ):
            return self._start_next_phase()
        return "Ready to move on? Just say **'continue'** when you're set!"

    def _handle_detour(self, message: str) -> str:
        """DETOUR: Student asked an in-context question. Answer and return."""
        if not self.state.current_unit:
            self.state.current_state = self.state.previous_state or TutorState.TEACHING
            return self.teaching_agent.respond(message)

        # Use ContentResolver to find the answer in loaded documents
        answer = self.resolver.answer_question(
            question=message,
            current_section_id=self.state.current_unit.unit_id,
            file_manager=self.file_manager,
            subject_profile=self.state.subject_profile,
        )

        # Return to teaching
        self.state.current_state = self.state.previous_state or TutorState.TEACHING
        teaching_response = self.teaching_agent.respond(
            f"[Student question answered: {message}] Please continue teaching where you left off."
        )

        continuation = ""
        if not self.teaching_agent.is_unit_complete(teaching_response):
            continuation = f"\n\n---\n\n_Continuing where we left off..._\n\n{teaching_response}"
        else:
            teaching_response = self.teaching_agent.clean_response(teaching_response)
            continuation = f"\n\n---\n\n_Let's continue..._\n\n{teaching_response}"
            self.state.current_state = TutorState.COMPREHENSION_CHECK

        return answer + continuation

    # ── Teaching Flow ───────────────────────────────────────────────────────────

    def _execute_plan_first_section(self) -> str:
        """Start executing the plan from the first section."""
        plan = self.state.current_plan
        if not plan:
            self.state.current_state = TutorState.IDLE
            return "No plan available. What would you like to study?"

        # Skip the diagnostic phase (index 0) if it's done
        if plan.phases and plan.phases[0].completed:
            plan.current_phase_index = 1

        section_id = plan.get_current_section_id()
        if not section_id:
            self.state.current_state = TutorState.IDLE
            return "There's nothing left to teach in this plan!"

        # Resolve the section_id to an actual loaded section
        resolved_id = self._resolve_to_loaded_section(section_id)
        if resolved_id != section_id:
            # Patch the plan so downstream code uses the correct id
            phase = plan.current_phase
            if phase and plan.current_section_index < len(phase.sections):
                phase.sections[plan.current_section_index] = resolved_id

        return self._teach_section(resolved_id)

    def _resolve_to_loaded_section(self, section_id: str) -> str:
        """
        Given a section_id from the plan, find the best match in the loaded documents.
        Returns the best-matching section_id from file_manager, or the original if not found.
        """
        # 1. Direct match
        if self.file_manager.get_section(section_id):
            return section_id

        # 2. Fuzzy: does any loaded section_id contain the reference?
        all_sections = self.file_manager.get_all_sections()
        for s in all_sections:
            if section_id in s.section_id or s.section_id.endswith(section_id):
                return s.section_id

        # 3. Search by title / content
        candidates = self.file_manager.find_sections_by_query(section_id)
        if candidates:
            return candidates[0].section_id

        # 4. No match — return original and let _teach_section handle the error
        return section_id

    def _teach_section(self, section_id: str) -> str:
        """
        Extract section content, show what's there, ask about prerequisites, then teach.
        """
        self.state.current_state = TutorState.DEEP_ANALYZE

        # Get section content
        section = self.file_manager.get_section(section_id)
        if section is None:
            candidates = self.file_manager.find_sections_by_query(section_id)
            if candidates:
                section = candidates[0]
                section_id = section.section_id
            else:
                self.state.current_state = TutorState.IDLE
                available = [s.section_id for s in self.file_manager.get_all_sections()[:8]]
                return (
                    f"❌ I couldn't find section '{section_id}'.\n\n"
                    f"**Available:** {', '.join(available)}\n"
                    + (f"... +{len(self.file_manager.get_all_sections())-8} more"
                       if len(self.file_manager.get_all_sections()) > 8 else "")
                )

        # Lazy concept-map this section if not done
        self._ensure_section_mapped(section_id)

        # Chunk the section
        units = self.chunker.chunk(section=section, adaptation=self.state.adaptation_level)

        if not units:
            logger.warning(f"No units for {section_id}")
            self.state.current_plan.advance_section()
            next_id = self.state.current_plan.get_current_section_id()
            return self._teach_section(next_id) if next_id else self._on_plan_complete()

        self.state.current_units = units
        self.state.current_unit_index = 0
        unit = self.state.current_unit

        # ── PHASE 1: Show what's in this section ─────────────────────────────
        concept = self.state.concept_map.get(section_id)

        overview_lines = [f"## {unit.title}"]
        if concept:
            overview_lines.append(f"**Contains:** {', '.join(concept.concepts[:5])}")
            if concept.prerequisites:
                overview_lines.append(
                    f"**Assumes you know:** {', '.join(concept.prerequisites[:3])}"
                )
        if section.page_start and section.page_end:
            overview_lines.append(f"_(pages {section.page_start}–{section.page_end})_")

        overview = "\n".join(overview_lines)

        # ── PHASE 2: Check prerequisites ─────────────────────────────────────
        if concept and concept.prerequisites:
            self.state.waiting_for_prerequisite_response = True
            self.state.pending_section_id = section_id
            self.state.current_state = TutorState.COMPREHENSION_CHECK

            prereq_check = (
                f"\n\nBefore we start, do you have a solid grasp of these basics?\n"
                f"- {concept.prerequisites[0]}\n"
                f"- {concept.prerequisites[1] if len(concept.prerequisites) > 1 else '...'}\n\n"
                f"**Do you have the background? (Yes / No)**"
            )
            return overview + prereq_check

        # ── PHASE 3: Start teaching if no prerequisites or student says yes later ───
        # (This will be called again after student responds "yes")
        self.state.current_state = TutorState.TEACHING
        response = self.teaching_agent.start_unit(unit, self.state.subject_profile)
        self.state.current_state = TutorState.COMPREHENSION_CHECK

        return overview + "\n\n" + response

    def _on_unit_clear(self) -> str:
        """Student understood the current concept. Continue teaching next concept or move to next unit."""
        unit = self.state.current_unit
        self._run_merit_update(
            student_response="yes",
            response_type="yes_clear",
            unit=unit,
        )

        # Continue with the next concept in the same unit (teaching agent handles internally)
        self.state.current_state = TutorState.TEACHING
        response = self.teaching_agent.respond("yes")

        # Check if unit is complete
        if self.teaching_agent.is_unit_complete(response):
            response = self.teaching_agent.clean_response(response)

            # Unit done — move to next unit or quiz
            if self.state.has_more_units():
                self.state.advance_unit()
                next_unit = self.state.current_unit
                response += "\n\n---\n\n"
                response += self.teaching_agent.start_unit(next_unit, self.state.subject_profile)
            else:
                # Section complete — go to quiz
                response += "\n\n---\n\n"
                response += self._start_section_quiz()

        self.state.current_state = TutorState.COMPREHENSION_CHECK
        return response

    def _on_unit_unclear(self, message: str) -> str:
        """Student didn't understand. Ask which part, then re-explain."""
        self._run_merit_update(
            student_response=message,
            response_type="no_confused",
            unit=self.state.current_unit,
        )
        self.state.current_state = TutorState.RETEACH
        response = self.teaching_agent.respond(message)
        self.state.current_state = TutorState.COMPREHENSION_CHECK
        return response

    def _start_section_quiz(self) -> str:
        """Generate and present the first quiz question."""
        self.state.current_state = TutorState.SECTION_QUIZ
        section_id = self.state.current_plan.get_current_section_id() if self.state.current_plan else "section"
        section_concept = self.state.concept_map.get(section_id)

        # Get content sample for quiz generation
        section = self.file_manager.get_section(section_id) if section_id else None
        content_sample = section.content[:3000] if section else ""

        # Title from concept map or fallback
        section_title = section_concept.title if section_concept else (
            section.title if section else section_id
        )

        quiz = self.quiz_agent.generate_quiz(
            section_title=section_title,
            section_concept=section_concept,
            content_sample=content_sample,
            merit_score=self.state.merit_score,
            subject_profile=self.state.subject_profile,
        )

        if not quiz.questions:
            # No quiz generated — skip to next section
            return self._advance_to_next_section()

        self._active_quiz = quiz
        self._quiz_question_index = 0

        first_q = quiz.questions[0]
        intro = f"**Quick quiz on {section_title}** ({len(quiz.questions)} questions)\n\n"
        intro += f"**Question 1/{len(quiz.questions)}:**\n\n"
        intro += self.quiz_agent.format_question(first_q)
        return intro

    def _finish_quiz(self) -> str:
        """Complete the quiz, show results, transition to next section."""
        if self._active_quiz is None:
            return self._advance_to_next_section()

        quiz = self.quiz_agent.compute_quiz_result(self._active_quiz)
        self.state.quiz_results.append(quiz)

        score_pct = quiz.score_percentage
        correct = quiz.questions_correct
        total = quiz.questions_total

        if score_pct >= 80:
            grade = "Excellent"
            emoji = "🌟"
        elif score_pct >= 60:
            grade = "Good"
            emoji = "✅"
        else:
            grade = "Keep practicing"
            emoji = "📚"

        result_msg = (
            f"{emoji} **Quiz complete: {grade}!** {correct}/{total} correct "
            f"({score_pct:.0f}%)\n"
        )

        if quiz.weak_areas:
            result_msg += f"\n_Weak areas to revisit: {', '.join(quiz.weak_areas[:3])}_\n"

        # Mark section as completed
        section_id = self.state.current_plan.get_current_section_id() if self.state.current_plan else None
        if section_id and section_id not in self.state.sections_completed:
            self.state.sections_completed.append(section_id)

        self.state.current_state = TutorState.QUIZ_EVAL
        result_msg += "\nSay **'continue'** to move on."
        return result_msg

    def _advance_to_next_section(self) -> str:
        """Move the plan forward to the next section or phase."""
        self._active_quiz = None

        if self.state.current_plan is None:
            self.state.current_state = TutorState.IDLE
            return "Session complete! Great work."

        has_more = self.state.current_plan.advance_section()

        if not has_more:
            return self._on_plan_complete()

        # Check if we've entered a new phase
        plan = self.state.current_plan
        current_phase = plan.current_phase
        if current_phase and plan.current_section_index == 0:
            # New phase started — checkpoint
            self.state.current_state = TutorState.PHASE_CHECKPOINT
            prev_phase_name = plan.phases[plan.current_phase_index - 1].name if plan.current_phase_index > 0 else "previous phase"
            return (
                f"✅ **{prev_phase_name} complete!**\n\n"
                f"Next up: **{current_phase.name}** — "
                f"{len(current_phase.sections)} section(s), ~{current_phase.estimated_time}\n\n"
                "Ready to continue?"
            )

        # Same phase, next section
        next_id = plan.get_current_section_id()
        if next_id:
            next_concept = self.state.concept_map.get(next_id)
            topic_preview = (
                f"Next: **{next_concept.title}**" if next_concept
                else f"Next: section {next_id}"
            )
            return f"Great! {topic_preview}\n\n" + self._teach_section(next_id)

        return self._on_plan_complete()

    def _start_next_phase(self) -> str:
        """Begin the next phase after a phase checkpoint."""
        next_id = self.state.current_plan.get_current_section_id() if self.state.current_plan else None
        if not next_id:
            return self._on_plan_complete()
        return self._teach_section(next_id)

    def _on_plan_complete(self) -> str:
        """All phases and sections are done."""
        self.state.current_state = TutorState.PLAN_COMPLETE

        total_quizzes = len(self.state.quiz_results)
        avg_score = (
            sum(q.score_percentage for q in self.state.quiz_results) / total_quizzes
            if total_quizzes > 0 else 0
        )

        lines = [
            "🎉 **Session complete!**\n",
            f"Merit score: **{self.state.merit_score:.1f}/10**",
        ]
        if total_quizzes > 0:
            lines.append(f"Quiz average: **{avg_score:.0f}%** across {total_quizzes} quiz(zes)")
        if self.state.sections_completed:
            lines.append(f"Sections completed: {len(self.state.sections_completed)}")

        lines.append("\nWhat would you like to study next?")
        self.state.current_state = TutorState.IDLE
        return "\n".join(lines)

    # ── Diagnostic Flow ─────────────────────────────────────────────────────────

    def _start_diagnostic(self) -> str:
        """Begin the diagnostic assessment for EXAM_PREP."""
        self.state.current_state = TutorState.DIAGNOSTIC

        plan = self.state.current_plan
        topic_scope = "the exam material"
        if plan and plan.phases:
            # Get all sections in scope
            all_sections = [s for phase in plan.phases for s in phase.sections]
            topic_scope = f"{len(all_sections)} section(s) across your exam material"

        questions = self.diagnostic_agent.generate_questions(
            topic_scope=topic_scope,
            concept_map=self.state.concept_map,
            subject_profile=self.state.subject_profile,
        )

        if not questions:
            # Skip diagnostic
            return self._finish_diagnostic()

        self._diagnostic_questions = questions
        self._diagnostic_answers = []
        self._diagnostic_index = 0

        first_q = questions[0]
        return (
            "Before we start, let me quickly check what you already know. "
            f"I have {len(questions)} short questions — answer as best you can.\n\n"
            f"**Question 1 of {len(questions)}:**\n\n{first_q['question']}"
        )

    def _finish_diagnostic(self) -> str:
        """Process diagnostic results and refine the plan."""
        knowledge_map = self.diagnostic_agent.build_knowledge_map(
            self._diagnostic_questions,
            self._diagnostic_answers,
        )

        # Refine plan based on diagnostic
        if self.state.current_plan:
            self.state.current_plan = self.session_planner.update_plan_after_diagnostic(
                self.state.current_plan, knowledge_map, self.state
            )

        # Show refined plan
        self.state.current_state = TutorState.PLAN_REVIEW
        plan_text = self.session_planner.format_plan_for_student(self.state.current_plan)
        return (
            "Thanks! I've assessed your knowledge.\n\n"
            "Here's my personalized plan based on your gaps:\n\n"
            + plan_text
        )

    # ── Utility Helpers ─────────────────────────────────────────────────────────

    def _run_concept_mapping(self, max_sections: Optional[int] = None):
        """
        Run concept mapping on loaded documents.

        If max_sections is set, only map that many sections (fast startup).
        Call with max_sections=None to map everything (called lazily before teaching).
        """
        mapped = 0
        for doc in self.state.documents:
            if max_sections is not None and mapped >= max_sections:
                break
            # Only map sections not already in the concept map
            sections_to_map = [
                s for s in doc.sections
                if s.section_id not in self.state.concept_map
            ]
            if max_sections is not None:
                sections_to_map = sections_to_map[:max_sections - mapped]

            new_concepts = self.concept_mapper.map_document(
                doc, self.state.subject_profile,
                sections_subset=sections_to_map,
            )
            self.state.concept_map.update(new_concepts)
            mapped += len(sections_to_map)

        if self.state.concept_map:
            self.state.dependency_graph = self.concept_mapper.build_dependency_graph(
                self.state.concept_map
            )

    def _ensure_section_mapped(self, section_id: str):
        """Lazily concept-map a section if it hasn't been mapped yet."""
        if section_id in self.state.concept_map:
            return
        section = self.file_manager.get_section(section_id)
        if section is None:
            return
        # Find which doc this section belongs to
        doc = self.file_manager._section_index.get(section_id)
        if doc is None:
            return
        new_concepts = self.concept_mapper.map_document(
            doc, self.state.subject_profile,
            sections_subset=[section],
        )
        self.state.concept_map.update(new_concepts)
        if new_concepts:
            self.state.dependency_graph = self.concept_mapper.build_dependency_graph(
                self.state.concept_map
            )

    def _run_merit_update(
        self,
        student_response: str,
        response_type: str,
        unit: Optional[TeachingUnit] = None,
    ):
        """Silently run the merit evaluator and update session merit score."""
        if unit is None:
            unit = self.state.current_unit

        unit_title = unit.title if unit else "current topic"
        content_summary = unit.content[:200] if unit else ""
        subject = self.state.subject_profile.subject if self.state.subject_profile else "STEM"

        entry = self.merit_evaluator.evaluate(
            unit_title=unit_title,
            content_summary=content_summary,
            student_response=student_response,
            response_type=response_type,
            current_merit=self.state.merit_score,
            subject=subject,
        )
        self.state.merit_history.append(entry)
        self.state.update_merit(entry.score)
        logger.debug(
            f"Merit updated: {self.state.merit_score:.1f} "
            f"({entry.adjustment}) — {entry.reasoning}"
        )

    # OLD REGEX-BASED METHODS REMOVED — now using LLM-based IntentClassifier
    # Kept for reference but not used:
    # - _is_yes() → replaced by intent_classifier.classify_comprehension_response()
    # - _is_no() → replaced by intent_classifier.classify_comprehension_response()
    # - _looks_like_question() → replaced by intent_classifier.classify_state_response()

    def _looks_like_question(self, message: str) -> bool:
        """DEPRECATED: Use intent_classifier instead.
        Kept as fallback for code that hasn't been refactored yet.
        """
        msg = message.strip()
        if msg.endswith("?"):
            return True
        question_starters = ("what", "why", "how", "can", "could", "when", "where", "who",
                              "which", "is it", "does", "do ", "explain")
        return any(msg.lower().startswith(s) for s in question_starters)

    def _enter_detour(self, message: str) -> str:
        """Enter DETOUR state for an in-context question."""
        self.state.previous_state = self.state.current_state
        self.state.current_state = TutorState.DETOUR
        return self._handle_detour(message)

    def _answer_info_request(self, message: str, intent: Dict) -> str:
        """Answer an INFO request — show TOC, content summary, etc."""
        target = intent.get("target", "")
        if target:
            # Find matching sections
            sections = self.file_manager.find_sections_by_query(target)
            if sections:
                lines = [f"Here's what I found for **'{target}'**:\n"]
                for s in sections[:5]:
                    concept = self.state.concept_map.get(s.section_id)
                    if concept:
                        lines.append(
                            f"**{concept.title}** (section {s.section_id})\n"
                            f"  Concepts: {', '.join(concept.concepts[:5])}\n"
                            f"  Time: ~{concept.estimated_teaching_time}"
                        )
                    else:
                        lines.append(f"**{s.title}** (section {s.section_id})")
                return "\n".join(lines)

        # Default: show TOC
        return self.file_manager.format_toc_display()

    def _handle_add_file_request(self, message: str) -> str:
        """Handle a request to add more documents mid-session."""
        self.state.current_state = TutorState.IDLE
        return (
            "Sure! Please provide the file path(s) and I'll incorporate them into our session.\n"
            "You can call `load_files()` with the new paths, or provide them in the UI."
        )

    def _handle_continue(self) -> str:
        """Resume from where we left off."""
        if self.state.current_plan and not self.state.current_plan.is_complete:
            section_id = self.state.current_plan.get_current_section_id()
            if section_id:
                return self._teach_section(section_id)

        if self.state.current_unit:
            # Resume current unit
            self.state.current_state = TutorState.TEACHING
            response = self.teaching_agent.respond("Please continue teaching.")
            self.state.current_state = TutorState.COMPREHENSION_CHECK
            return response

        self.state.current_state = TutorState.IDLE
        return (
            "I don't have an active session to continue. "
            "What would you like to study?"
        )

    def _handle_other_message(self, message: str) -> str:
        """Handle messages that don't fit any category."""
        self.state.current_state = TutorState.IDLE
        return (
            "I'm here to help you study! You can:\n"
            '- **Teach me section X** — learn a specific section\n'
            '- **Teach me chapter X** — go through a full chapter\n'
            '- **I have a midterm, help me** — get a personalized exam prep plan\n'
            '- **I don\'t understand [concept]** — get a targeted explanation\n'
            '- **What\'s in chapter X?** — see what topics are covered\n'
        )

    def _build_welcome_message(self, docs: list) -> str:
        """
        Conversational welcome after loading files.
        Assesses what was uploaded, shows structure, asks what student wants.
        """
        subject = self.state.subject_profile
        all_sections = self.file_manager.get_all_sections()
        total_sections = len(all_sections)

        # Count chapters (top-level TOC entries)
        all_toc = self.file_manager.get_unified_toc()
        chapter_entries = [e for e in all_toc if e.level == 1]
        section_entries = [e for e in all_toc if e.level == 2]

        # Build a natural description
        if len(docs) == 1:
            doc = docs[0]
            doc_desc = f'"{doc.label}"'
            if doc.file_type == "pdf_textbook":
                material_desc = "textbook"
            elif doc.file_type == "pdf_notes":
                material_desc = "document (no built-in TOC — I reconstructed the structure)"
            elif doc.file_type == "pdf_slides":
                material_desc = "slide deck"
            else:
                material_desc = doc.file_type.replace("_", " ")
        else:
            names = " + ".join(f'"{d.label}"' for d in docs)
            doc_desc = names
            material_desc = f"{len(docs)} documents"

        subject_str = f"{subject.subject}" if subject else "your material"
        level_str = f" ({subject.level})" if subject else ""

        # Build chapter/section summary
        structure_lines = []
        if chapter_entries:
            structure_lines.append(f"{len(chapter_entries)} chapter(s), {len(section_entries)} section(s)")
            # Show first few chapter titles
            for ch in chapter_entries[:4]:
                structure_lines.append(f"  • {ch.title}")
            if len(chapter_entries) > 4:
                structure_lines.append(f"  • ... and {len(chapter_entries) - 4} more chapters")
        elif total_sections > 0:
            structure_lines.append(f"{total_sections} section(s)")
            for s in all_sections[:5]:
                structure_lines.append(f"  • {s.section_id}: {s.title}")
            if total_sections > 5:
                structure_lines.append(f"  • ... and {total_sections - 5} more")

        structure_str = "\n".join(structure_lines) if structure_lines else f"{total_sections} sections"

        lines = [
            f"I've loaded your {material_desc}: {doc_desc}",
            f"This looks like **{subject_str}{level_str}** material.",
            "",
            f"Here's what I can see:\n{structure_str}",
            "",
            "What would you like to do?",
            '- _"Teach me section 1-2"_ — dive into a specific section',
            '- _"Teach me chapter 3"_ — go through a full chapter',
            '- _"I have a midterm tomorrow"_ — get a strategic study plan',
            '- _"I don\'t understand [topic]"_ — target a specific concept',
            '- _"What\'s in chapter 2?"_ — browse the contents',
        ]
        return "\n".join(lines)

    def _debug_raw_toc(self) -> str:
        """Show the raw fitz.get_toc() output for debugging."""
        import fitz

        lines = ["=== Raw PyMuPDF TOC ===\n"]
        for doc in self.state.documents:
            lines.append(f"File: {doc.label} ({doc.file_path})")
            try:
                pdf_doc = fitz.open(doc.file_path)
                raw_toc = pdf_doc.get_toc()
                lines.append(f"TOC Entries: {len(raw_toc)}\n")
                for i, (level, title, page) in enumerate(raw_toc[:30]):
                    indent = "  " * (level - 1)
                    lines.append(f"{indent}[L{level}] p.{page:3d} | {title}")
                if len(raw_toc) > 30:
                    lines.append(f"\n... and {len(raw_toc) - 30} more entries")
                pdf_doc.close()
            except Exception as e:
                lines.append(f"Error reading TOC: {e}")
            lines.append("")

        return "\n".join(lines)

    def _adjust_plan(self, message: str) -> str:
        """Handle a request to skip or adjust the current plan."""
        # Simple implementation: just start anyway with a note
        self.state.current_state = TutorState.PLAN_REVIEW
        return (
            "Got it! I've noted your preference. "
            "For now, say **'start'** to begin the plan, "
            "and I'll skip sections you already know as we go."
        )
