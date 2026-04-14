"""
QuizAgent — generates and evaluates section-completion quizzes.

Question types (all grounded in actual PDF content):
- easy_mc: Easy multiple choice (recall, warm-up)
- medium_answer: Medium open-answer (requires understanding)
- hard_problem: Multi-step problem requiring real work (presented as MC)
- worked_example: Book example with hint → student solves → compare with official answer

Questions adapt to the student's merit score.
"""

import logging
from datetime import datetime
from typing import List, Optional

from models.data_models import (
    AdaptationLevel, QuizQuestion, QuizResult,
    SectionConcept, SubjectProfile,
)
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

QUIZ_GENERATION_PROMPT = """You are creating a quiz for a {subject} student at the {level} level.

Section just taught: {section_title}
Key concepts covered: {concepts}
Key equations/examples referenced: {references}
Student merit score: {merit}/10

Content used for teaching:
{content_sample}

Generate a quiz appropriate for this student's level. Return ONLY a JSON object:
{{
  "questions": [
    {{
      "question_id": "q1",
      "question_type": "easy_mc",
      "question_text": "...",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct_answer": "A",
      "hint": "",
      "source_example": ""
    }},
    {{
      "question_id": "q2",
      "question_type": "medium_answer",
      "question_text": "...",
      "options": [],
      "correct_answer": "The student should explain...",
      "hint": "Think about...",
      "source_example": ""
    }},
    {{
      "question_id": "q3",
      "question_type": "hard_problem",
      "question_text": "...(include numbers that require calculation)",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct_answer": "B",
      "hint": "Start by...",
      "source_example": ""
    }},
    {{
      "question_id": "q4",
      "question_type": "worked_example",
      "question_text": "Let's work through an example from the material.",
      "options": [],
      "correct_answer": "(full worked solution here)",
      "hint": "First step: ...",
      "source_example": "Example X-Y (page ##)"
    }}
  ]
}}

Rules:
- All questions must be based ONLY on the content above
- MC options must all be plausible (no obviously wrong answers)
- Hard problems must require actual calculation or multi-step reasoning
- Worked examples must reference a specific example from the content with its page number
- If merit < 5: skip the hard_problem, add an extra easy_mc instead
- If merit > 7: make the hard_problem harder, add a bonus challenge question
- Include exactly 3-4 questions total"""

ANSWER_EVALUATION_PROMPT = """You are evaluating a student's answer for a {subject} quiz.

Question: {question_text}
Question type: {question_type}
Correct answer: {correct_answer}
Student's answer: {student_answer}

Evaluate and return ONLY a JSON object:
{{
  "is_correct": true/false,
  "feedback": "Brief, encouraging feedback explaining what was right/wrong and the correct reasoning. 1-2 sentences."
}}

For MC questions: is_correct is true only if the student chose the right option letter.
For open-answer: allow partial credit reasoning, is_correct = true if substantially correct.
For worked examples: is_correct = true if the student's approach and answer are correct."""


class QuizAgent:
    """Generates and evaluates section-completion quizzes."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def generate_quiz(
        self,
        section_title: str,
        section_concept: Optional[SectionConcept],
        content_sample: str,
        merit_score: float,
        subject_profile: Optional[SubjectProfile] = None,
    ) -> QuizResult:
        """Generate a quiz for a completed section."""
        subject = subject_profile.subject if subject_profile else "STEM"
        level = subject_profile.level if subject_profile else "intermediate"

        concepts = ", ".join(section_concept.concepts) if section_concept else "key concepts"
        references = []
        if section_concept:
            references += section_concept.key_equations[:3]
            references += section_concept.key_examples[:2]
        refs_str = ", ".join(references) if references else "concepts from this section"

        prompt = QUIZ_GENERATION_PROMPT.format(
            subject=subject,
            level=level,
            section_title=section_title,
            concepts=concepts,
            references=refs_str,
            merit=round(merit_score, 1),
            content_sample=content_sample[:3000],
        )

        try:
            result = self.llm.get_json_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.4,
            )
            questions = [
                QuizQuestion(
                    question_id=q.get("question_id", f"q{i+1}"),
                    question_text=q.get("question_text", ""),
                    question_type=q.get("question_type", "medium_answer"),
                    correct_answer=q.get("correct_answer", ""),
                    options=q.get("options", []),
                    hint=q.get("hint", ""),
                    source_example=q.get("source_example", ""),
                )
                for i, q in enumerate(result.get("questions", []))
            ]
        except Exception as e:
            logger.error(f"Quiz generation failed: {e}")
            questions = []

        return QuizResult(
            section_id=section_title,
            timestamp=datetime.now(),
            questions=questions,
        )

    def format_question(self, question: QuizQuestion, show_hint: bool = False) -> str:
        """Format a question for display to the student."""
        lines = [f"**{question.question_text}**"]

        if question.question_type == "worked_example":
            lines.append(f"\n📖 Source: {question.source_example}")
            lines.append("\nWork through this problem step by step.")
            lines.append("When you're ready, say **'show solution'** to see the official answer.")
            if show_hint and question.hint:
                lines.append(f"\n💡 Hint: {question.hint}")
        elif question.options:
            lines.append("")
            for opt in question.options:
                lines.append(opt)
            if show_hint and question.hint:
                lines.append(f"\n💡 Hint: {question.hint}")
        else:
            lines.append("\n_(Write your answer in your own words)_")
            if show_hint and question.hint:
                lines.append(f"\n💡 Hint: {question.hint}")

        return "\n".join(lines)

    def evaluate_answer(
        self,
        question: QuizQuestion,
        student_answer: str,
        subject: str = "STEM",
    ) -> QuizQuestion:
        """Evaluate a student's answer and return updated question with feedback."""
        # For worked examples: "show solution" is always accepted
        if question.question_type == "worked_example" and \
                "show solution" in student_answer.lower():
            question.student_answer = student_answer
            question.is_correct = True
            question.feedback = (
                f"Here's the official solution:\n\n{question.correct_answer}"
            )
            return question

        prompt = ANSWER_EVALUATION_PROMPT.format(
            subject=subject,
            question_text=question.question_text,
            question_type=question.question_type,
            correct_answer=question.correct_answer,
            student_answer=student_answer,
        )

        try:
            result = self.llm.get_json_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.2,
            )
            question.student_answer = student_answer
            question.is_correct = result.get("is_correct", False)
            question.feedback = result.get("feedback", "")
        except Exception as e:
            logger.warning(f"Answer evaluation failed: {e}")
            # Simple MC fallback
            if question.options and len(student_answer.strip()) == 1:
                correct_letter = question.correct_answer.strip().upper()[0]
                student_letter = student_answer.strip().upper()[0]
                question.is_correct = (student_letter == correct_letter)
                question.feedback = "Correct!" if question.is_correct else \
                    f"Not quite. The correct answer was {correct_letter}."
            else:
                question.is_correct = False
                question.feedback = "Could not evaluate automatically."

        return question

    def compute_quiz_result(self, quiz: QuizResult) -> QuizResult:
        """Compute final score and weak areas for a completed quiz."""
        answered = [q for q in quiz.questions if q.student_answer is not None]
        if not answered:
            return quiz

        correct = sum(1 for q in answered if q.is_correct)
        quiz.score_percentage = (correct / len(answered)) * 100

        # Mark weak areas from incorrect answers
        for q in answered:
            if not q.is_correct:
                # Use question text as a proxy for the weak area
                short_topic = q.question_text[:60].rstrip(".?!")
                quiz.weak_areas.append(short_topic)

        return quiz
