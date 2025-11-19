from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    password: Optional[str] = Field(None, min_length=4, description="Folder password must be at least 4 characters")


class FolderAccess(BaseModel):
    password: str


class FolderResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_password_protected: bool
    document_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True
