# OCIN Frontend — Screen & API Integration Guide for Claude Code

> **Backend**: FastAPI (Python)
> **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui
> **API Service**: `src/lib/api.ts` — all placeholder functions live here
> **Auth**: JWT Bearer tokens stored in `localStorage` key `ocin_jwt_token`

---

## Architecture Overview

```
src/
├── lib/
│   ├── api.ts          ← All API placeholders (start here)
│   ├── auth.ts         ← Mock auth (replace with api.ts calls)
│   └── avatars.ts      ← Avatar image imports
├── pages/
│   ├── Login.tsx        ← Login screen
│   ├── Register.tsx     ← Registration screen
│   ├── ForgotPassword.tsx ← Password reset request
│   ├── Dashboard.tsx    ← Home dashboard
│   ├── Agents.tsx       ← Agent CRUD
│   ├── Runs.tsx         ← Run history + streaming view
│   ├── Schedules.tsx    ← Schedule CRUD
│   ├── Tools.tsx        ← Tool connections
│   ├── Memory.tsx       ← Key/value memory facts
│   ├── Chat.tsx         ← Chat with agents (@mentions)
│   └── Settings.tsx     ← Profile, theme, API keys, plan, danger zone
├── components/
│   ├── OcinLogo.tsx     ← Theme-adaptive logo (CSS mask)
│   ├── AppSidebar.tsx   ← Navigation sidebar
│   ├── AppLayout.tsx    ← Layout wrapper
│   ├── ProtectedRoute.tsx ← Auth guard (uses lib/auth.ts)
│   └── ...ui/           ← shadcn components
└── hooks/
    ├── use-theme.tsx    ← Theme provider (6 themes)
    └── use-toast.ts     ← Toast notifications
```

---

## Screen-by-Screen Description

### 1. Login (`/login` — `src/pages/Login.tsx`)
**Purpose**: Email + password authentication, Google OAuth button
**Current state**: Mock auth via `lib/auth.ts` → `login()` stores fake JWT in localStorage
**API integration needed**:
- `apiLogin(email, password)` → `POST /api/v1/auth/login`
- Google OAuth flow (separate OAuth endpoint)
**UI features**:
- Theme switcher dropdown (top-right) — works without backend
- OCIN logo (theme-adaptive)
- "Forgot password" link → `/forgot-password`
- "Sign up" link → `/register`

### 2. Register (`/register` — `src/pages/Register.tsx`)
**Purpose**: Account creation with plan selection (Free/Pro/Business)
**API integration needed**:
- `apiRegister(email, password, plan)` → `POST /api/v1/auth/register`
**UI features**:
- Plan selection cards (Free, Pro, Business) with feature lists
- Password visibility toggle

### 3. Forgot Password (`/forgot-password` — `src/pages/ForgotPassword.tsx`)
**Purpose**: Request password reset email
**API integration needed**:
- `apiForgotPassword(email)` → `POST /api/v1/auth/forgot-password`
**UI features**:
- Email input → shows success state after submission

### 4. Dashboard (`/` — `src/pages/Dashboard.tsx`)
**Purpose**: Overview of workspace — stats cards, recent runs, quick actions
**Current state**: All data is hardcoded constants
**API integration needed**:
- `apiGetDashboardStats()` → `GET /api/v1/dashboard/stats`
  Returns: `{ active_agents, runs_today, schedules_active, tools_connected }`
- `apiGetRecentRuns(10)` → `GET /api/v1/dashboard/recent-runs?limit=10`
  Returns: `Run[]` with `{ id, agent, status, time, duration }`
**UI features**:
- 4 summary stat cards with icons
- Recent runs table with agent avatars and status badges
- Quick action buttons: Create agent, Run agent now, Add schedule
**Notes**: Agent avatars are mapped by agent name to static imports. Backend should return agent avatar URLs.

