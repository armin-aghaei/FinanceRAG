# Event Grid Integration Guide

This guide explains how the Event Grid integration works and how to set it up.

## 🏗️ Architecture Overview

### Event-Driven Document Processing Flow

```
┌─────────────┐
│    User     │
└──────┬──────┘
       │ 1. Upload PDF via API
       ↓
┌──────────────────────────┐
│    FastAPI Application   │
│  POST /documents/upload  │
└──────────┬───────────────┘
           │ 2. Save to Blob Storage
           ↓
┌──────────────────────────┐
│  Azure Blob Storage      │
│  (raw-documents)         │
└──────────┬───────────────┘
           │ 3. Fires BlobCreated event
           ↓
┌──────────────────────────┐
│  Azure Event Grid        │
│  (Event Router)          │
└──────────┬───────────────┘
           │ 4. Routes event to Function
           ↓
┌──────────────────────────┐
│  Azure Function          │
│  ProcessDocumentEvent    │
└──────────┬───────────────┘
           │ 5. Process document
           │
           ├──→ 6a. Analyze with Document Intelligence
           │
           ├──→ 6b. Store processed data
           │
           ├──→ 6c. Index in AI Search
           │
           └──→ 6d. Update database status
```

---

## ⚡ Benefits

### 1. **Faster API Response**
- **Before**: Upload takes 30+ seconds (includes processing)
- **After**: Upload takes <1 second (Event Grid handles processing)

### 2. **Reliability**
- **Automatic retries**: Event Grid retries failed events up to 30 times over 24 hours
- **Dead-letter queue**: Failed events are stored for investigation
- **Durable events**: Events aren't lost if services restart

### 3. **Scalability**
- **Independent scaling**: API and processing scale separately
- **Auto-scaling**: Azure Functions automatically scale to handle load
- **Cost-effective**: Only pay for actual processing time

### 4. **Monitoring**
- **Event tracking**: See event flow in Azure Monitor
- **Error visibility**: Failed events logged with details
- **Metrics**: Track processing times, success rates, etc.

---

## 📋 Prerequisites

1. **Azure Storage Account** with:
   - `raw-documents` container
   - `processed-documents` container

2. **Azure Function App**:
   - Runtime: Python 3.11
   - Plan: Consumption (serverless) or Premium

3. **Azure Services** (same as main app):
   - Document Intelligence
   - AI Search
   - PostgreSQL Database

---

## 🚀 Deployment Steps

### Step 1: Deploy the Azure Function

#### Option A: Using the Deployment Script
```bash
cd azure_setup

# Set environment variables first
export DATABASE_URL="postgresql://..."
export AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="https://..."
export AZURE_DOCUMENT_INTELLIGENCE_KEY="..."
export AZURE_SEARCH_ENDPOINT="https://..."
export AZURE_SEARCH_KEY="..."
export AZURE_OPENAI_ENDPOINT="https://..."
export AZURE_OPENAI_KEY="..."

# Run deployment
./deploy_function.sh
```

#### Option B: Manual Deployment
```bash
# Create Function App
az functionapp create \
  --resource-group rag-app-rg \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name rag-document-processor \
  --storage-account ragfunctionstorage \
  --os-type Linux

# Deploy code
cd azure_function
zip -r ../function.zip . -x "*.git*" -x "*__pycache__*"
cd ..

az functionapp deployment source config-zip \
  --resource-group rag-app-rg \
  --name rag-document-processor \
  --src function.zip

# Configure app settings (see below)
```

#### Configure Function App Settings
```bash
az functionapp config appsettings set \
  --name rag-document-processor \
  --resource-group rag-app-rg \
  --settings \
    DATABASE_URL="your-db-url" \
    AZURE_STORAGE_CONNECTION_STRING="your-storage-connection" \
    RAW_DOCUMENTS_CONTAINER="raw-documents" \
    PROCESSED_DOCUMENTS_CONTAINER="processed-documents" \
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="your-endpoint" \
    AZURE_DOCUMENT_INTELLIGENCE_KEY="your-key" \
    AZURE_SEARCH_ENDPOINT="your-search-endpoint" \
    AZURE_SEARCH_KEY="your-search-key" \
    AZURE_SEARCH_INDEX_PREFIX="rag-index"
```

---

