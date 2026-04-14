"""
DiagnosticAgent — assesses what the student already knows before large-scope sessions.

Used for: EXAM_PREP and MULTI_CHAPTER scope requests.
Asks 5-8 targeted gateway questions covering key concepts.
Builds a knowledge map: {concept → mastery_percentage}
This feeds into the Session Planner to skip known areas and prioritize gaps.
"""

import logging
from typing import Dict, List, Optional, Tuple

from models.data_models import SectionConcept, SubjectProfile
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

DIAGNOSTIC_QUESTION_PROMPT = """You are designing a quick diagnostic assessment for a {subject} student.

They are about to study: {topic_scope}

Key concepts in this material:
{concepts_list}

Design 5-7 short diagnostic questions that together reveal what the student knows.
- Each question should target a GATEWAY concept (one that many others depend on)
- Questions should be answerable in 1-2 sentences or a brief calculation
- Vary difficulty: include 2 easy, 2 medium, 2 hard questions
- Order from easier to harder

Return ONLY a JSON array:
[
  {{
    "concept": "concept being tested",
    "question": "the question to ask",
    "difficulty": "easy | medium | hard",
    "correct_answer_guide": "what a correct answer would include"
  }}
]"""

ANSWER_ASSESSMENT_PROMPT = """Assess this student's answer to a {subject} diagnostic question.

Question: {question}
Concept being tested: {concept}
What a correct answer would include: {correct_guide}
Student's answer: "{student_answer}"

Return ONLY a JSON object:
{{
  "mastery": <0.0 to 1.0>,
  "feedback": "<brief, encouraging, 1 sentence>"
}}

Mastery guide: 0.0=no knowledge, 0.3=vague memory, 0.6=partial understanding, 0.8=solid, 1.0=expert"""


class DiagnosticAgent:
    """Runs a quick diagnostic to assess student knowledge before teaching."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def generate_questions(
        self,
        topic_scope: str,
        concept_map: Dict[str, SectionConcept],
        subject_profile: Optional[SubjectProfile] = None,
    ) -> List[Dict]:
        """
        Generate diagnostic questions for the given scope.

        Returns a list of question dicts with: concept, question, difficulty,
        correct_answer_guide.
        """
        subject = subject_profile.subject if subject_profile else "STEM"

        # Collect key concepts from the concept map
        all_concepts = []
        for sc in concept_map.values():
            for concept in sc.concepts:
                all_concepts.append(f"- {concept} (from '{sc.title}')")

        concepts_list = "\n".join(all_concepts[:30]) if all_concepts else "Key STEM concepts"

        prompt = DIAGNOSTIC_QUESTION_PROMPT.format(
            subject=subject,
            topic_scope=topic_scope,
            concepts_list=concepts_list,
        )

        try:
            questions = self.llm.get_json_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.3,
            )
            if isinstance(questions, list):
                return questions
        except Exception as e:
            logger.error(f"Diagnostic question generation failed: {e}")

        return []

    def assess_answer(
        self,
        question: Dict,
        student_answer: str,
        subject: str = "STEM",
    ) -> Tuple[float, str]:
        """
        Assess one diagnostic answer.

        Returns (mastery_score 0.0-1.0, feedback_text).
        """
        prompt = ANSWER_ASSESSMENT_PROMPT.format(
            subject=subject,
            question=question.get("question", ""),
            concept=question.get("concept", ""),
            correct_guide=question.get("correct_answer_guide", ""),
            student_answer=student_answer[:500],
        )

        try:
            result = self.llm.get_json_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1,
            )
            mastery = float(result.get("mastery", 0.5))
            mastery = max(0.0, min(1.0, mastery))
            feedback = result.get("feedback", "")
            return mastery, feedback
        except Exception as e:
            logger.warning(f"Diagnostic answer assessment failed: {e}")
            return 0.5, "Got it, let's continue."

    def build_knowledge_map(
        self,
        questions: List[Dict],
        answers: List[Tuple[float, str]],
    ) -> Dict[str, float]:
        """Build concept → mastery_percentage map from diagnostic results."""
        knowledge_map: Dict[str, float] = {}
        for question, (mastery, _) in zip(questions, answers):
            concept = question.get("concept", "unknown")
            knowledge_map[concept] = mastery
        return knowledge_map
