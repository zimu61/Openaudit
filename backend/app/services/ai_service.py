import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod

import openai
import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)


def _strip_json_comments(text: str) -> str:
    """Remove single-line // comments from JSON-like text (outside of strings)."""
    result = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if in_string:
            result.append(ch)
            if ch == '\\' and i + 1 < len(text):
                i += 1
                result.append(text[i])
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            result.append(ch)
        elif ch == '/' and i + 1 < len(text) and text[i + 1] == '/':
            # Skip until end of line
            while i < len(text) and text[i] != '\n':
                i += 1
            continue
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def _repair_truncated_json(text: str) -> dict | list | None:
    """Best-effort repair of truncated JSON (e.g. AI response cut off mid-string)."""
    # Find the first { or [
    start = -1
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break
    if start < 0:
        return None

    fragment = text[start:]

    # Walk the fragment tracking structure
    stack = []
    in_string = False
    i = 0
    last_complete = 0  # position after last complete value/structure

    while i < len(fragment):
        ch = fragment[i]
        if in_string:
            if ch == '\\' and i + 1 < len(fragment):
                i += 2
                continue
            if ch == '"':
                in_string = False
                last_complete = i + 1
        else:
            if ch == '"':
                in_string = True
            elif ch in ('{', '['):
                stack.append('}' if ch == '{' else ']')
            elif ch in ('}', ']'):
                if stack and stack[-1] == ch:
                    stack.pop()
                    last_complete = i + 1
        i += 1

    if not stack:
        # JSON was actually complete, shouldn't reach here but try anyway
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            return None

    # Truncate to last complete position, clean trailing comma/whitespace, close
    base = fragment[:last_complete].rstrip(', \t\n\r')
    suffix = ''.join(reversed(stack))

    for candidate in [base + suffix, fragment.rstrip(', \t\n\r') + suffix]:
        cleaned = _strip_json_comments(candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            continue

    return None


def _extract_json(text: str) -> dict | list | None:
    """Extract JSON from AI response that may contain markdown or extra text."""
    if not text or not text.strip():
        return None

    # 1. Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences: ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        inner = match.group(1).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            pass
        # Try stripping // comments inside the fenced block
        try:
            return json.loads(_strip_json_comments(inner))
        except json.JSONDecodeError:
            pass

    # 3. Find first { ... } or [ ... ] block using raw_decode
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                result, _ = decoder.raw_decode(text[i:])
                return result
            except json.JSONDecodeError:
                pass
            # Try after stripping // comments
            try:
                cleaned = _strip_json_comments(text[i:])
                result, _ = decoder.raw_decode(cleaned)
                return result
            except json.JSONDecodeError:
                continue

    # 4. Last resort: try repairing truncated JSON
    repaired = _repair_truncated_json(text)
    if repaired is not None:
        return repaired

    return None


class AIProvider(ABC):
    @abstractmethod
    async def analyze(self, messages: list[dict], model: str) -> str:
        """Send messages to AI and return the response text."""
        ...


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, base_url: str | None = None):
        kwargs = {"api_key": api_key, "timeout": 120.0}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = openai.AsyncOpenAI(**kwargs)
        self._supports_json_mode = base_url is None  # Only native OpenAI guaranteed

    async def analyze(self, messages: list[dict], model: str) -> str:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        if self._supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        logger.info(f"Calling OpenAI API (model={model})...")
        response = await self.client.chat.completions.create(**kwargs)
        logger.info("OpenAI API response received")
        return response.choices[0].message.content or ""


class ClaudeProvider(AIProvider):
    def __init__(self, api_key: str):
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=120.0)

    async def analyze(self, messages: list[dict], model: str) -> str:
        # Convert from OpenAI format to Claude format
        system_msg = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                user_messages.append(msg)

        logger.info(f"Calling Claude API (model={model})...")
        response = await self.client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_msg,
            messages=user_messages,
            temperature=0.1,
        )
        logger.info("Claude API response received")
        return response.content[0].text


class AIService:
    def __init__(self):
        self.provider = self._create_provider()
        self.model = settings.get_ai_model()
        self._semaphore = asyncio.Semaphore(settings.AI_MAX_CONCURRENT)
        self._max_retries = 3

    def _create_provider(self) -> AIProvider:
        if settings.AI_PROVIDER == "claude":
            return ClaudeProvider(settings.ANTHROPIC_API_KEY)
        if settings.AI_PROVIDER == "openai_compatible":
            if not settings.OPENAI_BASE_URL:
                raise ValueError("OPENAI_BASE_URL is required when AI_PROVIDER=openai_compatible")
            if not settings.AI_MODEL:
                raise ValueError("AI_MODEL is required when AI_PROVIDER=openai_compatible")
            return OpenAIProvider(
                settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )
        # Default: native OpenAI
        return OpenAIProvider(settings.OPENAI_API_KEY)

    async def _call_with_retry(self, messages: list[dict]) -> str:
        """Call AI provider with retry and rate limiting."""
        async with self._semaphore:
            last_error = None
            for attempt in range(self._max_retries):
                try:
                    logger.info(f"AI call attempt {attempt + 1}/{self._max_retries} (provider={settings.AI_PROVIDER}, model={self.model})")
                    return await self.provider.analyze(messages, self.model)
                except Exception as e:
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning(
                        f"AI call failed (attempt {attempt + 1}/{self._max_retries}): {e}. "
                        f"Retrying in {wait}s..."
                    )
                    await asyncio.sleep(wait)
            raise RuntimeError(f"AI call failed after {self._max_retries} retries: {last_error}")

    async def identify_sources(
        self, method_snippets: list[dict], candidates: dict, file_path: str
    ) -> list[int]:
        """Identify which candidates are user-controlled sources."""
        from app.prompts.source_identification import build_source_identification_prompt

        messages = build_source_identification_prompt(method_snippets, candidates, file_path)
        response = await self._call_with_retry(messages)

        result = _extract_json(response)
        if result is None:
            logger.error(f"Failed to extract JSON from AI response: {response[:300]}")
            return []

        try:
            source_ids = result.get("source_ids", [])
            return [int(sid) for sid in source_ids]
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Failed to parse source_ids from AI response: {e}, response: {response[:300]}")
            return []

    async def analyze_vulnerability(
        self, source_info: dict, flow: dict, code_snippets: str
    ) -> dict:
        """Analyze a data flow for vulnerabilities."""
        from app.prompts.vulnerability_analysis import build_vulnerability_analysis_prompt

        messages = build_vulnerability_analysis_prompt(source_info, flow, code_snippets)
        response = await self._call_with_retry(messages)

        result = _extract_json(response)
        if result is None:
            logger.error(f"Failed to extract JSON from AI response: {response[:300]}")
            return {
                "vulnerability_type": "parse_error",
                "severity": "info",
                "ai_analysis": f"AI response could not be parsed: {response[:500]}",
                "confidence": 0.0,
            }

        try:
            return {
                "vulnerability_type": result.get("vulnerability_type", "Unknown"),
                "severity": result.get("severity", "info"),
                "ai_analysis": result.get("description", ""),
                "confidence": float(result.get("confidence", 0.5)),
                "remediation": result.get("remediation", ""),
            }
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Failed to parse vulnerability from AI response: {e}")
            return {
                "vulnerability_type": "parse_error",
                "severity": "info",
                "ai_analysis": f"AI response could not be parsed: {response[:500]}",
                "confidence": 0.0,
            }
