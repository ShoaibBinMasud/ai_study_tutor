"""
MeritEvaluator — silently scores student understanding after each interaction.

The student never sees this agent's output directly.
Runs one LLM call after each yes/no check and each quiz answer.
Output feeds into AdaptationLevel which controls future chunk sizes.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from models.data_models import AdaptationLevel, MeritEntry
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

MERIT_PROMPT = """You are assessing a student's understanding of {subject} content.

Context of recent interaction:
- Teaching unit: {unit_title}
- What was taught: {content_summary}
- Student response: "{student_response}"
- Response type: {response_type}
- Previous merit score: {current_merit}/10

Assess the student's understanding and return ONLY a JSON object:
{{
  "score": <float 1-10>,
  "reasoning": "<one sentence explaining the score>",
  "adjustment": "<slower | normal | faster>"
}}

Scoring guide:
- 1-3: Student is very confused, needs much slower pace and more examples
- 4-5: Student has gaps but is trying; slightly slower pace would help
- 6-7: Student understands adequately; normal pace is fine
- 8-9: Student understands well; can go faster with larger chunks
- 10: Student is excelling; can skip simpler material

Response type context:
- "yes_clear": Student said yes this is clear → score based on how much you trust that
- "no_confused": Student said no and explained what confused them → lower score, note the topic
- "question_asked": Student asked a follow-up question → assess question quality
- "quiz_correct": Student answered a quiz question correctly
- "quiz_incorrect": Student answered a quiz question incorrectly
- "quiz_partial": Student partially answered a quiz question"""


class MeritEvaluator:
    """Silent LLM-based merit scorer."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def evaluate(
        self,
        unit_title: str,
        content_summary: str,
        student_response: str,
        response_type: str,
        current_merit: float,
        subject: str = "STEM",
    ) -> MeritEntry:
        """
        Evaluate student understanding.

        Args:
            unit_title: What was being taught
            content_summary: Brief summary of content (first 200 chars of unit content)
            student_response: What the student said
            response_type: One of: yes_clear, no_confused, question_asked,
                          quiz_correct, quiz_incorrect, quiz_partial
            current_merit: Current merit score (1-10)
            subject: Detected subject name

        Returns:
            MeritEntry with score and adjustment
        """
        prompt = MERIT_PROMPT.format(
            subject=subject,
            unit_title=unit_title,
            content_summary=content_summary[:200],
            student_response=student_response[:300],
            response_type=response_type,
            current_merit=round(current_merit, 1),
        )

        try:
            result = self.llm.get_json_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.2,
            )

            score = float(result.get("score", current_merit))
            # Clamp to valid range
            score = max(1.0, min(10.0, score))

            return MeritEntry(
                timestamp=datetime.now(),
                unit_id=unit_title,
                score=score,
                reasoning=result.get("reasoning", ""),
                adjustment=result.get("adjustment", "normal"),
            )

        except Exception as e:
            logger.warning(f"Merit evaluation failed: {e}")
            # Fallback: simple heuristic
            if response_type == "yes_clear":
                score = min(current_merit + 0.3, 10.0)
            elif response_type in ("no_confused", "quiz_incorrect"):
                score = max(current_merit - 0.5, 1.0)
            else:
                score = current_merit

            return MeritEntry(
                timestamp=datetime.now(),
                unit_id=unit_title,
                score=score,
                reasoning="Heuristic fallback",
                adjustment=AdaptationLevel.from_merit(score).value,
            )
