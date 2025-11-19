"""
Metadata merger service for Azure Function.

This module provides functionality to merge metadata from Azure Table Storage
into Azure AI Search index chunks after semantic chunking is complete.
"""

import logging
import base64
import os
from typing import Dict, Any
from azure.data.tables import TableServiceClient, TableClient
import httpx
import asyncio

logger = logging.getLogger(__name__)

# Azure configuration from environment variables
AZURE_SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.environ.get("AZURE_SEARCH_KEY")
AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
TABLE_NAME = "documentmetadata"
INDEX_NAME = "finance-folder-2"  # Target index for metadata merging


class MetadataMerger:
    """Handles merging metadata from Table Storage into search index chunks."""

    def __init__(self):
        self.search_endpoint = AZURE_SEARCH_ENDPOINT
        self.search_key = AZURE_SEARCH_KEY
        self.table_client = self._get_table_client()

    def _get_table_client(self) -> TableClient:
        """Get Table Storage client."""
        table_service_client = TableServiceClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING
        )
        return table_service_client.get_table_client(TABLE_NAME)

    @staticmethod
    def _encode_blob_name(blob_name: str) -> str:
        """Encode blob name to Base64 for Table Storage key."""
        return base64.b64encode(blob_name.encode('utf-8')).decode('utf-8')

    def get_document_metadata(self, blob_name: str) -> Dict[str, Any]:
        """
        Retrieve document metadata from Table Storage.

        Args:
            blob_name: Blob name (e.g., "folder-3/uuid.pdf")

        Returns:
            Dictionary with metadata (folder_id, user_id, document_id)
        """
        try:
            encoded_key = self._encode_blob_name(blob_name)
            entity = self.table_client.get_entity(
                partition_key=encoded_key,
                row_key=encoded_key
            )
            return dict(entity)
        except Exception as e:
            logger.error(f"Error getting metadata for {blob_name}: {str(e)}")
            raise

    async def merge_metadata_for_document(
        self,
        blob_name: str,
        folder_id: int,
        user_id: int,
        document_id: int,
        max_retries: int = 5,
        retry_delay: int = 10
    ) -> dict:
        """
        Merge metadata from Table Storage into semantic chunks.

        This function:
        1. Constructs the blob URL and encodes it as parent_id
        2. Searches for all chunks with matching parent_id (with retries)
        3. Merges folder_id, user_id, document_id into those chunks

        Args:
            blob_name: Blob name in storage (e.g., "folder-3/uuid.pdf")
            folder_id: Folder ID for isolation
            user_id: User ID for isolation
            document_id: Document ID for tracking
            max_retries: Number of times to retry if no chunks found
            retry_delay: Seconds to wait between retries

        Returns:
            Dictionary with merge results
        """
        # Construct blob URL (matches what blob indexer uses)
        blob_url = (
            f"https://legalaicontracts.blob.core.windows.net/"
            f"raw-documents/{blob_name}"
        )

        # Base64-encode the blob URL (matches blob indexer's parent_id format)
        parent_id_base64 = base64.b64encode(blob_url.encode('utf-8')).decode('utf-8')

        logger.info(f"Starting metadata merge for blob: {blob_name}")
        logger.info(f"  Using index: {INDEX_NAME}")
        logger.info(f"  parent_id (base64): {parent_id_base64}")
        logger.info(f"  folder_id={folder_id}, user_id={user_id}, document_id={document_id}")

        # Retry logic: wait for indexer to create chunks
        for attempt in range(1, max_retries + 1):
            try:
                # Search for chunks with this parent_id
                chunks = await self._search_chunks_by_parent_id(parent_id_base64)

                if len(chunks) > 0:
                    logger.info(f"Found {len(chunks)} chunks on attempt {attempt}")

                    # Merge metadata into chunks
                    merge_result = await self._merge_metadata_into_chunks(
                        chunks=chunks,
                        folder_id=folder_id,
                        user_id=user_id,
                        document_id=document_id
                    )

                    return {
                        "status": "success",
                        "chunks_found": len(chunks),
                        "chunks_updated": merge_result.get("successful", 0),
                        "attempts": attempt
                    }
                else:
                    logger.info(f"No chunks found on attempt {attempt}/{max_retries}")
                    if attempt < max_retries:
                        logger.info(f"Waiting {retry_delay} seconds before retry...")
                        await asyncio.sleep(retry_delay)

            except Exception as e:
                logger.error(f"Error on attempt {attempt}: {str(e)}")
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay)

        return {
            "status": "no_chunks_found",
            "message": f"No chunks found after {max_retries} attempts",
            "attempts": max_retries
        }

    async def _search_chunks_by_parent_id(self, parent_id_base64: str) -> list:
        """
        Search for all chunks with matching parent_id.

        Args:
            parent_id_base64: Base64-encoded blob URL

        Returns:
            List of chunk dictionaries with chunk_id field
        """
        url = f"{self.search_endpoint}/indexes/{INDEX_NAME}/docs/search?api-version=2024-07-01"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={
                    "api-key": self.search_key,
                    "Content-Type": "application/json"
                },
                json={
                    "search": f"parent_id:'{parent_id_base64}'",
                    "select": "chunk_id",
                    "top": 1000  # Get all chunks for this document
                }
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("value", [])
            else:
                logger.error(f"Search failed: {response.status_code} - {response.text}")
                raise Exception(f"Search failed with status {response.status_code}")

    async def _merge_metadata_into_chunks(
        self,
        chunks: list,
        folder_id: int,
        user_id: int,
        document_id: int
    ) -> dict:
        """
        Merge metadata into chunks using Documents API.

        Args:
            chunks: List of chunk dictionaries with chunk_id
            folder_id: Folder ID to merge
            user_id: User ID to merge
            document_id: Document ID to merge

        Returns:
            Dictionary with merge results
        """
        # Prepare merge documents
        merge_docs = []
        for chunk in chunks:
            merge_docs.append({
                "@search.action": "merge",
                "chunk_id": chunk.get("chunk_id"),
                "folder_id": str(folder_id),
                "user_id": str(user_id),
                "document_id": str(document_id)
            })

        logger.info(f"Merging metadata into {len(merge_docs)} chunks...")

        # Upload merge documents
        url = f"{self.search_endpoint}/indexes/{INDEX_NAME}/docs/index?api-version=2024-07-01"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers={
                    "api-key": self.search_key,
                    "Content-Type": "application/json"
                },
                json={"value": merge_docs}
            )

            if response.status_code == 200:
                result = response.json()
                successful = sum(1 for item in result.get("value", []) if item.get("status"))
                logger.info(f"Successfully merged metadata into {successful} chunks")
                return {"successful": successful, "total": len(merge_docs)}
            else:
                logger.error(f"Merge failed: {response.status_code} - {response.text}")
                raise Exception(f"Merge failed with status {response.status_code}")


# Singleton instance
metadata_merger = MetadataMerger()
