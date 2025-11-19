from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.folder import Folder
from app.models.document import Document, DocumentStatus
from app.schemas.document import DocumentResponse, DocumentUploadResponse
from app.services.azure_blob import blob_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


def validate_file(file: UploadFile) -> None:
    """Validate uploaded file."""
    # Check file extension
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required"
        )

    file_ext = f".{file.filename.split('.')[-1].lower()}" if '.' in file.filename else ""
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )


async def verify_folder_ownership(
    folder_id: int,
    current_user: User,
    db: AsyncSession
) -> Folder:
    """Verify that the folder belongs to the current user."""
    result = await db.execute(
        select(Folder).where(
            Folder.id == folder_id,
            Folder.user_id == current_user.id
        )
    )
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found"
        )

    return folder


@router.post("/upload/{folder_id}", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    folder_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a document to a folder.

    NOTE: Document processing happens automatically via Azure Service Bus.
    After uploading to Azure Blob Storage, a message is published to Service Bus.
    A background worker consumes the message, triggers the indexer, polls for
    completion, and updates the document status to INDEXED or FAILED.
    This provides reliable, scalable, event-driven processing without
    blocking the API response.
    """
    # Validate file
    validate_file(file)

    # Verify folder ownership
    folder = await verify_folder_ownership(folder_id, current_user, db)

    # Check file size
    file_content = await file.read()
    file_size = len(file_content)

    if file_size > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE_MB}MB"
        )

    try:
        # Create document record first to get document_id
        new_document = Document(
            folder_id=folder_id,
            filename="",  # Will update after upload
            original_filename=file.filename,
            blob_url="",  # Will update after upload
            status=DocumentStatus.PENDING,
            file_size=file_size,
            content_type=file.content_type or "application/pdf"
        )

        db.add(new_document)
        await db.commit()
        await db.refresh(new_document)

        # Upload to Azure Blob Storage with metadata for indexer
        from io import BytesIO
        file_stream = BytesIO(file_content)

        blob_name, blob_url = blob_service.upload_file(
            file_content=file_stream,
            filename=file.filename,
            folder_id=folder_id,
            content_type=file.content_type or "application/pdf",
            user_id=current_user.id,  # For indexer metadata
            document_id=new_document.id  # For indexer metadata
        )

        # Update document with blob info
        new_document.filename = blob_name
        new_document.blob_url = blob_url
        await db.commit()
        await db.refresh(new_document)

        # Publish document indexing event to Service Bus queue
        # The background worker will:
        # 1. Receive the message
        # 2. Trigger Azure AI Search indexer
        # 3. Poll for indexing completion
        # 4. Update document status to INDEXED or FAILED
        from app.services.service_bus_service import service_bus_publisher

        await service_bus_publisher.publish_document_event(
            document_id=new_document.id,
            blob_name=blob_name,
            folder_id=folder_id,
            user_id=current_user.id
        )

        return {
            "id": new_document.id,
            "filename": new_document.original_filename,
            "status": new_document.status,
            "message": "Document uploaded successfully. Processing will begin shortly."
        }

    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload document"
        )


@router.get("/folder/{folder_id}", response_model=List[DocumentResponse])
async def list_documents(
    folder_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all documents in a folder."""
    # Verify folder ownership
    await verify_folder_ownership(folder_id, current_user, db)

    # Get documents
    result = await db.execute(
        select(Document)
        .where(Document.folder_id == folder_id)
        .order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()

    return documents


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific document."""
    # Get document with folder
    result = await db.execute(
        select(Document)
        .join(Folder)
        .where(
            Document.id == document_id,
            Folder.user_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a document and all associated data.

    Deletion process (all three data stores):
    1. Delete from Azure Blob Storage (raw and processed containers)
    2. Delete from Azure Table Storage (metadata)
    3. Delete chunks from Azure AI Search index (by document_id filter)
    4. Delete from PostgreSQL database

    If any step fails, we log the error but continue to ensure cleanup.
    """
    # Get document with folder
    result = await db.execute(
        select(Document)
        .join(Folder)
        .where(
            Document.id == document_id,
            Folder.user_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    deletion_errors = []

    try:
        # Step 1: Delete from Azure Blob Storage
        try:
            blob_service.delete_file(document.filename, settings.RAW_DOCUMENTS_CONTAINER)
            logger.info(f"Deleted blob: {document.filename}")
        except Exception as blob_error:
            error_msg = f"Failed to delete blob {document.filename}: {str(blob_error)}"
            logger.error(error_msg)
            deletion_errors.append(error_msg)

        # Delete processed blob if it exists
        if document.processed_blob_url:
            try:
                processed_blob_name = document.processed_blob_url.split('/')[-1]
                blob_service.delete_file(processed_blob_name, settings.PROCESSED_DOCUMENTS_CONTAINER)
                logger.info(f"Deleted processed blob: {processed_blob_name}")
            except Exception as processed_error:
                error_msg = f"Failed to delete processed blob: {str(processed_error)}"
                logger.error(error_msg)
                deletion_errors.append(error_msg)

        # Step 2: Delete from Azure Table Storage
        try:
            from app.services.azure_table_service import table_service
            table_service.delete_document_metadata(document.filename)
            logger.info(f"Deleted Table Storage metadata for: {document.filename}")
        except Exception as table_error:
            error_msg = f"Failed to delete Table Storage metadata: {str(table_error)}"
            logger.error(error_msg)
            deletion_errors.append(error_msg)

        # Step 3: Delete chunks from Azure AI Search index
        try:
            from app.services.indexer_service import indexer_service
            await indexer_service.delete_document_chunks(document_id)
            logger.info(f"Deleted search index chunks for document_id={document_id}")
        except Exception as index_error:
            error_msg = f"Failed to delete search index chunks: {str(index_error)}"
            logger.error(error_msg)
            deletion_errors.append(error_msg)

        # Step 4: Delete from PostgreSQL database
        try:
            await db.delete(document)
            await db.commit()
            logger.info(f"Deleted database record for document_id={document_id}")
        except Exception as db_error:
            await db.rollback()
            error_msg = f"Failed to delete database record: {str(db_error)}"
            logger.error(error_msg)
            deletion_errors.append(error_msg)
            # Re-raise database errors as they're critical
            raise

        # Log summary
        if deletion_errors:
            logger.warning(f"Document {document_id} deleted with {len(deletion_errors)} errors: {deletion_errors}")
        else:
            logger.info(f"Document {document_id} successfully deleted from all data stores")

        return None

    except Exception as e:
        logger.error(f"Critical error deleting document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
        )
