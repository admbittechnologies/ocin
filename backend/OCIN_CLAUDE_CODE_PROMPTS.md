# OCIN — Claude Code Phase Prompts (Simplified Architecture)

Use these prompts in order. Each one starts a new Claude Code task.
Drop the prompt as-is. Do not combine phases. Wait for Claude Code to finish before moving on.

> **Key difference from old architecture:** There are no per-user Docker containers.
> Agents are database configs. Execution is stateless and on-demand. Isolation is credential-scoped.

---

## PHASE 1 — Project scaffold

```
Read CLAUDE.md first and keep it in context for this entire session.

Build phase 1: project scaffold only.

Tasks:
- Create the full directory structure exactly as defined in CLAUDE.md
- Create docker-compose.yml with three services: api (FastAPI), db (PostgreSQL 16), redis (Redis 7)
  - No Docker socket mount — there are no per-user containers in this architecture
  - db uses a named volume for persistence
  - all services on a shared bridge network called ocin-network
- Create docker/Dockerfile.api for the FastAPI service
- Create app/config.py using pydantic-settings with these env vars:
  DATABASE_URL, REDIS_URL, SECRET_KEY, ADMIN_SECRET, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES,
  ENCRYPTION_KEY (Fernet key for encrypting stored API keys),
  and one optional var per provider: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY,
  OLLAMA_BASE_URL, OPENROUTER_API_KEY, MISTRAL_API_KEY, XAI_API_KEY, QWEN_API_KEY,
  DEEPSEEK_API_KEY, ZAI_API_KEY
- Create app/database.py with async SQLAlchemy engine, session factory, and get_db dependency
- Create app/main.py with the FastAPI app instance, lifespan context manager (starts APScheduler),
  and router registration stubs
- Create requirements.txt with: fastapi, uvicorn, sqlalchemy, asyncpg, alembic, pydantic,
  pydantic-settings, pydantic-ai, redis, python-jose, passlib[bcrypt], slowapi, python-dotenv,
  apscheduler, cryptography, httpx, croniter, python-json-logger
- Create .env.example with all vars set to placeholder values
- Create a minimal README.md

Do not create any routes, models, or business logic yet.
Stop when scaffold is complete and show me the full file tree.
```

---

## PHASE 2 — Database models and migrations

```
Read CLAUDE.md first and keep it in context for this entire session.

Phase 1 is complete. Now build phase 2: database models and Alembic migrations.

Tasks:
- Initialize Alembic with async support (asyncpg target)
- Configure alembic/env.py to use the async engine from app/database.py and auto-import all models
- Create SQLAlchemy ORM models matching the schema in CLAUDE.md:
  - app/models/user.py
  - app/models/agent.py (tool_ids as ARRAY of UUID)
  - app/models/tool.py (config as JSONB — this is where encrypted API keys live)
  - app/models/schedule.py
  - app/models/run.py (tool_calls as JSONB)
  - app/models/memory.py
  - app/models/memory_vectors.py (vector(1536) column, dormant — add comment "dormant in v1")
- Create app/models/__init__.py importing all models
- Enable pgvector in the first migration: op.execute("CREATE EXTENSION IF NOT EXISTS vector")
- Generate one Alembic migration creating all tables
- Add IVFFlat index on agent_memory_vectors.embedding with comment "dormant — no writes in v1"

Stop when `alembic upgrade head` runs cleanly. Show me the migration file.
```

---

## PHASE 3 — Auth

```
Read CLAUDE.md first and keep it in context for this entire session.

Phases 1–2 are complete. Now build phase 3: authentication.

Tasks:
- Create app/core/security.py with:
  - Password hashing (hash_password, verify_password) using bcrypt
  - JWT creation and verification (create_access_token, decode_token) using python-jose
  - API key generation using secrets.token_urlsafe
  - Fernet encryption helpers (encrypt_value, decrypt_value) for storing API keys at rest
- Create app/core/exceptions.py with custom HTTPException subclasses:
  UnauthorizedException, ForbiddenException, NotFoundException, ConflictException
- Create app/core/dependencies.py with:
  - get_db
  - get_current_user — decodes JWT from Authorization header, returns User ORM object
  - require_admin — validates ADMIN_SECRET header
  - check_plan_limits(resource) — checks user's plan against limits in CLAUDE.md
- Create app/schemas/user.py: UserCreate, UserLogin, UserOut, TokenOut
- Create app/services/user_service.py: create_user, get_user_by_email, get_user_by_id
- Create app/routers/auth.py:
  - POST /api/v1/auth/register
  - POST /api/v1/auth/login
  - POST /api/v1/auth/refresh
  - GET /api/v1/auth/me
- Wire auth router into app/main.py
- Add slowapi rate limiting to register and login (5 requests/minute)

Stop when all four auth endpoints work. Show me example curl commands.
```

