"""
Webhook endpoints for receiving notifications from Azure services.
"""

from fastapi import APIRouter, Request, HTTPException, status, Header
from typing import Optional
import logging
import hashlib
import hmac
import base64

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
    aeg_event_type: Optional[str] = Header(None)
):
    """
    Webhook triggered when a blob is created in Azure Storage.
    Immediately triggers the Azure AI Search indexer to process the new document.

    This provides instant document processing instead of waiting for the 5-minute schedule.
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

        indexer_service = IndexerService()
        triggered_count = 0

        # Process each blob creation event
        for event in events:
            event_type = event.get("eventType")

            if event_type == "Microsoft.Storage.BlobCreated":
                data = event.get("data", {})
                blob_url = data.get("url", "")

                logger.info(f"Blob created: {blob_url}")

                # Only trigger for raw-documents container
                if "/raw-documents/" in blob_url:
                    logger.info(f"Triggering indexer for new document")

                    # Trigger the indexer to run immediately
                    result = await indexer_service.run_indexer("rag-document-indexer")
                    triggered_count += 1

                    logger.info(f"Indexer triggered: {result}")

        return {
            "status": "processed",
            "events_received": len(events),
            "indexer_triggered": triggered_count
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
