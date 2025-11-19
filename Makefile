# Makefile for KMS Service Testing and Development
# Windows-compatible version

.PHONY: help sync sync-dev install install-dev test test-unit test-integration test-e2e test-all test-cov lint format clean clean-all docker-test-up docker-test-down docker-test ci-local setup setup-quick

# Detect OS
ifeq ($(OS),Windows_NT)
    DETECTED_OS := Windows
    RM := del /Q /F
    RMDIR := rmdir /S /Q
    SLEEP := timeout /t
    SHELL := cmd
else
    DETECTED_OS := $(shell uname -s)
    RM := rm -f
    RMDIR := rm -rf
    SLEEP := sleep
endif

# Default target
help:
	@echo Available commands:
	@echo.
	@echo === Setup ===
	@echo   make sync             - Sync all dependencies from lock file
	@echo   make sync-dev         - Sync with dev and test dependencies
	@echo   make setup            - Complete setup (sync + docker + db)
	@echo   make setup-quick      - Quick setup (sync only)
	@echo.
	@echo === Testing ===
	@echo   make test             - Run all tests
	@echo   make test-unit        - Run unit tests only
	@echo   make test-integration - Run integration tests only
	@echo   make test-e2e         - Run E2E tests only
	@echo   make test-cov         - Run tests with coverage report
	@echo   make test-quick       - Quick test run (fail fast)
	@echo   make test-parallel    - Run tests in parallel
	@echo.
	@echo === Code Quality ===
	@echo   make format           - Auto-format code with black, isort, ruff
	@echo   make lint             - Run linting checks
	@echo   make security         - Run security scans (bandit, safety)
	@echo.
	@echo === Docker ===
	@echo   make docker-test-up   - Start test environment with Docker Compose
	@echo   make docker-test-down - Stop test environment
	@echo   make docker-test      - Run tests in Docker environment
	@echo.
	@echo === Maintenance ===
	@echo   make clean            - Clean up cache and temporary files
	@echo   make clean-all        - Deep clean (including uv cache and venv)
	@echo   make ci-local         - Run full CI pipeline locally

# Installation with uv
sync:
	uv sync --frozen

sync-dev:
	uv sync --frozen --all-extras

# Legacy installation (for compatibility)
install:
	uv pip install -e .

install-dev:
	uv sync --frozen --all-extras

# Testing
test:
	uv run pytest tests/ -v

test-unit:
	uv run pytest tests/unit_test/ -v -m "unit"

test-integration:
	uv run pytest tests/integration_test/ -v -m "integration"

test-e2e:
	uv run pytest tests/e2e/ -v -m "e2e"

test-all:
	uv run pytest tests/ -v -m "unit or integration or e2e"

test-cov:
	uv run pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml

test-watch:
	uv run pytest-watch tests/ -v

# Code Quality
lint:
	@echo Running Ruff checks...
	uv run ruff check src/ tests/
	@echo Running Ruff format check...
	uv run ruff format --check src/ tests/

format:
	@echo Formatting with Ruff...
	uv run ruff format src/ tests/
	@echo Auto-fixing with Ruff...
	uv run ruff check src/ tests/ --fix --unsafe-fixes

# Docker Test Environment
docker-test-up:
	docker-compose -f docker/docker-compose.test.yml up -d --wait
	@echo Test environment is ready!

docker-test-down:
	docker-compose -f docker/docker-compose.test.yml down -v

docker-test:
	docker-compose -f docker/docker-compose.test.yml up --build --abort-on-container-exit

docker-test-rebuild:
	docker-compose -f docker/docker-compose.test.yml up --build --force-recreate --abort-on-container-exit

# CI Pipeline (Local)
ci-local: clean format lint security test-cov
	@echo.
	@echo ===================================
	@echo   Local CI pipeline completed!
	@echo ===================================
	@echo.

# Cleanup - Windows Compatible
ifeq ($(OS),Windows_NT)
clean:
	@echo Cleaning up...
	-@for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
	-@for /d /r . %%d in (*.egg-info) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
	-@for /d /r . %%d in (.pytest_cache) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
	-@for /d /r . %%d in (.mypy_cache) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
	-@for /d /r . %%d in (.ruff_cache) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
	-@for /d /r . %%d in (htmlcov) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
	-@del /s /q *.pyc 2>nul
	-@del /s /q *.pyo 2>nul
	-@if exist .coverage del /q .coverage 2>nul
	-@if exist coverage.xml del /q coverage.xml 2>nul
	-@if exist bandit-report.json del /q bandit-report.json 2>nul
	@echo Cleanup completed!
else
clean:
	@echo Cleaning up...
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage coverage.xml 2>/dev/null || true
	rm -f bandit-report.json 2>/dev/null || true
	@echo Cleanup completed!
endif

# Deep clean (including uv cache and venv)
clean-all: clean
	@echo Performing deep clean...
	uv cache clean 2>/dev/null || true
	rm -rf .venv 2>/dev/null || true
	@echo Deep clean completed!

# Database operations for testing
test-db-create:
	set PGPASSWORD=postgres && psql -h localhost -p 5433 -U postgres -c "CREATE DATABASE test_kms_db;" || echo Database already exists

test-db-drop:
	set PGPASSWORD=postgres && psql -h localhost -p 5433 -U postgres -c "DROP DATABASE IF EXISTS test_kms_db;"

test-db-reset: test-db-drop test-db-create
	@echo Test database reset completed!

# Run specific test file
test-file:
	uv run pytest $(FILE) -v

# Run tests with specific marker
test-marker:
	uv run pytest tests/ -v -m "$(MARKER)"

# Generate coverage badge
coverage-badge:
	uv run coverage-badge -o coverage.svg -f

# Show test coverage in browser
coverage-html:
	uv run pytest tests/ --cov=src --cov-report=html
	uv run python -m webbrowser htmlcov/index.html

# Quick test run (fail fast)
test-quick:
	uv run pytest tests/ -x -v --tb=short

# Parallel test execution
test-parallel:
	uv run pytest tests/ -n auto -v

# Pre-commit setup
pre-commit-install:
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg

pre-commit-run:
	uv run pre-commit run --all-files

# Environment setup
setup-env:
	@if not exist .env.test copy .env.example .env.test 2>nul || echo No .env.example file found
	@echo Remember to configure your .env.test file!

# Complete setup for new developers
setup: sync-dev docker-test-up test-db-create
	@echo Development environment setup completed!
	@echo Run 'make test' to verify everything works correctly.

# Quick setup (sync only)
setup-quick: sync-dev
	@echo Dependencies synced! Run 'make docker-test-up' to start services.