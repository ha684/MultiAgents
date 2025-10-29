# src/main.py
from datetime import datetime
import time
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo
import yaml

import uvicorn
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from prometheus_fastapi_instrumentator import Instrumentator
from langchain.globals import set_llm_cache

from src.core.config.settings import settings
from src.utils.logger_conf import logger
from src.infrastructure.database import database_connector
from src.infrastructure.cache import redis_client
from src.rag.vectorstores import vector_storage_migration
from src.middlewares.endpoint_manager import endpoint_manager
from src.middlewares.response_handler import ResponseHandlerMiddleware
from src.middlewares.exception_handler import exception_handler
from src.middlewares.rate_limit import RateLimitMiddleware
from src.domain.schemas.chat import HealthCheckResponse
from src.core.monitoring.observability import setup_tracing
from src.api import ROUTERS


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for FastAPI application"""
    logger.info("Starting up application...")
    app.state.redis = redis_client.get()
    try:
        setup_tracing(app)
        await database_connector.initialize()
        logger.info("Database connection initialized successfully")
        await vector_storage_migration.run_migrations()
        logger.info("Vector storage migration completed successfully")
        set_llm_cache(redis_client)
        logger.info("LLM cache initialized successfully")
    except Exception as e:
        raise ConnectionError(
            f"Failed to initialize database: {e}, Run docker compose first"
        )

    yield

    logger.info("Shutting down application...")

    try:
        await database_connector.close()
        await redis_client.clear("llm_cache")
        await redis_client.clear("rate_limit")
        await redis_client.close()
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
    allow_origins=settings.cors_allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
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
    if hasattr(response, "status_code"):
        response_info += f" - {response.status_code}"
    if isinstance(response, StreamingResponse):
        response_info += " (streaming)"

    logger.info(f"Request: {response_info} - Completed in {process_time:.4f}s")
    return response


app.exception_handler(Exception)(exception_handler)
app.exception_handler(HTTPException)(exception_handler)
app.exception_handler(RequestValidationError)(exception_handler)


@app.get("/health")
async def health_check() -> HealthCheckResponse:
    """Health check application"""
    return HealthCheckResponse(
        status="healthy", timestamp=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    )


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def landing():
    return """
    <!doctype html>
    <html>
        <head><meta charset="utf-8"><title>Service</title></head>
        <body style="font-family: system-ui; max-width: 720px; margin: 40px auto;">
        <h1>Service</h1>
            <ul>
                <li><a href="/docs">Swagger UI</a></li>
                <li><a href="/redoc">ReDoc</a></li>
                <li><a href="/health">Health check</a></li>
            </ul>
        </body>
    </html>
    """


@app.get("/health/global")
async def global_health_check():
    """Global health check for all managed endpoints"""
    await endpoint_manager.start_all_workers()
    return endpoint_manager.get_global_health()


@app.get("/health/specific")
async def endpoint_health_check(
    endpoint_name: str = Query(..., description="Name of the endpoint to check"),
):
    """Health check for specific endpoint"""
    manager = endpoint_manager.get_protector(endpoint_name)
    if not manager:
        raise HTTPException(
            status_code=404,
            detail=f"Endpoint {endpoint_name} not found or not protected",
        )

    await manager.start_workers()
    return manager.get_health_status()


Instrumentator().instrument(app).expose(app)

for router in ROUTERS:
    app.include_router(router)

if __name__ == "__main__":
    host = "0.0.0.0"
    with open("etc/log_config.yml", "r", encoding="utf-8") as f:
        log_config = yaml.safe_load(f)
    logger.info(f"Starting server on host={host}, port={settings.port}")
    uvicorn.run("src.main:app", host=host, port=settings.port, log_config=log_config)
