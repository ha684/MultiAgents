# src/main.py
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.api.document import router as document_router
from src.api.knowledge_base import router as knowledge_base_router
from src.api.chat import router as chat_router
from src.api.chunks import router as chunks_router
from src.api.websocket import router as websocket_router
from src.api.conv_agent import router as conversation_router
from src.api.auth import router as auth_router
from src.config.settings import settings
from src.utils.logger_conf import logger
from src.connector import database_connector
from src.rag.vector import vector_storage_migration
from src.middleware.rate_limit import RateLimitMiddleware
from src.middleware.response_handler import ResponseHandlerMiddleware
from src.middleware.exception_handler import exception_handler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for FastAPI application"""
    logger.info("Starting up application...")

    try:
        await database_connector.initialize()
        logger.info("Database connection initialized successfully")
        await vector_storage_migration.run_migrations()
        logger.info("Vector storage migration completed successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise e

    yield

    logger.info("Shutting down application...")

    try:
        await database_connector.close()
        logger.info("Database connection closed successfully")
    except Exception as e:
        logger.error(f"Error closing database connection: {e}")


app = FastAPI(
    title="Knowledge Management System",
    description="API for Knowledge Management System with RAG capabilities",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(ResponseHandlerMiddleware)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log requests with response handler support"""
    if (
        request.url.path.startswith("/websocket/")
        or request.url.path.startswith("/ws/")
        or request.headers.get("upgrade", "").lower() == "websocket"
        or request.headers.get("connection", "").lower() == "upgrade"
    ):
        return await call_next(request)

    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    response_info = f"{request.method} {request.url.path}"
    if hasattr(response, 'status_code'):
        response_info += f" - {response.status_code}"
    if isinstance(response, StreamingResponse):
        response_info += " (streaming)"
    
    logger.info(f"Request: {response_info} - Completed in {process_time:.4f}s")
    return response


app.exception_handler(Exception)(exception_handler)
app.exception_handler(HTTPException)(exception_handler)
app.exception_handler(RequestValidationError)(exception_handler)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


app.include_router(websocket_router)
app.include_router(document_router)
app.include_router(knowledge_base_router)
app.include_router(chat_router)
app.include_router(chunks_router)
app.include_router(conversation_router)
app.include_router(auth_router)

if __name__ == "__main__":
    logger.info(f"Starting server on host=0.0.0.0, port={settings.port}")
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
