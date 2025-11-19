"""
Database connection and models for Azure Function.

This module provides database connectivity to update document status
after successful indexing and metadata merge operations.
"""

import os
import logging
from enum import Enum
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime

logger = logging.getLogger(__name__)

# Base for SQLAlchemy models
Base = declarative_base()


class DocumentStatus(str, Enum):
    """Document processing status enum - must match backend model."""
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class Document(Base):
    """Document model - minimal version for status updates."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, nullable=False)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    blob_url = Column(String, nullable=False)
    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class DatabaseConnection:
    """Manages database connection for Azure Function."""

    _engine = None
    _SessionLocal = None

    @classmethod
    def initialize(cls):
        """Initialize database connection from environment variable."""
        if cls._engine is not None:
            return

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL environment variable not set")
            raise ValueError("DATABASE_URL environment variable is required")

        # Convert postgres:// to postgresql:// for SQLAlchemy
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        # Convert postgresql+asyncpg:// to postgresql:// for sync SQLAlchemy
        # (The main API uses async, but Azure Function uses sync)
        if database_url.startswith("postgresql+asyncpg://"):
            database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

        logger.info("Initializing database connection")
        cls._engine = create_engine(
            database_url,
            pool_pre_ping=True,  # Verify connections before using
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,  # Recycle connections after 1 hour
        )
        cls._SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls._engine)
        logger.info("Database connection initialized successfully")

    @classmethod
    def get_session(cls) -> Session:
        """Get a database session."""
        if cls._SessionLocal is None:
            cls.initialize()
        return cls._SessionLocal()


def update_document_status(
    document_id: int,
    status: DocumentStatus,
    error_message: Optional[str] = None
) -> bool:
    """
    Update document status in the database.

    Args:
        document_id: ID of the document to update
        status: New status to set
        error_message: Optional error message if status is FAILED

    Returns:
        True if update was successful, False otherwise
    """
    session = None
    try:
        session = DatabaseConnection.get_session()

        # Find the document
        document = session.query(Document).filter(Document.id == document_id).first()

        if not document:
            logger.error(f"Document {document_id} not found in database")
            return False

        old_status = document.status
        document.status = status
        document.updated_at = datetime.utcnow()

        if error_message:
            document.error_message = error_message

        session.commit()

        logger.info(
            f"Updated document {document_id} status: {old_status} → {status}"
            + (f" (error: {error_message})" if error_message else "")
        )

        return True

    except Exception as e:
        logger.error(f"Error updating document {document_id} status: {str(e)}", exc_info=True)
        if session:
            session.rollback()
        return False

    finally:
        if session:
            session.close()


def get_document_by_blob_name(blob_name: str) -> Optional[Document]:
    """
    Find a document by its blob filename.

    Args:
        blob_name: Blob name in format "folder-{id}/{uuid}.pdf"

    Returns:
        Document instance if found, None otherwise
    """
    session = None
    try:
        session = DatabaseConnection.get_session()

        # Extract the filename from the blob path
        # blob_name format: "folder-{folder_id}/{uuid}.pdf"
        filename = blob_name.split('/')[-1] if '/' in blob_name else blob_name

        # Query by filename
        document = session.query(Document).filter(Document.filename == filename).first()

        if document:
            logger.info(f"Found document {document.id} for blob {blob_name}")
            return document
        else:
            logger.warning(f"No document found for blob {blob_name} (filename: {filename})")
            return None

    except Exception as e:
        logger.error(f"Error finding document for blob {blob_name}: {str(e)}", exc_info=True)
        return None

    finally:
        if session:
            session.close()
