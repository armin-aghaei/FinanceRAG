from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Dict, Any
from app.core.database import get_db
from app.models.document import Document, DocumentStatus
from app.core.config import settings
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.servicebus import ServiceBusClient, ServiceBusSubQueue
from azure.servicebus.management import ServiceBusAdministrationClient
import logging
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/sync-document-status", response_model=Dict[str, int])
async def sync_document_status(db: AsyncSession = Depends(get_db)):
    """
    Sync document status with Azure AI Search index.

    Checks all PENDING documents and updates their status to INDEXED
    if they exist in the search index.

    This endpoint should be called periodically (e.g., every 5-10 minutes)
    by a scheduler or cron job.
    """
    try:
        # Get all PENDING documents
        result = await db.execute(
            select(Document).where(Document.status == DocumentStatus.PENDING)
        )
        pending_documents = result.scalars().all()

        if not pending_documents:
            return {"updated": 0, "still_pending": 0}

        # Initialize Azure Search client
        search_client = SearchClient(
            endpoint=settings.AZURE_SEARCH_ENDPOINT,
            index_name="document-chunks",
            credential=AzureKeyCredential(settings.AZURE_SEARCH_KEY)
        )

        updated_count = 0
        still_pending_count = 0

        for document in pending_documents:
            try:
                # Check if document has chunks in the search index
                # Search for chunks with this document_id
                results = search_client.search(
                    search_text="*",
                    filter=f"document_id eq '{document.id}'",
                    top=1
                )

                # If we find at least one chunk, the document has been indexed
                has_chunks = False
                for _ in results:
                    has_chunks = True
                    break

                if has_chunks:
                    document.status = DocumentStatus.INDEXED
                    updated_count += 1
                    logger.info(f"Updated document {document.id} to INDEXED")
                else:
                    still_pending_count += 1

            except Exception as e:
                logger.error(f"Error checking document {document.id}: {str(e)}")
                still_pending_count += 1

        # Commit all updates
        await db.commit()

        return {
            "updated": updated_count,
            "still_pending": still_pending_count
        }

    except Exception as e:
        logger.error(f"Error syncing document status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync document status"
        )


@router.get("/service-bus/queue-metrics", response_model=Dict[str, Any])
async def get_service_bus_queue_metrics():
    """
    Get Service Bus queue metrics.

    Returns queue depth, active message count, dead-letter count, etc.
    Useful for monitoring the document processing queue.
    """
    try:
        # Use management client to get queue runtime properties
        mgmt_client = ServiceBusAdministrationClient.from_connection_string(
            settings.SERVICE_BUS_CONNECTION_STRING
        )

        queue_runtime_properties = mgmt_client.get_queue_runtime_properties(
            settings.SERVICE_BUS_QUEUE_NAME
        )

        return {
            "queue_name": settings.SERVICE_BUS_QUEUE_NAME,
            "active_message_count": queue_runtime_properties.active_message_count,
            "dead_letter_message_count": queue_runtime_properties.dead_letter_message_count,
            "scheduled_message_count": queue_runtime_properties.scheduled_message_count,
            "total_message_count": queue_runtime_properties.total_message_count,
            "size_in_bytes": queue_runtime_properties.size_in_bytes,
            "created_at_utc": queue_runtime_properties.created_at_utc.isoformat() if queue_runtime_properties.created_at_utc else None,
            "updated_at_utc": queue_runtime_properties.updated_at_utc.isoformat() if queue_runtime_properties.updated_at_utc else None
        }

    except Exception as e:
        logger.error(f"Error getting Service Bus metrics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue metrics: {str(e)}"
        )


@router.get("/service-bus/dead-letter-messages", response_model=Dict[str, Any])
async def peek_dead_letter_messages(max_messages: int = 10):
    """
    Peek at dead-letter queue messages.

    Returns up to `max_messages` messages from the dead-letter queue
    without removing them. Useful for debugging failed document processing.
    """
    try:
        servicebus_client = ServiceBusClient.from_connection_string(
            settings.SERVICE_BUS_CONNECTION_STRING
        )

        # Get receiver for dead-letter queue
        receiver = servicebus_client.get_queue_receiver(
            queue_name=settings.SERVICE_BUS_QUEUE_NAME,
            sub_queue=ServiceBusSubQueue.DEAD_LETTER,
            max_wait_time=5
        )

        messages = []
        with receiver:
            # Peek messages (doesn't remove them)
            peeked_messages = receiver.peek_messages(max_message_count=max_messages)

            for msg in peeked_messages:
                messages.append({
                    "message_id": msg.message_id,
                    "enqueued_time": msg.enqueued_time_utc.isoformat() if msg.enqueued_time_utc else None,
                    "dead_letter_reason": msg.dead_letter_reason,
                    "dead_letter_error_description": msg.dead_letter_error_description,
                    "body": str(msg),
                    "delivery_count": msg.delivery_count
                })

        return {
            "total_peeked": len(messages),
            "messages": messages
        }

    except Exception as e:
        logger.error(f"Error peeking dead-letter messages: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to peek dead-letter messages: {str(e)}"
        )


@router.get("/worker-health", response_model=Dict[str, Any])
async def get_worker_health(db: AsyncSession = Depends(get_db)):
    """
    Check worker health and processing statistics.

    Returns counts of documents by status and identifies any stuck in PROCESSING.
    """
    try:
        # Count documents by status
        from sqlalchemy import func

        status_counts = {}
        for doc_status in DocumentStatus:
            result = await db.execute(
                select(func.count(Document.id)).where(Document.status == doc_status)
            )
            count = result.scalar()
            status_counts[doc_status.value] = count

        # Find documents stuck in PROCESSING for more than 10 minutes
        from datetime import datetime, timedelta
        ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)

        result = await db.execute(
            select(Document).where(
                and_(
                    Document.status == DocumentStatus.PROCESSING,
                    Document.processing_started_at < ten_minutes_ago
                )
            )
        )
        stuck_documents = result.scalars().all()

        return {
            "status_counts": status_counts,
            "stuck_processing_count": len(stuck_documents),
            "stuck_documents": [
                {
                    "id": doc.id,
                    "filename": doc.original_filename,
                    "processing_started_at": doc.processing_started_at.isoformat() if doc.processing_started_at else None
                }
                for doc in stuck_documents
            ]
        }

    except Exception as e:
        logger.error(f"Error getting worker health: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get worker health: {str(e)}"
        )
