# OCIN — Backend Context

> Read this file first before writing any code, answering any question, or making any architectural decision for this project.

---

## What is OCIN?

OCIN is a lean, web-based SaaS platform that lets non-technical users create and run personal AI agents from a browser. Users build agents through a React frontend; backend executes those agents on-demand using PydanticAI, calling out to third-party tool platforms (Composio, Apify, Maton.ai) as needed. There are no user-specific containers or persistent runtimes. Everything is stateless and config-driven.

The name is OCIN. The product is always referred to as OCIN, never as "the platform" or "the app".

---

## Guiding principles

- **Lean over heavy.** No LangChain, no LangGraph, no CrewAI. PydanticAI only.
- **Postgres over everything.** No Supabase, no Firebase, no MongoDB. One PostgreSQL database.
- **Stateless execution.** Agents are database configs. Each run instantiates a PydanticAI agent on-demand, executes it, and tears it down. No persistent processes per user.
- **Credential-scoped isolation.** Users are isolated at the data layer — every row is scoped by `user_id`. API keys are stored encrypted per user and injected at runtime only.
- **Plain language over config.** Scheduling, tool selection, and agent setup are abstracted into simple UI concepts. Complexity lives in the backend.
- **Simple memory first, vector-ready by design.** Long-term memory is key-value facts in Postgres for v1. `pgvector` extension is enabled from day one but the embedding pipeline is deferred to v2.
- **Type-safe everywhere.** All agent inputs, outputs, and tool calls use Pydantic models. No untyped dicts.

---

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Agent framework | PydanticAI | Multi-agent, type-safe, model-agnostic |
| API server | FastAPI | Async, WebSocket support for streaming |
| Database | PostgreSQL 16 + pgvector | Via asyncpg + SQLAlchemy async |
| Migrations | Alembic | Always version-controlled |
| Cache / queues | Redis 7 | Run state, streaming tokens, session TTL |
| Scheduler | APScheduler 3.x | One central instance inside the API process |
| Auth | JWT (python-jose) + bcrypt | Email + password login |
| Secrets | cryptography (Fernet) | Encrypts stored API keys at rest |
| Env management | pydantic-settings + python-dotenv | `.env` at project root |

**No Docker SDK. No per-user containers. No mounted Docker socket.**

---

## Repository structure

```
ocin-backend/
├── app/
│   ├── main.py                    # FastAPI app, lifespan, routers, central scheduler
│   ├── config.py                  # Settings via pydantic-settings
│   ├── database.py                # Async SQLAlchemy engine + session factory
│   ├── models/
│   │   ├── user.py
│   │   ├── agent.py
│   │   ├── tool.py
│   │   ├── run.py
│   │   ├── schedule.py
│   │   ├── memory.py
│   │   └── memory_vectors.py      # dormant in v1 — schema only
│   ├── schemas/
│   │   ├── user.py
│   │   ├── agent.py
│   │   ├── tool.py
│   │   ├── run.py
│   │   └── schedule.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── agents.py
│   │   ├── tools.py
│   │   ├── runs.py                # trigger + WebSocket stream
│   │   ├── schedules.py
│   │   ├── memory.py
│   │   └── admin.py
│   ├── services/
│   │   ├── agent_runner.py        # instantiates PydanticAI agent, executes run
│   │   ├── tool_loader.py         # resolves tool list for a given agent config
│   │   ├── schedule_service.py    # plain-language → cron, APScheduler job management
│   │   └── run_service.py         # run CRUD + Redis stream publishing
│   ├── integrations/
│   │   ├── composio.py            # Composio API wrapper
│   │   ├── apify.py               # Apify Actor runner
│   │   └── maton_gateway.py       # Maton.ai gateway HTTP client
│   └── core/
│       ├── security.py            # JWT, bcrypt, Fernet key encryption
│       ├── dependencies.py        # FastAPI Depends() — auth, plan limits
│       └── exceptions.py          # Custom HTTP exceptions
├── alembic/
│   └── versions/
├── docker-compose.yml             # api + postgres + redis only
├── docker/
│   └── Dockerfile.api
├── .env.example
├── requirements.txt
└── CLAUDE.md
```

---

## How a run works

```
POST /api/v1/runs/trigger { agent_id, input }
    │
    ├── Load agent config from DB (model, system_prompt, tool_ids, temperature)
    ├── Load user's encrypted API keys from DB → decrypt → pass to agent
    ├── Call tool_loader.py → build list of PydanticAI tools for this agent
    │     ├── builtin tools (always available)
    │     ├── composio tools (if composio tool configured)
    │     ├── apify tools (if apify tool configured)
    │     └── maton tools (if maton tool configured)
    ├── Instantiate PydanticAI agent with correct model + tools
    ├── Run agent — stream tokens to Redis channel ocin:run:{run_id}:stream
    ├── Save completed run record to DB (output, tool_calls, tokens, cost)
    └── Return run_id immediately → client polls or subscribes to WS stream
```

