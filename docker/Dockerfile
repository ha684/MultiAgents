# Multi-stage Dockerfile for production optimization
# Stage 1: Build stage
FROM python:3.12-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies needed for building
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency management
RUN pip install uv

# Set work directory
WORKDIR /app

# Copy pyproject.toml
COPY pyproject.toml ./

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV UV_HTTP_TIMEOUT=120

RUN uv pip install -r pyproject.toml --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
# RUN uv pip install opencv-python==4.12.0.0

# Stage 2: Production stage
FROM python:3.12-slim AS production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH"

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    pandoc \
    libreoffice \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Set work directory
WORKDIR /app

# Create non-root user for security FIRST
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

# Create necessary directories and set permissions
RUN mkdir -p /app/logs \
    && mkdir -p /tmp/nxkms \
    && mkdir -p /app/nltk_data \
    && chmod -R 777 /app/nltk_data \
    && chmod -R 777 /tmp/nxkms \
    && chown -R appuser:appuser /app \
    && chown -R appuser:appuser /tmp/nxkms

# Set NLTK environment variables
ENV NLTK_DATA=/app/nltk_data
ENV TEMP_DIR=/tmp/nxkms

# Switch to appuser before downloading NLTK data
USER appuser

# Download NLTK data as the appuser
RUN python -m nltk.downloader -d ${NLTK_DATA} punkt_tab averaged_perceptron_tagger_eng

# Copy application code (this should be done as root, then change ownership)
USER root
COPY . .
RUN chown -R appuser:appuser /app

# Switch back to appuser for runtime
USER appuser


# Expose port
EXPOSE 8000

# Health check
# HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
#     CMD curl -f http://localhost:8000/health || exit 1

# Default command
# CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
