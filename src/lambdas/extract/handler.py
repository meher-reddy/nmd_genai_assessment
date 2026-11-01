"""Lambda handler for LLM-based field extraction."""

import logging
import os

from tasks.extract import extract_fields

logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """Extract structured fields from a document using Bedrock."""
    logger.info("Extracting fields from document: %s", event.get("document_id"))
    return extract_fields(event)
