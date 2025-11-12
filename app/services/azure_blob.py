from azure.storage.blob import BlobServiceClient, ContentSettings
from app.core.config import settings
import uuid
from typing import BinaryIO, Tuple
import logging

logger = logging.getLogger(__name__)


class AzureBlobService:
    def __init__(self):
        self.blob_service_client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )
        self.raw_container = settings.RAW_DOCUMENTS_CONTAINER
        self.processed_container = settings.PROCESSED_DOCUMENTS_CONTAINER

    async def ensure_containers_exist(self):
        """Ensure that both blob containers exist."""
        try:
            # Create raw documents container if it doesn't exist
            raw_container_client = self.blob_service_client.get_container_client(self.raw_container)
            if not raw_container_client.exists():
                raw_container_client.create_container()
                logger.info(f"Created container: {self.raw_container}")

            # Create processed documents container if it doesn't exist
            processed_container_client = self.blob_service_client.get_container_client(self.processed_container)
            if not processed_container_client.exists():
                processed_container_client.create_container()
                logger.info(f"Created container: {self.processed_container}")

        except Exception as e:
            logger.error(f"Error ensuring containers exist: {str(e)}")
            raise

    def upload_file(
        self,
        file_content: BinaryIO,
        filename: str,
        folder_id: int,
        content_type: str = "application/pdf",
        user_id: int = None,
        document_id: int = None
    ) -> Tuple[str, str]:
        """
        Upload a file to the raw documents container.

        Returns:
            Tuple of (blob_name, blob_url)
        """
        # Generate unique blob name with folder isolation
        file_extension = filename.split('.')[-1] if '.' in filename else 'pdf'
        blob_name = f"folder-{folder_id}/{uuid.uuid4()}.{file_extension}"

        try:
            # Get blob client
            blob_client = self.blob_service_client.get_blob_client(
                container=self.raw_container,
                blob=blob_name
            )

            # Prepare metadata for Azure AI Search indexer
            # Metadata is used by the indexer to populate folder_id, user_id fields
            metadata = {
                'folder_id': str(folder_id),
            }

            if user_id is not None:
                metadata['user_id'] = str(user_id)

            if document_id is not None:
                metadata['document_id'] = str(document_id)

            # Upload the file with metadata
            content_settings = ContentSettings(content_type=content_type)
            blob_client.upload_blob(
                file_content,
                content_settings=content_settings,
                metadata=metadata,
                overwrite=True
            )

            # Return blob name and URL
            blob_url = blob_client.url
            logger.info(f"Uploaded file to blob storage: {blob_name}")

            return blob_name, blob_url

        except Exception as e:
            logger.error(f"Error uploading file to blob storage: {str(e)}")
            raise

    def delete_file(self, blob_name: str, container: str = None):
        """Delete a file from blob storage."""
        if container is None:
            container = self.raw_container

        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=container,
                blob=blob_name
            )
            blob_client.delete_blob()
            logger.info(f"Deleted blob: {blob_name}")

        except Exception as e:
            logger.error(f"Error deleting blob: {str(e)}")
            raise

    def get_blob_url(self, blob_name: str, container: str = None) -> str:
        """Get the URL of a blob."""
        if container is None:
            container = self.raw_container

        blob_client = self.blob_service_client.get_blob_client(
            container=container,
            blob=blob_name
        )
        return blob_client.url

    def download_blob(self, blob_name: str, container: str = None) -> bytes:
        """Download a blob's content."""
        if container is None:
            container = self.raw_container

        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=container,
                blob=blob_name
            )
            blob_data = blob_client.download_blob()
            return blob_data.readall()

        except Exception as e:
            logger.error(f"Error downloading blob: {str(e)}")
            raise


# Singleton instance
blob_service = AzureBlobService()
