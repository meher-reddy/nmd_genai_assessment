"""Tests for field extraction."""

import json

import pytest

from tasks.extract import FIELD_SCHEMAS, extract_fields

DRUG_EVENT = {
    "document_id": "doc-2",
    "title": "FDA Approval Letter: LUXTERA",
    "content": "The FDA has approved LUXTERA (miravimod) ...",
    "document_type": "drug_approval",
}


@pytest.fixture
def claude(mocker):
    return mocker.patch("tasks.extract.invoke_claude")


def test_returns_exactly_the_schema_fields(claude):
    claude.return_value = json.dumps(
        {
            "extracted_fields": {"drug_name": "LUXTERA (miravimod)", "indication": "plaque psoriasis", "notes": "x"},
            "extraction_confidence": 0.85,
        }
    )

    result = extract_fields(DRUG_EVENT)

    fields = result["extracted_fields"]
    assert set(fields) == set(FIELD_SCHEMAS["drug_approval"])
    assert fields["drug_name"] == "LUXTERA (miravimod)"
    assert fields["dosage"] is None
    assert "notes" not in fields
    assert result["extraction_confidence"] == 0.85


def test_prompt_asks_only_for_this_types_fields(claude):
    claude.return_value = '{"extracted_fields": {}, "extraction_confidence": 0.5}'

    extract_fields(DRUG_EVENT)

    prompt = claude.call_args.args[1]
    assert "dosage" in prompt
    assert "cve_ids" not in prompt


def test_uses_a_large_enough_output_limit(claude):
    claude.return_value = '{"extracted_fields": {}, "extraction_confidence": 0.5}'

    extract_fields(DRUG_EVENT)

    assert claude.call_args.kwargs["max_tokens"] >= 1024


def test_unknown_type_skips_bedrock(claude):
    result = extract_fields({**DRUG_EVENT, "document_type": "unknown"})

    claude.assert_not_called()
    assert result == {"document_id": "doc-2", "extracted_fields": {}, "extraction_confidence": 0.0}


def test_missing_type_skips_bedrock(claude):
    event = {key: value for key, value in DRUG_EVENT.items() if key != "document_type"}

    result = extract_fields(event)

    claude.assert_not_called()
    assert result["extracted_fields"] == {}


def test_unusable_reply_returns_empty_fields(claude):
    claude.return_value = "I couldn't find those fields."

    result = extract_fields(DRUG_EVENT)

    assert result["extracted_fields"] == {}
    assert result["extraction_confidence"] == 0.0
