"""Tests for results aggregation."""

import json

import pytest

from tasks.aggregate import aggregate_results

EVENT = {
    "preprocess_result": {"document_id": "drug-approval", "s3_bucket": "my-bucket"},
    "classify_result": {"document_type": "drug_approval", "confidence": 0.9},
    "extract_result": {"extracted_fields": {"drug_name": "LUXTERA"}, "confidence": 0.8},
}


@pytest.fixture
def s3(mocker):
    client = mocker.Mock()
    mocker.patch("tasks.aggregate.get_s3_client", return_value=client)
    return client


def test_writes_summary_to_results_prefix(s3):
    summary = aggregate_results(EVENT)

    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "my-bucket"
    assert kwargs["Key"] == "results/drug-approval.json"
    assert kwargs["ContentType"] == "application/json"
    assert json.loads(kwargs["Body"]) == summary


def test_summary_carries_both_confidences(s3):
    summary = aggregate_results(EVENT)

    assert summary["document_type"] == "drug_approval"
    assert summary["classification_confidence"] == 0.9
    assert summary["extraction_confidence"] == 0.8
    assert summary["extracted_fields"] == {"drug_name": "LUXTERA"}
    assert summary["status"] == "completed"


def test_missing_bucket_raises_instead_of_silently_skipping(s3):
    with pytest.raises(ValueError):
        aggregate_results({"preprocess_result": {"document_id": "drug-approval"}})

    s3.put_object.assert_not_called()
