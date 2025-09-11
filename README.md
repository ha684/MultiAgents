# KMS Service

Knowledge Management System Service with RAG (Retrieval-Augmented Generation) capabilities.

## Features

- **Knowledge Base Management**: Create and manage multiple knowledge bases
- **Document Processing**: Upload and process various document formats (PDF, DOCX, TXT, XLSX, PPTX, etc.)
- **RAG Implementation**: Retrieval-Augmented Generation with vector search and reranking
- **Asynchronous Processing**: Background document processing using Celery task queues
- **Vector Storage**: Document embeddings stored in Qdrant vector database
- **Multi-format Support**: Process documents with Langchain, Unstructured, and specialized loaders
- **RESTful API**: FastAPI-based REST API with automatic OpenAPI documentation
- **Database Integration**: PostgreSQL for metadata storage with SQLAlchemy ORM and Alembic migrations
- **File Storage**: MinIO for scalable document storage and management
- **Multi-language Support**: Language detection and processing for multiple languages
- **Chat Interface**: Message handling and conversational AI interactions (in development)
- **Flexible Processing**: Strategy pattern for extensible document processing workflows

## Project Structure

```
src/
├── api/                    # FastAPI route handlers
│   ├── services/          # Business logic services
│   │   ├── chat.py        # Chat service implementation
│   │   ├── document.py    # Document processing services
│   │   └── knowledge_base.py # Knowledge base management services
│   ├── chat.py           # Chat endpoints (in development)
│   ├── document.py       # Document management endpoints
│   └── knowledge_base.py # Knowledge base API endpoints
├── config/               # Application configuration
│   ├── settings.py       # Settings management with Pydantic
│   ├── celery_app.py     # Celery application setup
│   └── celery_config.py  # Celery configuration
├── db/                   # Database layer
│   ├── database.py       # Database connection and session management
│   ├── models.py         # SQLAlchemy ORM models
│   └── task_models.py    # Background task-related models
├── models/               # Pydantic API schemas
│   ├── chat.py          # Chat and message schemas
│   ├── common.py        # Common/shared schemas (pagination, search)
│   ├── document.py      # Document API schemas
│   └── knowledge_base.py # Knowledge base schemas
├── rag/                  # RAG (Retrieval-Augmented Generation)
│   ├── embeding/         # Text embedding services
│   ├── processor/        # Document processing strategies
│   │   ├── strategy/     # Processing strategy implementations
│   │   │   ├── base.py   # Base strategy interface
│   │   │   └── naive.py  # Basic processing strategy
│   │   ├── file.py       # File processor orchestration
│   │   └── tasks.py      # Processing tasks
│   ├── reranking/        # Result reranking services
│   └── vector/           # Vector storage operations
├── tasks/                # Celery background tasks
│   └── file.py          # Document processing background tasks
├── connector/            # External service connectors
│   └── minio_conn.py    # MinIO client implementation
├── nlp/                  # Natural Language Processing
│   └── language-detector.py # Multi-language detection
├── prompts/              # AI prompt templates by language
│   ├── english.yaml     # English prompts
│   ├── japanese.yaml    # Japanese prompts
│   ├── korean.yaml      # Korean prompts
│   ├── vietnamese.yaml  # Vietnamese prompts
│   └── prompt_loader.py # Prompt loading utilities
├── utils/                # Utility functions and helpers
│   ├── codec.py         # Encoding/decoding utilities
│   ├── constants.py     # Application constants
│   ├── decorators.py    # Common decorators
│   └── settings.py      # Settings utilities
└── main.py              # FastAPI application entry point
```

## API Endpoints

### Knowledge Bases

- `GET /kb/` - List knowledge bases
- `POST /kb/` - Create knowledge base
- `GET /kb/{kb_id}` - Get knowledge base details
- `POST /kb/{kb_id}/query` - Query knowledge base

### Documents

- `POST /documents/upload_and_process` - Upload and process document
- `POST /documents/process` - Process existing document
- `GET /documents/{document_id}` - Get document details
- `GET /documents/{document_id}/status` - Get processing status
- `POST /documents/status` - Get status for multiple documents
- `GET /documents` - List documents in knowledge base
- `DELETE /documents/{document_id}` - Delete document

### Chat

- `POST /chat/ask` - Send message to knowledge base (in development)

## Quick Start

### Prerequisites

