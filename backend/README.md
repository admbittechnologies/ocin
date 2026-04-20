# OCIN Backend

Lean SaaS platform for personal AI agents. Stateless, config-driven agent execution powered by PydanticAI.

## Quick Start

```bash
# Copy environment variables
cp .env.example .env

# Start services
docker-compose up -d

# Run migrations
docker-compose exec api alembic upgrade head

# Check health
curl http://localhost:8000/api/v1/health
```

## Tech Stack

- **Agent Framework**: PydanticAI
- **API Server**: FastAPI (async)
- **Database**: PostgreSQL 16 + pgvector
- **Cache/Queue**: Redis 7
- **Scheduler**: APScheduler
- **Auth**: JWT + bcrypt

## Project Structure

```
app/
├── main.py              # FastAPI app, lifespan, routers, central scheduler
├── config.py            # Settings via pydantic-settings
├── database.py          # Async SQLAlchemy engine + session factory
├── models/              # SQLAlchemy ORM models
├── schemas/             # Pydantic v2 schemas
├── routers/             # API route handlers
├── services/            # Business logic (agent_runner, tool_loader, etc.)
├── integrations/        # External API wrappers (Composio, Apify, Maton)
└── core/                # Security, dependencies, exceptions
```

## API Endpoints

- `POST /api/v1/auth/register` - User registration
- `POST /api/v1/auth/login` - User login
- `GET /api/v1/agents` - List agents
- `POST /api/v1/agents` - Create agent
- `GET /api/v1/tools` - List tools
- `POST /api/v1/tools` - Create tool
- `POST /api/v1/runs/trigger` - Trigger agent run
- `WS /api/v1/runs/{id}/stream` - Stream run output
- `POST /api/v1/schedules/` - Create schedule
- `GET /api/v1/memory/{agent_id}` - Get agent memory

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL and Redis (or use Docker)
docker-compose up -d db redis

# Run Alembic migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## See RUNNING.md

For detailed instructions on creating your first user and triggering a test run, see RUNNING.md.
