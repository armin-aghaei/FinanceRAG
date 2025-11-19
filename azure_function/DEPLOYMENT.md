# Azure Function Deployment Guide

## Overview

This Azure Function automatically processes uploaded documents by:
1. Triggering the Azure AI Search indexer
2. Merging metadata from Azure Table Storage into search index chunks
3. **Updating document status in PostgreSQL database** (INDEXED or FAILED)

## Prerequisites

- Azure Functions Core Tools
- Python 3.9 or higher
- Access to Azure subscription
- PostgreSQL database (same as the main API)

## Environment Variables

The following environment variables must be configured in the Azure Function App settings:

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AzureWebJobsStorage` | Connection string for Azure Storage (blob trigger) | `DefaultEndpointsProtocol=https;AccountName=...` |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search service endpoint | `https://your-search.search.windows.net` |
| `AZURE_SEARCH_KEY` | Azure AI Search admin API key | `your-search-admin-key` |
| `AZURE_STORAGE_CONNECTION_STRING` | Connection string for Table Storage (metadata) | `DefaultEndpointsProtocol=https;AccountName=...` |
| `DATABASE_URL` | **PostgreSQL connection string** | `postgresql://user:pass@host:5432/dbname` |

### DATABASE_URL Configuration

The `DATABASE_URL` must point to the same PostgreSQL database used by the main FastAPI application. This enables the Azure Function to update document status after processing.

**Format:**
```
postgresql://username:password@hostname:port/database_name
```

**Example:**
```
postgresql://ccpa_admin:MyPassword@my-postgres-server.postgres.database.azure.com:5432/finance_rag
```

**For Azure PostgreSQL with SSL:**
```
postgresql://username:password@hostname.postgres.database.azure.com:5432/dbname?sslmode=require
```

**Important Notes:**
- Use `postgresql://` not `postgres://` (both work, but SQLAlchemy prefers the former)
- Ensure the database user has `SELECT` and `UPDATE` permissions on the `documents` table
- The function uses connection pooling (pool_size=5, max_overflow=10)
- Connections are recycled after 1 hour to prevent stale connections

## Deployment Steps

### 1. Local Development

Create a `local.settings.json` file:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_SEARCH_ENDPOINT": "https://your-search.search.windows.net",
    "AZURE_SEARCH_KEY": "your-key",
    "AZURE_STORAGE_CONNECTION_STRING": "your-connection-string",
    "DATABASE_URL": "postgresql://localhost:5432/finance_rag"
  }
}
```

Run locally:
```bash
func start
```

### 2. Deploy to Azure

#### Option A: Using Azure Functions Core Tools

```bash
# Login to Azure
az login

# Create Function App (if not exists)
az functionapp create \
  --resource-group your-rg \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.9 \
  --functions-version 4 \
  --name your-function-app-name \
  --storage-account your-storage-account

# Deploy the function
func azure functionapp publish your-function-app-name
```

#### Option B: Using Azure Portal

1. Create a new Function App
2. Set runtime stack to Python 3.9
3. Configure environment variables in **Configuration** → **Application settings**
4. Deploy code via ZIP deployment or GitHub Actions

### 3. Configure Environment Variables in Azure

After deployment, add the environment variables:

```bash
# Set DATABASE_URL
az functionapp config appsettings set \
  --name your-function-app-name \
  --resource-group your-rg \
  --settings DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# Set other required variables
az functionapp config appsettings set \
  --name your-function-app-name \
  --resource-group your-rg \
  --settings \
    AZURE_SEARCH_ENDPOINT="https://your-search.search.windows.net" \
    AZURE_SEARCH_KEY="your-key" \
    AZURE_STORAGE_CONNECTION_STRING="your-connection-string"
```

### 4. Verify Deployment

Check function logs:

```bash
# Stream logs
func azure functionapp logstream your-function-app-name

