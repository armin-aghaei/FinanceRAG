# RAG Document Analysis API

A FastAPI-based application that allows users to upload PDF documents and interact with them using RAG (Retrieval Augmented Generation) powered by Azure AI services.

## Features

- **User Authentication**: Secure signup/login with JWT tokens
- **Folder Management**: Create password-protected folders for document organization (unlimited folders)
- **Document Upload**: Upload PDF documents to Azure Blob Storage
- **AI-Powered Analysis**: Automatic document analysis using Azure Document Intelligence Layout model
- **Semantic Chunking**: Azure AI Search skillset intelligently chunks documents by semantic boundaries
- **Vector Search**: Hybrid search combining vector embeddings and full-text search with folder isolation
- **RAG Chat**: Ask questions about your documents using Azure OpenAI GPT-4

## Architecture

### Event-Driven Document Processing with Integrated Vectorization

```
User uploads PDF → FastAPI API → Azure Blob Storage (raw-documents)
                                    │ (with folder_id, user_id metadata)
                                    ↓
                            Azure Event Grid (fires event)
                                    ↓
                            Azure Function (triggered)
                                    ↓
                         Triggers Azure AI Search Indexer
                                    ↓
                    ┌───────────────┴───────────────┐
                    │  Azure AI Search Indexer      │
                    │  (Integrated Vectorization)   │
                    │                                │
                    │  Skills Pipeline:              │
                    │  1. Document Layout Skill     │ ← Azure Document Intelligence
                    │     (extracts as markdown)     │
                    │  2. Text Split Skill           │
                    │     (2000 char chunks)         │
                    │  3. Azure OpenAI Embedding     │ ← Azure OpenAI Embeddings
                    │     (text-embedding-3-small)   │
                    └────────────┬───────────────────┘
                                 ↓
                    Single Azure AI Search Index
                     (with folder_id filtering)

User asks question → Generate embedding → Azure AI Search (hybrid vector+text search)
                                                  │ (filter by folder_id)
                                                  ↓
                                          Relevant chunks retrieved
                                                  ↓
                                          Azure OpenAI GPT-4
                                                  ↓
                                          Generated Answer
```

**Key Features:**
- ⚡ **Fast API responses** - Upload returns immediately, processing happens asynchronously
- 🔄 **Automatic retries** - Event Grid handles failures with exponential backoff
- 📈 **Auto-scaling** - Azure Functions and indexer scale based on load
- 💰 **Cost-effective** - Pay only for actual processing time, single index for all folders
- 🔒 **Folder Isolation** - Server-side filtering ensures users only access their folders
- 🧠 **Semantic Chunking** - Azure's Document Layout skill chunks by paragraphs/tables, not characters
- 🎯 **Hybrid Search** - Combines vector similarity and full-text search for best results

## Tech Stack

- **Backend**: FastAPI (Python 3.9+)
- **Processing**: Azure Functions (Python 3.11) - Event-driven
- **Database**: Azure PostgreSQL
- **Storage**: Azure Blob Storage
- **Event Routing**: Azure Event Grid
- **AI Services**:
  - Azure Document Intelligence
  - Azure AI Search
  - Azure OpenAI (GPT-4)
- **Authentication**: JWT with bcrypt
- **ORM**: SQLAlchemy (async)
- **Migrations**: Alembic

## Prerequisites

- Python 3.9 or higher (3.11 for Azure Function)
- Azure Account with the following resources:
  - Azure PostgreSQL Database
  - Azure Blob Storage Account
  - Azure Document Intelligence
  - Azure AI Search
  - Azure OpenAI
  - Azure Function App (for event-driven processing)
  - Azure Event Grid (configured automatically)

## Installation

1. **Clone the repository** (or navigate to project directory)

2. **Create a virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**:
   - Copy `.env.example` to `.env`
   - Fill in your Azure credentials and database connection string

5. **Run database migrations**:
```bash
alembic upgrade head
```