### 5. Agents (`/agents` — `src/pages/Agents.tsx`)
**Purpose**: CRUD for AI agents, each with provider/model/temperature/system prompt config
**Current state**: Hardcoded `defaultAgents` array, state managed locally
**API integration needed**:
- `apiGetAgents()` → `GET /api/v1/agents`
- `apiCreateAgent(agent)` → `POST /api/v1/agents`
- `apiUpdateAgent(id, agent)` → `PUT /api/v1/agents/:id`
- `apiDeleteAgent(id)` → `DELETE /api/v1/agents/:id`
- `apiToggleAgent(id, active)` → `PUT /api/v1/agents/:id/toggle`
- `apiGetProviderModels(provider)` → `GET /api/v1/providers/:name/models`
**UI features**:
- Grid of agent cards with avatar, role, provider, model, active toggle
- Search filter
- Create/Edit dialog: name, description, avatar picker (30 predefined), role (coordinator/worker/standalone), provider select, model ID, temperature slider, system prompt textarea
- OCIN is the default agent and cannot be deleted
- Provider list is filtered by `getConfiguredProviders()` — **TODO**: should check which providers have API keys stored in backend
**Data model**:
```typescript
interface Agent {
  id: string;
  name: string;
  description: string;
  avatar: string;       // URL to avatar image
  role: "coordinator" | "worker" | "standalone";
  provider: string;     // "OpenAI", "Anthropic", etc.
  modelId: string;      // "gpt-4o", "claude-3-sonnet", etc.
  temperature: number;  // 0.0 - 1.0
  systemPrompt: string;
  active: boolean;
  tools: string[];      // tool IDs this agent has access to
}
```

### 6. Runs (`/runs` — `src/pages/Runs.tsx`)
**Purpose**: Execution history for all agents, with detail view and live streaming
**Current state**: Hardcoded `mockRuns` array
**API integration needed**:
- `apiGetRuns()` → `GET /api/v1/runs`
- `apiGetRun(id)` → `GET /api/v1/runs/:id`
- `apiStreamRun(id, onChunk, onDone)` → `GET /api/v1/runs/:id/stream` (SSE)
- `apiTriggerRun(agentId)` → `POST /api/v1/runs/trigger`
**UI features**:
- Table: Agent, Trigger, Status, Started, Duration, Cost
- Click row → detail view with Input/Output/Error sections
- Running runs show live terminal-style streaming (monospace, dark bg, cursor blink)
- Tool call accordion (name, input JSON, output JSON, duration)
- Token count + cost display
**Data model**:
```typescript
interface Run {
  id: string;
  agent: string;
  trigger: string;          // "Schedule" | "Manual" | "Event" | "Webhook"
  status: "pending" | "running" | "success" | "failed";
  started: string;
  duration: string;
  cost: string;
  input?: string;
  output?: string;
  error?: string;
  tokens?: number;
  toolCalls?: { name: string; input: string; output: string; duration: string }[];
}
```

### 7. Schedules (`/schedules` — `src/pages/Schedules.tsx`)
**Purpose**: CRUD for automated agent triggers (recurring, webhook, event)
**Current state**: Hardcoded `defaultSchedules` array
**API integration needed**:
- `apiGetSchedules()` → `GET /api/v1/schedules`
- `apiCreateSchedule(schedule)` → `POST /api/v1/schedules`
- `apiUpdateSchedule(id, schedule)` → `PUT /api/v1/schedules/:id`
- `apiDeleteSchedule(id)` → `DELETE /api/v1/schedules/:id`
- `apiToggleSchedule(id, active)` → `PUT /api/v1/schedules/:id/toggle`
**UI features**:
- List with label, agent name, next/last run, active toggle, edit/delete
- Webhook schedules show copyable webhook URL
- Create/Edit dialog: description (textarea for complex instructions), agent select, trigger type select
- Webhook type shows "URL will be generated after creation" notice

