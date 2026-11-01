"""Tests for document classification."""

import pytest

from tasks.classify import DOCUMENT_TYPES, MAX_CONTENT_CHARS, classify_document

EVENT = {"document_id": "doc-1", "title": "CISA Advisory AA24-131A", "content": "CVE-2024-21887 affects ..."}


@pytest.fixture
def claude(mocker):
    return mocker.patch("tasks.classify.invoke_claude")


def test_returns_the_keys_the_state_machine_selects(claude):
    claude.return_value = '{"document_type": "cybersecurity_advisory", "confidence": 0.93, "reasoning": "CVEs"}'

    result = classify_document(EVENT)

    assert result["document_type"] == "cybersecurity_advisory"
    assert result["classification_confidence"] == 0.93


def test_normalises_case_and_spacing(claude):
    claude.return_value = '{"document_type": " Drug_Approval ", "confidence": 0.8}'

    assert classify_document(EVENT)["document_type"] == "drug_approval"


def test_type_outside_the_list_becomes_unknown(claude):
    claude.return_value = '{"document_type": "news_article", "confidence": 0.9}'

    result = classify_document(EVENT)

    assert result["document_type"] == "unknown"
    assert result["classification_confidence"] == 0.0


def test_unparseable_reply_becomes_unknown(claude):
    claude.return_value = "Sorry, I can't tell what this is."

    result = classify_document(EVENT)

    assert result["document_type"] == "unknown"
    assert result["classification_confidence"] == 0.0


def test_empty_document_skips_bedrock(claude):
    result = classify_document({"document_id": "empty", "title": "", "content": "   "})

    claude.assert_not_called()
    assert result["document_type"] == "unknown"


def test_prompt_lists_every_allowed_type(claude):
    claude.return_value = '{"document_type": "unknown", "confidence": 0.2}'

    classify_document(EVENT)

    prompt = claude.call_args.args[1]
    for document_type in [*DOCUMENT_TYPES, "unknown"]:
        assert document_type in prompt


def test_long_content_is_trimmed(claude):
    claude.return_value = '{"document_type": "unknown", "confidence": 0.2}'

    classify_document({**EVENT, "content": "x" * (MAX_CONTENT_CHARS + 5000)})

    prompt = claude.call_args.args[1]
    assert "x" * MAX_CONTENT_CHARS in prompt
    assert "x" * (MAX_CONTENT_CHARS + 1) not in prompt


def test_bedrock_errors_propagate_so_step_functions_can_retry(claude):
    claude.side_effect = RuntimeError("ThrottlingException")

    with pytest.raises(RuntimeError):
        classify_document(EVENT)