### Step 2: Configure Event Grid

#### Using the Setup Script
```bash
cd azure_setup
./event_grid_setup.sh
```

#### Manual Configuration
```bash
# Get storage account ID
STORAGE_ID=$(az storage account show \
  --name ragstorage2024 \
  --resource-group rag-app-rg \
  --query id \
  --output tsv)

# Get function key
FUNCTION_KEY=$(az functionapp keys list \
  --name rag-document-processor \
  --resource-group rag-app-rg \
  --query systemKeys.default \
  --output tsv)

# Create Event Grid subscription
az eventgrid event-subscription create \
  --name blob-created-subscription \
  --source-resource-id $STORAGE_ID \
  --endpoint "https://rag-document-processor.azurewebsites.net/runtime/webhooks/eventgrid?functionName=ProcessDocumentEvent&code=${FUNCTION_KEY}" \
  --endpoint-type azurefunction \
  --included-event-types Microsoft.Storage.BlobCreated \
  --subject-begins-with "/blobServices/default/containers/raw-documents/blobs/" \
  --advanced-filter data.contentType StringContains application/pdf
```

---

### Step 3: Test the Integration

1. **Upload a test PDF**:
```bash
curl -X POST "https://your-api.azurewebsites.net/api/v1/documents/upload/1" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@test.pdf"
```

2. **Check Event Grid metrics** (Azure Portal):
   - Navigate to: Storage Account → Events → Event subscriptions
   - View: Matched events, delivered events, failed events

3. **Monitor Function execution**:
```bash
az functionapp logs tail \
  --name rag-document-processor \
  --resource-group rag-app-rg
```

4. **Check document status**:
```bash
curl "https://your-api.azurewebsites.net/api/v1/documents/{id}" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Status should change: `pending` → `processing` → `indexed`

---

## 🔍 Monitoring and Debugging

### View Event Grid Events
```bash
# List event subscriptions
az eventgrid event-subscription list \
  --source-resource-id $STORAGE_ID

# Show subscription details
az eventgrid event-subscription show \
  --name blob-created-subscription \
  --source-resource-id $STORAGE_ID
```

### Function Logs
```bash
# Real-time logs
az functionapp logs tail \
  --name rag-document-processor \
  --resource-group rag-app-rg

# Or in Azure Portal:
# Function App → Functions → ProcessDocumentEvent → Monitor
```

### Event Grid Metrics (Azure Portal)
1. Go to Storage Account
2. Click "Events" in left menu
3. View metrics:
   - Published events
   - Matched events
   - Delivered events
   - Failed events

### Application Insights
Enable Application Insights for detailed telemetry:
```bash
az functionapp config appsettings set \
  --name rag-document-processor \
  --resource-group rag-app-rg \
  --settings \
    APPINSIGHTS_INSTRUMENTATIONKEY="your-key"
```

---

## 🐛 Troubleshooting

### Events Not Triggering Function

**Check 1: Event subscription exists**
```bash
az eventgrid event-subscription list \
  --source-resource-id $STORAGE_ID
```

**Check 2: Event filters are correct**
- Subject filter: `/blobServices/default/containers/raw-documents/blobs/`
- Content type filter: `application/pdf`

**Check 3: Function endpoint is correct**
```bash
# Should be:
# https://{function-app}.azurewebsites.net/runtime/webhooks/eventgrid?functionName=ProcessDocumentEvent&code={key}
```

**Check 4: View failed events**
Configure dead-letter queue:
```bash
az eventgrid event-subscription update \
  --name blob-created-subscription \
  --source-resource-id $STORAGE_ID \
  --deadletter-endpoint $DEADLETTER_STORAGE_ID/deadletters
```

### Function Failing to Process

**Check 1: Environment variables**
```bash
az functionapp config appsettings list \
  --name rag-document-processor \
  --resource-group rag-app-rg
```

**Check 2: Database connection**
- Verify DATABASE_URL is correct
- Check PostgreSQL firewall allows Azure services

**Check 3: Azure service credentials**
- Document Intelligence key/endpoint
- AI Search key/endpoint
- Storage connection string

**Check 4: Function logs**
```bash
az functionapp logs tail \
  --name rag-document-processor \
  --resource-group rag-app-rg
