"""
Azure Table Storage Service for Document Metadata

This service manages document metadata in Azure Table Storage,
which is indexed by Azure AI Search to provide metadata for semantic chunks.
"""

from azure.data.tables import TableServiceClient, TableClient
from app.core.config import settings
from typing import Dict, Any
import logging
import base64

logger = logging.getLogger(__name__)


class AzureTableService:
    def __init__(self):
        self.table_service_client = TableServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )
        self.table_name = "documentmetadata"
        self.table_client: TableClient = self.table_service_client.get_table_client(self.table_name)

        # Ensure table exists
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Ensure the table exists, create if it doesn't."""
        try:
            # Try to create the table (idempotent - won't fail if exists)
            self.table_service_client.create_table_if_not_exists(self.table_name)
            logger.info(f"Table '{self.table_name}' exists or was created")
        except Exception as e:
            logger.error(f"Error ensuring table exists: {str(e)}")
            # Don't raise - table might already exist

    @staticmethod
    def _encode_blob_name(blob_name: str) -> str:
        """
        Encode blob name to Base64 for use as Table Storage key.
        This handles blob names with forward slashes.

        Args:
            blob_name: Original blob name (e.g., "folder-3/uuid.pdf")

        Returns:
            Base64-encoded blob name safe for Table Storage keys
        """
        return base64.b64encode(blob_name.encode('utf-8')).decode('utf-8')

    @staticmethod
    def _decode_blob_name(encoded_name: str) -> str:
        """
        Decode Base64-encoded blob name.

        Args:
            encoded_name: Base64-encoded blob name

        Returns:
            Original blob name
        """
        return base64.b64decode(encoded_name.encode('utf-8')).decode('utf-8')

    def upsert_document_metadata(
        self,
        blob_name: str,
        folder_id: int,
        user_id: int,
        document_id: int,
        filename: str = None
    ) -> bool:
        """
        Upsert document metadata to Table Storage.

        Uses Base64 encoding for blob names to handle forward slashes,
        following Microsoft's recommended approach for dual data source indexing.

        Table Schema:
        - PartitionKey: Base64-encoded blob name (safe for Table Storage)
        - RowKey: Base64-encoded blob name (same as PartitionKey)
        - blob_name: Original blob name (for reference)
        - folder_id: Folder ID for isolation
        - user_id: User ID for isolation
        - document_id: Document ID for tracking
        - filename: Original filename (optional)

        Args:
            blob_name: Blob name in storage (e.g., "folder-3/uuid.pdf")
            folder_id: Folder ID
            user_id: User ID
            document_id: Document ID
            filename: Original filename (optional)

        Returns:
            True if successful
        """
        try:
            # Encode blob name to Base64 for use as Table Storage key
            encoded_key = self._encode_blob_name(blob_name)

            entity = {
                "PartitionKey": encoded_key,  # Base64-encoded for safety
                "RowKey": encoded_key,  # Same as PartitionKey
                "blob_name": blob_name,  # Store original for reference
                "folder_id": str(folder_id),  # Store as string for consistency
                "user_id": str(user_id),
                "document_id": str(document_id),
            }

            if filename:
                entity["filename"] = filename

            self.table_client.upsert_entity(entity)
            logger.info(f"Upserted metadata for blob: {blob_name} (key: {encoded_key})")
            return True

        except Exception as e:
            logger.error(f"Error upserting document metadata: {str(e)}")
            raise

    def get_document_metadata(self, blob_name: str) -> Dict[str, Any]:
        """
        Get document metadata from Table Storage.

        Args:
            blob_name: Blob name in storage

        Returns:
            Dictionary with metadata
        """
        try:
            encoded_key = self._encode_blob_name(blob_name)
            entity = self.table_client.get_entity(
                partition_key=encoded_key,
                row_key=encoded_key
            )
            return dict(entity)

        except Exception as e:
            logger.error(f"Error getting document metadata: {str(e)}")
            raise

    def delete_document_metadata(self, blob_name: str) -> bool:
        """
        Delete document metadata from Table Storage.

        Args:
            blob_name: Blob name in storage

        Returns:
            True if successful
        """
        try:
            encoded_key = self._encode_blob_name(blob_name)
            self.table_client.delete_entity(
                partition_key=encoded_key,
                row_key=encoded_key
            )
            logger.info(f"Deleted metadata for blob: {blob_name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting document metadata: {str(e)}")
            return False


# Singleton instance
table_service = AzureTableService()