- [Python 3.10-3.12](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [uv](https://docs.astral.sh/uv/) (recommended for dependency management)

### Development Setup

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd kms-service
   ```

2. **Start infrastructure services**:

   ```bash
   docker-compose up -d
   ```

3. **Install dependencies**:

   ```bash
   # Using uv (recommended)
   uv sync

   # Or using pip
   pip install -e .
   ```

4. **Configure environment**:

   ```bash
   cp env.example .env
   # Edit .env with your configuration values
   ```

5. **Initialize the database**:

   ```bash
   python init_db.py
   # Or run migrations
   alembic upgrade head
   ```

6. **Start the API server**:

   ```bash
   # Development server with auto-reload
   uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

   # Or using the Python module
   python -m src.main
   ```

7. **Start Celery worker** (in a separate terminal):
   ```bash
   celery -A src.config.celery_app worker -l info
   # Or for specific queue:
   # celery -A src.config.celery_app worker -l info -Q document_processing
   ```

### Access Points

After starting the services, you can access:

- **FastAPI Documentation**: http://localhost:8000/docs
- **API**: http://localhost:8000
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **Qdrant**: http://localhost:6333 (API) and http://localhost:6334 (Web UI)

## Using Docker Compose for Development

The Docker Compose configuration provides all required infrastructure services:

**Included Services:**

- **PostgreSQL**: Primary database for metadata storage
- **Redis**: Message broker for Celery task queue
- **Qdrant**: Vector database for embeddings storage and similarity search

**Optional Services** (commented out in docker-compose.yml):

- **MinIO**: Object storage for documents (alternative to local file storage)
- **Elasticsearch**: Full-text search capabilities (optional)
- **Celery Worker**: Background document processing container
- **Flower**: Celery monitoring interface

To enable optional services, uncomment them in `docker-compose.yml`.

### Environment Configuration

Create a `.env` file with the following variables:

```bash
# Database
DATABASE_URL=postgresql://kms_user:kms_password@localhost:5432/kms_db

# Vector Storage
VECTOR_STORAGE_URL=http://localhost:6333

# Redis/Celery
REDIS_URI=redis://localhost:6379

# File Storage (MinIO)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=kms-bucket
MINIO_SECURE=false

# Text Embeddings API
TEXT_EMBEDDINGS_URL=http://localhost:8001/embed
TEXT_EMBEDDINGS_API_KEY=your-api-key
TEXT_EMBEDDINGS_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIMENSIONS=768

# Reranking API
RERANK_URL=http://localhost:8000/rerank
RERANK_API_KEY=your-api-key
```

## Architecture Overview

### Document Processing Flow

1. **Document Upload**: Files are uploaded via the REST API endpoints
2. **Metadata Storage**: Document metadata is stored in PostgreSQL database
3. **Task Queuing**: Processing tasks are queued using Celery with Redis broker
4. **Content Extraction**: Documents are processed using Langchain loaders and Unstructured
5. **Language Detection**: Content language is detected for appropriate processing
6. **Text Chunking**: Content is split into manageable chunks using strategy pattern
7. **Embedding Generation**: Text chunks are converted to vector embeddings
8. **Vector Storage**: Embeddings are stored in Qdrant with metadata for similarity search
9. **Status Updates**: Processing status is tracked and updated throughout the pipeline

### Service Layer Architecture

The application follows a layered architecture:

- **API Layer** (`src/api/`): FastAPI route handlers
- **Service Layer** (`src/api/services/`): Business logic and orchestration
- **Data Layer** (`src/db/`): Database models and data access
- **Processing Layer** (`src/rag/`): Document processing and RAG implementation
- **Task Layer** (`src/tasks/`): Background job processing

### Key Components

#### Multi-language Support

The system includes language detection and multi-language prompt support:

```python
# Language detection
from lingua import Language, LanguageDetectorBuilder

# Supported languages with dedicated prompt templates
- English (english.yaml)
- Japanese (japanese.yaml)
- Korean (korean.yaml)
- Vietnamese (vietnamese.yaml)
```

#### Document Processing Strategies

The system uses a strategy pattern for flexible document processing:

```python
# Base strategy interface
class BaseStrategy:
    def chunk(self, file_path: str) -> List[Document]:
        """Process a file and return chunks"""
        pass

# Implemented strategies
- NaiveStrategy: Basic text extraction and chunking
- (Extensible for custom processing logic)
```

#### Vector Storage

Qdrant is used for storing and querying document embeddings:

- Collection-based organization by knowledge base
- High-performance similarity search capabilities
- Metadata filtering and faceted search support
- Scalable vector operations with HNSW indexing

#### Background Processing

Celery handles asynchronous document processing:

- Distributed task queues for horizontal scalability
- Comprehensive status tracking and error handling
- Configurable processing strategies and retry policies
- Integration with Redis for reliable message brokering

#### File Storage Options

Flexible file storage with multiple backends:

- **Local Storage**: Direct filesystem storage for development
- **MinIO**: S3-compatible object storage for production
- **Configurable**: Easy switching between storage backends

### Adding New Processing Strategies

To add a new processing strategy:

1. Create a new file in `src/rag/processor/strategy/`.
2. Implement a new class extending `BaseStrategy`.
3. Implement the `chunk` method to process documents.
4. Register the strategy in your processing pipeline.

Example:

```python
from langchain_core.documents import Document
from typing import List, Dict, Any
from src.rag.processor.strategy.base import BaseStrategy

class CustomStrategy(BaseStrategy):
    """
    Custom document processing strategy.
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Initialize custom parameters

    def chunk(self, file_path: str) -> List[Document]:
        """
        Process a file using custom logic.
        """
        # Custom implementation
        # ...
        return documents
```

### Development Commands

Common development tasks:

```bash
# Install dependencies with uv
uv sync

# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Start development server with hot reload
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Run Celery worker with auto-reload
celery -A src.config.celery_app worker -l info --autoscale=10,3

# Monitor Celery tasks (if Flower is installed)
celery -A src.config.celery_app flower
```

### Stopping Services

To stop all services:

```bash
docker-compose down
```

To stop and remove all data volumes:

```bash
docker-compose down -v
```
