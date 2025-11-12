from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchFieldDataType,
)
from azure.core.credentials import AzureKeyCredential
from app.core.config import settings
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class AISearchService:
    def __init__(self):
        self.endpoint = settings.AZURE_SEARCH_ENDPOINT
        self.credential = AzureKeyCredential(settings.AZURE_SEARCH_KEY)
        self.index_client = SearchIndexClient(
            endpoint=self.endpoint,
            credential=self.credential
        )

    def create_index(self, index_name: str) -> bool:
        """
        Create a new search index for a folder.

        Args:
            index_name: The name of the index to create

        Returns:
            True if successful
        """
        try:
            # Define the index schema
            fields = [
                SimpleField(
                    name="id",
                    type=SearchFieldDataType.String,
                    key=True,
                    filterable=True
                ),
                SearchableField(
                    name="filename",
                    type=SearchFieldDataType.String,
                    filterable=True
                ),
                SearchableField(
                    name="content",
                    type=SearchFieldDataType.String,
                    analyzer_name="en.microsoft"
                ),
                SearchableField(
                    name="table_content",
                    type=SearchFieldDataType.String,
                    analyzer_name="en.microsoft"
                ),
                SimpleField(
                    name="page_count",
                    type=SearchFieldDataType.Int32,
                    filterable=True
                ),
                SearchableField(
                    name="metadata",
                    type=SearchFieldDataType.String
                ),
            ]

            # Create the index
            index = SearchIndex(name=index_name, fields=fields)
            result = self.index_client.create_or_update_index(index)

            logger.info(f"Created search index: {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error creating search index: {str(e)}")
            raise

    def delete_index(self, index_name: str) -> bool:
        """Delete a search index."""
        try:
            self.index_client.delete_index(index_name)
            logger.info(f"Deleted search index: {index_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting search index: {str(e)}")
            return False

    def index_document(self, index_name: str, document: Dict[str, Any]) -> bool:
        """
        Index a single document.

        Args:
            index_name: The name of the index
            document: The document data to index

        Returns:
            True if successful
        """
        try:
            search_client = SearchClient(
                endpoint=self.endpoint,
                index_name=index_name,
                credential=self.credential
            )

            # Upload the document
            result = search_client.upload_documents(documents=[document])

            logger.info(f"Indexed document {document.get('id')} in index {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error indexing document: {str(e)}")
            raise

    def delete_document(self, index_name: str, document_id: str) -> bool:
        """Delete a document from the index."""
        try:
            search_client = SearchClient(
                endpoint=self.endpoint,
                index_name=index_name,
                credential=self.credential
            )

            search_client.delete_documents(documents=[{"id": document_id}])
            logger.info(f"Deleted document {document_id} from index {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting document from index: {str(e)}")
            return False

    def search(
        self,
        index_name: str,
        query: str,
        top: int = 5,
        select: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for documents in the index.

        Args:
            index_name: The name of the index to search
            query: The search query
            top: Number of results to return
            select: Fields to include in results

        Returns:
            List of search results
        """
        try:
            search_client = SearchClient(
                endpoint=self.endpoint,
                index_name=index_name,
                credential=self.credential
            )

            if select is None:
                select = ["id", "filename", "content"]

            results = search_client.search(
                search_text=query,
                top=top,
                select=select
            )

            # Convert results to list of dictionaries
            search_results = []
            for result in results:
                search_results.append({
                    "score": result.get("@search.score"),
                    "id": result.get("id"),
                    "filename": result.get("filename"),
                    "content": result.get("content"),
                    "table_content": result.get("table_content"),
                    "page_count": result.get("page_count")
                })

            logger.info(f"Search completed: {len(search_results)} results found")
            return search_results

        except Exception as e:
            logger.error(f"Error searching index: {str(e)}")
            raise


# Singleton instance
ai_search_service = AISearchService()
