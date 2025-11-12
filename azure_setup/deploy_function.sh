#!/bin/bash

# Deploy Azure Function Script
# This script deploys the document processing Azure Function

set -e  # Exit on error

echo "========================================="
echo "Azure Function Deployment"
echo "========================================="
echo ""

# Configuration - UPDATE THESE VALUES
RESOURCE_GROUP="rag-app-rg"
STORAGE_ACCOUNT="ragstorage2024"
FUNCTION_APP="rag-document-processor"
LOCATION="eastus"
RUNTIME="python"
RUNTIME_VERSION="3.11"

echo "Configuration:"
echo "  Resource Group: ${RESOURCE_GROUP}"
echo "  Function App: ${FUNCTION_APP}"
echo "  Runtime: ${RUNTIME} ${RUNTIME_VERSION}"
echo ""

# Step 1: Create storage account for function app (if needed)
echo "Step 1: Checking storage account for function..."
FUNC_STORAGE="${FUNCTION_APP}storage"

if ! az storage account show --name ${FUNC_STORAGE} --resource-group ${RESOURCE_GROUP} &>/dev/null; then
    echo "Creating storage account for function app..."
    az storage account create \
      --name ${FUNC_STORAGE} \
      --location ${LOCATION} \
      --resource-group ${RESOURCE_GROUP} \
      --sku Standard_LRS
    echo "✅ Storage account created"
else
    echo "✅ Storage account exists"
fi

# Step 2: Create Function App
echo ""
echo "Step 2: Creating/updating Function App..."

if ! az functionapp show --name ${FUNCTION_APP} --resource-group ${RESOURCE_GROUP} &>/dev/null; then
    echo "Creating new function app..."
    az functionapp create \
      --resource-group ${RESOURCE_GROUP} \
      --consumption-plan-location ${LOCATION} \
      --runtime ${RUNTIME} \
      --runtime-version ${RUNTIME_VERSION} \
      --functions-version 4 \
      --name ${FUNCTION_APP} \
      --storage-account ${FUNC_STORAGE} \
      --os-type Linux
    echo "✅ Function app created"
else
    echo "✅ Function app exists"
fi

# Step 3: Configure app settings
echo ""
echo "Step 3: Configuring application settings..."

# Get the connection string from main storage account
STORAGE_CONNECTION=$(az storage account show-connection-string \
  --name ${STORAGE_ACCOUNT} \
  --resource-group ${RESOURCE_GROUP} \
  --query connectionString \
  --output tsv)

echo "Setting environment variables..."
echo "⚠️  NOTE: Update these with your actual values!"

# Set required environment variables
az functionapp config appsettings set \
  --name ${FUNCTION_APP} \
  --resource-group ${RESOURCE_GROUP} \
  --settings \
    DATABASE_URL="${DATABASE_URL}" \
    AZURE_STORAGE_CONNECTION_STRING="${STORAGE_CONNECTION}" \
    RAW_DOCUMENTS_CONTAINER="raw-documents" \
    PROCESSED_DOCUMENTS_CONTAINER="processed-documents" \
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="${AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT}" \
    AZURE_DOCUMENT_INTELLIGENCE_KEY="${AZURE_DOCUMENT_INTELLIGENCE_KEY}" \
    AZURE_SEARCH_ENDPOINT="${AZURE_SEARCH_ENDPOINT}" \
    AZURE_SEARCH_KEY="${AZURE_SEARCH_KEY}" \
    AZURE_SEARCH_INDEX_PREFIX="rag-index" \
    AZURE_OPENAI_ENDPOINT="${AZURE_OPENAI_ENDPOINT}" \
    AZURE_OPENAI_KEY="${AZURE_OPENAI_KEY}" \
    AZURE_OPENAI_DEPLOYMENT="gpt-4"

echo "✅ App settings configured"

# Step 4: Deploy function code
echo ""
echo "Step 4: Deploying function code..."

# Navigate to function directory
cd "$(dirname "$0")/../azure_function"

# Create deployment package
echo "Creating deployment package..."
zip -r function.zip . -x "*.git*" -x "*__pycache__*" -x "*.venv*" -x "*local.settings.json*"

# Deploy
echo "Deploying to Azure..."
az functionapp deployment source config-zip \
  --resource-group ${RESOURCE_GROUP} \
  --name ${FUNCTION_APP} \
  --src function.zip

# Cleanup
rm function.zip

echo "✅ Function deployed"

# Step 5: Verify deployment
echo ""
echo "Step 5: Verifying deployment..."

az functionapp function show \
  --name ${FUNCTION_APP} \
  --resource-group ${RESOURCE_GROUP} \
  --function-name ProcessDocumentEvent

echo ""
echo "========================================="
echo "✅ Deployment Complete!"
echo "========================================="
echo ""
echo "Function App: https://${FUNCTION_APP}.azurewebsites.net"
echo ""
echo "Next steps:"
echo "  1. Verify environment variables in Azure Portal"
echo "  2. Run ./event_grid_setup.sh to configure Event Grid"
echo "  3. Test by uploading a PDF file"
echo ""