No containers. No exec commands. No hot-reload. Just a DB read and a function call.

---

## Database schema

### `users`
```
id               UUID PRIMARY KEY
email            TEXT UNIQUE NOT NULL
hashed_password  TEXT NOT NULL
api_key          TEXT UNIQUE
plan             TEXT DEFAULT 'free'     -- free | pro | business
created_at       TIMESTAMPTZ DEFAULT now()
```

### `agents`
```
id               UUID PRIMARY KEY
user_id          UUID REFERENCES users(id) ON DELETE CASCADE
name             TEXT NOT NULL
description      TEXT
avatar           VARCHAR(64) DEFAULT 'avatar-01'
role             TEXT DEFAULT 'worker'   -- coordinator | worker | standalone
model_provider   TEXT NOT NULL
model_id         TEXT NOT NULL
temperature      FLOAT DEFAULT 0.7
system_prompt    TEXT
tool_ids         UUID[]
is_active        BOOLEAN DEFAULT true
created_at       TIMESTAMPTZ DEFAULT now()
```

### `tools`
```
id               UUID PRIMARY KEY
user_id          UUID REFERENCES users(id) ON DELETE CASCADE
name             TEXT NOT NULL
source           TEXT NOT NULL           -- builtin | composio | apify | maton
source_key       TEXT
config           JSONB DEFAULT '{}'      -- encrypted API keys + connection IDs stored here
is_active        BOOLEAN DEFAULT true
```

### `schedules`
```
id               UUID PRIMARY KEY
user_id          UUID REFERENCES users(id) ON DELETE CASCADE
agent_id         UUID REFERENCES agents(id) ON DELETE CASCADE
label            TEXT NOT NULL           -- shown to user: "Every morning at 9"
cron_expression  TEXT NOT NULL           -- never shown to user
trigger_type     TEXT DEFAULT 'cron'     -- cron | webhook | event
payload          JSONB DEFAULT '{}'
is_active        BOOLEAN DEFAULT true
last_run_at      TIMESTAMPTZ
next_run_at      TIMESTAMPTZ
```

### `runs`
```
id               UUID PRIMARY KEY
user_id          UUID REFERENCES users(id) ON DELETE CASCADE
agent_id         UUID REFERENCES agents(id)
schedule_id      UUID REFERENCES schedules(id)   -- null if manual
status           TEXT DEFAULT 'pending'           -- pending | running | success | failed
input            TEXT
output           TEXT
tool_calls       JSONB DEFAULT '[]'
tokens_used      INT
cost_usd         FLOAT
started_at       TIMESTAMPTZ
finished_at      TIMESTAMPTZ
error            TEXT
```

### `agent_memory`
```
id               UUID PRIMARY KEY
agent_id         UUID REFERENCES agents(id) ON DELETE CASCADE
key              TEXT NOT NULL
value            TEXT NOT NULL
updated_at       TIMESTAMPTZ DEFAULT now()
UNIQUE(agent_id, key)
```

### `agent_memory_vectors` — dormant in v1
```
id               UUID PRIMARY KEY
agent_id         UUID REFERENCES agents(id) ON DELETE CASCADE
content          TEXT NOT NULL
embedding        vector(1536)
source           TEXT
source_id        UUID
created_at       TIMESTAMPTZ DEFAULT now()
```

---

## Supported LLM providers

| Provider | `model_provider` value | Example `model_id` |
|---|---|---|
| OpenAI | `openai` | `gpt-4o`, `gpt-4o-mini` |
| Anthropic | `anthropic` | `claude-sonnet-4-6`, `claude-opus-4-6` |
| Google | `google` | `gemini-2.0-flash`, `gemini-2.5-pro` |
| Ollama | `ollama` | `llama3.2`, `mistral` |
| OpenRouter | `openrouter` | `meta-llama/llama-3.1-70b-instruct` |
| Mistral | `mistral` | `mistral-large-latest` |
| xAI | `xai` | `grok-3` |
| Qwen | `qwen` | `qwen-max` |
| DeepSeek | `deepseek` | `deepseek-chat` |
| Z.ai | `zai` | TBD |

API keys are stored encrypted (Fernet) in `tools.config` JSONB, decrypted only at run time, and never logged.

---

## Agent architecture

Agents are configs, not processes. When a run is triggered:

1. `agent_runner.py` reads the agent row from DB
2. `tool_loader.py` builds the tool list from the agent's `tool_ids`
3. A PydanticAI `Agent` is instantiated in memory with the correct model and tools
4. The agent runs, streams output to Redis, then is garbage collected

