# Makefile for KMS Service Testing and Development

.PHONY: help install install-dev test test-unit test-integration test-e2e test-all test-cov lint format clean docker-test-up docker-test-down docker-test ci-local

# Default target
help:
	@echo "Available commands:"
	@echo "  make install          - Install production dependencies"
	@echo "  make install-dev      - Install development and test dependencies"
	@echo "  make test             - Run all tests"
	@echo "  make test-unit        - Run unit tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo "  make test-e2e         - Run E2E tests only"
	@echo "  make test-cov         - Run tests with coverage report"
	@echo "  make lint             - Run linting checks"
	@echo "  make format           - Format code with black and isort"
	@echo "  make clean            - Clean up cache and temporary files"
	@echo "  make docker-test-up   - Start test environment with Docker Compose"
	@echo "  make docker-test-down - Stop test environment"
	@echo "  make docker-test      - Run tests in Docker environment"
	@echo "  make ci-local         - Run full CI pipeline locally"

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[test,dev]"
	pip install -r requirements-test.txt

# Testing
test:
	pytest tests/ -v

test-unit:
	pytest tests/unit_test/ -v -m "unit"

test-integration:
	pytest tests/integration_test/ -v -m "integration"

test-e2e:
	pytest tests/e2e/ -v -m "e2e"

test-all:
	pytest tests/ -v -m "unit or integration or e2e"

test-cov:
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml

test-watch:
	pytest-watch tests/ -v

# Code Quality
lint:
	@echo "Running Ruff..."
	ruff check src/ tests/
	@echo "Running Black check..."
	black --check src/ tests/
	@echo "Running isort check..."
	isort --check-only src/ tests/
	@echo "Running mypy..."
	mypy src/ --ignore-missing-imports

format:
	@echo "Formatting with Black..."
	black src/ tests/
	@echo "Sorting imports with isort..."
	isort src/ tests/
	@echo "Auto-fixing with Ruff..."
	ruff check src/ tests/ --fix

security:
	@echo "Running Bandit security scan..."
	bandit -r src/ -f json -o bandit-report.json
	@echo "Running Safety dependency check..."
	safety check

# Docker Test Environment
docker-test-up:
	docker-compose -f docker-compose.test.yml up -d
	@echo "Waiting for services to be ready..."
	sleep 10
	@echo "Test environment is ready!"

docker-test-down:
	docker-compose -f docker-compose.test.yml down -v

docker-test:
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit

docker-test-rebuild:
	docker-compose -f docker-compose.test.yml up --build --force-recreate --abort-on-container-exit

# CI Pipeline (Local)
ci-local: clean lint security test-cov
	@echo "✅ Local CI pipeline completed successfully!"

# Cleanup
clean:
	@echo "Cleaning up..."
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
	@echo "✅ Cleanup completed!"

# Database operations for testing
test-db-create:
	PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -c "CREATE DATABASE test_kms_db;" || echo "Database already exists"

test-db-drop:
	PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -c "DROP DATABASE IF EXISTS test_kms_db;"

test-db-reset: test-db-drop test-db-create
	@echo "Test database reset completed!"

# Run specific test file
test-file:
	pytest $(FILE) -v

# Run tests with specific marker
test-marker:
	pytest tests/ -v -m "$(MARKER)"

# Generate coverage badge
coverage-badge:
	coverage-badge -o coverage.svg -f

# Show test coverage in browser
coverage-html:
	pytest tests/ --cov=src --cov-report=html
	python -m webbrowser htmlcov/index.html

# Quick test run (fail fast)
test-quick:
	pytest tests/ -x -v --tb=short

# Parallel test execution
test-parallel:
	pytest tests/ -n auto -v

# Pre-commit setup
pre-commit-install:
	pre-commit install
	pre-commit install --hook-type commit-msg

pre-commit-run:
	pre-commit run --all-files

# Environment setup
setup-env:
	cp .env.example .env.test || echo "No .env.example file found"
	@echo "Remember to configure your .env.test file!"

# Complete setup for new developers
setup: install-dev docker-test-up test-db-create
	@echo "✅ Development environment setup completed!"
	@echo "Run 'make test' to verify everything works correctly."

