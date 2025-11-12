from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.document import Document, DocumentStatus
from app.models.folder import Folder
from app.services.document_intelligence import document_intelligence_service
from app.services.ai_search import ai_search_service
from app.services.azure_blob import blob_service
from app.core.config import settings
import logging
import json
from io import BytesIO

logger = logging.getLogger(__name__)


async def process_document(document_id: int, db: AsyncSession):
    """
    Background task to process a document through the pipeline:
    1. Analyze with Document Intelligence
    2. Store processed results in blob storage
    3. Index in Azure AI Search
    """
    try:
        # Get the document
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            logger.error(f"Document {document_id} not found")
            return

        # Update status to processing
        document.status = DocumentStatus.PROCESSING
        await db.commit()

        # Get the folder to access search index name
        result = await db.execute(
            select(Folder).where(Folder.id == document.folder_id)
        )
        folder = result.scalar_one_or_none()

        if not folder:
            logger.error(f"Folder {document.folder_id} not found")
            document.status = DocumentStatus.FAILED
            document.error_message = "Folder not found"
            await db.commit()
            return

        # Ensure search index exists
        if not folder.search_index_name:
            logger.error(f"Folder {folder.id} has no search index")
            document.status = DocumentStatus.FAILED
            document.error_message = "Search index not configured"
            await db.commit()
            return

        try:
            ai_search_service.create_index(folder.search_index_name)
        except Exception as e:
            logger.warning(f"Index may already exist or error creating: {str(e)}")

        # Step 1: Analyze document with Document Intelligence
        logger.info(f"Analyzing document {document_id} with Document Intelligence")
        extracted_data = await document_intelligence_service.analyze_document(document.blob_url)

        # Step 2: Store processed data in blob storage
        logger.info(f"Storing processed data for document {document_id}")
        processed_data_json = json.dumps(extracted_data, indent=2)
        processed_blob_name = f"folder-{folder.id}/processed-{document.id}.json"

        from azure.storage.blob import BlobServiceClient
        blob_service_client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )
        processed_blob_client = blob_service_client.get_blob_client(
            container=settings.PROCESSED_DOCUMENTS_CONTAINER,
            blob=processed_blob_name
        )
        processed_blob_client.upload_blob(
            processed_data_json,
            overwrite=True
        )
        processed_blob_url = processed_blob_client.url

        # Update document with processed blob URL and metadata
        document.processed_blob_url = processed_blob_url
        document.doc_metadata = {
            "page_count": len(extracted_data.get("pages", [])),
            "table_count": len(extracted_data.get("tables", [])),
            "key_value_pairs": extracted_data.get("key_value_pairs", [])
        }

        # Step 3: Format for search and index
        logger.info(f"Indexing document {document_id} in Azure AI Search")
        search_doc = document_intelligence_service.format_for_search(
            extracted_data,
            document.id,
            document.original_filename
        )

        ai_search_service.index_document(folder.search_index_name, search_doc)

        # Update status to indexed
        document.status = DocumentStatus.INDEXED
        document.error_message = None
        await db.commit()

        logger.info(f"Successfully processed document {document_id}")

    except Exception as e:
        logger.error(f"Error processing document {document_id}: {str(e)}")

        # Update document status to failed
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if document:
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)
            await db.commit()
