"""LLM-based field extraction task logic."""

import logging
import os

from common.llm import LLMResponseError, clamp_confidence, invoke_claude, parse_json_object

logger = logging.getLogger(__name__)

EXTRACT_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-5-5")

# Extraction needs the whole document, but a cap stops one huge upload from running up cost.
MAX_CONTENT_CHARS = 40000
# Lists such as mitigation steps run long; 256 tokens would cut the JSON off mid-reply.
MAX_OUTPUT_TOKENS = 2048

FIELD_SCHEMAS = {
    "cybersecurity_advisory": {
        "severity": "overall severity if stated (e.g. critical, high), else null",
        "cve_ids": "list of CVE identifiers, e.g. CVE-2024-21887",
        "affected_products": "list of affected products",
        "mitigation_steps": "list of recommended actions, one short item each",
    },
    "drug_approval": {
        "drug_name": "brand name, with the generic name in parentheses if given",
        "indication": "condition and patients the drug is approved for",
        "approval_date": "approval date as YYYY-MM-DD",
        "applicant": "company that applied for approval",
        "dosage": "approved dose and form",
    },
    "airworthiness_directive": {
        "ad_number": "the AD number, e.g. 2024-09-15",
        "affected_aircraft": "list of affected aircraft models or series",
        "compliance_deadline": "when compliance is required, as worded in the document",
        "required_action": "short summary of the required inspections or repairs",
    },
    "financial_filing": {
        "company_name": "name of the reporting company",
        "filing_date": "date of the report as YYYY-MM-DD",
        "event_type": "main event reported, e.g. quarterly earnings, acquisition",
        "revenue": "reported revenue as written, with units",
        "net_income": "reported net income as written, with units",
    },
}

SYSTEM_PROMPT = "You extract facts from official documents. Reply with one JSON object and nothing else."


def build_prompt(document_type: str, title: str, content: str) -> str:
    """Build an extraction prompt that asks only for this document type's fields."""
    readable_type = document_type.replace("_", " ")
    fields = FIELD_SCHEMAS[document_type]
    field_lines = "\n".join(f'- "{name}": {description}' for name, description in fields.items())
    return f"""Extract these fields from the {readable_type} below:

{field_lines}

Rules:
- Use only what the document states. Never guess or fill in missing values.
- If a field is not stated, use null (or [] for a list field).
- Copy numbers, dates and identifiers exactly.
- "extraction_confidence" is a number from 0 to 1 for how complete and certain the extraction is.

Reply with only this JSON:
{{"extracted_fields": {{<every field listed above>}}, "extraction_confidence": <0 to 1>}}

<document>
<title>{title}</title>
<content>
{content}
</content>
</document>"""


def extract_fields(event: dict) -> dict:
    """Extract structured fields from document content using Bedrock.

    Args:
        event: Input with document content and classification.

    Returns:
        extracted_fields (always the type's full key set) and extraction_confidence.
    """
    document_id = event["document_id"]
    title = event.get("title", "")
    content = event.get("content", "")
    document_type = event.get("document_type", "unknown")
    logger.info("Extracting fields from: %s (type: %s)", document_id, document_type)

    schema = FIELD_SCHEMAS.get(document_type)
    if schema is None:
        logger.info("No field schema for type %r, skipping extraction for %s", document_type, document_id)
        return _result(document_id, {}, 0.0)

    prompt = build_prompt(document_type, title, content[:MAX_CONTENT_CHARS])
    try:
        reply = invoke_claude(EXTRACT_MODEL_ID, prompt, system=SYSTEM_PROMPT, max_tokens=MAX_OUTPUT_TOKENS)
        parsed = parse_json_object(reply)
    except LLMResponseError as exc:
        logger.warning("Unusable extraction reply for %s: %s", document_id, exc)
        return _result(document_id, {}, 0.0)

    raw_fields = parsed.get("extracted_fields")
    if not isinstance(raw_fields, dict):
        raw_fields = {}
    unexpected = sorted(set(raw_fields) - set(schema))
    if unexpected:
        logger.warning("Dropping unexpected fields %s for %s", unexpected, document_id)

    # Every result for a type has the same keys; anything the model left out becomes null.
    fields = {name: raw_fields.get(name) for name in schema}
    confidence = clamp_confidence(parsed.get("extraction_confidence"))
    logger.info("Extracted %d fields from %s (confidence %.2f)", len(fields), document_id, confidence)
    return _result(document_id, fields, confidence)


def _result(document_id: str, fields: dict, confidence: float) -> dict:
    return {"document_id": document_id, "extracted_fields": fields, "extraction_confidence": confidence}
