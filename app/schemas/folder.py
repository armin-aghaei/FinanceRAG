from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class FolderCreate(BaseModel):
    folder_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=4, description="Folder password must be at least 4 characters")


class FolderAccess(BaseModel):
    password: str


class FolderResponse(BaseModel):
    id: int
    folder_name: str
    user_id: int
    document_count: Optional[int] = 0
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
