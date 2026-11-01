"""Tests for the preprocess task."""

import io
import json

from tasks.preprocess import preprocess_document


def test_reads_document_from_s3_and_derives_id_from_key(mocker):
    s3 = mocker.Mock()
    document = {"title": "FDA Approval", "content": "Approved ...", "source": "FDA", "date": "2024-06-15"}
    s3.get_object.return_value = {"Body": io.BytesIO(json.dumps(document).encode())}
    mocker.patch("tasks.preprocess.get_s3_client", return_value=s3)

    result = preprocess_document({"s3_bucket": "my-bucket", "s3_key": "uploads/drug-approval.json"})

    s3.get_object.assert_called_once_with(Bucket="my-bucket", Key="uploads/drug-approval.json")
    assert result["document_id"] == "drug-approval"
    assert result["title"] == "FDA Approval"
    assert result["content"] == "Approved ..."
    assert result["status"] == "preprocessed"
