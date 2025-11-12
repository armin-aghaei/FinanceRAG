# Setup Guide

This guide walks you through setting up the RAG Document Analysis application from scratch.

## Step 1: Azure Resources Setup

### 1.1 Create a Resource Group
```bash
az group create --name rag-app-rg --location eastus
```

### 1.2 Create Azure PostgreSQL Database
```bash
# Create PostgreSQL Flexible Server
az postgres flexible-server create \
  --name rag-db-server \
  --resource-group rag-app-rg \
  --location eastus \
  --admin-user ragadmin \
  --admin-password "YourSecurePassword123!" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --version 14

# Create database
az postgres flexible-server db create \
  --resource-group rag-app-rg \
  --server-name rag-db-server \
  --database-name rag_db

# Configure firewall (allow Azure services)
az postgres flexible-server firewall-rule create \
  --resource-group rag-app-rg \
  --name rag-db-server \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

**Connection String Format:**
```
postgresql+asyncpg://ragadmin:YourSecurePassword123!@rag-db-server.postgres.database.azure.com:5432/rag_db
```

### 1.3 Create Azure Storage Account
```bash
# Create storage account
az storage account create \
  --name ragstorage2024 \
  --resource-group rag-app-rg \
  --location eastus \
  --sku Standard_LRS \
  --kind StorageV2

# Get connection string
az storage account show-connection-string \
  --name ragstorage2024 \
  --resource-group rag-app-rg \
  --query connectionString \
  --output tsv

# Create containers
az storage container create \
  --name raw-documents \
  --account-name ragstorage2024

az storage container create \
  --name processed-documents \
  --account-name ragstorage2024
```

### 1.4 Create Azure Document Intelligence
```bash
az cognitiveservices account create \
  --name rag-doc-intelligence \
  --resource-group rag-app-rg \
  --kind FormRecognizer \
  --sku S0 \
  --location eastus \
  --yes

# Get endpoint and key
az cognitiveservices account show \
  --name rag-doc-intelligence \
  --resource-group rag-app-rg \
  --query properties.endpoint \
  --output tsv

az cognitiveservices account keys list \
  --name rag-doc-intelligence \
  --resource-group rag-app-rg \
  --query key1 \
  --output tsv
```

### 1.5 Create Azure AI Search
```bash
az search service create \
  --name rag-search-service \
  --resource-group rag-app-rg \
  --sku basic \
  --location eastus

# Get admin key
az search admin-key show \
  --service-name rag-search-service \
  --resource-group rag-app-rg \
  --query primaryKey \
  --output tsv
```

**Endpoint Format:**
```
https://rag-search-service.search.windows.net
```

### 1.6 Create Azure OpenAI
1. Go to Azure Portal
2. Create "Azure OpenAI" resource
3. Deploy a GPT-4 model (e.g., "gpt-4")
4. Get the endpoint and API key from Keys and Endpoint section

**Note:** GPT-4 deployment requires approval. You may need to request access first.

## Step 2: Local Development Setup

### 2.1 Clone and Setup Python Environment
```bash
# Navigate to project directory
cd "Development Folder"

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2.2 Configure Environment Variables
```bash
# Copy example env file
cp .env.example .env

# Edit .env file with your Azure credentials
# Use a text editor to fill in all the values
```

Example `.env` file:
```env
DATABASE_URL=postgresql+asyncpg://ragadmin:YourSecurePassword123!@rag-db-server.postgres.database.azure.com:5432/rag_db

SECRET_KEY=your-super-secret-key-generate-a-strong-one
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=ragstorage2024;AccountKey=...
AZURE_STORAGE_ACCOUNT_NAME=ragstorage2024
AZURE_STORAGE_ACCOUNT_KEY=your-storage-key
RAW_DOCUMENTS_CONTAINER=raw-documents
PROCESSED_DOCUMENTS_CONTAINER=processed-documents

AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://rag-doc-intelligence.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=your-doc-intelligence-key

AZURE_SEARCH_ENDPOINT=https://rag-search-service.search.windows.net
AZURE_SEARCH_KEY=your-search-admin-key
AZURE_SEARCH_INDEX_PREFIX=rag-index

AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-openai-key
AZURE_OPENAI_DEPLOYMENT=gpt-4
AZURE_OPENAI_API_VERSION=2024-02-15-preview

ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
MAX_UPLOAD_SIZE_MB=50
```

