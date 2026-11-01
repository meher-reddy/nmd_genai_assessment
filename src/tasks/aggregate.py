"""Results aggregation task logic."""

import json
import logging
from datetime import UTC, datetime

from common.aws import get_s3_client

logger = logging.getLogger(__name__)

RESULTS_PREFIX = "results/"


def aggregate_results(event: dict) -> dict:
    """Aggregate extraction results and write summary to S3.

    Writes to results/{document_id}.json in the bucket the document came from. The EventBridge
    rule only matches uploads/, so this write does not start another pipeline run.

    Args:
        event: Full pipeline state with preprocess, classify, and extract results.

    Returns:
        Summary of the pipeline execution.
    """
    logger.info("Aggregating results")

    preprocess = event.get("preprocess_result", {})
    classify = event.get("classify_result", {})
    extract = event.get("extract_result", {})
    document_id = preprocess.get("document_id", "unknown")
    s3_bucket = preprocess.get("s3_bucket", "")

    summary = {
        "document_id": document_id,
        "document_type": classify.get("document_type", "unknown"),
        "classification_confidence": classify.get("confidence", 0.0),
        "extracted_fields": extract.get("extracted_fields", {}),
        "extraction_confidence": extract.get("confidence", 0.0),
        "status": "completed",
        "processed_at": datetime.now(UTC).isoformat(),
    }

    if not s3_bucket:
        raise ValueError(f"No s3_bucket in preprocess_result for {document_id}; cannot write results")

    key = f"{RESULTS_PREFIX}{document_id}.json"
    get_s3_client().put_object(
        Bucket=s3_bucket,
        Key=key,
        Body=json.dumps(summary, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    logger.info("Wrote results to s3://%s/%s", s3_bucket, key)
    return summary
