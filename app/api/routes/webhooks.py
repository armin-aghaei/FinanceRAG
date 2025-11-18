"""
Webhook endpoints for receiving notifications from Azure services.
"""

from fastapi import APIRouter, Request, HTTPException, status, Header, BackgroundTasks
from typing import Optional
import logging
import hashlib
import hmac
import base64
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.document import Document, DocumentStatus
from datetime import datetime

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

logger = logging.getLogger(__name__)


@router.post("/event-grid-validation")
async def event_grid_validation(request: Request):
    """
    Endpoint for Event Grid subscription validation.

    When you create an Event Grid subscription, Azure sends a validation event.
    This endpoint handles the validation handshake.
    """
    try:
        body = await request.json()

        # Check if this is a validation event
        if isinstance(body, list) and len(body) > 0:
            event = body[0]

            if event.get("eventType") == "Microsoft.EventGrid.SubscriptionValidationEvent":
                validation_code = event["data"]["validationCode"]
                logger.info(f"Received Event Grid validation request")

                return {
                    "validationResponse": validation_code
                }

        # If not a validation event, return 200 OK
        logger.info(f"Received Event Grid event: {body}")
        return {"status": "received"}

    except Exception as e:
        logger.error(f"Error processing Event Grid validation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process validation"
        )


@router.post("/document-processed")
async def document_processed_notification(
    request: Request,
    aeg_event_type: Optional[str] = Header(None)
):
    """
    Optional webhook to receive notifications when document processing completes.

    This can be used if you want the Azure Function to notify your API
    when processing is done. Useful for real-time updates to clients via WebSockets.

    Event Grid sends events with headers:
    - aeg-event-type: The event type
    - aeg-subscription-name: The subscription name
    """
    try:
        events = await request.json()

        logger.info(f"Received document processing notification")
        logger.info(f"Event type: {aeg_event_type}")

        # Process each event
        for event in events:
            event_type = event.get("eventType")
            data = event.get("data", {})

            logger.info(f"Processing event: {event_type}")
            logger.info(f"Event data: {data}")

            # You can add custom logic here, such as:
            # - Notifying connected WebSocket clients
            # - Sending push notifications
            # - Triggering additional workflows

        return {"status": "processed", "count": len(events)}

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook"
        )


@router.post("/blob-created")
async def blob_created_trigger(
    request: Request,
    background_tasks: BackgroundTasks,
    aeg_event_type: Optional[str] = Header(None)
):
    """
    Webhook triggered when a blob is created in Azure Storage.

    Workflow:
    1. Triggers Azure AI Search indexer to process the new document
    2. Schedules background task to merge metadata after indexing completes

    This provides instant document processing and automatic metadata propagation.
    """
    try:
        events = await request.json()

        # Handle Event Grid subscription validation
        if isinstance(events, list) and len(events) > 0:
            first_event = events[0]
            if first_event.get("eventType") == "Microsoft.EventGrid.SubscriptionValidationEvent":
                validation_code = first_event["data"]["validationCode"]
                logger.info("Event Grid validation received for blob-created webhook")
                return {"validationResponse": validation_code}

        # Import here to avoid circular imports
        from app.services.indexer_service import IndexerService
        from app.services.metadata_merger_service import metadata_merger_service
        from app.services.azure_table_service import table_service
        import asyncio

        indexer_service = IndexerService()
        triggered_count = 0
        metadata_merge_tasks = []

        # Process each blob creation event
        for event in events:
            event_type = event.get("eventType")

            if event_type == "Microsoft.Storage.BlobCreated":
                data = event.get("data", {})
                blob_url = data.get("url", "")

                logger.info(f"Blob created: {blob_url}")

                # Only trigger for raw-documents container
                if "/raw-documents/" in blob_url:
                    # Extract blob name from URL
                    # URL format: https://...blob.core.windows.net/raw-documents/folder-3/uuid.pdf
                    blob_name = blob_url.split("/raw-documents/")[1] if "/raw-documents/" in blob_url else None

                    if blob_name:
                        logger.info(f"Triggering indexer for new document: {blob_name}")

                        # Trigger the indexer to run immediately
                        result = await indexer_service.trigger_indexer_run()
                        triggered_count += 1

                        logger.info(f"Indexer triggered: {result}")

                        # Retrieve metadata from Table Storage
                        try:
                            metadata = table_service.get_document_metadata(blob_name)
                            folder_id = int(metadata.get('folder_id'))
                            user_id = int(metadata.get('user_id'))
                            document_id = int(metadata.get('document_id'))

                            logger.info(
                                f"Retrieved metadata for {blob_name}: "
                                f"folder_id={folder_id}, user_id={user_id}, document_id={document_id}"
                            )

                            # Schedule background task to merge metadata after indexing
                            # The merger service will retry multiple times waiting for chunks to be created
                            # Use BackgroundTasks to ensure task completes even after response is returned
                            background_tasks.add_task(
                                process_document_metadata,
                                blob_name=blob_name,
                                folder_id=folder_id,
                                user_id=user_id,
                                document_id=document_id
                            )
                            metadata_merge_tasks.append(blob_name)

                        except Exception as metadata_error:
                            logger.warning(f"Could not retrieve metadata for {blob_name}: {str(metadata_error)}")
                            # Continue processing - indexing will still work

        return {
            "status": "processed",
            "events_received": len(events),
            "indexer_triggered": triggered_count,
            "metadata_merge_scheduled": len(metadata_merge_tasks)
        }

    except Exception as e:
        logger.error(f"Error processing blob creation event: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process blob event: {str(e)}"
        )


