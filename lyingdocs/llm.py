"""LLM client abstraction supporting OpenAI and Anthropic providers.

Callers use provider-agnostic factory functions. Both providers return the same
``LLMResponse`` / ``ToolCall`` types so the agent loops need no provider-specific
branching.
"""

import json
import logging
import time
from dataclasses import dataclass

from anthropic import Anthropic, APIConnectionError as AnthropicConnectionError
from anthropic import APIError as AnthropicAPIError, RateLimitError as AnthropicRateLimitError
from openai import APIConnectionError, APIError, OpenAI, RateLimitError

logger = logging.getLogger("lyingdocs")


# ---------------------------------------------------------------------------
# Unified response types
# ---------------------------------------------------------------------------

@dataclass
class ToolCallFunction:
    name: str
    arguments: str  # JSON string


@dataclass
class ToolCall:
    id: str
    function: ToolCallFunction


@dataclass
class LLMResponse:
    """Provider-agnostic response wrapper used by both agent loops."""
    content: str | None
    tool_calls: list[ToolCall] | None


# ---------------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------------

ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com"

def make_client(api_key: str, base_url: str, provider: str = "openai"):
    """Create an LLM client for the given provider."""
    if provider == "anthropic":
        kwargs = {"api_key": api_key}
        # Support custom base_url (proxies, private endpoints, etc.)
        if base_url and base_url != ANTHROPIC_DEFAULT_BASE_URL:
            kwargs["base_url"] = base_url
        return Anthropic(**kwargs)
    return OpenAI(api_key=api_key, base_url=base_url)


# ---------------------------------------------------------------------------
# Provider-agnostic call functions
# ---------------------------------------------------------------------------

def call_llm(
    client,
    model: str,
    system_prompt: str,
    user_content: str,
    *,
    provider: str = "openai",
    max_retries: int = 3,
) -> str:
    """Call a chat completions / messages API and return the text response."""
    if provider == "anthropic":
        return _call_anthropic_llm(client, model, system_prompt, user_content, max_retries)
    return _call_openai_llm(client, model, system_prompt, user_content, max_retries)


def call_llm_with_tools(
    client,
    model: str,
    messages: list[dict],
    tools: list[dict],
    *,
    provider: str = "openai",
    max_retries: int = 5,
) -> LLMResponse:
    """Call chat completions / messages with function-calling tools.

    Returns a unified ``LLMResponse`` regardless of provider.
    """
    if provider == "anthropic":
        return _call_anthropic_with_tools(client, model, messages, tools, max_retries)
    return _call_openai_with_tools(client, model, messages, tools, max_retries)


# ---------------------------------------------------------------------------
# OpenAI implementation
# ---------------------------------------------------------------------------

