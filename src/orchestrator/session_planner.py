"""
SessionPlanner — creates a TeachingPlan based on the student's request and context.

Handles all request scopes:
- SINGLE_SECTION: "teach me section 1-2"
- CHAPTER: "teach me chapter 3"
- MULTI_CHAPTER: "teach me chapters 1-5"
- EXAM_PREP: "I have a midterm tomorrow"
- TARGETED_CONCEPT: "I don't understand friction"
- INFO: "what's in chapter 2?"
- CONTINUE: "continue from last time"
"""

import logging
import re
from typing import Dict, List, Optional

from models.data_models import (
    DependencyGraph, RequestScope, SectionConcept,
    SessionState, SubjectProfile, TeachingPhase, TeachingPlan,
)
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

INTENT_PROMPT = """Classify this student message into EXACTLY ONE category.

Message: "{message}"

Categories:
- TEACH_SECTION: Student wants to learn a specific section (e.g. "teach me section 1-2", "explain section 3.4")
- TEACH_CHAPTER: Student wants to learn a whole chapter (e.g. "teach me chapter 3", "go through chapter 1")
- TEACH_MULTI: Student wants multiple chapters (e.g. "teach me chapters 1-5", "cover chapters 2 and 3")
- EXAM_PREP: Student has an exam/test and needs help (e.g. "I have a midterm", "exam tomorrow", "help me prepare")
- TARGETED: Student doesn't understand a specific concept (e.g. "I don't understand friction", "explain entropy to me")
- INFO: Student wants information without teaching (e.g. "what's in chapter 2?", "what pages is section 3-1?")
- CONTINUE: Student wants to resume (e.g. "continue", "pick up where we left off", "keep going")
- ADD_FILE: Student wants to add a document (e.g. "here are my notes", "I also have the slides")
- OTHER: None of the above

Also extract the target if present (section number, chapter number, concept name, etc.)

Return ONLY a JSON object:
{{
  "intent": "TEACH_SECTION",
  "target": "1-2",
  "raw_target": "section 1-2"
}}"""


