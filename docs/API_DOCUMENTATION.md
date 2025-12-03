# API Documentation - KMS Service

## Base URL
```
http://localhost:8000
```

## Table of Contents
1. [Authentication APIs](#authentication-apis)
2. [Chat APIs](#chat-apis)
3. [Chunks APIs](#chunks-apis)
4. [Conversation APIs](#conversation-apis)
5. [Document APIs](#document-apis)
6. [Knowledge Base APIs](#knowledge-base-apis)
7. [WebSocket APIs](#websocket-apis)

---

## Authentication APIs

Base Path: `/auth`

### 1. **Google OAuth Login**
```http
GET /auth/google/login
```

**Description:** Initiate Google OAuth flow - redirects user to Google's OAuth consent screen

**Query Parameters:**
- `redirect_uri` (optional): Frontend redirect URI after OAuth

**Response:**
- Redirects to Google OAuth consent screen

---

### 2. **Google OAuth Callback**
```http
GET /auth/google/callback
```

**Description:** Google OAuth callback - exchanges Google code for temporary auth code

**Query Parameters:**
- `code` (required): Authorization code from Google
- `state` (optional): OAuth state parameter

**Response:**
- Redirects to frontend with temporary auth code

---

### 3. **Exchange Authorization Code**
```http
POST /auth/exchange-code
```

**Description:** Exchange temporary authorization code for access & refresh tokens

**Request Body:**
```json
{
  "code": "string"
}
```

**Response:**
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "Bearer",
  "user_id": "string"
}
```

---

### 4. **Register User**
```http
POST /auth/register
```

**Description:** Register a new user with email/password

**Request Body:**
```json
{
  "email": "user@example.com",
  "username": "string",
  "password": "string",
  "full_name": "string"
}
```

**Response:**
```json
{
  "data": {
    "id": "uuid",
    "email": "string",
    "username": "string",
    "full_name": "string"
  },
  "message": "User registered successfully. Please check your email for verification."
}
```

---

### 5. **Login**
```http
POST /auth/login
```

**Description:** Authenticate user with email/password and return JWT tokens

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "string"
}
```

**Response:**
```json
{
  "data": {
    "access_token": "string",
    "refresh_token": "string",
    "token_type": "Bearer"
  },
  "message": "Login successful",
  "user": {
    "id": "string",
    "email": "string",
    "username": "string",
    "full_name": "string",
    "avatar_url": "string",
    "auth_provider": "local|google"
  }
}
```

---

### 6. **Refresh Token**
```http
POST /auth/refresh
```

**Description:** Refresh access token using refresh token

**Request Body:**
```json
{
  "refresh_token": "string"
}
```

**Response:**
```json
{
  "data": {
    "access_token": "string",
    "refresh_token": "string",
    "token_type": "Bearer"
  },
  "message": "Token refreshed successfully"
}
```

---

### 7. **Logout**
```http
POST /auth/logout
```

**Description:** Logout user by revoking refresh token

**Request Body:**
```json
{
  "refresh_token": "string"
}
```

**Response:**
```
"Logout successful"
```

---

### 8. **Get Current User**
```http
GET /auth/me
```

**Description:** Get current user profile

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "id": "uuid",
  "email": "string",
  "username": "string",
  "full_name": "string",
  "role": "user|admin",
  "status": "active|pending_verification|suspended",
  "email_verified": true,
  "created_at": "datetime",
  "last_login_at": "datetime"
}
```

---

### 9. **Logout All Sessions**
```http
POST /auth/logout-all
```

**Description:** Logout user from all sessions

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response:**
```
"Logged out from {count} sessions"
```

---

### 10. **Get Profile**
```http
GET /auth/profile
```

**Description:** Get current user profile with permissions

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "id": "uuid",
  "email": "string",
  "username": "string",
  "full_name": "string",
  "role": "user|admin",
  "status": "active",
  "email_verified": true,
  "created_at": "datetime",
  "last_login_at": "datetime"
}
```

---

### 11. **Update Profile**
```http
PUT /auth/profile
```

**Description:** Update current user profile

**Headers:**
```
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "full_name": "string",
  "username": "string"
}
```

**Response:**
```json
{
  "id": "uuid",
  "email": "string",
  "username": "string",
  "full_name": "string",
  "role": "user",
  "status": "active",
  "email_verified": true,
  "created_at": "datetime",
  "last_login_at": "datetime"
}
```

---

### 12. **Change Password**
```http
POST /auth/password/change
```

**Description:** Change user password (only for local auth users)

**Headers:**
```
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "old_password": "string",
  "new_password": "string"
}
```

**Response:**
```json
{
  "message": "Password changed successfully"
}
```

---

### 13. **Request Password Reset**
```http
POST /auth/password/reset
```

**Description:** Request password reset

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Response:**
```json
{
  "message": "If the email exists, a password reset link has been sent"
}
```

---

### 14. **Confirm Password Reset**
```http
POST /auth/password/reset/confirm
```

**Description:** Confirm password reset with token

**Request Body:**
```json
{
  "token": "string",
  "new_password": "string"
}
```

**Response:**
```
"Password reset successful"
```

---

### 15. **Verify Email**
```http
POST /auth/email/verify
```

**Description:** Verify user email with token

**Request Body:**
```json
{
  "token": "string"
}
```

**Response:**
```json
{
  "id": "uuid",
  "email": "string",
  "email_verified": true
}
```

---

### 16. **Resend Verification Email**
```http
POST /auth/email/resend-verification
```

**Description:** Resend email verification

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response:**
```
"Verification email sent"
```

---

### 17. **List Users (Admin Only)**
```http
GET /auth/users
```

**Description:** List all users (admin only)

**Headers:**
```
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `page` (default: 1): Page number
- `size` (default: 10): Items per page

**Response:**
```json
[
  {
    "id": "uuid",
    "email": "string",
    "username": "string",
    "full_name": "string",
    "role": "user|admin",
    "status": "active",
    "email_verified": true,
    "created_at": "datetime",
    "last_login_at": "datetime"
  }
]
```

---

### 18. **Validate Token**
```http
GET /auth/validate
```

**Description:** Validate current token and return user info

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "user_id": "string",
  "email": "string",
  "role": "user|admin",
  "status": "active",
  "message": "Token is valid"
}
```

---

## Chat APIs

Base Path: `/chat`

**Authentication Required:** All endpoints require `Authorization: Bearer {access_token}`

### 1. **Ask Question (Non-Streaming)**
```http
POST /chat/ask
```

**Description:** Ask a question and get a complete response

**Endpoint Protection:**
- Max Concurrent Requests: 80
- Max Queue Size: 300
- Queue Timeout: 300s
- Processing Timeout: 600s

**Request Body:**
```json
{
  "message": {
    "role": "user",
    "parts": [
      {
        "text": "Your question here"
      }
    ]
  },
  "conversation_id": "uuid",
  "kb_id": "string (optional)",
  "app_name": "string"
}
```

**Validation:**
- Message text cannot be empty
- Message text max length: 30,000 characters

**Response:**
```json
{
  "role": "assistant",
  "parts": [
    {
      "text": "AI response here"
    }
  ],
  "created_at": "datetime"
}
```

---

### 2. **Ask Question (Server-Sent Events)**
```http
POST /chat/ask/sse
```

**Description:** Ask a question and get streaming response via Server-Sent Events

**Endpoint Protection:**
- Max Concurrent Requests: 80
- Max Queue Size: 300
- Queue Timeout: 300s
- Processing Timeout: 600s

**Request Body:**
```json
{
  "message": {
    "role": "user",
    "parts": [
      {
        "text": "Your question here"
      }
    ]
  },
  "conversation_id": "uuid",
  "kb_id": "string (optional)",
  "app_name": "string"
}
```

**Response:**
- Content-Type: `text/event-stream`
- Headers:
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`
  - `X-Accel-Buffering: no`

**Event Format:**
```
data: {"chunk": "text chunk", "type": "content"}

data: {"type": "done"}
```

---

## Chunks APIs

Base Path: `/chunks`

**Authentication Required:** All endpoints require `Authorization: Bearer {access_token}`

### 1. **Get Chunks by Document**
```http
GET /chunks/
```

**Description:** Get all chunks for a specific document

**Query Parameters:**
- `document_id` (required): The document ID to filter chunks by

**Response:**
```json
[
  {
    "page_content": "string",
    "metadata": {
      "chunk_id": "string",
      "document_id": "string",
      "chunk_index": 0,
      "source": "string"
    }
  }
]
```

---

### 2. **Get Chunk IDs by Document**
```http
GET /chunks/ids
```

**Description:** Get only the chunk IDs for a specific document

**Query Parameters:**
- `document_id` (required): The document ID to get chunk IDs for

**Response:**
```json
[
  "chunk_id_1",
  "chunk_id_2",
  "chunk_id_3"
]
```

---

### 3. **Get Chunks by IDs (Batch)**
```http
POST /chunks/batch
```

**Description:** Retrieve multiple chunks by their IDs

**Request Body:**
```json
{
  "chunk_ids": [
    "chunk_id_1",
    "chunk_id_2",
    "chunk_id_3"
  ]
}
```

**Response:**
```json
[
  {
    "page_content": "string",
    "metadata": {
      "chunk_id": "string",
      "document_id": "string",
      "chunk_index": 0
    }
  }
]
```

---

### 4. **Get Single Chunk by ID**
```http
GET /chunks/{chunk_id}
```

**Description:** Get a single chunk by its ID

**Path Parameters:**
- `chunk_id` (required): The ID of the chunk

**Response:**
```json
{
  "page_content": "string",
  "metadata": {
    "chunk_id": "string",
    "document_id": "string",
    "chunk_index": 0
  }
}
```

---

## Conversation APIs

**Authentication Required:** All endpoints require `Authorization: Bearer {access_token}`

### 1. **List Conversations**
```http
GET /conversation/list
```

**Description:** List all conversations for the current user

**Response:**
```json
[
  {
    "id": "uuid",
    "app_name": "string",
    "title": "string",
    "created_at": "datetime",
    "updated_at": "datetime",
    "user_id": "uuid"
  }
]
```

---

### 2. **Create Conversation**
```http
POST /conversation/create
```

**Description:** Create a new conversation

**Query Parameters:**
- `app_name` (required): Name of the application/agent

**Response:**
```json
{
  "id": "uuid",
  "app_name": "string",
  "title": "string",
  "created_at": "datetime",
  "updated_at": "datetime",
  "user_id": "uuid"
}
```

---

### 3. **List Messages**
```http
GET /message/list
```

**Description:** List all messages for a conversation

**Query Parameters:**
- `conversation_id` (required): The conversation ID

**Response:**
```json
[
  {
    "id": "uuid",
    "conversation_id": "uuid",
    "role": "user|assistant",
    "parts": [
      {
        "text": "string"
      }
    ],
    "created_at": "datetime"
  }
]
```

---

### 4. **Delete Conversation**
```http
DELETE /conversation/delete
```

**Description:** Delete a conversation and all its related data including messages, events, tasks, etc.

**Query Parameters:**
- `conversation_id` (required): The conversation ID to delete

**Response:**
```json
{
  "message": "Conversation deleted successfully"
}
```

---

### 5. **Update Conversation**
```http
PATCH /conversation/update
```

**Description:** Update conversation metadata

**Request Body:**
```json
{
  "conversation_id": "uuid",
  "title": "string (optional)",
  "metadata": {
    "key": "value"
  }
}
```

**Response:**
```json
{
  "id": "uuid",
  "app_name": "string",
  "title": "string",
  "created_at": "datetime",
  "updated_at": "datetime",
  "user_id": "uuid"
}
```

---

### 6. **Get Research Status**
```http
GET /{conversation_id}/status
```

**Description:** Check if research is running (to show "Skip" button in UI)

**Path Parameters:**
- `conversation_id` (required): The conversation ID

**Response:**
```json
{
  "is_running": true,
  "conversation_id": "uuid",
  "current_node": "string",
  "started_at": "datetime",
  "can_skip": true
}
```

---

### 7. **Skip Research**
```http
POST /{conversation_id}/skip
```

**Description:** Skip the current research operation

**Path Parameters:**
- `conversation_id` (required): The conversation ID

**Response:**
```json
{
  "status": "skipped",
  "conversation_id": "uuid"
}
```

---

## Document APIs

Base Path: `/documents`

**Authentication Required:** All endpoints require `Authorization: Bearer {access_token}`

### 1. **Upload and Process Document**
```http
POST /documents/upload_and_process
```

**Description:** Upload a document to a knowledge base and start processing

**Query Parameters:**
- `knowledge_base_id` (required): UUID of the knowledge base
- `metadata` (optional): Additional metadata as JSON

**Form Data:**
- `file` (required): File to upload

**File Constraints:**
- Max size: 100MB
- Supported formats: PDF, DOCX, TXT, etc.

**Response:**
```json
{
  "id": "uuid",
  "filename": "stored_filename.ext",
  "original_filename": "original_filename.ext",
  "status": "PENDING",
  "task_id": "string"
}
```

---

### 2. **Get Document**
```http
GET /documents/{document_id}
```

**Description:** Get document details

**Path Parameters:**
- `document_id` (required): UUID of the document

**Response:**
```json
{
  "id": "uuid",
  "filename": "string",
  "original_filename": "string",
  "knowledge_base_id": "uuid",
  "status": "PENDING|PROCESSING|FINISHED|FAILED",
  "file_size": 12345,
  "file_type": "application/pdf",
  "created_at": "datetime",
  "processed_at": "datetime",
  "created_by": "uuid",
  "is_active": true
}
```

---

### 3. **Get Document Content**
```http
GET /documents/documents/{document_id}/content
```

**Description:** Get full text content of a processed document (only available after processing is complete)

**Path Parameters:**
- `document_id` (required): UUID of the document

**Response:**
```json
{
  "document_id": "uuid",
  "filename": "string",
  "content": "Full text content of the document",
  "processed_at": "datetime"
}
```

---

### 4. **Get Document Status**
```http
GET /documents/{document_id}/status
```

**Description:** Get document processing status

**Path Parameters:**
- `document_id` (required): UUID of the document

**Response:**
```json
{
  "id": "uuid",
  "status": "PENDING|PROCESSING|FINISHED|FAILED",
  "progress": 0.75,
  "current_step": "embedding",
  "error_message": "string (if failed)",
  "updated_at": "datetime"
}
```

---

### 5. **Get Multiple Document Status**
```http
POST /documents/status
```

**Description:** Get processing status for multiple documents

**Request Body:**
```json
[
  "document_id_1",
  "document_id_2",
  "document_id_3"
]
```

**Response:**
```json
[
  {
    "id": "uuid",
    "status": "FINISHED",
    "progress": 1.0,
    "current_step": "completed"
  },
  {
    "id": "uuid",
    "status": "PROCESSING",
    "progress": 0.45,
    "current_step": "extracting"
  }
]
```

---

### 6. **List Documents**
```http
GET /documents
```

**Description:** List documents in a knowledge base

**Query Parameters:**
- `knowledge_base_id` (required): UUID of the knowledge base
- `skip` (default: 0): Number of items to skip
- `limit` (default: 10): Maximum number of items to return
- `query` (optional): Search query string
- `created_by` (optional): Filter by user ID

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "filename": "string",
      "original_filename": "string",
      "status": "FINISHED",
      "file_size": 12345,
      "created_at": "datetime",
      "is_active": true
    }
  ],
  "total": 100,
  "skip": 0,
  "limit": 10
}
```

---

### 7. **Delete Document**
```http
DELETE /documents/{document_id}
```

**Description:** Delete a document

**Path Parameters:**
- `document_id` (required): UUID of the document

**Response:**
```json
{
  "detail": "Document deleted successfully"
}
```

---

### 8. **Toggle Document Active Status**
```http
PATCH /documents/{document_id}/active
```

**Description:** Activate or deactivate a document

**Path Parameters:**
- `document_id` (required): UUID of the document

**Query Parameters:**
- `active` (required): Boolean value (true/false)

**Response:**
```json
{
  "id": "uuid",
  "filename": "string",
  "is_active": true,
  "updated_at": "datetime"
}
```

---

### 9. **Get Document Q&A Pairs**
```http
GET /documents/{document_id}/qa
```

**Description:** Get question-answer pairs for a document

**Path Parameters:**
- `document_id` (required): UUID of the document

**Response:**
```json
[
  {
    "id": "uuid",
    "document_id": "uuid",
    "question": "string",
    "answer": "string",
    "created_at": "datetime"
  }
]
```

---

### 10. **Get Related Documents**
```http
POST /documents/{document_id}/related
```

**Description:** Get related documents for a document based on semantic similarity

**Path Parameters:**
- `document_id` (required): The source document ID

**Query Parameters:**
- `kb_id` (required): Knowledge base ID

**Request Body (optional):**
```json
{
  "score_threshold": 0.0,
  "embed_top": 50,
  "rerank_top": 0
}
```

**Response:**
```json
{
  "source_document_id": "string",
  "related_documents": [
    {
      "document_id": "string",
      "score": 0.85,
      "filename": "string"
    }
  ],
  "total_found": 10
}
```

---

## Knowledge Base APIs

Base Path: `/kb`

**Authentication Required:** All endpoints require `Authorization: Bearer {access_token}`

### 1. **List All Knowledge Bases (Admin)**
```http
GET /kb/admin
```

**Description:** Get a list of all knowledge bases (admin only)

**Query Parameters:**
- `limit` (default: 10): Maximum number of items to return
- `skip` (default: 0): Number of items to skip

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "string",
      "description": "string",
      "created_by": "uuid",
      "created_at": "datetime",
      "updated_at": "datetime",
      "is_active": true,
      "document_count": 25
    }
  ],
  "total": 100,
  "skip": 0,
  "limit": 10
}
```

---

### 2. **List User's Knowledge Bases**
```http
POST /kb/user
```

**Description:** Get a list of knowledge bases for the current user

**Request Body:**
```json
{
  "skip": 0,
  "limit": 10
}
```

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "string",
      "description": "string",
      "created_by": "uuid",
      "created_at": "datetime",
      "updated_at": "datetime",
      "is_active": true,
      "document_count": 25
    }
  ],
  "total": 15,
  "skip": 0,
  "limit": 10
}
```

---

### 3. **Create Knowledge Base**
```http
POST /kb/create
```

**Description:** Create a new knowledge base

**Request Body:**
```json
{
  "name": "string",
  "description": "string (optional)"
}
```

**Response:**
```json
{
  "id": "uuid",
  "name": "string",
  "description": "string",
  "created_by": "uuid",
  "created_at": "datetime",
  "updated_at": "datetime",
  "is_active": true
}
```

---

### 4. **Get Knowledge Base by ID**
```http
GET /kb/{kb_id}
```

**Description:** Get a knowledge base by its ID

**Path Parameters:**
- `kb_id` (required): The ID of the knowledge base

**Response:**
```json
{
  "id": "uuid",
  "name": "string",
  "description": "string",
  "created_by": "uuid",
  "created_at": "datetime",
  "updated_at": "datetime",
  "is_active": true,
  "document_count": 25
}
```

---

### 5. **Query Knowledge Base**
```http
POST /kb/{kb_id}/query
```

**Description:** Perform a semantic search query on a knowledge base

**Path Parameters:**
- `kb_id` (required): The ID of the knowledge base

**Query Parameters:**
- `query` (required): The search query string

**Response:**
```json
[
  {
    "page_content": "string",
    "metadata": {
      "document_id": "string",
      "chunk_id": "string",
      "score": 0.95
    }
  }
]
```

---

### 6. **Delete Knowledge Base**
```http
DELETE /kb/{kb_id}
```

**Description:** Delete a knowledge base and all its documents

**Path Parameters:**
- `kb_id` (required): The ID of the knowledge base

**Response:**
```json
{
  "message": "Knowledge base deleted successfully"
}
```

---

### 7. **Get Q&A Pairs by Knowledge Base**
```http
GET /kb/{kb_id}/qa
```

**Description:** Get all question-answer pairs for a knowledge base

**Path Parameters:**
- `kb_id` (required): The ID of the knowledge base

**Query Parameters:**
- `limit` (default: 25): Maximum number of Q&A pairs to return

**Response:**
```json
[
  {
    "id": "uuid",
    "document_id": "uuid",
    "question": "string",
    "answer": "string",
    "created_at": "datetime"
  }
]
```

---

### 8. **Update Knowledge Base**
```http
PATCH /kb/{kb_id}
```

**Description:** Update a knowledge base

**Path Parameters:**
- `kb_id` (required): UUID of the knowledge base

**Request Body:**
```json
{
  "name": "string (optional)",
  "description": "string (optional)",
  "is_active": true
}
```

**Response:**
```json
{
  "id": "uuid",
  "name": "string",
  "description": "string",
  "created_by": "uuid",
  "created_at": "datetime",
  "updated_at": "datetime",
  "is_active": true
}
```

---

## WebSocket APIs

Base Path: `/websocket`

**Authentication Required:** All endpoints require `Authorization: Bearer {access_token}`

### 1. **Document Status WebSocket**
```
WebSocket: ws://localhost:8000/websocket/ws/document_status/{document_id}
```

**Description:** Real-time document processing status updates

**Path Parameters:**
- `document_id` (required): UUID of the document

**Connection Flow:**
1. Client connects via WebSocket
2. Server sends initial status immediately
3. Server pushes incremental updates (progress, success, error)
4. Connection closes when processing is complete or fails

**Message Types:**

**Initial Status:**
```json
{
  "type": "initial_status",
  "data": {
    "id": "uuid",
    "status": "PROCESSING",
    "progress": 0.0,
    "current_step": "extracting"
  }
}
```

**Status Update:**
```json
{
  "type": "status_update",
  "data": {
    "id": "uuid",
    "status": "PROCESSING",
    "progress": 0.65,
    "current_step": "embedding",
    "message": "Embedding document chunks..."
  }
}
```

**Complete:**
```json
{
  "type": "complete",
  "message": "Processing finished with status: COMPLETED"
}
```

**Error:**
```json
{
  "type": "error",
  "message": "Error message here"
}
```

**JavaScript Client Example:**
```javascript
const docId = "123e4567-e89b-12d3-a456-426614174000";
const token = "your_access_token";
const ws = new WebSocket(
  `ws://localhost:8000/websocket/ws/document_status/${docId}`,
  [],
  { headers: { Authorization: `Bearer ${token}` } }
);

ws.onopen = () => console.log("✅ Connected to document status stream");

ws.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  console.log("📨 Event:", payload);
  
  if (payload.type === "status_update") {
    updateProgressBar(payload.data.progress);
  } else if (payload.type === "complete") {
    console.log("✅ Processing complete!");
  } else if (payload.type === "error") {
    console.error("❌ Error:", payload.message);
  }
};