### Roles
- `coordinator` — receives all triggers, can delegate to worker agents by calling them directly in code
- `worker` — called by coordinator, returns typed Pydantic output
- `standalone` — triggered directly, no coordinator involved

Workers do not spawn other workers in v1. Delegation is coordinator → worker only.

---

## Scheduling

One central APScheduler instance runs inside the FastAPI process (started in `lifespan`). On startup it loads all active schedules from Postgres and registers them as CronTrigger jobs.

### Plain-language → cron
A cheap LLM call (gpt-4o-mini or claude-haiku) converts the user's label into a cron expression. The cron is validated with `croniter` before storing. Only the label is ever shown to the user.

| User says | Cron stored |
|---|---|---|
| "every morning at 9" | `0 9 * * *` |
| "every 30 minutes" | `*/30 * * * *` |
| "every Monday at 8am" | `0 8 * * 1` |

### Trigger types
- `cron` — APScheduler CronTrigger
- `webhook` — POST to `/webhooks/{schedule_id}`, HMAC-validated
- `event` — triggered by output of another run

---

## Built-in tools

Always available to every agent. Defined in `app/integrations/builtin.py`:

| Tool | What it does |
|---|---|
| `http_fetch` | GET/POST to external URL, returns body (10k char limit) |
| `get_datetime` | Returns current date/time, optionally in user's timezone |

Filesystem and shell tools are intentionally excluded — there is no per-user container to sandbox them in.

---

## External integrations

### Composio (`app/integrations/composio.py`)
- Handles OAuth connections (Gmail, Slack, Notion, GitHub, etc.)
- User authenticates via frontend → Composio stores the token → OCIN stores `composio_connection_id` in `tools.config`
- At run time: fetch available actions for the connection, register as PydanticAI tools, execute via Composio API

### Apify (`app/integrations/apify.py`)
- Runs Apify Actors by ID using `apify_api_token` from `tools.config`
- Polls for completion (max 5 min, 10s intervals)
- Returns dataset items (max 50) to the calling agent

### Maton.ai (`app/integrations/maton_gateway.py`)
- Direct HTTP client to Maton's gateway API
- Bypasses problematic MCP stdio integration
- 37 supported services with proper app-to-prefix mapping

#### Complete service table (37 supported services):

| Service | App Name |
|---------|----------|
| Google Sheets | google-sheet, google-sheets |
| Gmail | google-mail, gmail |
| Google Calendar | google-calendar |
| Google Drive | google-drive |
| Google Docs | google-docs |
| Google Slides | google-slides |
| Google Forms | google-forms |
| Google Meet | google-meet |
| Google Ads | google-ads |
| Google Analytics Data | google-analytics-data |
| Google Analytics Admin | google-analytics-admin |
| Google Search Console | google-search-console |
| Google Play | google-play |
| YouTube | youtube |
| HubSpot | hubspot |
| Salesforce | salesforce |
| Pipedrive | pipedrive |
| Apollo | apollo |
| Asana | asana |
| Jira | jira |
| ClickUp | clickup |
| Trello | trello |
| Notion | notion |
| Slack | slack |
| Outlook | outlook |
| WhatsApp Business | whatsapp-business |
| Mailchimp | mailchimp |
| Klaviyo | klaviyo |
| Typeform | typeform |
| JotForm | jotform |
| Stripe | stripe |
| QuickBooks | quickbooks |
| Xero | xero |
| WooCommerce | woocommerce |
| Chargebee | chargebee |
| Shopify | shopify |
| Airtable | airtable |
| Calendly | calendly |
| Fathom | fathom |
| LinkedIn | linkedin |

#### Error handling:
- **500 error** = OAuth token expired (connections older than ~1 month)
  Solution: User must go to maton.ai, delete the connection, and reconnect to refresh the OAuth token.
  Do NOT treat as "unsupported service".
- **403 error** = Insufficient OAuth permissions or connection needs reauth
  Solution: Reauthorize the connection at maton.ai.
- **404 error** = Requested resource not found
  Solution: Check your connection settings at maton.ai.
- **400+ error** = Request validation failed
  Solution: Check connection at maton.ai and try again.

#### Connection management (ctrl.maton.ai):
- Create connection: POST https://ctrl.maton.ai/connections
  Body: {"app": "slack"}
  Returns: {"connection_id": "...", "url": "...", "status": "..."}
- List connections: GET https://ctrl.maton.ai/connections
  Query: ?app=google-sheets&status=ACTIVE
  Returns: list of connection objects

#### Gateway URL pattern:
- Pattern: POST https://gateway.maton.ai/{app-prefix}/{api-path}
- Auth: Bearer <MATON_API_KEY>
- Optional header: Maton-Connection: <connection_id> to pick specific connection
- Maton automatically injects OAuth token for simple calls