@router.get("/health")
async def webhook_health():
    """Health check for webhook endpoint."""
    return {"status": "healthy", "endpoint": "webhooks"}


async def update_document_status_after_merge(document_id: int, merge_result: dict):
    """
    Update document status in database based on metadata merge result.

    Args:
        document_id: ID of the document to update
        merge_result: Result dictionary from metadata merger service
    """
    try:
        async with AsyncSessionLocal() as session:
            # Find the document
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()

            if not document:
                logger.error(f"Document {document_id} not found in database")
                return

            old_status = document.status

            # Update status based on merge result
            if merge_result.get('status') == 'success':
                document.status = DocumentStatus.INDEXED
                document.updated_at = datetime.utcnow()
                logger.info(
                    f"Successfully merged metadata into {merge_result.get('chunks_updated', 0)} chunks "
                    f"after {merge_result.get('attempts', 0)} attempts"
                )
            elif merge_result.get('status') == 'no_chunks_found':
                document.status = DocumentStatus.FAILED
                document.error_message = "No chunks found after metadata merge retries"
                document.updated_at = datetime.utcnow()
                logger.warning(f"Metadata merge failed: no chunks found after retries")
            else:
                document.status = DocumentStatus.FAILED
                document.error_message = merge_result.get('error', 'Metadata merge failed')
                document.updated_at = datetime.utcnow()
                logger.warning(f"Metadata merge failed: {merge_result}")

            await session.commit()

            logger.info(f"Updated document {document_id} status: {old_status} → {document.status}")

    except Exception as e:
        logger.error(f"Error updating document {document_id} status: {str(e)}", exc_info=True)


async def update_document_status_to_failed(document_id: int, error_message: str):
    """
    Update document status to FAILED in database.

    Args:
        document_id: ID of the document to update
        error_message: Error message to store
    """
    try:
        async with AsyncSessionLocal() as session:
            # Find the document
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()

            if not document:
                logger.error(f"Document {document_id} not found in database")
                return

            old_status = document.status
            document.status = DocumentStatus.FAILED
            document.error_message = error_message
            document.updated_at = datetime.utcnow()

            await session.commit()

            logger.info(f"Updated document {document_id} status: {old_status} → FAILED (error: {error_message})")

    except Exception as e:
        logger.error(f"Error updating document {document_id} status to FAILED: {str(e)}", exc_info=True)


async def process_document_metadata(blob_name: str, folder_id: int, user_id: int, document_id: int):
    """
    Background task to process document metadata merge and update status.

    This function is executed as a FastAPI background task, which ensures
    it completes even after the HTTP response is returned.

    Args:
        blob_name: Name of the blob in storage
        folder_id: Folder ID for the document
        user_id: User ID who uploaded the document
        document_id: Document ID in database
    """
    try:
        from app.services.metadata_merger_service import metadata_merger_service

        logger.info(f"Starting background metadata processing for document {document_id}")

        # Merge metadata into semantic chunks (with retry logic)
        # Wait up to 2 minutes for indexer to process the document
        result = await metadata_merger_service.merge_metadata_for_document(
            blob_name=blob_name,
            folder_id=folder_id,
            user_id=user_id,
            document_id=document_id,
            max_retries=12,  # Increased from 5 to 12
            retry_delay=10   # 12 retries × 10 seconds = 2 minutes total wait
        )

        logger.info(f"Metadata merge completed for {blob_name}: {result}")

        # Update document status based on merge result
        await update_document_status_after_merge(document_id, result)

    except Exception as e:
        logger.error(f"Background task failed for {blob_name}: {str(e)}", exc_info=True)

        # Update document status to FAILED
        await update_document_status_to_failed(
            document_id,
            f"Metadata merge error: {str(e)}"
        )
