"""
Pytest configuration and fixtures for all tests.
"""

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from uuid_extensions import uuid7

from src.core.security import JWTManager, PasswordManager
from src.database.models.user import User, UserRole, UserStatus
from src.dependencies.database_session import DatabaseSession
from src.infrastructure.cache import redis_client
from src.main import app
from src.middlewares.rate_limit import RateLimitMiddleware

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/test_kms_db",
)

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    echo=False,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Provide a database session for tests."""
    async with DatabaseSession() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient]:
    """Provide an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.fixture
def sync_client() -> Generator[TestClient]:
    """Provide a synchronous test client."""
    with TestClient(app) as client:
        yield client


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        hashed_password=PasswordManager.hash_password("testpassword123"),
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        email_verified=True,
        auth_provider="local",
        last_login_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin test user."""
    admin = User(
        email="admin@example.com",
        username="adminuser",
        full_name="Admin User",
        hashed_password=PasswordManager.hash_password("adminpassword123"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        email_verified=True,
        auth_provider="local",
        last_login_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.fixture
def test_user_token(test_user: User) -> str:
    """Generate JWT token for test user."""
    return JWTManager.create_access_token(
        user_id=str(test_user.id),
        email=test_user.email,
        role=test_user.role.value,
        session_id="1234567890",
    )


@pytest.fixture
def admin_user_token(admin_user: User) -> str:
    """Generate JWT token for admin user."""
    return JWTManager.create_access_token(
        user_id=str(admin_user.id),
        email=admin_user.email,
        role=admin_user.role.value,
        session_id="1234567890",
    )


@pytest.fixture
def auth_headers(test_user_token: str) -> dict:
    """Provide authentication headers for test user."""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def admin_auth_headers(admin_user_token: str) -> dict:
    """Provide authentication headers for admin user."""
    return {"Authorization": f"Bearer {admin_user_token}"}


@pytest_asyncio.fixture
async def test_knowledge_base(db_session: AsyncSession, test_user: User):
    """Create a test knowledge base."""
    from src.database.models.document import KnowledgeBase

    kb = KnowledgeBase(
        id=uuid7(),
        name="Test Knowledge Base",
        description="Test Description",
        tenant_id=test_user.id,
        is_active=True,
    )
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    return kb


@pytest_asyncio.fixture
async def test_document(db_session: AsyncSession, test_knowledge_base):
    """Create a test document."""
    from src.database.models.document import Document
    from src.domain.schemas.document import DocumentStatusEnum

    doc = Document(
        id=uuid7(),
        filename="test_document.pdf",
        original_filename="test_document.pdf",
        file_path="/test/path/test_document.pdf",
        file_size=1024,
        file_type="application/pdf",
        knowledge_base_id=test_knowledge_base.id,
        tenant_id=test_knowledge_base.tenant_id,
        status=DocumentStatusEnum.FINISHED.value,
        is_active=True,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def test_conversation(db_session: AsyncSession, test_user: User):
    """Create a test conversation."""
    from src.database.models.conversation import ConversationModel

    conversation = ConversationModel(
        id=uuid7(),
        user_id=test_user.id,
        name="Test Conversation",
        is_active=True,
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


@pytest.fixture(autouse=True)
def mock_rate_limit_middleware(monkeypatch):
    """
    Tự động bỏ qua RateLimitMiddleware trong tất cả các bài test.
    Thay thế phương thức `dispatch` (hoặc __call__) để không kết nối Redis.
    """

    async def mock_dispatch(self, request, call_next):
        return await call_next(request)

    monkeypatch.setattr(RateLimitMiddleware, "dispatch", mock_dispatch)


@pytest_asyncio.fixture(autouse=True)
async def clear_redis_cache():
    """Clear Redis cache before and after each test."""
    try:
        redis = redis_client.get()
        await redis.flushdb()
        yield
        await redis.flushdb()
    except Exception:
        yield


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for tests."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_for_testing_only")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")
