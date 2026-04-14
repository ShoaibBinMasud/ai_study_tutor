"""
Shared LLM Client for the AI STEM Tutor.

Consolidates all OpenAI API calls into one utility used by all agents.
Supports both regular chat completions and tool-calling.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

try:
    import tiktoken
    _tiktoken_available = True
except ImportError:
    _tiktoken_available = False

def _count_tokens(messages: List[Dict], model: str) -> int:
    """Count input tokens using tiktoken. Falls back to character estimate if unavailable."""
    if not _tiktoken_available:
        return sum(len(str(m.get("content", ""))) // 4 for m in messages)
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(enc.encode(content))
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total += len(enc.encode(block.get("text", "")))
        total += 4  # per-message overhead
    return total


class LLMClient:
    """Shared client for all LLM calls across the tutor system."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_url: str = "https://api.openai.com/v1/chat/completions",
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment or arguments")
        self.model = model or os.getenv("TUTOR_MODEL", "gpt-4o-mini")
        self.api_url = api_url

    def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.5,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        response_format: Optional[Dict] = None,
        timeout: int = 90,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request.

        Args:
            messages: Conversation messages (system, user, assistant roles)
            max_tokens: Maximum tokens in response
            temperature: Randomness (0=deterministic, 1=creative)
            tools: Optional tool definitions for function calling
            tool_choice: Optional tool choice strategy ("auto", "none", etc.)
            response_format: Optional response format (e.g., {"type": "json_object"})

        Returns:
            Full API response dict
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        import time as _time
        max_retries = 4
        backoff = 2  # seconds, doubles each retry

        input_tokens = _count_tokens(messages, self.model)
        logger.info(f"[TOKENS] model={self.model}  input≈{input_tokens:,}  max_out={max_tokens:,}")

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage", {})
                if usage:
                    logger.info(
                        f"[TOKENS] actual  in={usage.get('prompt_tokens',0):,}  "
                        f"out={usage.get('completion_tokens',0):,}  "
                        f"total={usage.get('total_tokens',0):,}"
                    )
                return data
            except requests.exceptions.Timeout:
                logger.error("LLM API request timed out")
                raise
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code
                logger.error(f"LLM API HTTP error: {status} - {e.response.text}")
                if status == 429 and attempt < max_retries - 1:
                    wait = backoff * (2 ** attempt)
                    logger.warning(f"Rate limited. Retrying in {wait}s (attempt {attempt + 1}/{max_retries})...")
                    _time.sleep(wait)
                    continue
                raise
            except Exception as e:
                logger.error(f"LLM API error: {e}")
                raise

    def get_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.5,
    ) -> str:
        """Convenience method: get just the text content from a chat completion."""
        response = self.chat(messages, max_tokens=max_tokens, temperature=temperature)
        return response["choices"][0]["message"]["content"]

    def get_json_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.3,
    ) -> Any:
        """Convenience method: get a parsed JSON response."""
        response = self.chat(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"]["content"]
        return json.loads(content)

    def get_vision_completion(
        self,
        image_b64: str,
        prompt: str,
        mime_type: str = "image/png",
        max_tokens: int = 3000,
        temperature: float = 0.1,
    ) -> str:
        """Send a single image + text prompt, return text response."""
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
            ],
        }]
        return self.get_completion(messages, max_tokens=max_tokens, temperature=temperature)
