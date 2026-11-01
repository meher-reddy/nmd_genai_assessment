"""Shared helpers for calling Claude on Amazon Bedrock and reading its JSON replies."""

import json
import logging
import math
import re

from common.aws import get_bedrock_client

logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = "bedrock-2023-05-31"
# Matches a Markdown code fence (three backticks, optionally "json") at the start or end of a reply.
CODE_FENCE = re.compile(r"^`{3}(?:json)?\s*|\s*`{3}$")


class LLMResponseError(ValueError):
    """The model replied, but the reply can't be used."""


def invoke_claude(model_id: str, prompt: str, *, system: str | None = None, max_tokens: int = 512) -> str:
    """Send one user message to Claude through Bedrock and return the reply text.

    Bedrock errors such as throttling are not caught here. They propagate so the Lambda
    fails and Step Functions can retry the step.
    """
    body = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    response = get_bedrock_client().invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(response["body"].read())

    usage = payload.get("usage", {})
    logger.info(
        "Bedrock reply: model=%s stop_reason=%s input_tokens=%s output_tokens=%s",
        model_id,
        payload.get("stop_reason"),
        usage.get("input_tokens"),
        usage.get("output_tokens"),
    )

    if payload.get("stop_reason") == "max_tokens":
        raise LLMResponseError(f"Reply was cut off at max_tokens={max_tokens}")

    blocks = payload.get("content", [])
    return "".join(block.get("text", "") for block in blocks if block.get("type") == "text")


def parse_json_object(text: str) -> dict:
    """Parse a JSON object from a model reply, tolerating code fences or a sentence around it."""
    cleaned = CODE_FENCE.sub("", text.strip())
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMResponseError(f"No JSON object in reply: {text[:200]!r}") from None
        try:
            result = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"Invalid JSON in reply: {exc}") from exc

    if not isinstance(result, dict):
        raise LLMResponseError(f"Expected a JSON object, got {type(result).__name__}")
    return result


def clamp_confidence(value: object) -> float:
    """Turn a model-reported confidence into a float between 0 and 1."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number):
        return 0.0
    return max(0.0, min(1.0, number))
