#!/bin/bash

# Azure Event Grid Setup Script
# This script configures Event Grid to trigger Azure Functions when PDFs are uploaded

set -e  # Exit on error

echo "========================================="
echo "Azure Event Grid Setup"
echo "========================================="
echo ""

# Configuration - UPDATE THESE VALUES
RESOURCE_GROUP="rag-app-rg"
STORAGE_ACCOUNT="ragstorage2024"
FUNCTION_APP="rag-document-processor"
LOCATION="eastus"
SUBSCRIPTION_NAME="blob-created-subscription"

# Derived values
STORAGE_ID="/subscriptions/$(az account show --query id -o tsv)/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/${STORAGE_ACCOUNT}"
FUNCTION_ID="/subscriptions/$(az account show --query id -o tsv)/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Web/sites/${FUNCTION_APP}"

echo "Configuration:"
echo "  Resource Group: ${RESOURCE_GROUP}"
echo "  Storage Account: ${STORAGE_ACCOUNT}"
echo "  Function App: ${FUNCTION_APP}"
echo ""

# Step 1: Check if resources exist
echo "Step 1: Verifying resources..."

if ! az storage account show --name ${STORAGE_ACCOUNT} --resource-group ${RESOURCE_GROUP} &>/dev/null; then
    echo "❌ Storage account ${STORAGE_ACCOUNT} not found"
    exit 1
fi
echo "✅ Storage account found"

if ! az functionapp show --name ${FUNCTION_APP} --resource-group ${RESOURCE_GROUP} &>/dev/null; then
    echo "❌ Function app ${FUNCTION_APP} not found"
    exit 1
fi
echo "✅ Function app found"

# Step 2: Get Function URL
echo ""
echo "Step 2: Getting Azure Function endpoint..."
FUNCTION_KEY=$(az functionapp keys list --name ${FUNCTION_APP} --resource-group ${RESOURCE_GROUP} --query systemKeys.default -o tsv)
FUNCTION_ENDPOINT="https://${FUNCTION_APP}.azurewebsites.net/runtime/webhooks/eventgrid?functionName=ProcessDocumentEvent&code=${FUNCTION_KEY}"

echo "Function endpoint: ${FUNCTION_ENDPOINT}"

# Step 3: Create Event Grid subscription
echo ""
echo "Step 3: Creating Event Grid subscription..."

az eventgrid event-subscription create \
  --name ${SUBSCRIPTION_NAME} \
  --source-resource-id ${STORAGE_ID} \
  --endpoint ${FUNCTION_ENDPOINT} \
  --endpoint-type azurefunction \
  --included-event-types Microsoft.Storage.BlobCreated \
  --subject-begins-with "/blobServices/default/containers/raw-documents/blobs/" \
  --advanced-filter data.contentType StringContains application/pdf

echo ""
echo "✅ Event Grid subscription created successfully!"

# Step 4: Verify subscription
echo ""
echo "Step 4: Verifying subscription..."

az eventgrid event-subscription show \
  --name ${SUBSCRIPTION_NAME} \
  --source-resource-id ${STORAGE_ID}

echo ""
echo "========================================="
echo "✅ Setup Complete!"
echo "========================================="
echo ""
echo "Event Grid is now configured to:"
echo "  1. Monitor: ${STORAGE_ACCOUNT}/raw-documents"
echo "  2. Filter: Only PDF files (BlobCreated events)"
echo "  3. Trigger: Azure Function ${FUNCTION_APP}"
echo ""
echo "Test by uploading a PDF to the raw-documents container."
echo ""