def _call_openai_llm(
    client: OpenAI, model: str, system_prompt: str, user_content: str, max_retries: int,
) -> str:
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
            )
            return resp.choices[0].message.content
        except RateLimitError:
            _wait_retry("Rate limited", attempt, max_retries, base=5)
        except APIConnectionError:
            _wait_retry("Connection error", attempt, max_retries, base=5)
        except APIError as exc:
            logger.error("OpenAI API error: %s", exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(3)
    raise RuntimeError("LLM call failed after %d retries" % max_retries)


def _call_openai_with_tools(
    client: OpenAI,
    model: str,
    messages: list[dict],
    tools: list[dict],
    max_retries: int,
) -> LLMResponse:
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, tools=tools, temperature=0.2,
            )
            msg = resp.choices[0].message
            return _openai_msg_to_response(msg)
        except RateLimitError:
            _wait_retry("Rate limited", attempt, max_retries, base=5)
        except APIConnectionError:
            _wait_retry("Connection error", attempt, max_retries, base=5)
        except APIError as exc:
            logger.error("OpenAI API error: %s", exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(3)
    raise RuntimeError("LLM call failed after %d retries" % max_retries)


def _openai_msg_to_response(msg) -> LLMResponse:
    tool_calls = None
    if msg.tool_calls:
        tool_calls = [
            ToolCall(
                id=tc.id,
                function=ToolCallFunction(
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                ),
            )
            for tc in msg.tool_calls
        ]
    return LLMResponse(content=msg.content, tool_calls=tool_calls)


# ---------------------------------------------------------------------------
# Anthropic implementation
# ---------------------------------------------------------------------------

def _call_anthropic_llm(
    client: Anthropic, model: str, system_prompt: str, user_content: str, max_retries: int,
) -> str:
    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=8192,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
                temperature=0.2,
            )
            return resp.content[0].text
        except AnthropicRateLimitError:
            _wait_retry("Rate limited", attempt, max_retries, base=5)
        except AnthropicConnectionError:
            _wait_retry("Connection error", attempt, max_retries, base=5)
        except AnthropicAPIError as exc:
            logger.error("Anthropic API error: %s", exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(3)
    raise RuntimeError("LLM call failed after %d retries" % max_retries)


def _call_anthropic_with_tools(
    client: Anthropic,
    model: str,
    messages: list[dict],
    tools: list[dict],
    max_retries: int,
) -> LLMResponse:
    """Call Anthropic messages API with tool use.

    Converts OpenAI-format tool schemas and messages to Anthropic format,
    then normalises the response back to ``LLMResponse``.
    """
    system_prompt, anthropic_messages = _convert_messages_for_anthropic(messages)
    anthropic_tools = _convert_tools_for_anthropic(tools)

    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=8192,
                system=system_prompt,
                messages=anthropic_messages,
                tools=anthropic_tools,
                temperature=0.2,
            )
            return _anthropic_response_to_llm_response(resp)
        except AnthropicRateLimitError:
            _wait_retry("Rate limited", attempt, max_retries, base=5)
        except AnthropicConnectionError:
            _wait_retry("Connection error", attempt, max_retries, base=5)
        except AnthropicAPIError as exc:
            logger.error("Anthropic API error: %s", exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(3)
    raise RuntimeError("LLM call failed after %d retries" % max_retries)


def _convert_messages_for_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
    """Convert OpenAI-style messages to Anthropic format.

    Returns (system_prompt, messages).  Anthropic requires system as a
    top-level parameter, not in the messages list.  Tool call / tool result
    messages also need structural conversion.
    """
    system_prompt = ""
    converted: list[dict] = []

    for msg in messages:
        role = msg.get("role")

        if role == "system":
            system_prompt = msg.get("content", "")
            continue

        if role == "assistant":
            content_blocks = []
            if msg.get("content"):
                content_blocks.append({"type": "text", "text": msg["content"]})
            for tc in msg.get("tool_calls", []):
                fn = tc["function"]
                try:
                    tool_input = json.loads(fn["arguments"])
                except (json.JSONDecodeError, TypeError):
                    tool_input = {}
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": fn["name"],
                    "input": tool_input,
                })
            if content_blocks:
                converted.append({"role": "assistant", "content": content_blocks})
            continue

        if role == "tool":
            # Anthropic groups tool results under a single "user" message
            tool_result = {
                "type": "tool_result",
                "tool_use_id": msg["tool_call_id"],
                "content": msg.get("content", ""),
            }
            # Merge with the previous user message if it already has tool results
            if converted and converted[-1]["role"] == "user" and isinstance(converted[-1]["content"], list):
                converted[-1]["content"].append(tool_result)
            else:
                converted.append({"role": "user", "content": [tool_result]})
            continue

        if role == "user":
            converted.append({"role": "user", "content": msg.get("content", "")})
            continue

    return system_prompt, converted


def _convert_tools_for_anthropic(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-format tool schemas to Anthropic format."""
    anthropic_tools = []
    for tool in tools:
        fn = tool.get("function", {})
        anthropic_tools.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return anthropic_tools


def _anthropic_response_to_llm_response(resp) -> LLMResponse:
    """Convert an Anthropic response to the unified LLMResponse format."""
    text_parts = []
    tool_calls = []

    for block in resp.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(
                id=block.id,
                function=ToolCallFunction(
                    name=block.name,
                    arguments=json.dumps(block.input),
                ),
            ))

    content = "\n".join(text_parts) if text_parts else None
    return LLMResponse(
        content=content,
        tool_calls=tool_calls if tool_calls else None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_retry(reason: str, attempt: int, max_retries: int, *, base: int = 5) -> None:
    wait = base * (2 ** attempt)
    logger.warning(
        "%s — retrying in %ds (attempt %d/%d)",
        reason, wait, attempt + 1, max_retries,
    )
    time.sleep(wait)
