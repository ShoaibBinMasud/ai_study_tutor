"""
Gemini LLM Client — drop-in replacement for LLMClient using the google-genai SDK.

Returns responses in OpenAI-compatible format so existing agent code works
without changes (accesses response["choices"][0]["message"]["content"]).

Used by PlannerAgent for its larger context window and faster throughput.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logger = logging.getLogger(__name__)


class GeminiLLMClient:
    """
    Gemini API client with an OpenAI-compatible chat() interface.

    Converts OpenAI-style message lists to Gemini's content format,
    calls the Gemini SDK, then wraps the response in the OpenAI
    response shape so PlannerAgent can use it without modification.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash-lite",
    ):
        api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or arguments")
        self.model = model
        self.client = genai.Client(api_key=api_key)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 8000,
        temperature: float = 0.1,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        response_format: Optional[Dict] = None,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """
        Send a chat request to Gemini and return an OpenAI-compatible response dict.
        """
        system_text, contents = self._convert_messages(messages)

        response_mime_type = None
        if response_format and response_format.get("type") == "json_object":
            response_mime_type = "application/json"

        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system_text if system_text else None,
            response_mime_type=response_mime_type,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        text = response.text or ""
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": text,
                        "tool_calls": None,
                    },
                    "finish_reason": "stop",
                }
            ]
        }

    # ── Conversion helpers ────────────────────────────────────────────────────

    @staticmethod
    def _convert_messages(messages: List[Dict[str, Any]]):
        """
        Split OpenAI messages into:
          - system_text: concatenated system message text (for system_instruction)
          - contents: list of Gemini Content objects

        Role mapping: "assistant" → "model", "system" → extracted separately.
        """
        system_parts: List[str] = []
        contents: List[types.Content] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content") or ""

            if role == "system":
                if isinstance(content, str):
                    system_parts.append(content)
                continue

            gemini_role = "model" if role == "assistant" else "user"

            if isinstance(content, str):
                parts = [types.Part(text=content)] if content else [types.Part(text="")]
            elif isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(types.Part(text=item["text"]))
                    else:
                        parts.append(types.Part(text=str(item)))
            else:
                parts = [types.Part(text=str(content))]

            # Gemini requires alternating user/model turns — merge consecutive same-role messages
            if contents and contents[-1].role == gemini_role:
                contents[-1].parts.extend(parts)
            else:
                contents.append(types.Content(role=gemini_role, parts=parts))

        # Gemini requires the conversation to end on a user turn
        if not contents or contents[-1].role != "user":
            contents.append(types.Content(role="user", parts=[types.Part(text="Continue.")]))

        return "\n\n".join(system_parts), contents
