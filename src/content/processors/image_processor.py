"""
Image Processor — handwritten notes, whiteboard photos, scanned pages.

Uses vision LLM to extract text and structure from images.
Falls back gracefully if vision API is unavailable.
"""

import base64
import logging
import os
import re
from pathlib import Path
from typing import List

from models.data_models import ProcessedDocument, TOCEntry, Section
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

VISION_PROMPT = """Analyze this image which appears to be a student's study material
(handwritten notes, whiteboard, or scanned page).

Extract ALL content and structure it as follows:
1. Identify any visible headings or topics
2. Extract all text, equations, and key points
3. Describe any diagrams or figures briefly

Return a JSON object:
{
  "title": "main topic or heading visible",
  "sections": [
    {
      "heading": "section heading or topic",
      "content": "full text content of this section including equations"
    }
  ],
  "has_equations": true/false,
  "has_diagrams": true/false,
  "subject_hints": "any clues about subject (e.g., physics equations, chemical formulas)"
}"""


class ImageProcessor:
    """Processes image files (PNG, JPG, WEBP) into ProcessedDocument format."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def process(self, file_path: str) -> ProcessedDocument:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {file_path}")

        label = path.stem.replace("_", " ").replace("-", " ").title()

        try:
            extracted = self._extract_with_vision(file_path)
        except Exception as e:
            logger.warning(f"Vision extraction failed for {file_path}: {e}")
            extracted = {"title": label, "sections": [{"heading": label, "content": ""}]}

        toc_entries = []
        sections = []
        doc_title = extracted.get("title", label)

        for i, sec in enumerate(extracted.get("sections", [])):
            section_id = f"img_{path.stem}_sec{i+1}"
            heading = sec.get("heading", f"Section {i+1}")
            content = sec.get("content", "")

            toc_entries.append(TOCEntry(
                title=heading,
                level=2,
                page_or_slide=i + 1,
                source_file=file_path,
                section_id=section_id,
            ))
            sections.append(Section(
                section_id=section_id,
                title=heading,
                content=content,
                page_start=1,
                page_end=1,
                source_file=file_path,
            ))

        if not sections:
            sections.append(Section(
                section_id=f"img_{path.stem}",
                title=doc_title,
                content="",
                page_start=1,
                page_end=1,
                source_file=file_path,
            ))

        return ProcessedDocument(
            file_path=file_path,
            file_type="image",
            label=label,
            toc=toc_entries,
            sections=sections,
        )

    def _extract_with_vision(self, file_path: str) -> dict:
        """Send image to vision LLM and parse response."""
        with open(file_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        ext = Path(file_path).suffix.lower().lstrip(".")
        mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png", "webp": "image/webp"}
        mime_type = mime_map.get(ext, "image/png")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_data}"},
                    },
                ],
            }
        ]

        return self.llm.get_json_completion(messages, max_tokens=2000, temperature=0.1)
