"""
Metadata Merger Service for Semantic Chunks

This service handles automatic metadata propagation from Table Storage
to semantic chunks created by DocumentIntelligenceLayoutSkill.

Since dual data source indexing doesn't work with semantic chunking's
generated child document IDs, this service uses the Documents API to
directly merge metadata after the blob indexer creates chunks.
"""

import httpx
import base64
import asyncio
from typing import Optional
from app.core.config import settings
from app.services.azure_table_service import table_service
import logging

logger = logging.getLogger(__name__)


class MetadataMergerService:
    def __init__(self):
        self.endpoint = settings.AZURE_SEARCH_ENDPOINT
        self.api_key = settings.AZURE_SEARCH_KEY

    def _get_index_name_for_folder(self, folder_id: int) -> str:
        """
        Determine the index name based on folder ID.

        All documents use the same index: finance-folder-2
        Folder isolation is handled via the folder_id field in the index.

        Args:
            folder_id: The folder ID (not used for index selection)

        Returns:
            Index name to use for this folder
        """
        return "finance-folder-2"

    async def merge_metadata_for_document(
        self,
        blob_name: str,
        folder_id: int,
        user_id: int,
        document_id: int,
        max_retries: int = 3,
        retry_delay: int = 10,
        index_name: str = None
    ) -> dict:
        """
        Merge metadata from Table Storage into semantic chunks.

        This function:
        1. Constructs the blob URL and encodes it as parent_id
        2. Searches for all chunks with matching parent_id
        3. Merges folder_id, user_id, document_id into those chunks

        Args:
            blob_name: Blob name in storage (e.g., "folder-3/uuid.pdf")
            folder_id: Folder ID for isolation
            user_id: User ID for isolation
            document_id: Document ID for tracking
            max_retries: Number of times to retry if no chunks found
            retry_delay: Seconds to wait between retries
            index_name: Optional index name override (defaults to finance-folder-2)

        Returns:
            Dictionary with merge results
        """
        # Determine which index to use
        if index_name is None:
            index_name = self._get_index_name_for_folder(folder_id)

        # Construct blob URL (matches what blob indexer uses)
        blob_url = (
            f"https://legalaicontracts.blob.core.windows.net/"
            f"raw-documents/{blob_name}"
        )

        # Base64-encode the blob URL (matches blob indexer's parent_id format)
        parent_id_base64 = base64.b64encode(blob_url.encode('utf-8')).decode('utf-8')

        logger.info(f"Starting metadata merge for blob: {blob_name}")
        logger.info(f"  Using index: {index_name}")
        logger.info(f"  parent_id (base64): {parent_id_base64}")
        logger.info(f"  folder_id={folder_id}, user_id={user_id}, document_id={document_id}")

        # Retry logic: wait for indexer to create chunks
        for attempt in range(1, max_retries + 1):
            try:
                # Search for chunks with this parent_id
                chunks = await self._search_chunks_by_parent_id(parent_id_base64, index_name)

                if len(chunks) > 0:
                    logger.info(f"Found {len(chunks)} chunks on attempt {attempt}")

                    # Merge metadata into chunks
                    merge_result = await self._merge_metadata_into_chunks(
                        chunks=chunks,
                        folder_id=folder_id,
                        user_id=user_id,
                        document_id=document_id,
                        index_name=index_name
                    )

                    return {
                        "status": "success",
                        "chunks_found": len(chunks),
                        "chunks_updated": merge_result.get("successful", 0),
                        "attempts": attempt
                    }
                else:
                    logger.warning(
                        f"No chunks found on attempt {attempt}/{max_retries}. "
                        f"Indexer may still be processing..."
                    )

                    if attempt < max_retries:
                        logger.info(f"Waiting {retry_delay} seconds before retry...")
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(
                            f"No chunks found after {max_retries} attempts. "
                            f"Indexer may have failed or document may not have been processed."
                        )
                        return {
                            "status": "no_chunks_found",
                            "chunks_found": 0,
                            "attempts": attempt,
                            "message": "No chunks found after maximum retries"
                        }

            except Exception as e:
                logger.error(f"Error during metadata merge attempt {attempt}: {str(e)}")

                if attempt < max_retries:
                    await asyncio.sleep(retry_delay)
                else:
                    return {
                        "status": "error",
                        "error": str(e),
                        "attempts": attempt
                    }

        return {
            "status": "error",
            "message": "Unexpected end of retry loop"
        }

    async def _search_chunks_by_parent_id(self, parent_id_base64: str, index_name: str) -> list:
        """
        Search for all chunks with matching parent_id.

        Note: Azure AI Search Document Intelligence skillset sometimes adds an extra
        character to the parent_id. We try both the exact match and with the extra char.

        Args:
            parent_id_base64: Base64-encoded blob URL
            index_name: Name of the index to search

        Returns:
            List of chunk dictionaries with chunk_id field
        """
        url = f"{self.endpoint}/indexes/{index_name}/docs/search?api-version=2024-07-01"

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try exact match first
            response = await client.post(
                url,
                headers={
                    "api-key": self.api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "search": "*",
                    "filter": f"parent_id eq '{parent_id_base64}'",
                    "select": "chunk_id",
                    "top": 1000  # Max chunks per document
                }
            )

            if response.status_code == 200:
                data = response.json()
                chunks = data.get('value', [])

                # If no chunks found, try with an extra '0' at the end
                # (Azure AI Search Document Intelligence quirk)
                if len(chunks) == 0:
                    logger.info(f"No chunks found with exact parent_id, trying with extra character...")
                    response = await client.post(
                        url,
                        headers={
                            "api-key": self.api_key,
                            "Content-Type": "application/json"
                        },
                        json={
                            "search": "*",
                            "filter": f"parent_id eq '{parent_id_base64}0'",
                            "select": "chunk_id",
                            "top": 1000
                        }
                    )

                    if response.status_code == 200:
                        data = response.json()
                        chunks = data.get('value', [])
                        if len(chunks) > 0:
                            logger.info(f"Found {len(chunks)} chunks with modified parent_id")

                return chunks
            else:
                logger.error(f"Search failed: {response.status_code} - {response.text}")
                raise Exception(f"Search failed with status {response.status_code}")

    async def _merge_metadata_into_chunks(
        self,
        chunks: list,
        folder_id: int,
        user_id: int,
        document_id: int,
        index_name: str
    ) -> dict:
        """
        Merge metadata into chunks using Documents API.

        Args:
            chunks: List of chunk dictionaries with chunk_id
            folder_id: Folder ID to merge
            user_id: User ID to merge
            document_id: Document ID to merge
            index_name: Name of the index to update

        Returns:
            Dictionary with merge results
        """
        # Prepare merge documents
        merge_docs = []
        for chunk in chunks:
            merge_docs.append({
                "@search.action": "merge",
                "chunk_id": chunk['chunk_id'],
                "folder_id": str(folder_id),
                "user_id": str(user_id),
                "document_id": str(document_id)
            })

        logger.info(f"Merging metadata into {len(merge_docs)} chunks...")

        # Upload merge documents
        url = f"{self.endpoint}/indexes/{index_name}/docs/index?api-version=2024-07-01"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers={
                    "api-key": self.api_key,
                    "Content-Type": "application/json"
                },
                json={"value": merge_docs}
            )

            if response.status_code in [200, 201]:
                result = response.json()
                successful = sum(1 for r in result.get('value', []) if r.get('status'))

                logger.info(f"Metadata merge completed: {successful}/{len(merge_docs)} chunks updated")

                return {
                    "successful": successful,
                    "total": len(merge_docs),
                    "result": result
                }
            else:
                logger.error(f"Merge failed: {response.status_code} - {response.text}")
                raise Exception(f"Merge failed with status {response.status_code}")


# Singleton instance
metadata_merger_service = MetadataMergerService()