---

## PHASE 4 — Agent CRUD

```
Read CLAUDE.md first and keep it in context for this entire session.

Phases 1–3 are complete. Now build phase 4: agent management.

Tasks:
- Create app/schemas/agent.py: AgentCreate, AgentUpdate, AgentOut
  - AgentCreate must validate model_provider is one of the supported values in CLAUDE.md
  - AgentOut must include resolved tool names alongside tool_ids
- Create app/services/agent_service.py: create_agent, get_agent, list_agents, update_agent, delete_agent
  - Enforce plan limits before create (check max agents for user's plan)
  - On create: if user has no coordinator agent yet, set role to 'coordinator' automatically
- Create app/routers/agents.py with full CRUD:
  - GET /api/v1/agents/
  - POST /api/v1/agents/
  - GET /api/v1/agents/{id}
  - PUT /api/v1/agents/{id}
  - DELETE /api/v1/agents/{id}
- All routes require auth and enforce ownership
- Wire agents router into app/main.py

Stop when full agent CRUD works. Show me curl commands for create and update.
```

---

## PHASE 5 — Tool management

```
Read CLAUDE.md first and keep it in context for this entire session.

Phases 1–4 are complete. Now build phase 5: tool configuration.

Tasks:
- Create app/schemas/tool.py: ToolCreate, ToolOut
- Create app/services/tool_service.py: create_tool, list_tools, delete_tool
  - On create: if the tool config contains any API keys, encrypt them with Fernet before storing
  - On read: never decrypt keys in list/get responses — return a "configured: true" flag instead
  - Enforce plan limits on max tool integrations
- Create app/routers/tools.py:
  - GET /api/v1/tools/ — list user's configured tools (builtin always listed)
  - POST /api/v1/tools/ — add a new tool (validate source is builtin | composio | apify | maton)
  - DELETE /api/v1/tools/{id}
- Wire tools router into app/main.py

Stop when a user can add a Composio tool config and retrieve it without seeing the raw key.
```

---

## PHASE 6 — Integrations

```
Read CLAUDE.md first and keep it in context for this entire session.

Phases 1–5 are complete. Now build phase 6: the three external tool integrations.

These are pure API wrapper modules — no PydanticAI agent logic yet.

Tasks:

### app/integrations/composio.py
- ComposioClient class with:
  - get_available_actions(connection_id, api_key) — fetches action list from Composio API
  - execute_action(connection_id, api_key, action_id, params) — executes a Composio action
  - Returns typed Pydantic response objects
  - Handles auth errors gracefully: raise a clear exception, do not crash silently

### app/integrations/apify.py
- ApifyClient class with:
  - run_actor(actor_id, input_data, api_token) → List[dict]
  - Polls for run completion (max 5 minutes, 10s intervals)
  - Returns at most 50 dataset items
  - Raises TimeoutError if actor doesn't finish in time

### app/integrations/maton.py
- MatonClient class with:
  - trigger_workflow(webhook_url, payload, webhook_secret) → dict
  - Computes HMAC-SHA256 signature and sends in X-Maton-Signature header
  - Returns Maton response body

### app/integrations/builtin.py
- Two simple PydanticAI-compatible tool functions:
  - http_fetch(url, method, body, headers) → HttpResult (status_code, body truncated to 10k, headers)
  - get_datetime(timezone) → DateTimeResult (date, time, day_of_week, unix_timestamp)

Stop when all three external clients have unit-testable methods. Show me a direct call to each.
```

