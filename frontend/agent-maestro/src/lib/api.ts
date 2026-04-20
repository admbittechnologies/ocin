/**
 * ============================================================================
 * OCIN API Service — FastAPI Backend Integration
 * ============================================================================
 *
 * Base URL comes from environment: VITE_API_BASE_URL
 * Auth: Bearer token from localStorage (key: "ocin_jwt_token")
 *
 * FastAPI backend structure:
 *   /api/v1/auth/login          POST
 *   /api/v1/auth/register       POST
 *   /api/v1/auth/forgot-password POST
 *   /api/v1/auth/change-password POST
 *   /api/v1/auth/me              GET
 *   /api/v1/agents               GET, POST
 *   /api/v1/agents/:id           GET, PUT, DELETE
 *   /api/v1/runs                 GET
 *   /api/v1/runs/:id             GET
 *   /api/v1/runs/:id/stream      WebSocket
 *   /api/v1/runs/trigger          POST
 *   /api/v1/schedules            GET, POST
 *   /api/v1/schedules/:id        PUT, DELETE
 *   /api/v1/tools                GET
 *   /api/v1/tools/:id/connect    POST
 *   /api/v1/tools/:id/disconnect POST
 *   /api/v1/memory               GET, POST
 *   /api/v1/memory/:id           PUT, DELETE
 *   /api/v1/settings/api-keys    GET, PUT
 *   /api/v1/settings/plan        PUT
 *   /api/v1/settings/account     DELETE
 *   /api/v1/dashboard/stats      GET
 *   /api/v1/dashboard/recent-runs GET
 *   /api/v1/chat/send            POST
 *   /api/v1/chat/stream           WebSocket
 *   /api/v1/providers/:name/models GET
 * ============================================================================
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
const WS_BASE = API_BASE.replace('http://', 'ws://').replace('https://', 'wss://');

function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem("ocin_jwt_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// User-friendly error messages for common HTTP status codes
const STATUS_MESSAGES: Record<number, string> = {
  400: "Invalid request. Please check your input.",
  401: "Invalid email or password.",
  403: "You don't have permission to perform this action.",
  404: "The requested resource was not found.",
  409: "A resource with this information already exists.",
  422: "Invalid input. Please check your data.",
  429: "Too many requests. Please try again later.",
  500: "Something went wrong on our end. Please try again.",
  503: "Service temporarily unavailable. Please try again later.",
};

function extractErrorMessage(error: unknown): string | null {
  if (typeof error === 'string') return error;
  if (!error || typeof error !== 'object') return null;

  const err = error as Record<string, unknown>;

  // FastAPI: { detail: "message" }
  if (typeof err.detail === 'string') return err.detail;

  // FastAPI validation errors: { detail: [{ msg: "...", type: "...", loc: [...] }] }
  if (Array.isArray(err.detail) && err.detail.length > 0) {
    const firstError = err.detail[0] as { msg?: string } | undefined;
    if (firstError?.msg) return firstError.msg;
  }

  // Alternative format: { message: "message" }
  if (typeof err.message === 'string') return err.message;

  // Fallback: look for any string value in common error fields
  for (const key of ['error', 'error_description', 'msg']) {
    if (typeof err[key] === 'string') return err[key] as string;
  }

  return null;
}

async function handleResponse(res: Response): Promise<unknown> {
  if (!res.ok) {
    const contentType = res.headers.get("content-type");
    let errorMessage: string;

    if (contentType?.includes("application/json")) {
      const error = await res.json();
      const extracted = extractErrorMessage(error);
      errorMessage = extracted || STATUS_MESSAGES[res.status] || `Request failed: ${res.status}`;
    } else {
      errorMessage = STATUS_MESSAGES[res.status] || `Request failed: ${res.status} ${res.statusText}`;
    }

    throw new Error(errorMessage);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// AUTH
// ---------------------------------------------------------------------------
// FastAPI: POST /api/v1/auth/login
// Body: { email: string, password: string }
// Returns: { access_token: string, user: { email, plan } }
export async function apiLogin(email: string, password: string) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return await handleResponse(res) as { access_token: string; user: { email: string; plan: string } };
}

// FastAPI: POST /api/v1/auth/register
// Body: { email, password, plan }
// Returns: { access_token, user }
export async function apiRegister(email: string, password: string, plan: string) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, plan }),
  });
  return await handleResponse(res) as { access_token: string; user: { email: string; plan: string } };
}

// FastAPI: POST /api/v1/auth/forgot-password
// Body: { email }
export async function apiForgotPassword(email: string) {
  const res = await fetch(`${API_BASE}/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return await handleResponse(res);
}

// FastAPI: POST /api/v1/auth/change-password
// Body: { current_password, new_password }
// Headers: Authorization Bearer
export async function apiChangePassword(currentPassword: string, newPassword: string) {
  const res = await fetch(`${API_BASE}/auth/change-password`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  return await handleResponse(res);
}

// FastAPI: GET /api/v1/auth/me
// Headers: Authorization Bearer
export async function apiGetCurrentUser() {
  const res = await fetch(`${API_BASE}/auth/me`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as { email: string; plan: string };
}

// ---------------------------------------------------------------------------
// DASHBOARD
// ---------------------------------------------------------------------------

// FastAPI: GET /api/v1/dashboard/stats
// Returns: { active_agents, runs_today, schedules_active, tools_connected }
export async function apiGetDashboardStats() {
  const res = await fetch(`${API_BASE}/dashboard/stats`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as {
    active_agents: number;
    runs_today: number;
    schedules_active: number;
    tools_connected: number;
  };
}

// FastAPI: GET /api/v1/dashboard/recent-runs?limit=10
// Returns: Run[]
export async function apiGetRecentRuns(limit = 10) {
  const res = await fetch(`${API_BASE}/dashboard/recent-runs?limit=${limit}`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as Array<{
    id: string;
    agent: string;
    agent_id?: string;
    status: string;
    started: string;
    duration: string;
    schedule_id?: string | null;
    schedule_name?: string | null;
  }>;
}

// ---------------------------------------------------------------------------
// AGENTS
// ---------------------------------------------------------------------------

// FastAPI: GET /api/v1/agents
// Returns: Agent[] with snake_case fields to match backend response
export async function apiGetAgents() {
  const res = await fetch(`${API_BASE}/agents`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as Array<{
    id: string;
    name: string;
    description: string;
    avatar: string;
    user_id: string;
    role: string;
    provider: string;
    model_id: string;
    temperature: number;
    system_prompt: string;
    is_active: boolean;
    tools: string[];
  }>;
}

// FastAPI: GET /api/v1/agents/:id
// Returns: Agent with avatar field (slug like "avatar-07")
export async function apiGetAgent(agentId: string) {
  const res = await fetch(`${API_BASE}/agents/${agentId}`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to fetch agent ${agentId}`);
  return await handleResponse(res) as {
    id: string;
    name: string;
    description: string;
    avatar: string;
    user_id: string;
    role: string;
    provider: string;
    model_id: string;
    temperature: number;
    system_prompt: string;
    is_active: boolean;
    tools: string[];
  };
}

// FastAPI: POST /api/v1/agents
// Body: { name, description, avatar, role, provider, model_id, temperature, system_prompt, tools }
export async function apiCreateAgent(agent: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/agents`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(agent),
  });
  return await handleResponse(res) as { id: string } & Record<string, unknown>;
}

// FastAPI: PUT /api/v1/agents/:id
export async function apiUpdateAgent(id: string, agent: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/agents/${id}`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify(agent),
  });
  return await handleResponse(res) as { id: string } & Record<string, unknown>;
}

// FastAPI: DELETE /api/v1/agents/:id
export async function apiDeleteAgent(id: string) {
  const res = await fetch(`${API_BASE}/agents/${id}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res);
}

// FastAPI: PUT /api/v1/agents/:id/toggle
// Body: { active: boolean }
export async function apiToggleAgent(id: string, active: boolean) {
  const res = await fetch(`${API_BASE}/agents/${id}/toggle`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify({ active }),
  });
  return await handleResponse(res);
}

// ---------------------------------------------------------------------------
// RUNS
// ---------------------------------------------------------------------------

// FastAPI: GET /api/v1/runs
// Returns: Run[]
export async function apiGetRuns() {
  const res = await fetch(`${API_BASE}/runs`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as Array<{
    id: string;
    agent: string;
    trigger: string;
    status: string;
    started: string;
    duration: string;
    cost: string;
  }>;
}

// FastAPI: GET /api/v1/runs/:id
export async function apiGetRun(id: string) {
  const res = await fetch(`${API_BASE}/runs/${id}`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  if (res.status === 404) return null;
  return await handleResponse(res) as {
    id: string;
    agent: string;
    trigger: string;
    status: string;
    started: string;
    duration: string;
    cost: string;
    input?: string;
    output?: string;
    error?: string;
    tokens?: number;
    toolCalls?: { name: string; input: string; output: string; duration: string }[];
  } | null;
}

// FastAPI: SSE http://localhost:8000/api/v1/runs/:id/stream?token={jwt}
export function apiStreamRun(id: string, onChunk: (data: unknown) => void, onDone: () => void): () => void {
  const token = localStorage.getItem("ocin_jwt_token");
  const esUrl = `${API_BASE}/runs/${id}/stream?token=${token}`;

  const es = new EventSource(esUrl);

  // Backend sends named SSE events:
  //   event: connected  → data: {"type": "connected"}
  //   event: token     → data: {"token": "H"}
  //   event: done      → data: {"type": "done", "run_id": "...", "status": "success"}

  // Listen for "connected" event
  es.addEventListener('connected', (e) => {
    console.log("SSE connected:", e.data);
  });

  // Listen for "token" events
  es.addEventListener('token', (e) => {
    try {
      const data = JSON.parse(e.data) as Record<string, unknown>;
      if (data.token && typeof data.token === 'string') {
        onChunk(data.token);
      }
    } catch (err) {
      console.error("SSE token parse error:", err, "raw data:", e.data);
    }
  });

  // Listen for "done" event
  es.addEventListener('done', (e) => {
    try {
      const data = JSON.parse(e.data) as Record<string, unknown>;
      console.log("SSE done:", data);
    } catch (err) {
      console.error("SSE done parse error:", err, "raw data:", e.data);
    }
    es.close();
    onDone();
  });

  // Handle connection errors
  es.onerror = (event) => {
    console.error("SSE connection error:", event);
    es.close();
    onDone();
  };

  return () => {
    es.close();
  };
}

// FastAPI: POST /api/v1/runs/trigger
// Body: { agent_id }
export async function apiTriggerRun(agentId: string) {
  const res = await fetch(`${API_BASE}/runs/trigger`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ agent_id: agentId, input: "" }),
  });
  return await handleResponse(res) as { run_id: string };
}

// ---------------------------------------------------------------------------
// SCHEDULES
// ---------------------------------------------------------------------------

// FastAPI: GET /api/v1/schedules
// Returns: Schedule[]
export async function apiGetSchedules() {
  const res = await fetch(`${API_BASE}/schedules`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as Array<{
    id: string;
    label: string;
    agentName: string;
    triggerType: string;
    nextRun?: string;
    lastRun?: string;
    active: boolean;
  }>;
}

// FastAPI: POST /api/v1/schedules
// Body: { label, agent_name, trigger_type, ... }
export async function apiCreateSchedule(schedule: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/schedules`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(schedule),
  });
  return await handleResponse(res) as { id: string } & Record<string, unknown>;
}

// FastAPI: PUT /api/v1/schedules/:id
export async function apiUpdateSchedule(id: string, schedule: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/schedules/${id}`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify(schedule),
  });
  return await handleResponse(res) as { id: string } & Record<string, unknown>;
}

// FastAPI: DELETE /api/v1/schedules/:id
export async function apiDeleteSchedule(id: string) {
  const res = await fetch(`${API_BASE}/schedules/${id}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res);
}

// FastAPI: PUT /api/v1/schedules/:id/toggle
// Body: { active: boolean }
export async function apiToggleSchedule(id: string, active: boolean) {
  const res = await fetch(`${API_BASE}/schedules/${id}/toggle`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify({ active }),
  });
  return await handleResponse(res);
}

// ---------------------------------------------------------------------------
// TOOLS
// ---------------------------------------------------------------------------

// FastAPI: GET /api/v1/tools
// Returns: Tool[]
export async function apiGetTools() {
  const res = await fetch(`${API_BASE}/tools`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as Array<{
    id: string;
    name: string;
    description: string;
    type: string;
    source?: string;
    source_key?: string | null;
    is_active?: boolean;
    configured?: boolean;
    // Legacy format - kept for compatibility
    connected?: boolean;
    usedBy?: string[];
  }>;
}

// FastAPI: POST /api/v1/tools
// Body: { name, source, source_key }
export async function apiCreateTool(name: string, source: string, sourceKey?: string) {
  const res = await fetch(`${API_BASE}/tools`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ name, source, source_key: sourceKey }),
  });
  return await handleResponse(res) as { id: string; name: string; source: string };
}

// FastAPI: POST /api/v1/tools/:id/connect
// Body: { api_token?, actor_id? } (depends on tool type)
export async function apiConnectTool(toolId: string, credentials: Record<string, string>) {
  const res = await fetch(`${API_BASE}/tools/${toolId}/connect`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(credentials),
  });
  return await handleResponse(res);
}

// FastAPI: POST /api/v1/tools/:id/disconnect
export async function apiDisconnectTool(toolId: string) {
  const res = await fetch(`${API_BASE}/tools/${toolId}/disconnect`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res);
}

// ---------------------------------------------------------------------------
// MEMORY
// ---------------------------------------------------------------------------

// FastAPI: GET /api/v1/memory
// Returns: Fact[]
export async function apiGetMemoryFacts() {
  const res = await fetch(`${API_BASE}/memory`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as Array<{
    id: string;
    key: string;
    value: string;
  }>;
}

// FastAPI: GET /api/v1/memory/{agent_id}
// Returns: [{key, value, updated_at}, ...]
export async function apiGetAgentMemory(agentId: string) {
  const res = await fetch(`${API_BASE}/memory/${agentId}`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as Array<{
    key: string;
    value: string;
    updated_at: string;
  }>;
}

// FastAPI: POST /api/v1/memory
// Body: { key, value }
export async function apiCreateMemoryFact(key: string, value: string) {
  const res = await fetch(`${API_BASE}/memory`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ key, value }),
  });
  return await handleResponse(res) as { id: string; key: string; value: string };
}

// FastAPI: PUT /api/v1/memory/{agent_id}/{key}
// Body is a plain string (the value)
export async function apiSetAgentMemory(agentId: string, key: string, value: string) {
  const res = await fetch(`${API_BASE}/memory/${agentId}/${key}`, {
    method: "PUT",
    headers: {
      "Content-Type": "text/plain",
      ...getAuthHeaders(),
    },
    body: value,
  });
  return await handleResponse(res);
}

// FastAPI: PUT /api/v1/memory/:id
// Body: { value }
export async function apiUpdateMemoryFact(id: string, value: string) {
  const res = await fetch(`${API_BASE}/memory/${id}`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify({ value }),
  });
  return await handleResponse(res);
}

// FastAPI: DELETE /api/v1/memory/{agent_id}/{key}
export async function apiDeleteAgentMemory(agentId: string, key: string) {
  const res = await fetch(`${API_BASE}/memory/${agentId}/${key}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res);
}

// FastAPI: DELETE /api/v1/memory/:id
export async function apiDeleteMemoryFact(id: string) {
  const res = await fetch(`${API_BASE}/memory/${id}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res);
}

// ---------------------------------------------------------------------------
// SETTINGS
// ---------------------------------------------------------------------------

// FastAPI: GET /api/v1/settings/api-keys
// Returns: { provider: "masked_key" } (keys are masked, e.g. "sk-...abc")
export async function apiGetApiKeys() {
  const res = await fetch(`${API_BASE}/settings/api-keys`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as Record<string, string>;
}

// FastAPI: PUT /api/v1/settings/api-keys
// Body: { provider, api_key }
export async function apiSaveApiKey(provider: string, apiKey: string) {
  const res = await fetch(`${API_BASE}/settings/api-keys`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify({ provider, api_key: apiKey }),
  });
  return await handleResponse(res);
}

export async function apiDeleteApiKey(provider: string) {
  const res = await fetch(`${API_BASE}/settings/api-keys/${provider.toLowerCase()}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res);
}

// FastAPI: PUT /api/v1/settings/plan
// Body: { plan: "free" | "pro" | "business" }
export async function apiUpdatePlan(plan: string) {
  const res = await fetch(`${API_BASE}/settings/plan`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify({ plan }),
  });
  return await handleResponse(res);
}

// FastAPI: DELETE /api/v1/settings/account
export async function apiDeleteAccount() {
  const res = await fetch(`${API_BASE}/settings/account`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res);
}

// ---------------------------------------------------------------------------
// CHAT
// ---------------------------------------------------------------------------

// FastAPI: POST /api/v1/chat/send
// Body: { agent_id, message, thread_id?, attachments?: { name, type, data_base64 }[] }
export async function apiSendChatMessage(
  agentId: string,
  message: string,
  threadId?: string,
  attachments?: { name: string; type: string; dataBase64: string }[]
) {
  const res = await fetch(`${API_BASE}/chat/send`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ agent_id: agentId, message, thread_id: threadId || null, attachments }),
  });
  return await handleResponse(res) as { message_id: string; thread_id?: string };
}

// FastAPI: GET /api/v1/chat/threads
export async function apiGetThreads(agentId?: string) {
  const url = agentId
    ? `${API_BASE}/chat/threads?agent_id=${agentId}`
    : `${API_BASE}/chat/threads`;
  const res = await fetch(url, { headers: getAuthHeaders() });
  const data = await handleResponse(res);
  // Backend returns { threads: [], total: 0 } — destructure to get threads array
  const threads = data.threads || [];
  return threads as Array<{
    id: string;
    title: string;
    agent_id: string;
    agent_name: string;
    last_message_at: string;
  }>;
}

// FastAPI: GET /api/v1/chat/threads/{id}/messages
// Backend returns { messages: [] } — wrapper object with messages array
export async function apiGetThreadMessages(threadId: string) {
  const res = await fetch(`${API_BASE}/chat/threads/${threadId}/messages`, {
    headers: getAuthHeaders(),
  });
  const data = await handleResponse(res);
  return { messages: data.messages || [] } as { messages: Array<{
    id: string;
    role: "user" | "assistant";
    content: string;
    agent_id?: string;
    agent_name?: string;
    created_at: string;
  }>};
}

// FastAPI: DELETE /api/v1/chat/threads/{id}
export async function apiDeleteThread(threadId: string) {
  const res = await fetch(`${API_BASE}/chat/threads/${threadId}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res);
}

// FastAPI: SSE http://localhost:8000/api/v1/chat/stream?message_id=xxx&token={jwt}
export function apiStreamChatResponse(
  messageId: string,
  onToken: (data: unknown) => void,
  onDone: () => void
): () => void {
  const token = localStorage.getItem("ocin_jwt_token");
  const esUrl = `${API_BASE}/chat/stream?message_id=${messageId}&token=${token}`;

  let es: EventSource | null = new EventSource(esUrl);
  let doneReceived = false;
  let retryCount = 0;
  const MAX_RETRIES = 3;
  const RETRY_DELAY = 1000; // ms

  // Backend sends named SSE events:
  //   event: connected  → data: {"type": "connected"}
  //   event: token     → data: {"token": "H"}
  //   event: done      → data: {"type": "done", "run_id": "...", "status": "success"}

  const reconnect = () => {
    if (retryCount >= MAX_RETRIES) {
      console.error("SSE max retries reached, giving up");
      onDone();
      return;
    }

    retryCount++;
    console.log(`SSE reconnecting (attempt ${retryCount}/${MAX_RETRIES})...`);

    // Close previous connection
    if (es) {
      es.close();
    }

    // Create new connection with increased timeout
    es = new EventSource(esUrl);
    setupEventListeners(es);
  };

  const setupEventListeners = (eventSource: EventSource) => {
    // Listen for "connected" event
    eventSource.addEventListener('connected', (e) => {
      console.log("SSE connected:", e.data);
      retryCount = 0; // Reset retry count on successful connection
    });

    // Listen for "token" events
    eventSource.addEventListener('token', (e) => {
      try {
        const data = JSON.parse(e.data) as Record<string, unknown>;
        if (data.token && typeof data.token === 'string') {
          onToken(data.token);
        }
      } catch (err) {
        console.error("SSE token parse error:", err, "raw data:", e.data);
      }
    });

    // Listen for "done" event
    eventSource.addEventListener('done', (e) => {
      try {
        const data = JSON.parse(e.data) as Record<string, unknown>;
        console.log("SSE done:", data);
        // Process any final content from "done" event before closing
        if (typeof data.content === 'string' && data.content) {
          // Backend may send final content in "done" event
          // Emit it through onToken callback for consistency
          onToken(data.content);
        }
      } catch (err) {
        console.error("SSE done parse error:", err, "raw data:", e.data);
      }
      doneReceived = true;
      eventSource.close();
      onDone();
    });

    // Handle connection errors - only close if done was received
    eventSource.onerror = (event) => {
      console.error("SSE connection error:", event);

      if (doneReceived) {
        // Already got done event, just clean up
        eventSource.close();
        onDone();
      } else {
        // Connection dropped before done - try to reconnect
        console.log("SSE connection dropped before done, reconnecting...");
        setTimeout(reconnect, RETRY_DELAY);
      }
    };
  };

  setupEventListeners(es);

  return () => {
    if (es) {
      es.close();
    }
  };
}

// ---------------------------------------------------------------------------
// PROVIDERS / MODELS
// ---------------------------------------------------------------------------

// FastAPI: GET /api/v1/providers/:name/models
// Returns: { models: string[] }
// Optional: Pass apiKey to use provider's own API for introspection
export async function apiGetProviderModels(providerName: string, apiKey?: string) {
  const token = apiKey ? apiKey : localStorage.getItem("ocin_jwt_token");

  const headers = token
    ? { "Content-Type": "application/json", Authorization: `Bearer ${token}` }
    : getAuthHeaders();

  const res = await fetch(`${API_BASE}/providers/${providerName}/models`, {
    method: "GET",
    headers,
  });

  return await handleResponse(res) as { models: string[] };
}

// ---------------------------------------------------------------------------
// APPROVALS
// ---------------------------------------------------------------------------

export interface Approval {
  id: string;
  user_id: string;
  agent_id: string;
  agent_name: string;
  run_id: string;
  schedule_id: string | null;
  kind: string;
  title: string;
  description: string;
  payload: Record<string, any>;
  status: "pending" | "approved" | "rejected" | "expired";
  resolved_at: string | null;
  resolution_note: string | null;
  expires_at: string | null;
  created_at: string;
}

// FastAPI: GET /api/v1/approvals
// Query: ?status=pending|approved|rejected
// Returns: Approval[]
export async function apiGetApprovals(status?: string): Promise<Approval[]> {
  const url = status
    ? `${API_BASE}/approvals?status=${status}`
    : `${API_BASE}/approvals`;
  const res = await fetch(url, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  const data = await handleResponse(res);
  return data.approvals ?? [];
}

// FastAPI: GET /api/v1/approvals/{id}
export async function apiGetApproval(id: string): Promise<Approval> {
  const res = await fetch(`${API_BASE}/approvals/${id}`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  if (res.status === 404) return null;
  return await handleResponse(res) as Approval;
}

// FastAPI: POST /api/v1/approvals/{id}/approve
// Body: {note?: string}
export async function apiApproveApproval(id: string, note?: string): Promise<Approval> {
  const res = await fetch(`${API_BASE}/approvals/${id}/approve`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ note }),
  });
  return await handleResponse(res) as Approval;
}

// FastAPI: POST /api/v1/approvals/{id}/reject
// Body: {note?: string}
export async function apiRejectApproval(id: string, note?: string): Promise<Approval> {
  const res = await fetch(`${API_BASE}/approvals/${id}/reject`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ note }),
  });
  return await handleResponse(res) as Approval;
}

// FastAPI: GET /api/v1/approvals/pending/count
export async function apiGetPendingApprovalsCount(): Promise<{ count: number }> {
  const res = await fetch(`${API_BASE}/approvals/pending/count`, {
    method: "GET",
    headers: getAuthHeaders(),
  });
  return await handleResponse(res) as { count: number };
}
