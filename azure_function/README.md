# Document Processing Azure Function

This Azure Function is triggered by Event Grid when PDFs are uploaded to Azure Blob Storage. It processes documents through the RAG pipeline.

## 📋 Function Overview

**Trigger**: Azure Event Grid (BlobCreated events)
**Runtime**: Python 3.11
**Plan**: Consumption (serverless)

### What It Does

1. **Listens** for BlobCreated events in the `raw-documents` container
2. **Filters** for PDF files only
3. **Analyzes** documents with Azure Document Intelligence
4. **Stores** processed data in `processed-documents` container
5. **Indexes** content in Azure AI Search
6. **Updates** document status in PostgreSQL database

## 🚀 Local Development

### Prerequisites

- [Azure Functions Core Tools](https://docs.microsoft.com/azure/azure-functions/functions-run-local)
- Python 3.11
- Azure Storage Emulator or actual Azure Storage account

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure local settings
cp local.settings.json.example local.settings.json
# Edit local.settings.json with your Azure credentials

# Start function locally
func start
```

The function will be available at: `http://localhost:7071`

### Testing Locally

```bash
# Option 1: Use Azure Storage Explorer to upload a file
# This will trigger the real Event Grid event

# Option 2: Send test event manually
curl -X POST http://localhost:7071/runtime/webhooks/eventgrid?functionName=ProcessDocumentEvent \
  -H "Content-Type: application/json" \
  -H "aeg-event-type: Notification" \
  -d @test-event.json
```

Example `test-event.json`:
```json
[{
  "topic": "/subscriptions/.../Microsoft.Storage/storageAccounts/...",
  "subject": "/blobServices/default/containers/raw-documents/blobs/folder-1/test.pdf",
  "eventType": "Microsoft.Storage.BlobCreated",
  "data": {
    "api": "PutBlob",
    "url": "https://storage.blob.core.windows.net/raw-documents/folder-1/test.pdf",
    "contentType": "application/pdf",
    "blobType": "BlockBlob"
  }
}]
```

## 📦 Deployment

### Option 1: Using Deployment Script

```bash
cd ../azure_setup
./deploy_function.sh
```

### Option 2: Manual Deployment

```bash
# Create deployment package
zip -r function.zip . -x "*.git*" -x "*__pycache__*" -x "*.venv*"

# Deploy
az functionapp deployment source config-zip \
  --resource-group rag-app-rg \
  --name rag-document-processor \
  --src function.zip
```

### Option 3: GitHub Actions

Push to main branch - automatic deployment via `.github/workflows/deploy-function.yml`

## ⚙️ Configuration

### Required Environment Variables

Set these in Azure Portal (Function App → Configuration) or via CLI:

```bash
DATABASE_URL                          # PostgreSQL connection string
AZURE_STORAGE_CONNECTION_STRING       # Blob storage connection
RAW_DOCUMENTS_CONTAINER               # Raw documents container name
PROCESSED_DOCUMENTS_CONTAINER         # Processed documents container name
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT  # Document Intelligence endpoint
AZURE_DOCUMENT_INTELLIGENCE_KEY       # Document Intelligence key
AZURE_SEARCH_ENDPOINT                 # AI Search endpoint
AZURE_SEARCH_KEY                      # AI Search admin key
AZURE_SEARCH_INDEX_PREFIX             # Search index prefix
```

## 📁 Project Structure

```
azure_function/
├── function_app.py          # Main function with Event Grid trigger
├── host.json                # Function app configuration
├── local.settings.json      # Local development settings
├── requirements.txt         # Python dependencies
├── shared_code/
│   ├── config.py           # Configuration management
│   └── document_processor.py  # Document processing logic
└── README.md               # This file
```

## 🔧 Configuration Files

### host.json

Controls function runtime behavior:
- **Timeout**: 10 minutes (configurable)
- **Retry Strategy**: Exponential backoff
- **Max Retries**: 3 attempts
- **Logging**: Info level by default

### local.settings.json

Local development configuration. **DO NOT commit to git** (contains secrets).

## 📊 Monitoring

### View Logs

```bash
# Real-time logs
az functionapp logs tail \
  --name rag-document-processor \
  --resource-group rag-app-rg

# Or in Azure Portal:
# Function App → Functions → ProcessDocumentEvent → Monitor
```

### Application Insights

Enable for detailed telemetry:
```bash
az functionapp config appsettings set \
  --name rag-document-processor \
  --resource-group rag-app-rg \
  --settings APPINSIGHTS_INSTRUMENTATIONKEY="your-key"
```

### Key Metrics

- **Execution Count**: Number of function invocations
- **Success Rate**: Percentage of successful executions
- **Duration**: Average execution time
- **Errors**: Failed executions with stack traces

## 🐛 Troubleshooting

### Function Not Triggering

1. **Check Event Grid subscription**:
```bash
az eventgrid event-subscription list \
  --source-resource-id "/subscriptions/.../storageAccounts/..."
```

2. **Verify event filters**: Ensure PDF content type filter is correct

3. **Check function status**: Ensure function app is running

### Function Failing

1. **Check environment variables**: Verify all required settings are configured

2. **Test database connection**: Ensure PostgreSQL allows Azure service access

3. **Review logs**:
```bash
az functionapp logs tail --name rag-document-processor --resource-group rag-app-rg
```

4. **Check quotas**: Verify Document Intelligence and AI Search quotas

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection timeout` | Database unreachable | Check firewall rules |
| `Invalid credentials` | Wrong API key | Verify environment variables |
| `Quota exceeded` | Service limit reached | Upgrade service tier |
| `Index not found` | AI Search index missing | Function creates it automatically on first run |

## 🔒 Security

### Best Practices

1. **Use Managed Identity** (recommended):
```bash
az functionapp identity assign \
  --name rag-document-processor \
  --resource-group rag-app-rg
```

2. **Store secrets in Key Vault**:
```bash
# Reference in app settings
@Microsoft.KeyVault(SecretUri=https://vault.vault.azure.net/secrets/db-password/)
```

3. **Restrict network access**:
```bash
az functionapp config access-restriction add \
  --name rag-document-processor \
  --resource-group rag-app-rg \
  --priority 100 \
  --rule-name "AllowEventGrid" \
  --service-tag AzureEventGrid
```

## 📈 Performance Tuning

### Increase Timeout

For large PDFs, increase the timeout:

```json
// host.json
{
  "functionTimeout": "00:15:00"  // 15 minutes
}
```

### Optimize Retry Strategy

```json
// host.json
{
  "retry": {
    "strategy": "exponentialBackoff",
    "maxRetryCount": 5,
    "minimumInterval": "00:00:10",
    "maximumInterval": "00:10:00"
  }
}
```

### Scale Settings (Premium Plan)

```bash
az functionapp plan update \
  --name your-plan \
  --resource-group rag-app-rg \
  --max-burst 20  # Maximum concurrent instances
```

## 🧪 Testing

### Unit Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-mock

# Run tests
pytest tests/
```

### Integration Tests

1. Upload test PDF to blob storage
2. Monitor function logs
3. Check database for updated status
4. Verify document in AI Search index

## 📚 Resources

- [Azure Functions Python Developer Guide](https://docs.microsoft.com/azure/azure-functions/functions-reference-python)
- [Event Grid Trigger](https://docs.microsoft.com/azure/azure-functions/functions-bindings-event-grid-trigger)
- [Function App Best Practices](https://docs.microsoft.com/azure/azure-functions/functions-best-practices)

## 🤝 Contributing

1. Make changes to function code
2. Test locally with `func start`
3. Deploy and verify in Azure
4. Monitor for errors

---

For more information, see the main project documentation:
- `../EVENT_GRID_GUIDE.md` - Complete Event Grid setup guide
- `../EVENT_GRID_IMPLEMENTATION.md` - Implementation details
- `../README.md` - Main project documentation