ws.onerror = (error) => console.error("WebSocket error:", error);
ws.onclose = () => console.log("❌ Disconnected");
```

---

### 2. **Document Status Info**
```http
GET /websocket/document_status/{document_id}/info
```

**Description:** Get information about the WebSocket endpoint for document status

**Path Parameters:**
- `document_id` (required): UUID of the document

**Response:**
```json
{
  "websocket_url": "ws://localhost:8000/websocket/ws/document_status/{document_id}",
  "description": "Use this WebSocket to receive real-time updates about a document's processing status.",
  "example_event": {
    "event": "status_update",
    "data": {
      "phase": "extracting_text",
      "progress": 0.45,
      "message": "Extracting text from PDF..."
    }
  }
}
```

---

## Common Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "detail": "Error message describing what went wrong"
}
```

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```

### 403 Forbidden
```json
{
  "detail": "Not authorized to access this resource"
}
```

### 404 Not Found
```json
{
  "detail": "Resource not found"
}
```

### 413 Payload Too Large
```json
{
  "detail": "File too large. Maximum size allowed is 100MB"
}
```

### 422 Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

---

## Authentication

Most endpoints require authentication using JWT Bearer tokens.

### How to Authenticate:

1. **Login or Register** to get access token:
   ```http
   POST /auth/login
   ```

2. **Include token in requests:**
   ```
   Authorization: Bearer {your_access_token}
   ```

3. **Refresh token when expired:**
   ```http
   POST /auth/refresh
   ```

### Token Expiration:
- Access tokens expire after a certain period
- Use the refresh token to get a new access token
- Refresh tokens are long-lived but can be revoked

---

## Rate Limiting

Some endpoints have rate limiting and queue management:

### Chat Endpoints:
- **Max Concurrent Requests:** 80
- **Max Queue Size:** 300
- **Queue Timeout:** 300 seconds
- **Processing Timeout:** 600 seconds

If these limits are exceeded, you'll receive a 429 Too Many Requests error.

---

## Best Practices

1. **Always handle errors gracefully** - Check status codes and error messages
2. **Use WebSockets for real-time updates** - Especially for document processing
3. **Implement token refresh logic** - Don't let users get logged out unexpectedly
4. **Use pagination** - Don't fetch all records at once
5. **Validate input** - Check file sizes and formats before uploading
6. **Use SSE for chat** - For better user experience with streaming responses
7. **Clean up WebSocket connections** - Always close connections when done
8. **Retry failed requests** - With exponential backoff for transient errors

---

## Postman Collection

You can import these endpoints into Postman for easier testing. Create a collection with:

1. **Environment Variables:**
   - `base_url`: `http://localhost:8000`
   - `access_token`: Your JWT token
   - `refresh_token`: Your refresh token

2. **Pre-request Script (for authenticated requests):**
   ```javascript
   pm.request.headers.add({
     key: 'Authorization',
     value: 'Bearer ' + pm.environment.get('access_token')
   });
   ```

---

## Support

For issues or questions:
- Check error messages for specific guidance
- Review logs for detailed error information
- Contact the development team

---

**Last Updated:** November 23, 2025
**API Version:** 1.0.0

