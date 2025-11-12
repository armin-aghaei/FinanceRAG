"""
Azure AI Search Indexer Management Service

This service manages the Azure AI Search indexer for RAG document processing.
Replaces the manual per-folder index approach with a single index and folder filtering.
"""

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from app.core.config import settings
from typing import List, Dict, Any, Optional
import logging
import httpx

logger = logging.getLogger(__name__)


class IndexerService:
    def __init__(self):
        self.endpoint = settings.AZURE_SEARCH_ENDPOINT
        self.credential = AzureKeyCredential(settings.AZURE_SEARCH_KEY)
        self.index_name = "document-chunks"
        self.indexer_name = "rag-document-indexer"

        self.search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=self.credential
        )

    async def trigger_indexer_run(self, wait_for_completion: bool = False) -> Dict[str, Any]:
        """
        Trigger the indexer to run immediately.

        Args:
            wait_for_completion: If True, wait for indexer to complete

        Returns:
            Indexer execution status
        """
        try:
            # Trigger indexer via REST API
            url = f"{self.endpoint}/indexers/{self.indexer_name}/run?api-version=2024-07-01"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={
                        "api-key": settings.AZURE_SEARCH_KEY,
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code == 202:
                    logger.info(f"Indexer {self.indexer_name} triggered successfully")

                    if wait_for_completion:
                        status = await self.get_indexer_status()
                        return status

                    return {"status": "running", "message": "Indexer triggered"}
                else:
                    logger.error(f"Failed to trigger indexer: {response.text}")
                    return {"status": "error", "message": response.text}

        except Exception as e:
            logger.error(f"Error triggering indexer: {str(e)}")
            raise

    async def get_indexer_status(self) -> Dict[str, Any]:
        """
        Get the current status of the indexer.

        Returns:
            Indexer status information
        """
        try:
            url = f"{self.endpoint}/indexers/{self.indexer_name}/status?api-version=2024-07-01"

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={"api-key": settings.AZURE_SEARCH_KEY}
                )

                if response.status_code == 200:
                    status_data = response.json()
                    return {
                        "status": status_data.get("status"),
                        "lastResult": status_data.get("lastResult"),
                        "executionHistory": status_data.get("executionHistory", [])[:5]
                    }
                else:
                    logger.error(f"Failed to get indexer status: {response.text}")
                    return {"status": "error", "message": response.text}

        except Exception as e:
            logger.error(f"Error getting indexer status: {str(e)}")
            raise

    async def search_with_folder_filter(
        self,
        query: str,
        query_vector: List[float],
        folder_id: int,
        top: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Perform vector search with folder isolation filter.

        Args:
            query: The search query text
            query_vector: The query embedding vector
            folder_id: Folder ID to filter by
            top: Number of results to return

        Returns:
            List of search results
        """
        try:
            # Create vector query
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=top,
                fields="content_vector"
            )

            # Search with folder filter (hybrid search: vector + text)
            results = self.search_client.search(
                search_text=query,
                vector_queries=[vector_query],
                filter=f"folder_id eq {folder_id}",
                select=["chunk_content", "title", "page_number", "document_id", "parent_id"],
                top=top
            )

            # Convert results to list
            search_results = []
            for result in results:
                search_results.append({
                    "score": result.get("@search.score", 0),
                    "content": result.get("chunk_content", ""),
                    "title": result.get("title", ""),
                    "page_number": result.get("page_number"),
                    "document_id": result.get("document_id"),
                    "parent_id": result.get("parent_id")
                })

            logger.info(f"Search completed: {len(search_results)} results found for folder {folder_id}")
            return search_results

        except Exception as e:
            logger.error(f"Error searching index: {str(e)}")
            raise

    async def delete_document_chunks(self, document_id: int) -> bool:
        """
        Delete all chunks for a specific document from the index.

        Args:
            document_id: The document ID to delete chunks for

        Returns:
            True if successful
        """
        try:
            # Search for all chunks with this document_id
            results = self.search_client.search(
                search_text="*",
                filter=f"document_id eq {document_id}",
                select=["id"],
                top=1000  # Max chunks per document
            )

            # Collect document IDs to delete
            doc_ids = [{"id": result["id"]} for result in results]

            if doc_ids:
                # Delete documents
                self.search_client.delete_documents(documents=doc_ids)
                logger.info(f"Deleted {len(doc_ids)} chunks for document {document_id}")
            else:
                logger.info(f"No chunks found for document {document_id}")

            return True

        except Exception as e:
            logger.error(f"Error deleting document chunks: {str(e)}")
            return False

    async def get_index_stats(self, folder_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get statistics about the index.

        Args:
            folder_id: Optional folder ID to get stats for specific folder

        Returns:
            Index statistics
        """
        try:
            # Get total document count
            if folder_id:
                results = self.search_client.search(
                    search_text="*",
                    filter=f"folder_id eq {folder_id}",
                    include_total_count=True,
                    top=0
                )
            else:
                results = self.search_client.search(
                    search_text="*",
                    include_total_count=True,
                    top=0
                )

            # Azure Search results have a get_count() method
            total_count = 0
            for _ in results:
                total_count += 1

            return {
                "total_chunks": total_count,
                "folder_id": folder_id,
                "index_name": self.index_name
            }

        except Exception as e:
            logger.error(f"Error getting index stats: {str(e)}")
            return {"error": str(e)}


# Singleton instance
indexer_service = IndexerService()
