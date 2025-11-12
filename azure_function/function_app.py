"""
Azure Function triggered by Event Grid when a blob is created.
Processes PDF documents uploaded to Azure Blob Storage.
"""

import azure.functions as func
import logging
import json
import os
from datetime import datetime

app = func.FunctionApp()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.function_name(name="ProcessDocumentEvent")
@app.event_grid_trigger(arg_name="event")
async def process_document_event(event: func.EventGridEvent):
    """
    Triggered when a new blob is created in Azure Blob Storage.

    Event schema:
    {
        "topic": "/subscriptions/{id}/resourceGroups/{rg}/providers/Microsoft.Storage/storageAccounts/{account}",
        "subject": "/blobServices/default/containers/raw-documents/blobs/folder-1/abc123.pdf",
        "eventType": "Microsoft.Storage.BlobCreated",
        "data": {
            "api": "PutBlob",
            "url": "https://storage.blob.core.windows.net/raw-documents/folder-1/abc123.pdf",
            "contentType": "application/pdf",
            "blobType": "BlockBlob"
        }
    }
    """
    try:
        # Parse event data
        event_data = event.get_json()
        logger.info(f"Processing Event Grid event: {event.event_type}")
        logger.info(f"Event subject: {event.subject}")

        # Extract blob information
        blob_url = event_data.get("url")
        content_type = event_data.get("contentType", "")
        subject = event.subject  # Format: /blobServices/default/containers/{container}/blobs/{path}

        # Validate this is a PDF in the raw-documents container
        if "raw-documents" not in subject:
            logger.info(f"Skipping non-raw-documents blob: {subject}")
            return

        if content_type != "application/pdf":
            logger.info(f"Skipping non-PDF file: {content_type}")
            return

        # Extract blob path (e.g., "folder-1/abc123.pdf")
        blob_path = subject.split("/blobs/")[-1]
        logger.info(f"Processing blob: {blob_path}")

        # Extract folder ID and find document in database
        folder_id = _extract_folder_id(blob_path)
        if not folder_id:
            logger.error(f"Could not extract folder ID from path: {blob_path}")
            return

        # Import processing logic
        from shared_code.document_processor import process_document_from_blob

        # Process the document
        await process_document_from_blob(
            blob_url=blob_url,
            blob_path=blob_path,
            folder_id=folder_id
        )

        logger.info(f"Successfully processed document: {blob_path}")

    except Exception as e:
        logger.error(f"Error processing Event Grid event: {str(e)}", exc_info=True)
        # Re-raise to trigger Event Grid retry mechanism
        raise


def _extract_folder_id(blob_path: str) -> int:
    """
    Extract folder ID from blob path.

    Expected format: folder-{id}/filename.pdf
    Returns: folder_id as integer or None
    """
    try:
        parts = blob_path.split("/")
        if len(parts) >= 1 and parts[0].startswith("folder-"):
            folder_id_str = parts[0].replace("folder-", "")
            return int(folder_id_str)
    except (ValueError, IndexError) as e:
        logger.error(f"Error extracting folder ID: {str(e)}")

    return None
