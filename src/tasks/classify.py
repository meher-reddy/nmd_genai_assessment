"""Document classification task logic using Bedrock LLM."""

import logging
import os

from common.llm import LLMResponseError, clamp_confidence, invoke_claude, parse_json_object

logger = logging.getLogger(__name__)

CLASSIFY_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-5-5")

# The opening of a document is enough to tell its type, so long documents are trimmed to save tokens.
MAX_CONTENT_CHARS = 8000

UNKNOWN = "unknown"
DOCUMENT_TYPES = {
    "cybersecurity_advisory": "security alert about vulnerabilities, often listing CVE IDs and fixes (e.g. CISA)",
    "drug_approval": "regulator's approval of a medicine, with indication and dosage (e.g. FDA letter)",
    "airworthiness_directive": "mandatory aircraft safety order requiring inspections or repairs (e.g. FAA AD)",
    "financial_filing": "company disclosure to a securities regulator: earnings, deals, events (e.g. SEC 8-K)",
}

SYSTEM_PROMPT = "You classify official documents. Reply with one JSON object and nothing else."


def build_prompt(title: str, content: str) -> str:
    """Build the classification prompt, listing every allowed type with a short description."""
    type_lines = "\n".join(f"- {name}: {description}" for name, description in DOCUMENT_TYPES.items())
    return f"""Classify the document below as exactly one of these types:

{type_lines}
- {UNKNOWN}: does not clearly match any type above

Rules:
- Decide by the document's main purpose, not by topics it only mentions in passing.
- If two types seem plausible, pick the one that explains why the document was issued and lower your confidence.
- Prefer "{UNKNOWN}" to guessing.
- "confidence" is a number from 0 to 1.

Reply with only this JSON:
{{"document_type": "<one type from the list>", "confidence": <0 to 1>, "reasoning": "<one short sentence>"}}

<document>
<title>{title}</title>
<content>
{content}
</content>
</document>"""


def classify_document(event: dict) -> dict:
    """Classify a document using Bedrock LLM.

    Args:
        event: Input with document content from preprocessing.

    Returns:
        document_type and classification_confidence (the keys the state machine selects), plus reasoning.
    """
    document_id = event["document_id"]
    title = event.get("title", "")
    content = event.get("content", "")
    logger.info("Classifying document: %s", document_id)

    if not title.strip() and not content.strip():
        logger.warning("Document %s has no text, classifying as %s", document_id, UNKNOWN)
        return _result(document_id, UNKNOWN, 0.0, "Document has no text.")

    prompt = build_prompt(title, content[:MAX_CONTENT_CHARS])
    try:
        reply = invoke_claude(CLASSIFY_MODEL_ID, prompt, system=SYSTEM_PROMPT, max_tokens=256)
        parsed = parse_json_object(reply)
    except LLMResponseError as exc:
        logger.warning("Unusable classification reply for %s: %s", document_id, exc)
        return _result(document_id, UNKNOWN, 0.0, "Model reply could not be used.")

    document_type = str(parsed.get("document_type", "")).strip().lower()
    confidence = clamp_confidence(parsed.get("confidence"))
    if document_type not in DOCUMENT_TYPES and document_type != UNKNOWN:
        logger.warning("Model returned unexpected type %r for %s", document_type, document_id)
        document_type, confidence = UNKNOWN, 0.0

    logger.info("Classified %s as %s (confidence %.2f)", document_id, document_type, confidence)
    return _result(document_id, document_type, confidence, str(parsed.get("reasoning", "")))


def _result(document_id: str, document_type: str, confidence: float, reasoning: str) -> dict:
    return {
        "document_id": document_id,
        "document_type": document_type,
        "classification_confidence": confidence,
        "reasoning": reasoning,
    }