### 2.3 Generate Secret Key
```bash
# Generate a secure secret key for JWT
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2.4 Initialize Database
```bash
# Run migrations
alembic upgrade head
```

### 2.5 Start Development Server
```bash
# Start the server
uvicorn app.main:app --reload

# The API will be available at:
# http://localhost:8000
# Swagger docs: http://localhost:8000/docs
```

## Step 3: Testing the API

### 3.1 Test User Registration
```bash
curl -X POST "http://localhost:8000/api/v1/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpassword123"
  }'
```

### 3.2 Test Login
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpassword123"
  }'
```

Save the `access_token` from the response.

### 3.3 Test Creating a Folder
```bash
curl -X POST "http://localhost:8000/api/v1/folders" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "folder_name": "My Documents",
    "password": "folderpass123"
  }'
```

## Step 4: Deploy to Azure App Service

### 4.1 Create App Service
```bash
az appservice plan create \
  --name rag-app-plan \
  --resource-group rag-app-rg \
  --sku B1 \
  --is-linux

az webapp create \
  --name rag-document-app \
  --resource-group rag-app-rg \
  --plan rag-app-plan \
  --runtime "PYTHON:3.11"
```

### 4.2 Configure App Settings
```bash
# Set environment variables (replace with your actual values)
az webapp config appsettings set \
  --name rag-document-app \
  --resource-group rag-app-rg \
  --settings \
    DATABASE_URL="your-database-url" \
    SECRET_KEY="your-secret-key" \
    AZURE_STORAGE_CONNECTION_STRING="your-storage-connection" \
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="your-endpoint" \
    AZURE_DOCUMENT_INTELLIGENCE_KEY="your-key" \
    AZURE_SEARCH_ENDPOINT="your-search-endpoint" \
    AZURE_SEARCH_KEY="your-search-key" \
    AZURE_OPENAI_ENDPOINT="your-openai-endpoint" \
    AZURE_OPENAI_KEY="your-openai-key" \
    AZURE_OPENAI_DEPLOYMENT="gpt-4" \
    ENVIRONMENT="production"
```

### 4.3 Configure Startup Command
```bash
az webapp config set \
  --name rag-document-app \
  --resource-group rag-app-rg \
  --startup-file "startup.sh"
```

### 4.4 Deploy Code
```bash
# Option 1: Using ZIP deploy
zip -r app.zip . -x "venv/*" -x ".git/*" -x "__pycache__/*"

az webapp deployment source config-zip \
  --name rag-document-app \
  --resource-group rag-app-rg \
  --src app.zip

# Option 2: Using local git
az webapp deployment source config-local-git \
  --name rag-document-app \
  --resource-group rag-app-rg

git remote add azure <git-url-from-previous-command>
git push azure main
```

### 4.5 View Logs
```bash
az webapp log tail \
  --name rag-document-app \
  --resource-group rag-app-rg
```

## Step 5: Frontend Setup (Lovable)

1. Go to [Lovable.dev](https://lovable.dev)
2. Use the prompt from README.md to generate the frontend
3. Update the API endpoint in the frontend to point to your Azure App Service URL
4. Deploy the frontend (Lovable provides hosting)

## Troubleshooting

### Database Connection Issues
- Ensure firewall rules allow your IP or Azure services
- Verify connection string format
- Check username and password

### Azure Services Authentication
- Verify all API keys are correct
- Check service endpoints
- Ensure services are in the same region for better performance

### File Upload Issues
- Check blob storage connection string
- Verify containers exist
- Check file size limits

### Document Processing Failures
- Check Document Intelligence quota
- Verify blob URLs are accessible
- Review error_message field in documents table

## Next Steps

1. Set up monitoring with Azure Application Insights
2. Configure custom domain for your App Service
3. Enable SSL/HTTPS
4. Set up automated backups for PostgreSQL
5. Configure autoscaling for App Service
6. Implement rate limiting
7. Add comprehensive logging

## Cost Optimization Tips

- Use Free tier for App Service during development
- Start with Basic tier for Azure AI Search
- Use Burstable tier for PostgreSQL
- Monitor usage and adjust service tiers accordingly
- Set up cost alerts in Azure

## Security Checklist

- [ ] Change all default passwords
- [ ] Use strong SECRET_KEY for JWT
- [ ] Enable HTTPS only
- [ ] Configure CORS properly
- [ ] Set up Azure Key Vault for secrets
- [ ] Enable Azure AD authentication
- [ ] Configure network security groups
- [ ] Enable audit logging
- [ ] Regular security updates
- [ ] Implement rate limiting
