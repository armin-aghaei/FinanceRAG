#!/bin/bash
# Check Azure AI Search Indexer Status

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

SEARCH_ENDPOINT="${AZURE_SEARCH_ENDPOINT:-https://aa-legal-ai-search.search.windows.net}"
SEARCH_ADMIN_KEY="${AZURE_SEARCH_KEY}"
INDEXER_NAME="rag-document-indexer"
INDEX_NAME="document-chunks"

echo "========================================="
echo "Azure AI Search Indexer Status"
echo "========================================="
echo ""

# Check indexer status
echo "📊 Indexer Status:"
curl -s "${SEARCH_ENDPOINT}/indexers/${INDEXER_NAME}/status?api-version=2024-11-01-preview" \
  -H "api-key: ${SEARCH_ADMIN_KEY}" | jq '{
    name: .name,
    status: .status,
    lastResult: {
      status: .lastResult.status,
      startTime: .lastResult.startTime,
      endTime: .lastResult.endTime,
      itemsProcessed: .lastResult.itemsProcessed,
      itemsFailed: .lastResult.itemsFailed,
      errors: .lastResult.errors,
      warnings: .lastResult.warnings
    }
  }'

echo ""
echo "📈 Index Statistics:"
curl -s "${SEARCH_ENDPOINT}/indexes/${INDEX_NAME}/stats?api-version=2024-11-01-preview" \
  -H "api-key: ${SEARCH_ADMIN_KEY}" | jq '{
    documentCount: .documentCount,
    storageSize: .storageSize
  }'

echo ""
echo "🔍 Sample Chunks (first 3):"
curl -s "${SEARCH_ENDPOINT}/indexes/${INDEX_NAME}/docs?api-version=2024-11-01-preview&\$top=3&\$select=id,title,folder_id,user_id,chunk_content" \
  -H "api-key: ${SEARCH_ADMIN_KEY}" | jq '.value[] | {
    id: .id,
    title: .title,
    folder_id: .folder_id,
    user_id: .user_id,
    chunk_preview: (.chunk_content | .[0:200])
  }'

echo ""
