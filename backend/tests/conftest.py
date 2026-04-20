"""Shared fixtures for testing approval workflow."""
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.models.agent import Agent
from app.models.approval import Approval
from app.models.run import Run
from app.core.dependencies import CurrentUser


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://ocin:ocinpass@localhost:5432/ocin_test"

# Create async engine for tests
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=StaticPool,
    connect_args={"server_settings": {"application_name": "ocin_tests"}},
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a clean database session for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an HTTP client for testing API endpoints."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        hashed_password=hash_password("test"),  # Short password to avoid bcrypt length issues
        plan="free",
        api_key="test_api_key_123"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_agent(db_session: AsyncSession, test_user: User) -> Agent:
    """Create a test agent."""
    agent = Agent(
        user_id=test_user.id,
        name="Test Agent",
        description="A test agent for approval workflow",
        avatar="avatar-01",
        role="worker",
        model_provider="openai",
        model_id="gpt-4o-mini",
        temperature=0.7,
        system_prompt="You are a helpful assistant.",
        tool_ids=[],
        is_active=True
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


@pytest.fixture
async def test_run(db_session: AsyncSession, test_user: User, test_agent: Agent) -> Run:
    """Create a test run."""
    run = Run(
        user_id=test_user.id,
        agent_id=test_agent.id,
        input="Test input",
        status="pending",
        tokens_used=0,
        cost_usd=0.0
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


@pytest.fixture
async def test_approval(db_session: AsyncSession, test_user: User, test_agent: Agent, test_run: Run) -> Approval:
    """Create a test approval."""
    approval = Approval(
        user_id=test_user.id,
        agent_id=test_agent.id,
        run_id=test_run.id,
        kind="send_email",
        title="Send email to customer",
        description="This will send an email to customer@example.com",
        payload={
            "to": "customer@example.com",
            "subject": "Product update",
            "body": "Your product has been shipped!"
        },
        status="pending",
        expires_at=datetime.now() + timedelta(hours=24)
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)
    return approval


@pytest.fixture
def auth_token(test_user: User) -> str:
    """Generate JWT token for test user."""
    return create_access_token(data={"sub": str(test_user.id)})


@pytest.fixture
async def auth_headers(auth_token: str) -> dict:
    """Generate authorization headers."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
async def authenticated_client(client: AsyncClient, auth_headers: dict) -> AsyncClient:
    """Create an authenticated HTTP client."""
    client.headers.update(auth_headers)
    return client