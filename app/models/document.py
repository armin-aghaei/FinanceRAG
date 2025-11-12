from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    blob_url = Column(String, nullable=False)  # URL in raw-documents container
    processed_blob_url = Column(String, nullable=True)  # URL in processed-documents container
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    file_size = Column(Integer, nullable=True)  # Size in bytes
    content_type = Column(String, default="application/pdf", nullable=False)
    metadata = Column(JSON, nullable=True)  # Store extracted metadata from Document Intelligence
    error_message = Column(String, nullable=True)  # Store error details if processing fails
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    folder = relationship("Folder", back_populates="documents")
