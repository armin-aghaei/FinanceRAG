from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import verify_password, get_password_hash
from app.models.user import User
from app.models.folder import Folder
from app.models.document import Document
from app.schemas.folder import FolderCreate, FolderResponse, FolderAccess

router = APIRouter(prefix="/folders", tags=["Folders"])


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    folder_data: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new folder for the current user.

    With Integrated Vectorization, all folders share a single Azure AI Search index.
    Folder isolation is handled via folder_id filtering at query time.
    """
    # Hash the folder password if provided
    hashed_password = get_password_hash(folder_data.password) if folder_data.password else None

    # Create the folder
    new_folder = Folder(
        user_id=current_user.id,
        folder_name=folder_data.name,
        description=folder_data.description,
        hashed_password=hashed_password
    )

    db.add(new_folder)
    await db.commit()
    await db.refresh(new_folder)

    # Return response with frontend-expected fields
    return {
        "id": new_folder.id,
        "name": new_folder.folder_name,
        "description": new_folder.description,
        "is_password_protected": new_folder.hashed_password is not None,
        "document_count": 0,
        "created_at": new_folder.created_at
    }


@router.get("", response_model=List[FolderResponse])
async def list_folders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all folders for the current user."""
    # Get folders with document count
    result = await db.execute(
        select(
            Folder,
            func.count(Document.id).label("document_count")
        )
        .outerjoin(Document, Folder.id == Document.folder_id)
        .where(Folder.user_id == current_user.id)
        .group_by(Folder.id)
    )

    folders_with_counts = result.all()

    # Format response with frontend-expected fields
    response = []
    for folder, doc_count in folders_with_counts:
        folder_dict = {
            "id": folder.id,
            "name": folder.folder_name,
            "description": folder.description,
            "is_password_protected": folder.hashed_password is not None,
            "document_count": doc_count,
            "created_at": folder.created_at
        }
        response.append(folder_dict)

    return response


@router.post("/{folder_id}/access")
async def verify_folder_access(
    folder_id: int,
    access_data: FolderAccess,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Verify folder password and grant access."""
    # Get the folder
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

    # Verify password
    if not verify_password(access_data.password, folder.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect folder password"
        )

    return {"message": "Access granted", "folder_id": folder_id}


@router.get("/{folder_id}", response_model=FolderResponse)
async def get_folder(
    folder_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific folder."""
    result = await db.execute(
        select(
            Folder,
            func.count(Document.id).label("document_count")
        )
        .outerjoin(Document, Folder.id == Document.folder_id)
        .where(
            Folder.id == folder_id,
            Folder.user_id == current_user.id
        )
        .group_by(Folder.id)
    )

    folder_data = result.one_or_none()

    if not folder_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found"
        )

    folder, doc_count = folder_data

    return {
        "id": folder.id,
        "name": folder.folder_name,
        "description": folder.description,
        "is_password_protected": folder.hashed_password is not None,
        "document_count": doc_count,
        "created_at": folder.created_at
    }


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a folder and all its documents."""
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

    # TODO: Delete associated blobs from Azure Storage
    # TODO: Delete document chunks from shared Azure AI Search index (use indexer_service)

    await db.delete(folder)
    await db.commit()

    return None
