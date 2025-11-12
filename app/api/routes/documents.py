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

    NOTE: Document processing happens automatically via Azure Event Grid.
    When the file is uploaded to Azure Blob Storage, an Event Grid event
    is triggered which invokes an Azure Function to process the document.
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

        # Processing happens automatically via Azure AI Search Indexer
        # The indexer runs every 5 minutes and:
        # 1. Detects new blobs in raw-documents container
        # 2. Extracts structure with Document Intelligence Layout skill
        # 3. Chunks semantically with Text Split skill
        # 4. Generates embeddings with Azure OpenAI skill
        # 5. Indexes chunks with folder_id, user_id metadata for isolation
        #
        # The Event Grid function still monitors and updates document status

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
    """Delete a document."""
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

    try:
        # Delete from blob storage
        blob_service.delete_file(document.filename, settings.RAW_DOCUMENTS_CONTAINER)

        if document.processed_blob_url:
            # Extract blob name from URL and delete processed version
            # This is a simplified version - you might need more robust URL parsing
            processed_blob_name = document.processed_blob_url.split('/')[-1]
            blob_service.delete_file(processed_blob_name, settings.PROCESSED_DOCUMENTS_CONTAINER)

        # Delete from database
        await db.delete(document)
        await db.commit()

        return None

    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
        )