```

### Documents Stuck in "Processing"

**Possible causes:**
1. Function timeout (default: 10 minutes)
2. Document Intelligence quota exceeded
3. AI Search index doesn't exist
4. Network connectivity issues

**Solutions:**
1. Increase function timeout:
```json
// host.json
{
  "functionTimeout": "00:15:00"  // 15 minutes
}
```

2. Check quotas in Azure Portal

3. Manually trigger processing:
```bash
# Get the blob URL from database
# Call function directly with test event
```

---

## 📊 Performance Tuning

### Function Configuration

**Increase timeout for large PDFs**:
```json
// host.json
{
  "functionTimeout": "00:15:00"
}
```

**Configure retry strategy**:
```json
// host.json
{
  "retry": {
    "strategy": "exponentialBackoff",
    "maxRetryCount": 3,
    "minimumInterval": "00:00:05",
    "maximumInterval": "00:05:00"
  }
}
```

**Scale settings** (Premium plan):
```bash
az functionapp plan update \
  --name your-plan \
  --resource-group rag-app-rg \
  --max-burst 20  # Max instances
```

### Event Grid Configuration

**Delivery retry**:
- Default: 30 attempts over 24 hours
- Customizable in Event Grid subscription

**Batch delivery**:
```bash
az eventgrid event-subscription create \
  ... \
  --max-delivery-attempts 10 \
  --event-delivery-schema eventgridschema
```

---

## 💰 Cost Optimization

### Event Grid Costs
- **First 100K operations/month**: FREE
- **Next 10M operations**: $0.60 per million
- **Your scenario**: 10K documents/month = ~$0.01/month

### Azure Functions Costs (Consumption Plan)
- **First 1M executions**: FREE
- **Next executions**: $0.20 per million
- **Execution time**: $0.000016 per GB-second

**Example calculation (10K documents/month)**:
- Executions: 10,000 (free tier)
- Avg execution time: 30 seconds
- Avg memory: 512 MB
- Cost: ~$2.40/month

### Cost Savings vs. Always-On Processing
- **Before**: Larger App Service needed = $50-100/month extra
- **After**: Consumption plan = $2-5/month
- **Savings**: ~$50-95/month

---

## 🔐 Security Best Practices

1. **Use Managed Identity** instead of connection strings:
```bash
az functionapp identity assign \
  --name rag-document-processor \
  --resource-group rag-app-rg
```

2. **Store secrets in Key Vault**:
```bash
# Reference Key Vault secrets in app settings
@Microsoft.KeyVault(SecretUri=https://your-vault.vault.azure.net/secrets/db-password/)
```

3. **Restrict Function App access**:
```bash
az functionapp config access-restriction add \
  --name rag-document-processor \
  --resource-group rag-app-rg \
  --priority 100 \
  --rule-name "AllowEventGrid" \
  --service-tag AzureEventGrid
```

4. **Enable HTTPS only**:
```bash
az functionapp update \
  --name rag-document-processor \
  --resource-group rag-app-rg \
  --set httpsOnly=true
```

---

## 🔄 CI/CD Integration

### GitHub Actions
The workflow is already set up in `.github/workflows/deploy-function.yml`.

**Setup secrets in GitHub**:
1. Go to repository Settings → Secrets
2. Add: `AZURE_FUNCTION_PUBLISH_PROFILE`
3. Get publish profile:
```bash
az functionapp deployment list-publishing-profiles \
  --name rag-document-processor \
  --resource-group rag-app-rg \
  --xml
```

### Automated Deployment
Push to main branch with changes in `azure_function/` directory triggers deployment.

---

## 📚 Additional Resources

- [Azure Event Grid Documentation](https://docs.microsoft.com/azure/event-grid/)
- [Azure Functions Python Guide](https://docs.microsoft.com/azure/azure-functions/functions-reference-python)
- [Event Grid Event Schema](https://docs.microsoft.com/azure/event-grid/event-schema-blob-storage)
- [Monitoring Azure Functions](https://docs.microsoft.com/azure/azure-functions/functions-monitoring)

---

## 🎯 Next Steps

1. **Enable Application Insights** for detailed monitoring
2. **Configure dead-letter queue** for failed events
3. **Set up alerts** for processing failures
4. **Implement retry logic** for transient failures
5. **Add integration tests** for the Function

---

Last Updated: 2024