class SessionPlanner:
    """Creates scope-aware TeachingPlans from student requests."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    # ── Intent Classification ───────────────────────────────────────────────

    def classify_intent(self, message: str) -> Dict:
        """Classify student message intent. Returns dict with intent, target, raw_target."""
        try:
            result = self.llm.get_json_completion(
                [{"role": "user", "content": INTENT_PROMPT.format(message=message)}],
                max_tokens=100,
                temperature=0.1,
            )
            return result
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}")
            return {"intent": "OTHER", "target": "", "raw_target": message}

    # ── Plan Creation ───────────────────────────────────────────────────────

    def create_plan(
        self,
        intent: Dict,
        state: SessionState,
    ) -> Optional[TeachingPlan]:
        """
        Create a TeachingPlan based on classified intent and current session state.

        Returns None for INFO, CONTINUE, ADD_FILE, OTHER.
        """
        intent_type = intent.get("intent", "OTHER")
        target = intent.get("target", "")

        if intent_type == "TEACH_SECTION":
            return self._plan_single_section(target, state)
        elif intent_type == "TEACH_CHAPTER":
            return self._plan_chapter(target, state)
        elif intent_type == "TEACH_MULTI":
            return self._plan_multi_chapter(target, state)
        elif intent_type == "EXAM_PREP":
            return self._plan_exam_prep(intent.get("raw_target", ""), state)
        elif intent_type == "TARGETED":
            return self._plan_targeted_concept(target or intent.get("raw_target", ""), state)

        return None

    def _plan_single_section(self, section_ref: str, state: SessionState) -> TeachingPlan:
        """Plan for a single section request."""
        section_ids = self._resolve_section_ids(section_ref, state)

        # Check for prerequisite gaps
        gap_ids = []
        if state.dependency_graph and state.sections_completed:
            gap_ids = state.dependency_graph.find_gaps(
                state.sections_completed, section_ids
            ) if section_ids else []

        phases = []
        if gap_ids:
            phases.append(TeachingPhase(
                name="Quick Prerequisite Review",
                sections=gap_ids,
                estimated_time=self._estimate_time(gap_ids, state),
                priority="critical",
            ))

        phases.append(TeachingPhase(
            name=f"Section {section_ref}",
            sections=section_ids,
            estimated_time=self._estimate_time(section_ids, state),
            priority="critical",
        ))

        return TeachingPlan(
            scope=RequestScope.SINGLE_SECTION,
            phases=phases,
            estimated_total_time=self._estimate_time(gap_ids + section_ids, state),
        )

    def _plan_chapter(self, chapter_ref: str, state: SessionState) -> TeachingPlan:
        """Plan for a full chapter — groups sections into logical phases."""
        section_ids = self._get_chapter_sections(chapter_ref, state)

        if not section_ids:
            # Fallback: treat as targeted concept
            return self._plan_targeted_concept(chapter_ref, state)

        # Group into phases: Foundation, Core, Applications
        total = len(section_ids)
        if total <= 2:
            phases = [TeachingPhase(
                name=f"Chapter {chapter_ref}",
                sections=section_ids,
                estimated_time=self._estimate_time(section_ids, state),
                priority="critical",
            )]
        else:
            # Split roughly into thirds
            third = max(1, total // 3)
            foundation = section_ids[:third]
            core = section_ids[third:third * 2]
            applications = section_ids[third * 2:]

            phases = [
                TeachingPhase(
                    name="Foundations",
                    sections=foundation,
                    estimated_time=self._estimate_time(foundation, state),
                    priority="critical",
                ),
                TeachingPhase(
                    name="Core Theory",
                    sections=core,
                    estimated_time=self._estimate_time(core, state),
                    priority="critical",
                ),
            ]
            if applications:
                phases.append(TeachingPhase(
                    name="Applications & Examples",
                    sections=applications,
                    estimated_time=self._estimate_time(applications, state),
                    priority="important",
                ))

        return TeachingPlan(
            scope=RequestScope.CHAPTER,
            phases=phases,
            estimated_total_time=self._estimate_time(section_ids, state),
        )

    def _plan_multi_chapter(self, chapters_ref: str, state: SessionState) -> TeachingPlan:
        """Plan for multiple chapters — same as chapter but larger scope."""
        chapter_refs = self._parse_chapter_range(chapters_ref)
        all_sections = []
        chapter_phases = []

        for ch_ref in chapter_refs:
            ch_sections = self._get_chapter_sections(ch_ref, state)
            if ch_sections:
                all_sections.extend(ch_sections)
                chapter_phases.append(TeachingPhase(
                    name=f"Chapter {ch_ref}",
                    sections=ch_sections,
                    estimated_time=self._estimate_time(ch_sections, state),
                    priority="critical",
                ))

        return TeachingPlan(
            scope=RequestScope.MULTI_CHAPTER,
            phases=chapter_phases,
            estimated_total_time=self._estimate_time(all_sections, state),
        )

    def _plan_exam_prep(self, raw_request: str, state: SessionState) -> TeachingPlan:
        """
        Exam prep plan — requires diagnostic first, then strategic prioritization.

        The diagnostic results are filled in later by DiagnosticAgent.
        Returns a plan that will be updated after diagnostic.
        """
        # Get all sections in scope
        all_section_ids = list(state.concept_map.keys()) if state.concept_map else []

        # Sort by dependency order
        if state.dependency_graph:
            all_section_ids = state.dependency_graph.get_teaching_order(all_section_ids)

        phases = [TeachingPhase(
            name="Diagnostic Assessment",
            sections=[],  # No sections — diagnostic runs first
            estimated_time="5-10 min",
            priority="critical",
        )]

        if all_section_ids:
            phases.append(TeachingPhase(
                name="Priority Topics",  # Will be refined after diagnostic
                sections=all_section_ids,
                estimated_time=self._estimate_time(all_section_ids, state),
                priority="critical",
            ))

        return TeachingPlan(
            scope=RequestScope.EXAM_PREP,
            phases=phases,
            estimated_total_time="1-2 hours",
        )

    def update_plan_after_diagnostic(
        self,
        plan: TeachingPlan,
        knowledge_map: Dict[str, float],
        state: SessionState,
    ) -> TeachingPlan:
        """
        Refine an EXAM_PREP plan after diagnostic results are known.

        Skips strong areas (mastery > 0.8) and reorders by impact.
        """
        skip_concepts = [c for c, m in knowledge_map.items() if m >= 0.8]
        weak_concepts = [c for c, m in knowledge_map.items() if m < 0.5]

        # Map concepts to section IDs
        def concept_to_sections(concepts):
            result = []
            for c in concepts:
                for sid, sc in state.concept_map.items():
                    if c in sc.concepts and sid not in result:
                        result.append(sid)
            return result

        skip_sections = concept_to_sections(skip_concepts)
        weak_sections = concept_to_sections(weak_concepts)

        # Get all sections with dependency order
        all_ids = list(state.concept_map.keys())
        if state.dependency_graph:
            all_ids = state.dependency_graph.get_teaching_order(all_ids)

        # Filter: skip what student knows
        teachable = [sid for sid in all_ids if sid not in skip_sections]

        # Split into phases: critical gaps first, then remaining
        critical = [sid for sid in teachable if sid in weak_sections]
        remaining = [sid for sid in teachable if sid not in weak_sections]

        phases = [
            TeachingPhase(
                name="Diagnostic Assessment",
                sections=[],
                estimated_time="Done",
                priority="critical",
                completed=True,  # Already done
            )
        ]

        if critical:
            phases.append(TeachingPhase(
                name="Critical Gaps (Highest Priority)",
                sections=critical,
                estimated_time=self._estimate_time(critical, state),
                priority="critical",
            ))

        if remaining:
            phases.append(TeachingPhase(
                name="Important Topics",
                sections=remaining,
                estimated_time=self._estimate_time(remaining, state),
                priority="important",
            ))

        plan.phases = phases
        plan.skip_list = skip_sections
        plan.priority_concepts = weak_concepts
        plan.diagnostic_results = knowledge_map
        plan.current_phase_index = 1 if phases[0].completed else 0
        plan.estimated_total_time = self._estimate_time(critical + remaining, state)

        return plan

    def _plan_targeted_concept(self, concept_ref: str, state: SessionState) -> TeachingPlan:
        """Plan for a specific concept the student doesn't understand."""
        # Search for the concept in the concept map
        matching_sections = []
        for sid, sc in state.concept_map.items():
            if any(concept_ref.lower() in c.lower() for c in sc.concepts) or \
               concept_ref.lower() in sc.title.lower():
                matching_sections.append(sid)

        if not matching_sections:
            # Fallback: show all available sections
            matching_sections = list(state.concept_map.keys())[:3]

        # Check prerequisites
        gap_ids = []
        if state.dependency_graph:
            gap_ids = state.dependency_graph.find_gaps(
                state.sections_completed, matching_sections
            )

        phases = []
        if gap_ids:
            phases.append(TeachingPhase(
                name="Prerequisites First",
                sections=gap_ids,
                estimated_time=self._estimate_time(gap_ids, state),
                priority="critical",
            ))

        phases.append(TeachingPhase(
            name=f'Understanding "{concept_ref}"',
            sections=matching_sections,
            estimated_time=self._estimate_time(matching_sections, state),
            priority="critical",
        ))

        return TeachingPlan(
            scope=RequestScope.TARGETED_CONCEPT,
            phases=phases,
            estimated_total_time=self._estimate_time(gap_ids + matching_sections, state),
        )

    # ── Plan Formatting ─────────────────────────────────────────────────────

    def format_plan_for_student(self, plan: TeachingPlan) -> str:
        """Format a teaching plan as a readable message for the student."""
        if not plan.phases:
            return "I'll start teaching right away."

        lines = ["Here's my plan:\n"]
        active_phases = [p for p in plan.phases if not p.completed]

        for i, phase in enumerate(active_phases):
            time_str = f" (~{phase.estimated_time})" if phase.estimated_time else ""
            priority_marker = "⚡" if phase.priority == "critical" else "📚"
            lines.append(f"{priority_marker} **Phase {i+1}: {phase.name}**{time_str}")
            if phase.sections:
                # Show concept names rather than raw section IDs
                lines.append(f"   {len(phase.sections)} topic(s) to cover")

        if plan.skip_list:
            lines.append(f"\n✅ Skipping {len(plan.skip_list)} topic(s) you already know well.")

        if plan.estimated_total_time:
            lines.append(f"\n⏱️ Estimated total: {plan.estimated_total_time}")

        lines.append("\nReady to start, or want to adjust this plan?")
        return "\n".join(lines)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _resolve_section_ids(self, section_ref: str, state: SessionState) -> List[str]:
        """Find section IDs matching a reference like '1-2', 'section 3.4'."""
        clean_ref = section_ref.lower().replace("section", "").strip()

        # Direct match
        if clean_ref in state.concept_map:
            return [clean_ref]

        # Partial match
        matches = [
            sid for sid in state.concept_map
            if clean_ref in sid.lower()
        ]
        if matches:
            return matches[:1]

        # Try to find in file manager sections via title
        return [clean_ref] if clean_ref else []

    def _get_chapter_sections(self, chapter_ref: str, state: SessionState) -> List[str]:
        """Get all section IDs belonging to a chapter."""
        clean_ref = re.sub(r'[^0-9]', '', chapter_ref)

        sections = [
            sid for sid in state.concept_map
            if sid.startswith(f"{clean_ref}-") or sid.startswith(f"{clean_ref}.")
        ]

        # Order by dependency
        if sections and state.dependency_graph:
            sections = state.dependency_graph.get_teaching_order(sections)

        return sections

    def _parse_chapter_range(self, chapters_ref: str) -> List[str]:
        """Parse '1-5' or '1,3,5' or '2 and 3' into chapter number list."""
        # Range like "1-5"
        range_match = re.search(r'(\d+)\s*[-–to]+\s*(\d+)', chapters_ref)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            return [str(i) for i in range(start, end + 1)]

        # List like "1, 3, 5" or "1 and 3"
        nums = re.findall(r'\d+', chapters_ref)
        return nums if nums else []

    def _estimate_time(self, section_ids: List[str], state: SessionState) -> str:
        """Estimate teaching time based on concept map data."""
        total_minutes = 0
        for sid in section_ids:
            sc = state.concept_map.get(sid)
            if sc:
                time_str = sc.estimated_teaching_time
                mins = re.search(r'(\d+)', time_str)
                total_minutes += int(mins.group(1)) if mins else 15
            else:
                total_minutes += 15  # default

        if total_minutes < 60:
            return f"{total_minutes} min"
        hours = total_minutes // 60
        mins = total_minutes % 60
        return f"{hours}h {mins}min" if mins else f"{hours}h"
