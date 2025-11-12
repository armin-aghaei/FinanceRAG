# API Reference

Base URL (Development): `http://localhost:8000/api/v1`
Base URL (Production): `https://your-app-name.azurewebsites.net/api/v1`

## Authentication

All endpoints except `/auth/signup` and `/auth/login` require authentication via JWT token in the Authorization header:

```
Authorization: Bearer <your_jwt_token>
```

---

## Endpoints

### Authentication

#### POST /auth/signup
Register a new user.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response (201):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

#### POST /auth/login
Authenticate and get JWT token.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

#### GET /auth/me
Get current user information.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### Folders

#### POST /folders
Create a new folder.

**Headers:**
```
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "folder_name": "My Documents",
  "password": "folderpass123"
}
```

**Response (201):**
```json
{
  "id": 1,
  "folder_name": "My Documents",
  "user_id": 1,
  "search_index_name": "rag-index-my-documents-1",
  "document_count": 0,
  "created_at": "2024-01-15T10:35:00Z",
  "updated_at": "2024-01-15T10:35:00Z"
}
```

---

#### GET /folders
List all folders for current user.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
[
  {
    "id": 1,
    "folder_name": "My Documents",
    "user_id": 1,
    "search_index_name": "rag-index-my-documents-1",
    "document_count": 5,
    "created_at": "2024-01-15T10:35:00Z",
    "updated_at": "2024-01-15T10:35:00Z"
  }
]
```

---

#### GET /folders/{folder_id}
Get specific folder details.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "id": 1,
  "folder_name": "My Documents",
  "user_id": 1,
  "search_index_name": "rag-index-my-documents-1",
  "document_count": 5,
  "created_at": "2024-01-15T10:35:00Z",
  "updated_at": "2024-01-15T10:35:00Z"
}
```

---

#### POST /folders/{folder_id}/access
Verify folder password.

**Headers:**
```
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "password": "folderpass123"
}
```

**Response (200):**
```json
{
  "message": "Access granted",
  "folder_id": 1
}
```

---

#### DELETE /folders/{folder_id}
Delete a folder and all its documents.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (204):**
No content

---

### Documents

#### POST /documents/upload/{folder_id}
Upload a PDF document to a folder.

**Headers:**
```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**Request Body (Form Data):**
- `file`: PDF file (max 50MB by default)

**Response (201):**
```json
{
  "id": 1,
  "filename": "financial-report.pdf",
  "status": "pending",
  "message": "Document uploaded successfully. Processing will begin shortly."
}
```

**Document Status Values:**
- `pending`: Uploaded, waiting for processing
- `processing`: Being analyzed by Document Intelligence
- `indexed`: Successfully processed and indexed
- `failed`: Processing failed (check error_message)

---

#### GET /documents/folder/{folder_id}
List all documents in a folder.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
[
  {
    "id": 1,
    "folder_id": 1,
    "filename": "folder-1/abc123.pdf",
    "original_filename": "financial-report.pdf",
    "status": "indexed",
    "file_size": 2048576,
    "content_type": "application/pdf",
    "metadata": {
      "page_count": 10,
      "table_count": 3,
      "key_value_pairs": []
    },
    "error_message": null,
    "created_at": "2024-01-15T10:40:00Z",
    "updated_at": "2024-01-15T10:42:00Z"
  }
]
```

---

#### GET /documents/{document_id}
Get specific document details.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "id": 1,
  "folder_id": 1,
  "filename": "folder-1/abc123.pdf",
  "original_filename": "financial-report.pdf",
  "status": "indexed",
  "file_size": 2048576,
  "content_type": "application/pdf",
  "metadata": {
    "page_count": 10,
    "table_count": 3
  },
  "error_message": null,
  "created_at": "2024-01-15T10:40:00Z",
  "updated_at": "2024-01-15T10:42:00Z"
}
```

---

#### DELETE /documents/{document_id}
Delete a document.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (204):**
No content

---

### Chat (RAG)

#### POST /chat
Ask a question about documents in a folder.

**Headers:**
```
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "query": "What were the total revenues in Q4?",
  "folder_id": 1
}
```

**Response (200):**
```json
{
  "answer": "According to the financial report, the total revenues in Q4 were $2.5 million, representing a 15% increase from Q3. This information is found in the quarterly earnings document.",
  "sources": [
    {
      "filename": "financial-report.pdf",
      "relevance_score": 0.89,
      "document_id": "1"
    },
    {
      "filename": "quarterly-earnings.pdf",
      "relevance_score": 0.76,
      "document_id": "2"
    }
  ]
}
```

---

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "detail": "Error description"
}
```

### 401 Unauthorized
```json
{
  "detail": "Could not validate credentials"
}
```

### 404 Not Found
```json
{
  "detail": "Resource not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error message"
}
```

---

## Rate Limits

Currently no rate limits are enforced. Consider implementing rate limiting in production.

---

## Example Workflow

1. **Sign up**: `POST /auth/signup`
2. **Login**: `POST /auth/login` (save the token)
3. **Create folder**: `POST /folders`
4. **Verify folder access**: `POST /folders/{id}/access`
5. **Upload document**: `POST /documents/upload/{folder_id}`
6. **Wait for processing**: Poll `GET /documents/{document_id}` until status is "indexed"
7. **Ask questions**: `POST /chat` with your query

---

## SDK Examples

### Python Example
```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# Login
response = requests.post(f"{BASE_URL}/auth/login", json={
    "email": "user@example.com",
    "password": "password123"
})
token = response.json()["access_token"]

headers = {"Authorization": f"Bearer {token}"}

# Create folder
response = requests.post(
    f"{BASE_URL}/folders",
    json={"folder_name": "My Docs", "password": "pass123"},
    headers=headers
)
folder_id = response.json()["id"]

# Upload document
with open("document.pdf", "rb") as f:
    files = {"file": f}
    response = requests.post(
        f"{BASE_URL}/documents/upload/{folder_id}",
        files=files,
        headers=headers
    )

# Ask question
response = requests.post(
    f"{BASE_URL}/chat",
    json={"query": "What is this document about?", "folder_id": folder_id},
    headers=headers
)
print(response.json()["answer"])
```

### JavaScript Example
```javascript
const BASE_URL = "http://localhost:8000/api/v1";

// Login
const loginResponse = await fetch(`${BASE_URL}/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    email: "user@example.com",
    password: "password123"
  })
});
const { access_token } = await loginResponse.json();

const headers = {
  "Authorization": `Bearer ${access_token}`,
  "Content-Type": "application/json"
};

// Create folder
const folderResponse = await fetch(`${BASE_URL}/folders`, {
  method: "POST",
  headers,
  body: JSON.stringify({
    folder_name: "My Docs",
    password: "pass123"
  })
});
const { id: folderId } = await folderResponse.json();

// Upload document
const formData = new FormData();
formData.append("file", fileInput.files[0]);

await fetch(`${BASE_URL}/documents/upload/${folderId}`, {
  method: "POST",
  headers: { "Authorization": `Bearer ${access_token}` },
  body: formData
});

// Ask question
const chatResponse = await fetch(`${BASE_URL}/chat`, {
  method: "POST",
  headers,
  body: JSON.stringify({
    query: "What is this document about?",
    folder_id: folderId
  })
});
const { answer } = await chatResponse.json();
console.log(answer);
```