# Or use Azure Portal → Function App → Monitor → Log stream
```

Upload a test PDF and verify:
1. Function triggers successfully
2. Indexer runs
3. Metadata merges into chunks
4. **Document status updates to "indexed" in PostgreSQL**

## Database Schema Requirements

The Azure Function expects the following database schema:

```sql
-- Documents table (simplified)
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    folder_id INTEGER NOT NULL,
    filename VARCHAR NOT NULL,
    original_filename VARCHAR NOT NULL,
    blob_url VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',  -- 'pending', 'processing', 'indexed', 'failed'
    error_message VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Status values
-- 'pending'    - Document uploaded, waiting for processing
-- 'processing' - Currently being processed (optional, not currently used)
-- 'indexed'    - Successfully indexed and searchable
-- 'failed'     - Processing failed (error_message contains details)
```

## Monitoring

### Application Insights

Enable Application Insights for the Function App to monitor:
- Function executions
- Success/failure rates
- Database connection health
- Processing duration

### Logs to Monitor

Key log messages:
- `"Updating document {id} status to INDEXED"` - Successful processing
- `"Successfully updated document {id} status to INDEXED"` - Database update succeeded
- `"Updating document {id} status to FAILED"` - Processing failed
- `"Failed to update document {id} status in database"` - Database connection issue

### Common Issues

**Issue: "DATABASE_URL environment variable not set"**
- Solution: Add `DATABASE_URL` to Function App configuration

**Issue: Database connection timeout**
- Solution: Check firewall rules, ensure Azure Function IP is whitelisted
- For Azure PostgreSQL, enable "Allow Azure services" in firewall settings

**Issue: SSL connection error**
- Solution: Add `?sslmode=require` to DATABASE_URL for Azure PostgreSQL

**Issue: Document status not updating**
- Check Application Insights for database errors
- Verify database user has UPDATE permission on documents table
- Check network connectivity between Function App and PostgreSQL

## Testing

### Manual Test

1. Upload a PDF via the API
2. Check Azure Function execution logs
3. Query the database:
   ```sql
   SELECT id, filename, status, error_message, updated_at
   FROM documents
   ORDER BY updated_at DESC
   LIMIT 10;
   ```
4. Verify status changed from 'pending' to 'indexed'

### Load Testing

For high-volume scenarios, monitor:
- Database connection pool utilization
- Function concurrency
- Indexer queue depth

## Security Best Practices

1. **Secrets Management**: Store `DATABASE_URL` in Azure Key Vault and reference via Key Vault references
2. **Least Privilege**: Database user should only have SELECT/UPDATE on documents table
3. **SSL/TLS**: Always use `sslmode=require` for production databases
4. **Connection Pooling**: Function uses connection pooling to prevent connection exhaustion
5. **Error Handling**: Failed status updates are logged but don't prevent processing

## Troubleshooting

### Enable Detailed Logging

Set environment variable:
```bash
az functionapp config appsettings set \
  --name your-function-app-name \
  --resource-group your-rg \
  --settings PYTHON_ENABLE_WORKER_EXTENSIONS=1 PYTHON_THREADPOOL_THREAD_COUNT=4
```

### Test Database Connection

Create a test function endpoint:
```python
@app.route(route="test-db")
def test_db(req: func.HttpRequest) -> func.HttpResponse:
    try:
        from shared_code.database import DatabaseConnection
        session = DatabaseConnection.get_session()
        session.close()
        return func.HttpResponse("Database connection successful", status_code=200)
    except Exception as e:
        return func.HttpResponse(f"Database error: {str(e)}", status_code=500)
```

## Rollback Plan

If issues occur after deployment:

1. **Disable database updates**: Remove `DATABASE_URL` environment variable temporarily
2. **Use manual sync**: Call `/admin/sync-document-status` endpoint to batch-update statuses
3. **Revert code**: Redeploy previous version without database integration

## Next Steps

After successful deployment:

1. Monitor frontend to confirm polling stops when status changes to "indexed"
2. Set up Application Insights alerts for failed status updates
3. Consider adding retry logic for transient database failures
4. Implement database connection health checks

## Support

For issues or questions:
- Check Application Insights logs
- Review function execution history in Azure Portal
- Verify all environment variables are set correctly
- Test database connectivity from Function App
