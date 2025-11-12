from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any
from app.models.document import DocumentStatus


class DocumentResponse(BaseModel):
    id: int
    folder_id: int
    filename: str
    original_filename: str
    status: DocumentStatus
    file_size: Optional[int]
    content_type: str
    metadata: Optional[Dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class DocumentUploadResponse(BaseModel):
    id: int
    filename: str
    status: DocumentStatus
    message: str


class ChatRequest(BaseModel):
    query: str
    folder_id: int


class ChatResponse(BaseModel):
    answer: str
    sources: Optional[list] = []
