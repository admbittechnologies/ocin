# OCIN Backend — Running Guide

## Quick Start

```bash
# Copy environment variables
cp .env.example .env

# Edit .env with your secrets
# At minimum, set:
#   SECRET_KEY (for JWT)
#   ADMIN_SECRET (for admin endpoints)
#   ENCRYPTION_KEY (32-byte key for API key encryption)

# Start services with Docker
docker-compose up -d

# Wait for services to be ready (check with docker-compose ps)
# Then run migrations
docker-compose exec api alembic upgrade head

# Check health
curl http://localhost:8000/api/v1/health
```

## Running Locally (without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL and Redis (or use Docker)
docker-compose up -d db redis

# Copy and edit .env
cp .env.example .env

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Creating Your First User

```bash
# Register a new user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepassword123"
  }'

# Response includes access_token and user info
# Save the access_token for subsequent requests
```

## Creating an Agent

```bash
# Create an agent (requires valid JWT)
curl -X POST http://localhost:8000/api/v1/agents \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "name": "Research Assistant",
    "description": "Helps with research tasks",
    "model_provider": "openai",
    "model_id": "gpt-4o-mini",
    "temperature": 0.7,
    "system_prompt": "You are a helpful research assistant."
  }'

# Response includes agent_id
```

## Triggering a Test Run

```bash
# Trigger an agent run
curl -X POST http://localhost:8000/api/v1/runs/trigger \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "agent_id": "YOUR_AGENT_ID",
    "input": "What is the capital of France?"
  }'

# Response: {"run_id": "uuid-here"}
```

## Testing the WebSocket Stream

```bash
# Connect to the WebSocket stream for run output
wscat -c "ws://localhost:8000/api/v1/runs/YOUR_RUN_ID/stream?token=YOUR_ACCESS_TOKEN"

# You'll see tokens streamed in real-time
# Final message: {"type":"done","run_id":"uuid-here","status":"success"}
```

## Creating a Schedule

```bash
# Create a schedule with plain language
curl -X POST http://localhost:8000/api/v1/schedules \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "agent_id": "YOUR_AGENT_ID",
    "label": "every day at 9am",
    "trigger_type": "cron",
    "payload": {"input": "Daily summary"}
  }'

# The label "every day at 9am" is automatically converted to "0 9 * * *"
```

## Admin Endpoints

```bash
# List all users (requires ADMIN_SECRET header)
curl http://localhost:8000/api/v1/admin/users \
  -H "X-Admin-Secret: YOUR_ADMIN_SECRET"

# Update user plan
curl -X PUT http://localhost:8000/api/v1/admin/users/USER_ID/plan \
  -H "Content-Type: application/json" \
  -H "X-Admin-Secret: YOUR_ADMIN_SECRET" \
  -d '{"plan": "pro"}'

# List all runs across all users
curl http://localhost:8000/api/v1/admin/runs \
  -H "X-Admin-Secret: YOUR_ADMIN_SECRET"
```

## Troubleshooting

### Database connection errors
- Ensure PostgreSQL is running: `docker-compose ps db`
- Check DATABASE_URL in .env matches your setup

### Redis connection errors
- Ensure Redis is running: `docker-compose ps redis`
- Check REDIS_URL in .env

### Migration errors
- Run `alembic downgrade base` then `alembic upgrade head`
- Check alembic/versions/ for migration files

### Agent execution failures
- Check logs: `docker-compose logs -f api`
- Verify API keys are set for the model provider being used
- Built-in tools (http_fetch, get_datetime) don't require API keys

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/api/v1/health
