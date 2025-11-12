"""
Document processing logic for Azure Function.
Simplified to work with Azure AI Search Integrated Vectorization.
The indexer handles chunking, embedding, and indexing automatically.
"""

import logging
import json
import httpx
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from azure.core.credentials import AzureKeyCredential

from shared_code.config import settings

logger = logging.getLogger(__name__)


# Database models (simplified for function use)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Enum as SQLEnum
import enum

Base = declarative_base()


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    folder_id = Column(Integer)
    filename = Column(String)
    original_filename = Column(String)
    blob_url = Column(String)
    processed_blob_url = Column(String)
    status = Column(SQLEnum(DocumentStatus))
    metadata = Column(String)  # JSON string
    error_message = Column(String)


class Folder(Base):
    __tablename__ = "folders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    folder_name = Column(String)


# Indexer Service
class IndexerService:
    """
    Simplified indexer service for Azure Function.
    Triggers the Azure AI Search indexer which handles all processing automatically.
    """
    def __init__(self):
        self.endpoint = settings.AZURE_SEARCH_ENDPOINT
        self.indexer_name = "rag-document-indexer"
        self.api_key = settings.AZURE_SEARCH_KEY

    async def trigger_indexer_run(self) -> dict:
        """Trigger the indexer to run immediately."""
        try:
            url = f"{self.endpoint}/indexers/{self.indexer_name}/run?api-version=2024-07-01"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={
                        "api-key": self.api_key,
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code == 202:
                    logger.info(f"Indexer {self.indexer_name} triggered successfully")
                    return {"status": "running", "message": "Indexer triggered"}
                else:
                    logger.error(f"Failed to trigger indexer: {response.text}")
                    return {"status": "error", "message": response.text}

        except Exception as e:
            logger.error(f"Error triggering indexer: {str(e)}")
            raise

    async def get_indexer_status(self) -> dict:
        """Get the current status of the indexer."""
        try:
            url = f"{self.endpoint}/indexers/{self.indexer_name}/status?api-version=2024-07-01"

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={"api-key": self.api_key}
                )

                if response.status_code == 200:
                    status_data = response.json()
                    return {
                        "status": status_data.get("status"),
                        "lastResult": status_data.get("lastResult"),
                        "executionHistory": status_data.get("executionHistory", [])[:5]
                    }
                else:
                    logger.error(f"Failed to get indexer status: {response.text}")
                    return {"status": "error", "message": response.text}

        except Exception as e:
            logger.error(f"Error getting indexer status: {str(e)}")
            raise

    async def wait_for_indexer_completion(self, max_wait_seconds: int = 300, poll_interval: int = 5) -> dict:
        """
        Wait for indexer to complete processing.

        Args:
            max_wait_seconds: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds

        Returns:
            Final indexer status
        """
        elapsed = 0
        while elapsed < max_wait_seconds:
            status = await self.get_indexer_status()

            last_result = status.get("lastResult", {})
            if last_result:
                status_value = last_result.get("status")

                if status_value == "success":
                    logger.info("Indexer completed successfully")
                    return status
                elif status_value in ["transientFailure", "failed"]:
                    logger.error(f"Indexer failed: {last_result.get('errorMessage')}")
                    return status

            # Still running, wait and check again
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            logger.info(f"Indexer still running... ({elapsed}s elapsed)")

        logger.warning(f"Indexer timeout after {max_wait_seconds}s")
        return {"status": "timeout", "message": f"Indexer did not complete within {max_wait_seconds}s"}


# Main processing function
async def process_document_from_blob(blob_url: str, blob_path: str, folder_id: int):
    """
    Process a document that was uploaded to blob storage.

    With Integrated Vectorization, the Azure AI Search indexer handles:
    - Document Intelligence extraction (Layout model with markdown output)
    - Semantic chunking (2000 char chunks, 500 char overlap)
    - Embedding generation (Azure OpenAI text-embedding-3-small)
    - Indexing to Azure AI Search

    This function just needs to:
    1. Update document status to processing
    2. Trigger the indexer
    3. Monitor indexer status
    4. Update document status when complete

    Args:
        blob_url: Full URL of the blob
        blob_path: Path within the container (e.g., "folder-1/abc123.pdf")
        folder_id: ID of the folder this document belongs to
    """
    engine = None
    session = None

    try:
        # Create database connection
        # Convert async URL to sync for SQLAlchemy 1.x style
        db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Find document by blob path/filename
        document = session.query(Document).filter(
            Document.filename == blob_path,
            Document.folder_id == folder_id
        ).first()

        if not document:
            logger.error(f"Document not found for blob: {blob_path}")
            return

        # Update status to processing
        document.status = DocumentStatus.PROCESSING
        session.commit()
        logger.info(f"Processing document {document.id} - triggering indexer")

        # Initialize indexer service
        indexer_service = IndexerService()

        # Trigger the indexer to process the new blob
        # The indexer will:
        # 1. Read blob metadata (folder_id, user_id, document_id)
        # 2. Extract content with Document Intelligence Layout skill
        # 3. Chunk content semantically with Text Split skill
        # 4. Generate embeddings with Azure OpenAI Embedding skill
        # 5. Index chunks with folder_id for isolation
        trigger_result = await indexer_service.trigger_indexer_run()

        if trigger_result.get("status") == "error":
            raise Exception(f"Failed to trigger indexer: {trigger_result.get('message')}")

        logger.info(f"Indexer triggered for document {document.id}")

        # Wait for indexer to complete (with timeout)
        # Note: In production, you might want to make this async/background
        # and update status via a separate monitoring function
        indexer_status = await indexer_service.wait_for_indexer_completion(
            max_wait_seconds=300,  # 5 minutes max
            poll_interval=10  # Check every 10 seconds
        )

        last_result = indexer_status.get("lastResult", {})
        if last_result.get("status") == "success":
            # Update status to indexed
            document.status = DocumentStatus.INDEXED
            document.error_message = None
            document.metadata = json.dumps({
                "indexer_result": "success",
                "items_indexed": last_result.get("itemsProcessed", 0)
            })
            session.commit()
            logger.info(f"Successfully processed document {document.id} via indexer")

        elif last_result.get("status") in ["transientFailure", "failed"]:
            # Indexer failed
            raise Exception(f"Indexer failed: {last_result.get('errorMessage', 'Unknown error')}")

        else:
            # Timeout or unknown status
            logger.warning(f"Indexer status unclear for document {document.id}: {indexer_status}")
            # Keep status as PROCESSING - indexer may still complete
            document.metadata = json.dumps({
                "indexer_result": "timeout",
                "note": "Indexer may still be running"
            })
            session.commit()

    except Exception as e:
        logger.error(f"Error processing document: {str(e)}", exc_info=True)

        # Update document status to failed
        if session and document:
            try:
                document.status = DocumentStatus.FAILED
                document.error_message = str(e)[:500]  # Limit error message length
                session.commit()
            except Exception as commit_error:
                logger.error(f"Error updating document status: {str(commit_error)}")

        # Re-raise to trigger Event Grid retry
        raise

    finally:
        if session:
            session.close()
        if engine:
            engine.dispose()
