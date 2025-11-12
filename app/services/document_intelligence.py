from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from app.core.config import settings
from typing import Dict, Any
import logging
import json

logger = logging.getLogger(__name__)


class DocumentIntelligenceService:
    def __init__(self):
        self.client = DocumentAnalysisClient(
            endpoint=settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_DOCUMENT_INTELLIGENCE_KEY)
        )

    async def analyze_document(self, document_url: str) -> Dict[str, Any]:
        """
        Analyze a document using Azure Document Intelligence.

        Args:
            document_url: The URL of the document in blob storage

        Returns:
            Dictionary containing extracted text and metadata
        """
        try:
            # Start the analysis
            poller = self.client.begin_analyze_document_from_url(
                model_id="prebuilt-document",  # Use prebuilt document model
                document_url=document_url
            )

            # Wait for completion
            result = poller.result()

            # Extract content
            extracted_data = {
                "content": result.content,
                "pages": [],
                "tables": [],
                "key_value_pairs": [],
                "entities": []
            }

            # Extract page information
            for page in result.pages:
                page_data = {
                    "page_number": page.page_number,
                    "width": page.width,
                    "height": page.height,
                    "unit": page.unit,
                    "lines": []
                }

                if page.lines:
                    for line in page.lines:
                        page_data["lines"].append({
                            "content": line.content,
                            "polygon": [{"x": p.x, "y": p.y} for p in line.polygon] if line.polygon else []
                        })

                extracted_data["pages"].append(page_data)

            # Extract tables
            if result.tables:
                for table in result.tables:
                    table_data = {
                        "row_count": table.row_count,
                        "column_count": table.column_count,
                        "cells": []
                    }

                    for cell in table.cells:
                        table_data["cells"].append({
                            "content": cell.content,
                            "row_index": cell.row_index,
                            "column_index": cell.column_index,
                            "row_span": cell.row_span if hasattr(cell, 'row_span') else 1,
                            "column_span": cell.column_span if hasattr(cell, 'column_span') else 1
                        })

                    extracted_data["tables"].append(table_data)

            # Extract key-value pairs
            if result.key_value_pairs:
                for kv_pair in result.key_value_pairs:
                    if kv_pair.key and kv_pair.value:
                        extracted_data["key_value_pairs"].append({
                            "key": kv_pair.key.content,
                            "value": kv_pair.value.content
                        })

            logger.info(f"Successfully analyzed document: {document_url}")
            return extracted_data

        except Exception as e:
            logger.error(f"Error analyzing document: {str(e)}")
            raise

    def format_for_search(self, extracted_data: Dict[str, Any], document_id: int, filename: str) -> Dict[str, Any]:
        """
        Format extracted data for Azure AI Search indexing.

        Returns:
            Dictionary formatted for search indexing
        """
        # Combine all text content
        full_text = extracted_data.get("content", "")

        # Extract table data as text
        table_text = []
        for table in extracted_data.get("tables", []):
            table_text.append(f"Table with {table['row_count']} rows and {table['column_count']} columns")
            for cell in table["cells"]:
                table_text.append(cell["content"])

        # Create search document
        search_doc = {
            "id": str(document_id),
            "filename": filename,
            "content": full_text,
            "table_content": " ".join(table_text),
            "page_count": len(extracted_data.get("pages", [])),
            "metadata": json.dumps(extracted_data.get("key_value_pairs", []))
        }

        return search_doc


# Singleton instance
document_intelligence_service = DocumentIntelligenceService()
