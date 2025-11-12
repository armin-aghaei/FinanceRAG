#!/usr/bin/env python3
"""
Test script to upload a document to Azure Blob Storage with metadata
for Azure AI Search Integrated Vectorization testing
"""
import os
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "raw-documents"
PDF_PATH = "/Users/arminaghaei/Desktop/Finance AI/PDF to Database App/Sample Documents/aapl-20250927-10k.pdf"

# Test metadata
TEST_USER_ID = 1
TEST_FOLDER_ID = 1
TEST_DOCUMENT_ID = 1

def upload_test_document():
    """Upload test document with metadata to Azure Blob Storage"""

    print("=" * 60)
    print("Testing Azure AI Search Integrated Vectorization")
    print("=" * 60)
    print()

    # Initialize blob service client
    blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(CONTAINER_NAME)

    # Get filename
    filename = os.path.basename(PDF_PATH)
    blob_name = f"folder_{TEST_FOLDER_ID}/{filename}"

    print(f"📄 Uploading: {filename}")
    print(f"📁 Blob path: {blob_name}")
    print(f"👤 User ID: {TEST_USER_ID}")
    print(f"📂 Folder ID: {TEST_FOLDER_ID}")
    print(f"🆔 Document ID: {TEST_DOCUMENT_ID}")
    print()

    # Metadata for Azure AI Search
    metadata = {
        "user_id": str(TEST_USER_ID),
        "folder_id": str(TEST_FOLDER_ID),
        "document_id": str(TEST_DOCUMENT_ID)
    }

    # Upload blob
    blob_client = container_client.get_blob_client(blob_name)

    with open(PDF_PATH, "rb") as data:
        blob_client.upload_blob(
            data,
            overwrite=True,
            metadata=metadata
        )

    print("✅ Upload successful!")
    print()
    print("Next steps:")
    print("  1. Azure AI Search indexer will detect the new blob (runs every 5 minutes)")
    print("  2. DocumentIntelligenceLayoutSkill will extract document structure")
    print("  3. TextSplitSkill will chunk the markdown content")
    print("  4. AzureOpenAIEmbeddingSkill will generate embeddings")
    print("  5. Chunks will be stored in 'document-chunks' index")
    print()
    print("Monitor indexer status:")
    print("  ./check_indexer_status.sh")
    print()

if __name__ == "__main__":
    upload_test_document()
