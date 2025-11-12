"""Configuration for Azure Function"""
import os


class Settings:
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    RAW_DOCUMENTS_CONTAINER = os.getenv("RAW_DOCUMENTS_CONTAINER", "raw-documents")
    PROCESSED_DOCUMENTS_CONTAINER = os.getenv("PROCESSED_DOCUMENTS_CONTAINER", "processed-documents")

    # Azure Document Intelligence
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    AZURE_DOCUMENT_INTELLIGENCE_KEY = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")

    # Azure AI Search
    AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
    AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
    AZURE_SEARCH_INDEX_PREFIX = os.getenv("AZURE_SEARCH_INDEX_PREFIX", "rag-index")

    # Azure OpenAI (if needed for future enhancements)
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
    AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")


settings = Settings()
