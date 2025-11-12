#!/bin/bash

# Complete Azure AI Search Integrated Vectorization Setup
# This script creates the index, skillset, data source, and indexer

set -e  # Exit on error

echo "========================================="
echo "Azure AI Search Integrated Vectorization"
echo "========================================="
echo ""

# Configuration - Using values from Legal AI deployment
SEARCH_SERVICE="aa-legal-ai-search"
STORAGE_ACCOUNT="legalaicontracts"
AZURE_OPENAI_ENDPOINT="https://armin-mh2ki86i-eastus2.cognitiveservices.azure.com"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-large"

# Load credentials from environment variables or .env file
AZURE_OPENAI_KEY="${AZURE_OPENAI_KEY}"
SEARCH_ADMIN_KEY="${AZURE_SEARCH_KEY}"
STORAGE_CONNECTION="${AZURE_STORAGE_CONNECTION_STRING}"

SEARCH_ENDPOINT="https://${SEARCH_SERVICE}.search.windows.net"

echo "Configuration:"
echo "  Search Service: ${SEARCH_SERVICE}"
echo "  Storage Account: ${STORAGE_ACCOUNT}"
echo "  OpenAI Endpoint: ${AZURE_OPENAI_ENDPOINT}"
echo ""

# Step 1: Create Index
echo "Step 1: Creating search index..."

# Replace placeholders in index schema
INDEX_JSON=$(cat index_schema.json)

curl -X PUT "${SEARCH_ENDPOINT}/indexes/document-chunks?api-version=2024-11-01-preview" \
  -H "Content-Type: application/json" \
  -H "api-key: ${SEARCH_ADMIN_KEY}" \
  -d "$INDEX_JSON"

echo "✅ Index created"

# Step 2: Create Skillset
echo ""
echo "Step 2: Creating skillset..."

# Replace placeholders in skillset and add API key (using Azure-recommended config)
SKILLSET_JSON=$(cat skillset_config.json | \
  sed "s|\${AZURE_OPENAI_ENDPOINT}|${AZURE_OPENAI_ENDPOINT}|g" | \
  sed "s|\${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}|${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}|g" | \
  jq --arg key "$AZURE_OPENAI_KEY" '.skills[2].apiKey = $key')

curl -X PUT "${SEARCH_ENDPOINT}/skillsets/rag-semantic-skillset?api-version=2024-11-01-preview" \
  -H "Content-Type: application/json" \
  -H "api-key: ${SEARCH_ADMIN_KEY}" \
  -d "$SKILLSET_JSON"

echo "✅ Skillset created"

# Step 3: Create Data Source
echo ""
echo "Step 3: Creating data source..."

# Replace placeholders in data source
DATASOURCE_JSON=$(cat datasource_config.json | \
  sed "s|\${AZURE_STORAGE_CONNECTION_STRING}|${STORAGE_CONNECTION}|g")

curl -X PUT "${SEARCH_ENDPOINT}/datasources/blob-datasource?api-version=2024-11-01-preview" \
  -H "Content-Type: application/json" \
  -H "api-key: ${SEARCH_ADMIN_KEY}" \
  -d "$DATASOURCE_JSON"

echo "✅ Data source created"

# Step 4: Create Indexer
echo ""
echo "Step 4: Creating indexer..."

INDEXER_JSON=$(cat indexer_config.json)

curl -X PUT "${SEARCH_ENDPOINT}/indexers/rag-document-indexer?api-version=2024-11-01-preview" \
  -H "Content-Type: application/json" \
  -H "api-key: ${SEARCH_ADMIN_KEY}" \
  -d "$INDEXER_JSON"

echo "✅ Indexer created"

# Step 5: Verify Setup
echo ""
echo "Step 5: Verifying setup..."

# Check index
INDEX_STATUS=$(curl -s "${SEARCH_ENDPOINT}/indexes/document-chunks?api-version=2024-11-01-preview" \
  -H "api-key: ${SEARCH_ADMIN_KEY}")

if echo "$INDEX_STATUS" | grep -q "document-chunks"; then
  echo "✅ Index verified"
else
  echo "❌ Index verification failed"
fi

# Check skillset
SKILLSET_STATUS=$(curl -s "${SEARCH_ENDPOINT}/skillsets/rag-semantic-skillset?api-version=2024-11-01-preview" \
  -H "api-key: ${SEARCH_ADMIN_KEY}")

if echo "$SKILLSET_STATUS" | grep -q "rag-semantic-skillset"; then
  echo "✅ Skillset verified"
else
  echo "❌ Skillset verification failed"
fi

echo ""
echo "========================================="
echo "✅ Setup Complete!"
echo "========================================="
echo ""
echo "Azure AI Search Integrated Vectorization is configured:"
echo ""
echo "  Index: document-chunks"
echo "  Skillset: rag-semantic-skillset (3 skills)"
echo "    1. Document Intelligence Layout (semantic sections by h3 headers)"
echo "       - Preserves tables as HTML, figures as <figure> tags"
echo "       - Chunks by document structure (paragraphs, tables, sections)"
echo "    2. Text Split (max 5000 chars, 500 overlap, only splits large sections)"
echo "    3. Azure OpenAI Embedding (text-embedding-3-large, 3072 dims)"
echo "  Data Source: blob-datasource (raw-documents)"
echo "  Indexer: rag-document-indexer (runs every 5 minutes)"
echo ""
echo "Next steps:"
echo "  1. Upload a test PDF to raw-documents container"
echo "  2. Monitor indexer: az search indexer show-status ..."
echo "  3. Verify chunks in index"
echo ""
