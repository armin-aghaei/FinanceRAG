"""
Azure Service Bus Service for Document Processing Queue

This service publishes document indexing events to Azure Service Bus queue,
which are consumed by the background worker for reliable status tracking.
"""

from azure.servicebus.aio import ServiceBusClient, ServiceBusMessage
from app.core.config import settings
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)


class ServiceBusPublisher:
    """Publisher for document indexing events to Service Bus queue."""

    def __init__(self):
        self.connection_string = settings.SERVICE_BUS_CONNECTION_STRING
        self.queue_name = settings.SERVICE_BUS_QUEUE_NAME

    async def publish_document_event(
        self,
        document_id: int,
        blob_name: str,
        folder_id: int,
        user_id: int
    ) -> bool:
        """
        Publish document indexing event to Service Bus queue.

        This message will be consumed by the background worker, which will:
        1. Trigger the Azure AI Search indexer
        2. Poll for indexing completion
        3. Update document status to INDEXED or FAILED

        Args:
            document_id: ID of the document in PostgreSQL
            blob_name: Name of blob in raw-documents container (e.g., "folder-3/uuid.pdf")
            folder_id: Folder ID for isolation
            user_id: User ID who uploaded the document

        Returns:
            True if message published successfully, False otherwise
        """
        try:
            async with ServiceBusClient.from_connection_string(
                self.connection_string
            ) as client:
                sender = client.get_queue_sender(self.queue_name)

                async with sender:
                    # Create message payload
                    message_body = json.dumps({
                        "document_id": document_id,
                        "blob_name": blob_name,
                        "folder_id": folder_id,
                        "user_id": user_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    # Create Service Bus message
                    message = ServiceBusMessage(
                        body=message_body,
                        message_id=f"doc-{document_id}",  # Unique ID for tracking
                        time_to_live=timedelta(days=7)  # Message expires after 7 days
                    )

                    # Send message to queue
                    await sender.send_messages(message)

                    logger.info(
                        f"Published document {document_id} to Service Bus queue "
                        f"(blob: {blob_name}, folder: {folder_id}, user: {user_id})"
                    )

                    return True

        except Exception as e:
            logger.error(
                f"Failed to publish document {document_id} to Service Bus: {str(e)}",
                exc_info=True
            )
            # Don't raise - allow upload to succeed even if queue publish fails
            # Worker can be triggered manually or via scheduled indexer as fallback
            return False


# Singleton instance
service_bus_publisher = ServiceBusPublisher()