---

## PHASE 7 — Agent runner

```
Read CLAUDE.md first and keep it in context for this entire session.

Phases 1–6 are complete. Now build phase 7: the core agent execution engine.

Tasks:

### app/services/tool_loader.py
- build_tools_for_agent(agent, db) → List of PydanticAI tool functions
  - Always includes builtin tools (http_fetch, get_datetime)
  - For each tool_id in agent.tool_ids:
    - If source == 'composio': fetch available actions, return as PydanticAI tools
    - If source == 'apify': return run_actor as a PydanticAI tool
    - If source == 'maton': return trigger_workflow as a PydanticAI tool
  - Decrypt API keys from tool.config using Fernet before passing to integration clients
  - Errors loading a single tool should log and skip — not abort the whole run

### app/services/agent_runner.py
- run_agent(run_id, agent_id, user_id, input_text, db, redis) — main execution function
  - Load agent config from DB
  - Load + decrypt tool credentials
  - Call tool_loader.build_tools_for_agent()
  - Instantiate PydanticAI Agent with correct model, system_prompt, temperature, tools
  - Run the agent
  - Stream output tokens to Redis channel: ocin:run:{run_id}:stream
  - On finish: update run record (status, output, tool_calls, tokens_used, cost_usd, finished_at)
  - On error: update run record with status='failed' and error message
  - Use typed result_type — never Any

### app/services/run_service.py
- create_run(user_id, agent_id, schedule_id, input) → Run
- update_run(run_id, **fields)
- list_runs(user_id, page, page_size)
- get_run(run_id, user_id)

Stop when you can trigger a run in code (not yet via HTTP) and see output streamed to Redis.
Show me the test call and the Redis messages.
```

---

## PHASE 8 — Runs and streaming

```
Read CLAUDE.md first and keep it in context for this entire session.

Phases 1–7 are complete. Now build phase 8: the runs API and WebSocket streaming.

Tasks:

### app/routers/runs.py
- GET /api/v1/runs/ — paginated, filterable by agent_id and status
- GET /api/v1/runs/{id} — full detail including tool_calls JSONB
- POST /api/v1/runs/trigger:
  - Accepts agent_id and input text
  - Creates run record (status='pending')
  - Launches run_agent() as a background task (FastAPI BackgroundTasks)
  - Returns run_id immediately
- WS /api/v1/runs/{id}/stream:
  - Authenticates via JWT passed as ?token= query param
  - Subscribes to Redis channel ocin:run:{run_id}:stream
  - Forwards tokens to the WebSocket client
  - Sends {"status": "done", "run_id": "..."} when run completes

### app/routers/memory.py
- GET /api/v1/memory/{agent_id}
- PUT /api/v1/memory/{agent_id}/{key}
- DELETE /api/v1/memory/{agent_id}/{key}

Wire both routers into app/main.py.

Stop when a manual trigger returns a run_id and the WebSocket streams output live.
Show me the full WebSocket message sequence from trigger to done.
```

---

## PHASE 9 — Scheduling

```
Read CLAUDE.md first and keep it in context for this entire session.

Phases 1–8 are complete. Now build phase 9: scheduling.

Tasks:

### Central APScheduler setup (in app/main.py lifespan)
- On startup: create AsyncIOScheduler, load all active schedules from DB, register each as a CronTrigger job
- Each job calls run_agent() with the schedule's agent_id and payload
- Expose a reload_schedules() function that re-syncs jobs from DB (called after any schedule change)

### app/services/schedule_service.py
- parse_schedule_label(label) → str (cron expression)
  - Makes a cheap LLM call (gpt-4o-mini or claude-haiku) to convert plain language to cron
  - Validates returned cron with croniter before returning
  - Raises ValueError with a user-friendly message if parsing fails
- create_schedule, list_schedules, update_schedule, delete_schedule
- pause_schedule, resume_schedule — update is_active and add/remove APScheduler job
- calculate_next_run(cron_expression) → datetime

### app/routers/schedules.py
- POST /api/v1/schedules/ — accepts label (plain language), agent_id, trigger_type, payload
- GET /api/v1/schedules/
- PUT /api/v1/schedules/{id}
- DELETE /api/v1/schedules/{id}
- POST /api/v1/schedules/{id}/pause
- POST /api/v1/schedules/{id}/resume

### Webhook trigger
- POST /api/v1/webhooks/{schedule_id} — public endpoint, validates HMAC-SHA256, triggers run

Enforce plan limits on max active schedules.
Wire schedules router into app/main.py.

Stop when a schedule created via API fires at the correct time and creates a run record.
Show me the run record it created.
```

