"""
ContentResolver — answers in-context student questions using loaded documents.

Used during DETOUR state when a student asks a question mid-teaching.
Searches the loaded documents for the relevant content and provides a direct answer.
"""

import logging
from typing import Optional

from models.data_models import SubjectProfile
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

RESOLUTION_PROMPT = """You are a {subject} tutor. A student asked a question while studying.

Question: "{question}"

Relevant content from the study material:
{content}

Answer the question directly and concisely (2-4 sentences max).
Reference specific equations, figures, or examples from the material if relevant.
After answering, the student will continue with their study session.
"""


class ContentResolver:
    """Answers in-context student questions from loaded documents."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def answer_question(
        self,
        question: str,
        current_section_id: str,
        file_manager,
        subject_profile: Optional[SubjectProfile] = None,
    ) -> str:
        """
        Find relevant content and answer the student's question.

        Args:
            question: Student's question
            current_section_id: Section currently being taught (for context)
            file_manager: FileManager instance with loaded documents
            subject_profile: Detected subject profile

        Returns:
            Answer string to show the student
        """
        subject = subject_profile.subject if subject_profile else "STEM"

        # Search for relevant content
        matching_sections = file_manager.find_sections_by_query(question)

        # Fallback to current section
        if not matching_sections:
            current = file_manager.get_section(current_section_id)
            if current:
                matching_sections = [current]

        if not matching_sections:
            return f"_I couldn't find specific content for that question in your materials. Here's what I can offer:_\n\n{self._general_answer(question, subject)}"

        # Compile content from top matches
        content_parts = []
        for section in matching_sections[:2]:
            snippet = section.content[:1000]
            content_parts.append(f"[From {section.title}]:\n{snippet}")

        content = "\n\n".join(content_parts)

        prompt = RESOLUTION_PROMPT.format(
            subject=subject,
            question=question,
            content=content,
        )

        try:
            answer = self.llm.get_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.3,
            )
            return f"**Answer:** {answer}"
        except Exception as e:
            logger.warning(f"Content resolution failed: {e}")
            return f"_Hmm, I couldn't look that up right now. Let's continue and I can revisit this._"

    def _general_answer(self, question: str, subject: str) -> str:
        """Fallback when no relevant content found."""
        try:
            answer = self.llm.get_completion(
                [{"role": "user", "content": f"Answer this {subject} question briefly: {question}"}],
                max_tokens=200,
                temperature=0.3,
            )
            return answer
        except Exception:
            return "I don't have enough context in your loaded materials to answer that question."
