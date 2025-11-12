"""
Azure AI Search service for document retrieval with folder isolation
"""
import re
import base64
from typing import List, Dict, Any, Optional
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import os

class SearchService:
    """Service for searching documents with folder isolation"""

    def __init__(self):
        self.endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
        self.key = os.getenv("AZURE_SEARCH_KEY")
        self.index_name = "document-chunks"

        self.client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(self.key)
        )

    @staticmethod
    def extract_folder_id_from_parent_id(parent_id: str) -> Optional[int]:
        """
        Extract folder_id from base64-encoded parent_id

        parent_id format (base64): https://...blob.core.windows.net/raw-documents/folder_X/filename.pdf
        Returns: X (as integer) or None if not found
        """
        try:
            # Decode base64
            decoded = base64.b64decode(parent_id + "==").decode('utf-8', errors='ignore')

            # Extract folder_X pattern
            match = re.search(r'/folder_(\d+)/', decoded)
            if match:
                return int(match.group(1))
            return None
        except Exception:
            return None

    def search_with_folder_filter(
        self,
        query: str,
        folder_id: int,
        top: int = 5,
        use_semantic: bool = True,
        debug: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search documents with folder isolation

        Args:
            query: Search query text
            folder_id: Folder ID to filter by (enforces user isolation)
            top: Number of results to return
            use_semantic: Use semantic search ranking
            debug: Print debug information

        Returns:
            List of search results filtered by folder_id
        """
        # Perform search without folder filter first
        # (since folder_id field is null, we filter in application layer)
        search_params = {
            "search_text": query,
            "top": top * 3,  # Get more results to filter
            "select": ["id", "parent_id", "title", "chunk_content"],
        }

        if use_semantic:
            search_params["query_type"] = "semantic"
            search_params["semantic_configuration_name"] = "semantic-config"

        results = list(self.client.search(**search_params))

        if debug:
            print(f"\n[DEBUG] Total raw results from Azure Search: {len(results)}")
            folder_distribution = {}

        # Filter results by folder_id extracted from parent_id
        filtered_results = []
        for result in results:
            parent_id = result.get("parent_id")
            if parent_id:
                result_folder_id = self.extract_folder_id_from_parent_id(parent_id)

                if debug:
                    # Track folder distribution
                    if result_folder_id:
                        folder_distribution[result_folder_id] = folder_distribution.get(result_folder_id, 0) + 1

                if result_folder_id == folder_id:
                    filtered_results.append({
                        "id": result.get("id"),
                        "title": result.get("title"),
                        "content": result.get("chunk_content"),
                        "score": result.get("@search.score"),
                        "folder_id": result_folder_id
                    })

                    if len(filtered_results) >= top:
                        break

        if debug:
            print(f"[DEBUG] Folder distribution in results: {folder_distribution}")
            print(f"[DEBUG] Results matching folder_id={folder_id}: {len(filtered_results)}")

        return filtered_results

    def search_multi_folder(
        self,
        query: str,
        folder_ids: List[int],
        top: int = 5,
        use_semantic: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search across multiple folders (for users with multiple folder access)

        Args:
            query: Search query text
            folder_ids: List of folder IDs user has access to
            top: Number of results to return
            use_semantic: Use semantic search ranking

        Returns:
            List of search results from allowed folders
        """
        search_params = {
            "search_text": query,
            "top": top * 5,  # Get more results to filter
            "select": ["id", "parent_id", "title", "chunk_content"],
        }

        if use_semantic:
            search_params["query_type"] = "semantic"
            search_params["semantic_configuration_name"] = "semantic-config"

        results = list(self.client.search(**search_params))

        # Filter results by allowed folder_ids
        filtered_results = []
        for result in results:
            parent_id = result.get("parent_id")
            if parent_id:
                result_folder_id = self.extract_folder_id_from_parent_id(parent_id)
                if result_folder_id in folder_ids:
                    filtered_results.append({
                        "id": result.get("id"),
                        "title": result.get("title"),
                        "content": result.get("chunk_content"),
                        "score": result.get("@search.score"),
                        "folder_id": result_folder_id
                    })

                    if len(filtered_results) >= top:
                        break

        return filtered_results
