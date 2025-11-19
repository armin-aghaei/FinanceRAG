"""
Azure Function triggered by Service Bus when a document upload is published.
Triggers Azure AI Search indexer to immediately process the new document.
The indexer reads metadata from blob storage and populates chunks automatically.
Updates document status in PostgreSQL database upon completion.
"""

import azure.functions as func
import logging
import os
import requests
import asyncio

app = func.FunctionApp()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import database utilities
try:
    from shared_code.database import (
        update_document_status,
        get_document_by_blob_name,
        DocumentStatus
    )
    logger.info("✅ Successfully imported database utilities")
except Exception as import_error:
    logger.error(f"❌ Failed to import database utilities: {import_error}", exc_info=True)
    raise

# Azure Search configuration
AZURE_SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.environ.get("AZURE_SEARCH_KEY")
INDEXER_NAME = "finance-folder-2-indexer"  # Main indexer for finance-folder-2 index


@app.function_name(name="ProcessDocumentBlob")
@app.blob_trigger(arg_name="myblob", path="raw-documents/{name}",
                  connection="AzureWebJobsStorage")
async def process_document_blob(myblob: func.InputStream):
    """
    Triggered when a new blob is created in the raw-documents container.
    Triggers the Azure AI Search indexer to immediately process the document,
    then merges metadata from Table Storage into the semantic chunks.

    Args:
        myblob: Input stream for the uploaded blob
    """
    try:
        # Get blob name from the trigger binding
        blob_name = myblob.name.split("/")[-1] if "/" in myblob.name else myblob.name
        blob_path = myblob.name.replace("raw-documents/", "")  # Get path without container name

        logger.info(f"Blob trigger activated for: {blob_path}")
        logger.info(f"Blob size: {myblob.length} bytes")

        # Validate this is a PDF file
        if not blob_path.lower().endswith('.pdf'):
            logger.info(f"Skipping non-PDF file: {blob_path}")
            return

        logger.info(f"Processing new PDF: {blob_path}")

        # Trigger Azure AI Search indexer to process the new document
        # The indexer reads metadata from blob storage and populates chunks automatically
        await trigger_indexer()
        logger.info(f"Successfully triggered indexer for document: {blob_path}")

    except Exception as e:
        logger.error(f"Error processing blob trigger: {str(e)}", exc_info=True)
        # Re-raise to trigger Azure Functions retry mechanism
        raise


async def trigger_indexer():
    """Trigger the Azure AI Search indexer to run immediately."""
    try:
        url = f"{AZURE_SEARCH_ENDPOINT}/indexers/{INDEXER_NAME}/run?api-version=2024-07-01"
        headers = {
            "api-key": AZURE_SEARCH_KEY,
            "Content-Length": "0"
        }

        response = requests.post(url, headers=headers)

        if response.status_code == 202:
            logger.info("Successfully triggered Azure AI Search indexer")
        else:
            logger.warning(f"Indexer trigger returned status {response.status_code}: {response.text}")

    except Exception as e:
        logger.error(f"Error triggering indexer: {str(e)}")
        # Don't re-raise - we don't want to fail the event if indexer trigger fails
        # The scheduled indexer will pick it up anyway


@app.function_name(name="ProcessDocumentQueue")
@app.service_bus_queue_trigger(arg_name="msg", queue_name="document-indexing",
                                connection="ServiceBusConnection")
async def process_document_queue(msg: func.ServiceBusMessage):
    """
    Triggered when a new message arrives in the Service Bus queue.
    Processes the document by triggering the indexer and merging metadata.

    Args:
        msg: Service Bus message containing document processing details
    """
    try:
        # Get message body
        import json
        message_body = msg.get_body().decode('utf-8')
        data = json.loads(message_body)

        document_id = data.get('document_id')
        blob_name = data.get('blob_name')
        folder_id = data.get('folder_id')
        user_id = data.get('user_id')

        logger.info(f"Service Bus trigger activated for document {document_id}")
        logger.info(f"Blob: {blob_name}, Folder: {folder_id}, User: {user_id}")

        # Validate required fields
        if not all([document_id, blob_name, folder_id, user_id]):
            logger.error(f"Missing required fields in message: {data}")
            return

        try:
            # Update document status to PROCESSING
            logger.info(f"Updating document {document_id} status to PROCESSING")
            success = update_document_status(document_id, DocumentStatus.PROCESSING)
            if not success:
                error_msg = f"Failed to update document {document_id} to PROCESSING status"
                logger.error(error_msg)
                raise Exception(error_msg)

            # Trigger Azure AI Search indexer to process the new document
            await trigger_indexer()
            logger.info(f"Successfully triggered indexer for document {document_id}")

            # Wait for indexer to complete processing
            # The indexer reads metadata directly from blob storage and populates chunks
            # No need for manual metadata merging!
            logger.info(f"Waiting 30 seconds for indexer to process document...")
            await asyncio.sleep(30)

            # Update document status to INDEXED in database
            logger.info(f"Updating document {document_id} status to INDEXED")
            success = update_document_status(document_id, DocumentStatus.INDEXED)
            if success:
                logger.info(f"✅ Document {document_id} successfully indexed!")
            else:
                error_msg = f"Failed to update document {document_id} to INDEXED status"
                logger.error(error_msg)
                raise Exception(error_msg)

        except Exception as processing_error:
            # Log error and update document status to FAILED
            logger.error(f"Error processing document {document_id}: {str(processing_error)}", exc_info=True)

            # Update document status to FAILED
            update_document_status(
                document_id,
                DocumentStatus.FAILED,
                f"Processing error: {str(processing_error)}"
            )
            # Re-raise to trigger retry
            raise

    except Exception as e:
        logger.error(f"Error processing Service Bus message: {str(e)}", exc_info=True)
        # Re-raise to trigger Azure Functions retry mechanism and eventually dead-letter
        raise


@app.function_name(name="TestDatabaseConnection")
@app.route(route="test-db", methods=["GET"])
def test_database_connection(req: func.HttpRequest) -> func.HttpResponse:
    """
    Test HTTP endpoint to verify database connection and log output.

    Usage: GET https://rag-document-processor.azurewebsites.net/api/test-db?document_id=39
    """
    try:
        document_id = req.params.get('document_id', '39')
        document_id = int(document_id)

        logger.info(f"Test endpoint called for document {document_id}")

        # Test database connection
        from shared_code.database import DatabaseConnection
        session = DatabaseConnection.get_session()

        from shared_code.database import Document
        doc = session.query(Document).filter(Document.id == document_id).first()

        if doc:
            result = {
                "status": "success",
                "document_id": doc.id,
                "filename": doc.filename,
                "current_status": doc.status.value if hasattr(doc.status, 'value') else str(doc.status),
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "database_url": os.environ.get("DATABASE_URL", "NOT SET")[:50] + "..."
            }
            logger.info(f"Database connection successful, found document {document_id}")
            session.close()

            import json
            return func.HttpResponse(
                json.dumps(result, indent=2),
                mimetype="application/json",
                status_code=200
            )
        else:
            logger.warning(f"Document {document_id} not found")
            session.close()
            return func.HttpResponse(
                f"Document {document_id} not found",
                status_code=404
            )

    except Exception as e:
        logger.error(f"Test endpoint error: {str(e)}", exc_info=True)
        import json
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )
