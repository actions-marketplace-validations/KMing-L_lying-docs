"""OpenAI client wrapper with retry logic and function-calling support."""

import json
import logging
import time

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

logger = logging.getLogger("lyingdocs")


def make_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url)


def call_llm(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_content: str,
    max_retries: int = 3,
) -> str:
    """Call chat completions API with retry logic."""
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
            wait = 5 * (2**attempt)
            logger.warning(
                "Rate limited — retrying in %ds (attempt %d/%d)",
                wait, attempt + 1, max_retries,
            )
            time.sleep(wait)
        except APIConnectionError:
            logger.warning(
                "Connection error — retrying in 5s (attempt %d/%d)",
                attempt + 1, max_retries,
            )
            time.sleep(5)
        except APIError as exc:
            logger.error("API error: %s", exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(3)
    raise RuntimeError("LLM call failed after %d retries" % max_retries)


def call_llm_with_tools(
    client: OpenAI,
    model: str,
    messages: list[dict],
    tools: list[dict],
    max_retries: int = 5,
):
    """Call chat completions with function-calling tools.

    Returns the raw response message object (which may contain tool_calls).
    """
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                temperature=0.2,
            )
            return resp.choices[0].message
        except RateLimitError:
            wait = 5 * (2**attempt)
            logger.warning(
                "Rate limited — retrying in %ds (attempt %d/%d)",
                wait, attempt + 1, max_retries,
            )
            time.sleep(wait)
        except APIConnectionError:
            logger.warning(
                "Connection error — retrying in 5s (attempt %d/%d)",
                attempt + 1, max_retries,
            )
            time.sleep(5)
        except APIError as exc:
            logger.error("API error: %s", exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(3)
    raise RuntimeError("LLM call failed after %d retries" % max_retries)