---

## PHASE 10 — Admin and health

```
Read CLAUDE.md first and keep it in context for this entire session.

Phases 1–9 are complete. Now build phase 10: admin routes and health check.

Tasks:

### app/routers/admin.py — all routes require ADMIN_SECRET header
- GET /api/v1/admin/users — list all users with plan, run count this month, agent count
- PUT /api/v1/admin/users/{id}/plan — change plan (free | pro | business)
- GET /api/v1/admin/runs — all runs across all users, paginated, filterable by user_id/status/date

### Health check
- GET /api/v1/health — no auth required
  Returns: { api: "ok", db: "ok"|"error", redis: "ok"|"error", scheduler: "ok"|"error" }
  Actually tests connectivity for each — do not fake it

Wire admin router into app/main.py.

Stop when all admin endpoints return correct data. Show me the health check response.
```

---

## PHASE 11 — Hardening

```
Read CLAUDE.md first and keep it in context for this entire session.

Phases 1–10 are complete. Now build phase 11: hardening and final review.

Tasks:

### Security audit
- Every authenticated route has get_current_user dependency
- Every DB query is scoped by user_id — no cross-user data leakage possible
- Webhook endpoint validates HMAC before any other logic
- No API keys appear in any log statement (check all logging calls)
- Decrypted keys exist only as local variables inside run_agent(), never stored in a wider scope

### Rate limiting audit
- slowapi applied to: POST /auth/register, POST /auth/login, POST /runs/trigger, POST /webhooks/{id}
- Global rate limit per user: 100 requests/minute on all authenticated routes

### Error handling
- All routes return structured JSON: {"error": "message", "code": "ERROR_CODE"}
- Integration failures (Composio down, Apify timeout) never return 500 — return {"error": "tool unavailable", "code": "TOOL_ERROR"}
- Schedule parse failures return a clear message: {"error": "Could not understand schedule. Try 'every day at 9am'", "code": "SCHEDULE_PARSE_ERROR"}

### Structured logging
- Every request logs: method, path, user_id, status_code, duration_ms
- Every run logs: run_id, agent_id, model_provider, model_id, tokens_used, duration_ms
- Use python-json-logger with JSON formatter

### Final output
- Verify docker-compose.yml and Dockerfile.api build cleanly
- Verify alembic upgrade head runs on a fresh DB
- Write RUNNING.md covering: how to start locally, how to run migrations, how to create first user, how to test a run end-to-end, how to test the WebSocket stream

Stop when all checks pass. Show me RUNNING.md.
```

---

## PHASE 12 — Frontend integration check (run after frontend is built)

```
Read CLAUDE.md first and keep it in context for this entire session.

The frontend lives in ../ocin-frontend.

Tasks:
- Read every API call in the frontend (fetch / axios calls)
- List every endpoint the frontend calls
- For each endpoint: check it exists, check request shape matches, check response shape matches
- Produce a gap report: missing endpoints, shape mismatches, fields the frontend expects that the backend doesn't return
- If the frontend uses WebSocket, verify the message format matches phase 8's streaming implementation
- Fix all gaps in the backend — do not modify the frontend

Stop after producing the gap report and wait for approval before making fixes.
```

---

## Notes

- Start each phase with a fresh Claude Code session or `/clear`
- If Claude Code gets stuck mid-phase: re-paste the prompt and add "continue from where you left off — do not restart"
- If you change an architectural decision: update CLAUDE.md immediately so future phases inherit it
- Never skip a phase — each depends on the previous
- The old Docker-per-user architecture is gone. If Claude Code suggests anything involving `docker_service.py`, container provisioning, or exec commands — stop it and redirect back to CLAUDE.md