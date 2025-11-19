"""
Document Indexing Worker

Background worker that consumes messages from Azure Service Bus and orchestrates
document indexing with automatic status updates.

Workflow:
1. Receive message from Service Bus queue (document_id, blob_name, folder_id, user_id)
2. Acquire PostgreSQL row-level lock (prevents duplicate processing)
3. Trigger Azure AI Search indexer
4. Poll for indexing completion (check if chunks exist in index)
5. Update document status to INDEXED or FAILED
6. Complete message (delete from queue) on success, dead-letter on failure
"""

from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from app.services.indexer_service import indexer_service
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.document import Document, DocumentStatus
from sqlalchemy import select
from datetime import datetime
import asyncio
import json
import logging
import uuid

logger = logging.getLogger(__name__)


class DocumentIndexingWorker:
    """Background worker for processing document indexing events."""

    def __init__(self):
        self.connection_string = settings.SERVICE_BUS_CONNECTION_STRING
        self.queue_name = settings.SERVICE_BUS_QUEUE_NAME
        self.max_concurrent_messages = 10  # Process up to 10 documents concurrently
        self.max_retries = 12  # 12 retries × 10 seconds = 2 minutes max wait
        self.retry_delay = 10  # seconds between retries

    async def start(self):
        """
        Start the worker loop.

        This runs continuously, polling Service Bus for messages and processing them.
        """
        logger.info("Document indexing worker starting...")

        try:
            async with ServiceBusClient.from_connection_string(
                self.connection_string
            ) as client:
                receiver = client.get_queue_receiver(
                    queue_name=self.queue_name,
                    max_wait_time=5  # Wait up to 5 seconds for messages
                )

                async with receiver:
                    logger.info(f"Worker connected to queue: {self.queue_name}")

                    while True:
                        try:
                            # Receive batch of messages
                            received_msgs = await receiver.receive_messages(
                                max_message_count=self.max_concurrent_messages,
                                max_wait_time=5
                            )

                            if received_msgs:
                                logger.info(f"Received {len(received_msgs)} messages from queue")

                                # Process messages concurrently
                                tasks = [
                                    self.process_message(msg, receiver)
                                    for msg in received_msgs
                                ]
                                await asyncio.gather(*tasks, return_exceptions=True)
                            else:
                                # No messages, brief pause before next poll
                                await asyncio.sleep(1)

                        except Exception as e:
                            logger.error(f"Error in worker loop: {str(e)}", exc_info=True)
                            await asyncio.sleep(5)  # Back off on error

        except Exception as e:
            logger.error(f"Fatal worker error: {str(e)}", exc_info=True)
            raise

    async def process_message(self, message, receiver):
        """
        Process a single document indexing message.

        Args:
            message: Service Bus message
            receiver: Service Bus receiver for completing/dead-lettering messages
        """
        try:
            # Parse message
            data = json.loads(str(message))
            document_id = data["document_id"]
            blob_name = data["blob_name"]
            folder_id = data["folder_id"]
            user_id = data["user_id"]

            logger.info(f"Processing document {document_id} (blob: {blob_name})")

            # Try to acquire processing lock
            lock_acquired = await self.try_acquire_lock(document_id)

            if not lock_acquired:
                # Document already processed or being processed
                logger.info(f"Document {document_id} already processed, skipping")
                await receiver.complete_message(message)
                return

            # Trigger indexer
            logger.info(f"Triggering indexer for document {document_id}")
            await indexer_service.trigger_indexer_run()

            # Poll for indexing completion
            success = await self.wait_for_indexing(document_id, blob_name)

            if success:
                # Update status to INDEXED
                await self.update_document_status(
                    document_id,
                    DocumentStatus.INDEXED,
                    error_message=None
                )

                # Complete message (delete from queue)
                await receiver.complete_message(message)
                logger.info(f"✅ Document {document_id} indexed successfully")

            else:
                # Indexing failed after retries
                await self.update_document_status(
                    document_id,
                    DocumentStatus.FAILED,
                    error_message="Indexing timeout: chunks not found after 2 minutes"
                )

                # Move to dead-letter queue for investigation
                await receiver.dead_letter_message(
                    message,
                    reason="IndexingTimeout",
                    error_description="Document chunks not found in index after maximum retries"
                )
                logger.error(f"❌ Document {document_id} indexing failed, moved to DLQ")

        except Exception as e:
            logger.error(
                f"Error processing message for document {data.get('document_id', 'unknown')}: {str(e)}",
                exc_info=True
            )

            # Abandon message (will be retried by Service Bus)
            try:
                await receiver.abandon_message(message)
            except Exception as abandon_error:
                logger.error(f"Failed to abandon message: {str(abandon_error)}")

    async def try_acquire_lock(self, document_id: int) -> bool:
        """
        Try to acquire processing lock for document.

        Uses PostgreSQL row-level locking (FOR UPDATE) to prevent duplicate processing.

        Args:
            document_id: Document ID to lock

        Returns:
            True if lock acquired, False if document already processed/processing
        """
        try:
            async with AsyncSessionLocal() as session:
                # Acquire row-level lock
                result = await session.execute(
                    select(Document)
                    .where(Document.id == document_id)
                    .with_for_update()  # PostgreSQL row-level lock
                )
                document = result.scalar_one_or_none()

                if not document:
                    logger.warning(f"Document {document_id} not found in database")
                    return False

                # Check if already processed
                if document.status != DocumentStatus.PENDING:
                    logger.info(f"Document {document_id} status is {document.status}, skipping")
                    return False

                # Acquire lock
                document.status = DocumentStatus.PROCESSING
                document.processing_started_at = datetime.utcnow()
                document.processing_lock_id = str(uuid.uuid4())

                await session.commit()

                logger.info(f"Acquired lock for document {document_id}")
                return True

        except Exception as e:
            logger.error(f"Error acquiring lock for document {document_id}: {str(e)}")
            return False

    async def wait_for_indexing(self, document_id: int, blob_name: str) -> bool:
        """
        Poll Azure AI Search index for document chunks.

        Waits up to 2 minutes (12 retries × 10 seconds) for indexer to create chunks.

        Args:
            document_id: Document ID to check
            blob_name: Blob name in storage

        Returns:
            True if chunks found, False if timeout
        """
        for attempt in range(1, self.max_retries + 1):
            logger.info(
                f"Checking for chunks (attempt {attempt}/{self.max_retries}) "
                f"for document {document_id}"
            )

            # Check if chunks exist in index
            chunks_exist = await self.check_chunks_exist(document_id)

            if chunks_exist:
                logger.info(f"Chunks found for document {document_id} on attempt {attempt}")
                return True

            # Wait before next retry
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay)

        logger.warning(
            f"Chunks not found for document {document_id} after {self.max_retries} attempts"
        )
        return False

    async def check_chunks_exist(self, document_id: int) -> bool:
        """
        Check if document chunks exist in Azure AI Search index.

        Args:
            document_id: Document ID to check

        Returns:
            True if chunks exist, False otherwise
        """
        try:
            # Search for chunks with this document_id
            results = indexer_service.search_client.search(
                search_text="*",
                filter=f"document_id eq '{document_id}'",
                select=["chunk_id"],
                top=1  # Just need to know if any exist
            )

            # Check if any results
            for _ in results:
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking chunks for document {document_id}: {str(e)}")
            return False

    async def update_document_status(
        self,
        document_id: int,
        status: DocumentStatus,
        error_message: str = None
    ):
        """
        Update document status in PostgreSQL.

        Args:
            document_id: Document ID to update
            status: New status
            error_message: Optional error message for FAILED status
        """
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Document).where(Document.id == document_id)
                )
                document = result.scalar_one_or_none()

                if not document:
                    logger.error(f"Document {document_id} not found for status update")
                    return

                old_status = document.status
                document.status = status
                document.updated_at = datetime.utcnow()

                if error_message:
                    document.error_message = error_message

                await session.commit()

                logger.info(
                    f"Updated document {document_id} status: {old_status} → {status}"
                )

        except Exception as e:
            logger.error(
                f"Error updating document {document_id} status: {str(e)}",
                exc_info=True
            )


# Singleton instance
document_worker = DocumentIndexingWorker()