#### Supported native API examples:
```
# Create Google Sheet
POST https://gateway.maton.ai/google-sheets/v4/spreadsheets
Body: {"properties": {"title": "My Sheet"}}

# Append rows to sheet
POST https://gateway.maton.ai/google-sheets/v4/spreadsheets/{id}/values/{range}:append
Params: valueInputOption=RAW
Body: {"values": [["col1", "col2"], ["val1", "val2"]]}

# Send Slack message
POST https://gateway.maton.ai/slack/api/chat.postMessage
Body: {"channel": "C0123456", "text": "Hello"}

# Create HubSpot contact
POST https://gateway.maton.ai/hubspot/crm/v3/objects/contacts
Body: {"properties": {"firstname": "John", "lastname": "Doe", "email": "john@example.com"}}

# Create HubSpot company
POST https://gateway.maton.ai/hubspot/crm/v3/objects/companies
Body: {"properties": {"name": "Acme Corp", "website": "acme.com"}}

# Send LinkedIn post
POST https://gateway.maton.ai/linkedin/v2/ugcPosts
Body: LinkedIn UGC post format
```

---

## API routes

All routes prefixed `/api/v1/`. Auth routes are public; all others require `Authorization: Bearer <token>`.

```
POST   /auth/register
POST   /auth/login
POST   /auth/refresh
GET    /auth/me

GET    /agents/
POST   /agents/
GET    /agents/{id}
PUT    /agents/{id}
DELETE /agents/{id}

GET    /tools/
POST   /tools/
DELETE /tools/{id}

GET    /schedules/
POST   /schedules/
PUT    /schedules/{id}
DELETE /schedules/{id}
POST   /schedules/{id}/pause
POST   /schedules/{id}/resume

GET    /runs/
GET    /runs/{id}
POST   /runs/trigger
WS     /runs/{id}/stream

GET    /memory/{agent_id}
PUT    /memory/{agent_id}/{key}
DELETE /memory/{agent_id}/{key}

POST   /webhooks/{schedule_id}     -- public, HMAC-validated

GET    /admin/users
PUT    /admin/users/{id}/plan
GET    /admin/runs
GET    /health
```

---

## Plan limits

| Limit | free | pro | business |
|---|---|---|---|
| Max agents | 2 | 10 | unlimited |
| Max active schedules | 2 | 20 | unlimited |
| Runs per month | 100 | 2000 | unlimited |
| Max tool integrations | 2 | 10 | unlimited |
| Allowed providers | openai, anthropic | all | all |
| Ollama | no | yes | yes |

---

## Security rules

- Never log decrypted API keys
- Webhook endpoints validate HMAC before doing anything else
- All admin routes require `ADMIN_SECRET` header, not a user JWT
- Rate-limit all public endpoints with slowapi
- All DB queries must be scoped by `user_id` — users cannot access other users' data

---

## Mandatory verification before claiming any backend task complete

- docker compose exec api python -m py_compile <each_modified_file> — must exit 0
- docker compose exec api python -c "from app.<module> import ..." — must print ok
- docker compose ps api after restart — must show "running" not "restarting"
- One real API call exercising the changed code path — must return the expected status code


---

## Coding conventions

- Python 3.11+
- `async def` everywhere — all routes and service methods
- SQLAlchemy 2.x async style
- Pydantic v2 for all schemas
- PydanticAI agents always use typed `result_type` — never `Any`
- `pydantic-settings` for env vars in `config.py`
- Never use `print()` — use Python `logging` with JSON formatter
- One Alembic migration per logical change
- Development environment is Windows — never use curl, bash heredocs, or Linux shell
  commands for local testing. Use Python with requests library or docker cp +
  python3 for all HTTP calls and file operations inside containers.
- **Progress streaming**: Frontend must handle SSE/WebSocket messages with `type='progress'`
  to show real-time tool execution feedback. These messages include emojis and status
  updates (e.g., "📊 Creating Google Sheet...", "✅ Spreadsheet ready: ...").
- **Python execution**: Never run python3 or pip on the host. The project runs in Docker. To execute Python in the project context, use docker compose exec api python -c "..." or docker compose exec api python -m .... Same for pip: docker compose exec api pip .... Imports of project modules (app.*, pydantic, pydantic_ai, etc.) only work inside the api container.

---

## What NOT to build

- No Docker SDK, no per-user containers, no mounted Docker socket
- No LangChain, no LangGraph, no CrewAI
- No external vector database — pgvector is in Postgres already
- No embedding pipeline in v1
- No billing / payment integration in v1
- No peer-to-peer agent delegation in v1
- No frontend code