### 8. Tools (`/tools` — `src/pages/Tools.tsx`)
**Purpose**: Manage tools available to agents (built-in + external integrations)
**Current state**: Hardcoded `defaultTools` array
**API integration needed**:
- `apiGetTools()` → `GET /api/v1/tools`
- `apiConnectTool(toolId, credentials)` → `POST /api/v1/tools/:id/connect`
- `apiDisconnectTool(toolId)` → `POST /api/v1/tools/:id/disconnect`
**UI features**:
- "Connected" section: tool cards with icon/logo, description, "Used by" agents list
- "Available" section: unconnected tools with "Connect" button
- Built-in tools (File, HTTP, DateTime, Wait) are always connected
- External tools: Composio (OAuth flow), Apify (API token + actor ID), Maton.ai (API token)
- Each external tool has its own branded logo
- Connect dialog adapts based on tool type
- Remove confirmation shows which agents will lose access

### 9. Memory (`/memory` — `src/pages/Memory.tsx`)
**Purpose**: Key-value fact store for agent context
**Current state**: Hardcoded `defaultFacts` array
**API integration needed**:
- `apiGetMemoryFacts()` → `GET /api/v1/memory`
- `apiCreateMemoryFact(key, value)` → `POST /api/v1/memory`
- `apiUpdateMemoryFact(id, value)` → `PUT /api/v1/memory/:id`
- `apiDeleteMemoryFact(id)` → `DELETE /api/v1/memory/:id`
**UI features**:
- Table: Key (monospace, primary color), Value, Edit/Delete buttons
- Inline editing (click edit → input replaces value text)
- Add new fact: expandable row with key + value inputs

### 10. Chat (`/chat` — `src/pages/Chat.tsx`)
**Purpose**: Chat interface to interact with agents, with @mention agent switching
**Current state**: Simulated responses from hardcoded arrays
**API integration needed**:
- `apiSendChatMessage(agentId, message, attachments?)` → `POST /api/v1/chat/send`
- `apiStreamChatResponse(messageId, onToken, onDone)` → `GET /api/v1/chat/stream` (SSE)
**UI features**:
- Message bubbles with agent avatars (assistant) and user icon
- @mention popup: type `@` to filter and select agents (keyboard nav: arrows, Enter, Tab, Escape)
- Active agent indicator shows who you're talking to
- Typing indicator (bouncing dots) during response
- File/image attachments: paste from clipboard, drag & drop, or click paperclip button
- Attachments are temporary (in-memory, ObjectURLs) — images render inline, files show name
- Auto-resizing textarea input
- Empty state with agent selector buttons

### 11. Settings (`/settings` — `src/pages/Settings.tsx`)
**Purpose**: User preferences, appearance, API keys, subscription, account management
**API integration needed**:
- `apiChangePassword(current, new)` → `POST /api/v1/auth/change-password`
- `apiSaveApiKey(provider, key)` → `PUT /api/v1/settings/api-keys`
- `apiGetApiKeys()` → `GET /api/v1/settings/api-keys` (returns masked keys)
- `apiUpdatePlan(plan)` → `PUT /api/v1/settings/plan`
- `apiDeleteAccount()` → `DELETE /api/v1/settings/account`
**UI features**:
- **Appearance**: 6 theme cards (Dark, Light, Frappé, Blue, Orange, Rose) — stored in localStorage, no backend needed
- **Profile**: Read-only email display
- **Subscription Plan**: 3 plan cards (Free $0, Pro $29, Business $99) with feature lists
- **Change Password**: Current + new password fields
- **API Keys**: Per-provider (OpenAI, Anthropic, Google, Mistral, OpenRouter, Grok, Qwen, DeepSeek) with masked input, visibility toggle, save button
- **Danger Zone**: Delete account button with confirmation dialog

---

## Shared Components

| Component | File | Purpose |
|-----------|------|---------|
| `OcinLogo` | `src/components/OcinLogo.tsx` | Theme-adaptive logo using CSS mask (changes color with `--primary`) |
| `AppSidebar` | `src/components/AppSidebar.tsx` | Navigation sidebar with collapsible icon mode |
| `ProtectedRoute` | `src/components/ProtectedRoute.tsx` | Auth guard — redirects to `/login` if no token |
| `StatusBadge` | `src/components/StatusBadge.tsx` | Color-coded status pills (success/running/failed/pending) |
| `EmptyState` | `src/components/EmptyState.tsx` | Empty list placeholder with icon, text, CTA button |
| `NavLink` | `src/components/NavLink.tsx` | Sidebar navigation link with active state |