6. **Start the development server**:
```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Authentication
- `POST /api/v1/auth/signup` - Register a new user
- `POST /api/v1/auth/login` - Login and get JWT token
- `GET /api/v1/auth/me` - Get current user info

### Folders
- `POST /api/v1/folders` - Create a new folder
- `GET /api/v1/folders` - List all user's folders
- `GET /api/v1/folders/{folder_id}` - Get folder details
- `POST /api/v1/folders/{folder_id}/access` - Verify folder password
- `DELETE /api/v1/folders/{folder_id}` - Delete folder

### Documents
- `POST /api/v1/documents/upload/{folder_id}` - Upload a document
- `GET /api/v1/documents/folder/{folder_id}` - List documents in folder
- `GET /api/v1/documents/{document_id}` - Get document details
- `DELETE /api/v1/documents/{document_id}` - Delete document

### Chat
- `POST /api/v1/chat` - Ask a question about documents in a folder

### Webhooks
- `POST /api/v1/webhooks/event-grid-validation` - Event Grid subscription validation
- `POST /api/v1/webhooks/document-processed` - Document processing notifications

## Environment Variables

See `.env.example` for all required environment variables.

Key variables:
- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: JWT secret key
- `AZURE_STORAGE_CONNECTION_STRING`: Azure Blob Storage connection
- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`: Document Intelligence endpoint
- `AZURE_DOCUMENT_INTELLIGENCE_KEY`: Document Intelligence API key
- `AZURE_SEARCH_ENDPOINT`: AI Search endpoint
- `AZURE_SEARCH_KEY`: AI Search admin key
- `AZURE_OPENAI_ENDPOINT`: OpenAI endpoint
- `AZURE_OPENAI_KEY`: OpenAI API key
- `AZURE_OPENAI_DEPLOYMENT`: OpenAI chat deployment name (e.g., "gpt-4")
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`: OpenAI embedding deployment name (e.g., "text-embedding-3-small")

## Azure Resources Setup

### 1. Azure PostgreSQL
```bash
az postgres flexible-server create \
  --name your-postgres-server \
  --resource-group your-rg \
  --location eastus \
  --admin-user your-admin \
  --admin-password your-password \
  --sku-name Standard_B1ms
```

### 2. Azure Blob Storage
```bash
az storage account create \
  --name yourstorageaccount \
  --resource-group your-rg \
  --location eastus \
  --sku Standard_LRS

az storage container create --name raw-documents --account-name yourstorageaccount
az storage container create --name processed-documents --account-name yourstorageaccount
```

### 3. Azure Document Intelligence
Create via Azure Portal or:
```bash
az cognitiveservices account create \
  --name your-doc-intelligence \
  --resource-group your-rg \
  --kind FormRecognizer \
  --sku S0 \
  --location eastus
```

### 4. Azure AI Search
```bash
az search service create \
  --name your-search-service \
  --resource-group your-rg \
  --sku basic \
  --location eastus
```

**Setup Integrated Vectorization:**
After creating the search service, run the deployment script:
```bash
cd azure_setup
chmod +x setup_integrated_vectorization.sh
./setup_integrated_vectorization.sh
```

This creates:
- Single `document-chunks` index with vector fields
- Blob datasource connected to `raw-documents` container
- Skillset with Document Layout, Text Split, and Azure OpenAI Embedding skills
- Indexer that runs every 5 minutes

### 5. Azure OpenAI
Create via Azure Portal and deploy:
- **Chat model**: GPT-4 or GPT-4-turbo
- **Embedding model**: text-embedding-3-small (1536 dimensions)

## Deployment to Azure App Service

1. **Create App Service**:
```bash
az webapp up --name your-app-name --resource-group your-rg --runtime PYTHON:3.11
```

2. **Configure environment variables**:
```bash
az webapp config appsettings set --name your-app-name --resource-group your-rg --settings @appsettings.json
```

3. **Deploy**:
```bash
# Using GitHub Actions (see .github/workflows/deploy.yml)
# Or using Azure CLI
az webapp deploy --name your-app-name --resource-group your-rg --src-path .
```

## Frontend Integration (Lovable)

Use the following prompt in Lovable to create the frontend:

```
Create a modern RAG document analysis web application with the following features:

**Authentication Pages:**
- Sign up page (email, password)
- Login page
- Protected routes requiring authentication

**Main Dashboard:**
- Display user's folders in a grid/list view
- "Create New Folder" button (modal with folder name + password)
- Each folder card shows: folder name, document count, created date
- Click folder to access (requires folder password entry)

**Folder View:**
- Document upload area (drag & drop + file picker for PDFs)
- List of uploaded documents with status badges (Processing/Indexed/Failed)
- Delete document option
- Chat interface on the same page

**Chat Interface:**
- Chat input box at bottom
- Message history display (user messages + AI responses)
- Clear conversation button
- Loading state while AI generates response

**Styling:**
- Modern, clean UI with Tailwind CSS
- Responsive design (mobile + desktop)
- Professional color scheme (blues/grays)
- Loading states and error handling
- Toast notifications for success/error messages

**API Integration:**
- Connect to FastAPI backend at [your-azure-url]
- JWT token storage and management
- Axios or Fetch for API calls
- Handle authentication headers

**State Management:**
- Use React Context or Zustand for auth state
- Manage folder and document state
```

## Development

### Creating a new migration:
```bash
alembic revision --autogenerate -m "description"
```

### Running migrations:
```bash
alembic upgrade head
```

### Rolling back:
```bash
alembic downgrade -1
```

## Future Enhancements

- [ ] EDGAR API integration for SEC filings
- [ ] Support for additional document types (Word, Excel, images)
- [ ] Document versioning
- [ ] Shared folders between users
- [ ] Chat history persistence
- [ ] Export chat conversations
- [ ] Advanced analytics dashboard
- [ ] Webhook notifications for processing completion

## License

MIT License

## Support

For issues and questions, please create an issue in the GitHub repository.
