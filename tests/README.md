# Testing Guide

This document provides comprehensive information about testing.

## Table of Contents

- [Quick Start](#quick-start)
- [Overview](#overview)
- [Test Structure](#test-structure)
- [Setup](#setup)
- [Running Tests](#running-tests)
- [Test Types](#test-types)
- [CI/CD](#cicd)
- [Writing Tests](#writing-tests)
- [Troubleshooting](#troubleshooting)

## Quick Start

Get started with testing in under 2 minutes:

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Sync dependencies (fast!)
make sync-dev

# 3. Start test infrastructure
make docker-test-up

# 4. Run tests
make test

# 5. View coverage report
make coverage-html
```

That's it! For detailed information, continue reading below.

## Overview

The KMS Service uses pytest for testing with comprehensive coverage of:
- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test interactions between components
- **E2E Tests**: Test complete user workflows

### Technology Stack

- **Testing Framework**: [pytest](https://pytest.org/) with async support
- **Package Manager**: [uv](https://github.com/astral-sh/uv) - An extremely fast Python package installer and resolver, written in Rust
- **Coverage**: pytest-cov for test coverage reporting
- **Mocking**: pytest-mock and unittest.mock

### Why uv?

This project uses **uv** for dependency management, providing significant benefits:

| Feature | pip | uv | Improvement |
|---------|-----|-----|-------------|
| Dependency installation | ~60s | ~5s | **12x faster** ⚡ |
| Lock file support | ❌ | ✅ | Reproducible builds 🔒 |
| Cache management | Manual | Built-in | Automatic optimization 🚀 |
| Parallel downloads | Limited | Full | Maximum speed 📦 |

**Key benefits:**
- ⚡ **10-100x faster** than pip for dependency resolution and installation
- 🔒 **Deterministic builds** with `uv.lock` ensuring all environments are identical
- 🎯 **Drop-in replacement** for pip with familiar commands
- 🦀 **Written in Rust** for maximum performance and reliability

## Test Structure

```
tests/
├── conftest.py                 # Shared fixtures and configuration
├── unit_test/                  # Unit tests
│   ├── test_auth_endpoints.py
│   ├── test_chat_endpoints.py
│   ├── test_document_endpoints.py
│   ├── test_knowledge_base_endpoints.py
│   ├── test_chunks_endpoints.py
│   ├── test_conversation_endpoints.py
│   └── test_websocket_endpoints.py
├── integration_test/           # Integration tests
│   ├── test_auth_flow.py
│   ├── test_document_workflow.py
│   └── test_knowledge_base_workflow.py
└── e2e/                        # End-to-end tests
    └── test_complete_user_journey.py
```

## Setup

### 1. Install Dependencies

**Recommended: Using uv (fast & modern)**

```bash
# Sync all dependencies from lock file (recommended)
make sync-dev

# Or using uv directly
uv sync --frozen --all-extras
```

**Alternative: Using make (legacy)**

```bash
# Install development dependencies
make install-dev
```

> **Note**: This project uses [uv](https://github.com/astral-sh/uv) for fast, reliable dependency management. Dependencies are locked in `uv.lock` for reproducibility.

### 2. Set Up Test Environment

```bash
# Start test infrastructure (PostgreSQL, Redis, Qdrant)
make docker-test-up

# Create test database
make test-db-create

# Or do everything at once
make setup
```

### 3. Configure Environment Variables

Create a `.env.test` file:

```env
ENVIRONMENT=test
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/test_kms_db
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/test_kms_db
REDIS_HOST=localhost
REDIS_PORT=6380
QDRANT_HOST=localhost
QDRANT_PORT=6334
JWT_SECRET_KEY=test_secret_key_for_testing_only
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

## Running Tests

### Quick Commands (Using Make)

```bash
# Run all tests
make test

# Run specific test types
make test-unit          # Unit tests only
make test-integration   # Integration tests only
make test-e2e          # E2E tests only

# Run with coverage
make test-cov

# Quick test (fail fast)
make test-quick

# Parallel execution
make test-parallel

# Run in Docker
make docker-test
```

### Direct Commands (Using uv)

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test types
uv run pytest tests/unit_test/ -v -m "unit"
uv run pytest tests/integration_test/ -v -m "integration"
uv run pytest tests/e2e/ -v -m "e2e"

# Run with coverage
uv run pytest tests/ -v --cov=src --cov-report=term-missing
```

### Advanced Options

```bash
# Run specific test file
uv run pytest tests/unit_test/test_auth_endpoints.py -v

# Run specific test
uv run pytest tests/unit_test/test_auth_endpoints.py::TestAuthEndpoints::test_login_success -v

# Run with markers
uv run pytest -m "unit"              # Only unit tests
uv run pytest -m "integration"       # Only integration tests
uv run pytest -m "auth"              # Only auth-related tests
uv run pytest -m "slow"              # Only slow tests
uv run pytest -m "not slow"          # Skip slow tests

# Run tests in parallel
uv run pytest tests/ -n auto

# Run tests with verbose output
uv run pytest tests/ -vv

# Stop on first failure
uv run pytest tests/ -x

# Show local variables in tracebacks
uv run pytest tests/ -l

# Run with specific coverage
uv run pytest tests/unit_test/ --cov=src.api --cov-report=html
```

> **Tip**: All `pytest` commands can be run directly or via `uv run` for consistency with your environment.

## Test Types

### Unit Tests

Unit tests verify individual components in isolation using mocks and stubs.

**Characteristics:**
- Fast execution
- No external dependencies
- Mock all external services
- Focus on single function/method behavior

**Example:**
```python
@pytest.mark.unit
@pytest.mark.auth
class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_login_success(self, async_client):
        with patch("src.api.auth.auth_service.authenticate_user") as mock_auth:
            mock_auth.return_value = (mock_user, mock_token)
            
            response = await async_client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "pass"}
            )
            
            assert response.status_code == 200
```

### Integration Tests

Integration tests verify interactions between multiple components.

**Characteristics:**
- Moderate execution time
- May use test database
- Test component interactions
- Verify data flow

**Example:**
```python
@pytest.mark.integration
@pytest.mark.requires_db
class TestDocumentWorkflow:
    @pytest.mark.asyncio
    async def test_upload_and_query(self, async_client, auth_headers):
        # Upload document
        upload_response = await async_client.post(...)
        
        # Verify status
        status_response = await async_client.get(...)
        
        # Query document
        query_response = await async_client.get(...)
```

### E2E Tests

E2E tests verify complete user scenarios from start to finish.

**Characteristics:**
- Slower execution
- Use full infrastructure
- Test realistic user flows
- Verify end-to-end functionality

**Example:**
```python
@pytest.mark.e2e
@pytest.mark.slow
class TestCompleteUserJourney:
    @pytest.mark.asyncio
    async def test_new_user_journey(self, async_client):
        # Register -> Login -> Create KB -> Upload -> Chat -> Logout
        ...
```

## CI/CD

### GitHub Actions

The project includes a comprehensive GitHub Actions workflow powered by **uv** for fast dependency installation that runs on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches

**Pipeline stages:**
1. **Test**: Runs all test suites with coverage (using `uv sync` and `uv run`)
2. **Code Quality**: Auto-formatting and linting checks
3. **Security**: Security scanning with Bandit and Safety
4. **Build**: Docker image build (on main branch)
5. **Deploy**: Deployment to production (on main branch)

**Key features:**
- ⚡ **10-100x faster** dependency installation with `uv`
- 🔒 **Reproducible builds** using `uv.lock`
- 🔧 **Auto-formatting** before tests to prevent CI failures
- 📊 **Coverage reports** uploaded to Codecov

### Local CI Simulation

Run the full CI pipeline locally:

```bash
make ci-local
```

This will:
- Clean up temporary files
- Auto-format code (black, isort, ruff)
- Run linting checks
- Run security scans
- Run all tests with coverage
- Generate reports

> **Note**: The local CI pipeline mirrors what runs in GitHub Actions, ensuring consistency between local and CI environments.

## Writing Tests

### Best Practices

1. **Use Descriptive Names**
   ```python
   def test_user_cannot_access_other_users_documents():
       ...
   ```

2. **Follow AAA Pattern** (Arrange, Act, Assert)
   ```python
   async def test_create_knowledge_base():
       # Arrange
       user = await create_test_user()
       
       # Act
       response = await client.post("/kb/create", ...)
       
       # Assert
       assert response.status_code == 200
   ```

3. **Use Fixtures for Common Setup**
   ```python
   @pytest.fixture
   async def authenticated_client(async_client, test_user_token):
       async_client.headers["Authorization"] = f"Bearer {test_user_token}"
       return async_client
   ```

4. **Test Edge Cases**
   ```python
   async def test_upload_document_exceeds_size_limit():
       ...
   
   async def test_upload_document_invalid_format():
       ...
   ```

5. **Use Markers Appropriately**
   ```python
   @pytest.mark.slow
   @pytest.mark.e2e
   @pytest.mark.requires_db
   async def test_full_workflow():
       ...
   ```

### Available Fixtures

From `conftest.py`:

- `async_client`: AsyncClient for HTTP requests
- `sync_client`: Synchronous TestClient
- `db_session`: Database session
- `test_user`: Regular test user
- `admin_user`: Admin test user
- `test_user_token`: JWT token for test user
- `admin_user_token`: JWT token for admin user
- `auth_headers`: Authentication headers
- `admin_auth_headers`: Admin authentication headers
- `test_knowledge_base`: Test knowledge base
- `test_document`: Test document
- `test_conversation`: Test conversation

### Creating New Tests

1. Choose appropriate test directory (`unit_test`, `integration_test`, `e2e`)
2. Create test file: `test_<feature>_<type>.py`
3. Add appropriate markers
4. Use existing fixtures or create new ones
5. Follow naming conventions

Example:

```python
"""
Unit tests for new feature.
"""
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.unit
@pytest.mark.my_feature
class TestMyFeature:
    """Test my new feature."""
    
    @pytest.mark.asyncio
    async def test_feature_success(self, async_client, auth_headers):
        """Test successful feature execution."""
        # Test implementation
        pass
    
    @pytest.mark.asyncio
    async def test_feature_failure(self, async_client, auth_headers):
        """Test feature failure handling."""
        # Test implementation
        pass
```

## Troubleshooting

### Common Issues

1. **Tests fail due to database connection**
   ```bash
   # Ensure test database is running
   make docker-test-up
   
   # Check database status
   docker ps | grep postgres-test
   ```

2. **Redis connection errors**
   ```bash
   # Restart Redis
   docker-compose -f docker-compose.test.yml restart redis-test
   ```

3. **Import errors**
   ```bash
   # Resync dependencies from lock file
   make sync-dev
   
   # Or using uv directly
   uv sync --frozen --all-extras
   ```

4. **Outdated dependencies**
   ```bash
   # Clean uv cache and resync
   make clean-all
   make sync-dev
   ```

5. **Fixtures not found**
   ```python
   # Ensure conftest.py is in tests/ directory
   # Check fixture names match usage
   ```

6. **Async test warnings**
   ```python
   # Always use @pytest.mark.asyncio for async tests
   # Dependencies should be synced from uv.lock which includes pytest-asyncio
   ```

### Debug Mode

Run tests with extra debugging:

```bash
# Show print statements
uv run pytest tests/ -s

# Show local variables on failure
uv run pytest tests/ -l

# Use Python debugger
uv run pytest tests/ --pdb

# Increase verbosity
uv run pytest tests/ -vv

# Full debug mode
uv run pytest tests/ -vv -s -l --tb=long
```

### Coverage Reports

```bash
# Generate HTML coverage report
make coverage-html

# View coverage in terminal
make test-cov

# Generate coverage badge
make coverage-badge
```

## Test Metrics

Target metrics for the project:

- **Overall Coverage**: > 80%
- **Critical Paths**: > 95%
- **API Endpoints**: 100%
- **Unit Test Speed**: < 5 seconds total
- **Integration Test Speed**: < 30 seconds total
- **E2E Test Speed**: < 2 minutes total

## Additional Resources

### Testing
- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [FastAPI Testing Guide](https://fastapi.tiangolo.com/tutorial/testing/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)

### Tools
- [uv Documentation](https://github.com/astral-sh/uv) - Fast Python package manager
- [uv User Guide](https://docs.astral.sh/uv/) - Official uv documentation
- [Ruff](https://docs.astral.sh/ruff/) - Fast Python linter (same creators as uv)

## Contributing

When adding new features:

1. **Sync dependencies** - `make sync-dev` to ensure you have latest deps
2. **Write tests first** (TDD approach) - Create tests before implementation
3. **Format code** - `make format` to auto-format your code
4. **Run tests locally** - `make test` to verify functionality
5. **Check code quality** - `make lint` to catch issues early
6. **Run full CI pipeline** - `make ci-local` before committing
7. **Maintain coverage** - Ensure coverage stays above 80%
8. **Update documentation** - Update this README if adding new test patterns

### Pre-commit Checklist

```bash
# Quick workflow before committing
make format      # Auto-format code
make lint        # Check for issues
make test-quick  # Run tests (fail fast)
make ci-local    # Full CI pipeline (when ready to commit)
```

> **Tip**: The CI/CD pipeline will auto-format your code, but it's better to do it locally first!

## Support

For testing issues:
1. Check this README
2. Review existing tests for patterns
3. Check CI/CD logs
4. Contact the development team