---

## FastAPI Backend Endpoints Summary

```
Auth:
  POST   /api/v1/auth/login             { email, password } → { access_token, user }
  POST   /api/v1/auth/register          { email, password, plan } → { access_token, user }
  POST   /api/v1/auth/forgot-password   { email } → { success }
  POST   /api/v1/auth/change-password   { current_password, new_password } → { success }
  GET    /api/v1/auth/me                → { email, plan }

Dashboard:
  GET    /api/v1/dashboard/stats        → { active_agents, runs_today, schedules_active, tools_connected }
  GET    /api/v1/dashboard/recent-runs  ?limit=10 → Run[]

Agents:
  GET    /api/v1/agents                 → Agent[]
  POST   /api/v1/agents                 { ...agent } → Agent
  PUT    /api/v1/agents/:id             { ...agent } → Agent
  DELETE /api/v1/agents/:id             → { success }
  PUT    /api/v1/agents/:id/toggle      { active } → { success }

Runs:
  GET    /api/v1/runs                   → Run[]
  GET    /api/v1/runs/:id               → Run
  GET    /api/v1/runs/:id/stream        SSE stream of execution output
  POST   /api/v1/runs/trigger           { agent_id } → { run_id }

Schedules:
  GET    /api/v1/schedules              → Schedule[]
  POST   /api/v1/schedules             { ...schedule } → Schedule
  PUT    /api/v1/schedules/:id          { ...schedule } → Schedule
  DELETE /api/v1/schedules/:id          → { success }
  PUT    /api/v1/schedules/:id/toggle   { active } → { success }

Tools:
  GET    /api/v1/tools                  → Tool[]
  POST   /api/v1/tools/:id/connect      { api_token?, actor_id? } → { success }
  POST   /api/v1/tools/:id/disconnect   → { success }

Memory:
  GET    /api/v1/memory                 → Fact[]
  POST   /api/v1/memory                { key, value } → Fact
  PUT    /api/v1/memory/:id            { value } → { success }
  DELETE /api/v1/memory/:id            → { success }

Settings:
  GET    /api/v1/settings/api-keys      → { [provider]: "masked_key" }
  PUT    /api/v1/settings/api-keys      { provider, api_key } → { success }
  PUT    /api/v1/settings/plan          { plan } → { success }
  DELETE /api/v1/settings/account       → { success }

Chat:
  POST   /api/v1/chat/send             { agent_id, message, attachments? } → { message_id }
  GET    /api/v1/chat/stream           ?message_id=xxx → SSE token stream

Providers:
  GET    /api/v1/providers/:name/models → { models: string[] }
```

---

## Integration Priority

1. **Auth** (`lib/auth.ts` → use `api.ts` functions) — login, register, token management
2. **Agents** — core CRUD, provider model fetching
3. **Runs** — fetch history, SSE streaming
4. **Schedules** — CRUD + toggle
5. **Tools** — connect/disconnect
6. **Memory** — CRUD
7. **Chat** — send + SSE streaming
8. **Settings** — API keys, password, plan
9. **Dashboard** — stats + recent runs (depends on agents/runs)

---

## Important Notes

- All mock data is currently hardcoded in each page file as `const` arrays (e.g., `mockRuns`, `defaultAgents`, `defaultSchedules`, `defaultFacts`, `defaultTools`). Replace with `useEffect` + API calls or React Query.
- The `getConfiguredProviders()` function in `src/pages/Agents.tsx` is a placeholder — it should call the backend to check which providers have API keys configured.
- SSE streaming is used for run output and chat responses. FastAPI supports SSE via `StreamingResponse`.
- Agent avatars are currently static imports. Backend should store avatar selection and return URLs.
- Theme preference is stored in localStorage (`ocin-theme`) — no backend needed.
- File attachments in chat are temporary (in-memory ObjectURLs). If persistence is needed, add a file upload endpoint.
