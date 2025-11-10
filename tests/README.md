# Testing Guide for KMS Service

This document provides comprehensive information about testing the Knowledge Management System (KMS) Service.

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Setup](#setup)
- [Running Tests](#running-tests)
- [Test Types](#test-types)
- [CI/CD](#cicd)
- [Writing Tests](#writing-tests)
- [Troubleshooting](#troubleshooting)

## Overview

The KMS Service uses pytest for testing with comprehensive coverage of:
- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test interactions between components
- **E2E Tests**: Test complete user workflows

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

```bash
# Install development dependencies
make install-dev

# Or using pip directly
pip install -e ".[test,dev]"
pip install -r requirements-test.txt
```

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

### Quick Commands

```bash
# Run all tests
make test

# Run specific test types
make test-unit          # Unit tests only
make test-integration   # Integration tests only
make test-e2e          # E2E tests only

# Run with coverage
make test-cov

# Run in Docker
make docker-test
```

### Advanced Options

```bash
# Run specific test file
pytest tests/unit_test/test_auth_endpoints.py -v

# Run specific test
pytest tests/unit_test/test_auth_endpoints.py::TestAuthEndpoints::test_login_success -v

# Run with markers
pytest -m "unit"              # Only unit tests
pytest -m "integration"       # Only integration tests
pytest -m "auth"              # Only auth-related tests
pytest -m "slow"              # Only slow tests
pytest -m "not slow"          # Skip slow tests

# Run tests in parallel
pytest tests/ -n auto

# Run tests with verbose output
pytest tests/ -vv

# Stop on first failure
pytest tests/ -x

# Show local variables in tracebacks
pytest tests/ -l

# Run with specific coverage
pytest tests/unit_test/ --cov=src.api --cov-report=html
```

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

The project includes a comprehensive GitHub Actions workflow that runs on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches

**Pipeline stages:**
1. **Test**: Runs all test suites with coverage
2. **Code Quality**: Linting, formatting checks
3. **Security**: Security scanning with Bandit and Safety
4. **Build**: Docker image build (on main branch)
5. **Deploy**: Deployment to production (on main branch)

### Local CI Simulation

Run the full CI pipeline locally:

```bash
make ci-local
```

This will:
- Run linting checks
- Run security scans
- Run all tests with coverage
- Generate reports

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
   # Reinstall package in editable mode
   pip install -e .
   ```

4. **Fixtures not found**
   ```python
   # Ensure conftest.py is in tests/ directory
   # Check fixture names match usage
   ```

5. **Async test warnings**
   ```python
   # Always use @pytest.mark.asyncio for async tests
   # Install pytest-asyncio
   pip install pytest-asyncio
   ```

### Debug Mode

Run tests with extra debugging:

```bash
# Show print statements
pytest tests/ -s

# Show local variables on failure
pytest tests/ -l

# Use Python debugger
pytest tests/ --pdb

# Increase verbosity
pytest tests/ -vv
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

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [FastAPI Testing Guide](https://fastapi.tiangolo.com/tutorial/testing/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)

## Contributing

When adding new features:

1. Write tests first (TDD approach)
2. Ensure all tests pass
3. Maintain or improve coverage
4. Update this README if adding new test patterns
5. Run `make ci-local` before committing

## Support

For testing issues:
1. Check this README
2. Review existing tests for patterns
3. Check CI/CD logs
4. Contact the development team

