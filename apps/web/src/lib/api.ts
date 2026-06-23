/**
 * Typed API client. All HTTP calls to the backend go through here.
 *
 * - Injects `Authorization: Bearer <access>` from the auth store.
 * - On 401 with an expired access token, attempts a single refresh + retry.
 * - Maps the backend's structured error envelope to ApiError.
 */
import { useAuthStore } from "@/stores/auth-store";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface ApiErrorPayload {
  error: { code: string; message: string; details?: Record<string, unknown> };
  request_id?: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: Json;
  headers?: Record<string, string>;
  auth?: boolean; // default true
  signal?: AbortSignal;
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const refresh = useAuthStore.getState().refreshToken;
    if (!refresh) return false;
    const res = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) {
      useAuthStore.getState().clear();
      return false;
    }
    const data = await res.json();
    useAuthStore.getState().setTokens({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      accessExpiresAt: data.access_token_expires_at,
      refreshExpiresAt: data.refresh_token_expires_at,
    });
    return true;
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function rawRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {}, auth = true, signal } = opts;
  const finalHeaders: Record<string, string> = {
    accept: "application/json",
    ...headers,
  };
  if (body !== undefined) finalHeaders["content-type"] = "application/json";
  if (auth) {
    const access = useAuthStore.getState().accessToken;
    if (access) finalHeaders.authorization = `Bearer ${access}`;
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: finalHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  if (res.status === 204) return undefined as T;

  let payload: unknown = null;
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) payload = await res.json();
  else payload = await res.text();

  if (!res.ok) {
    const env = payload as ApiErrorPayload;
    throw new ApiError(
      res.status,
      env?.error?.code ?? "http_error",
      env?.error?.message ?? `HTTP ${res.status}`,
      env?.error?.details ?? {},
      env?.request_id,
    );
  }
  return payload as T;
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  try {
    return await rawRequest<T>(path, opts);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401 && opts.auth !== false) {
      const refreshed = await tryRefresh();
      if (refreshed) return rawRequest<T>(path, opts);
    }
    throw e;
  }
}

// ---------- typed surface ----------
export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  updated_at: string;
  roles: { id: string; name: string; description: string | null }[];
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  access_token_expires_at: string;
  refresh_token_expires_at: string;
}

export interface LoginResponse {
  user: User;
  tokens: TokenPair;
}

// ---------- repositories (Phase 2) ----------
export interface Repository {
  id: string;
  owner_id: string;
  name: string;
  source_type: "git" | "local" | "github";
  url: string;
  default_branch: string;
  status: "new" | "ingesting" | "ready" | "failed";
  last_indexed_at: string | null;
  stats: Record<string, unknown> | null;
  qdrant_collection: string | null;
  created_at: string;
  updated_at: string;
}

export interface IngestJob {
  id: string;
  repository_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  files_seen: number;
  files_indexed: number;
  chunks_indexed: number;
  bytes_indexed: number;
  celery_task_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepositoryFile {
  id: string;
  path: string;
  language: string | null;
  size_bytes: number;
  lines: number;
  chunk_count: number;
}

export interface CodeChunkPreview {
  id: string;
  start_line: number;
  end_line: number;
  token_count: number;
  language: string | null;
  content: string;
}

// ---------- search (Phase 3) ----------
export type SearchMode = "hybrid" | "dense" | "lexical";

export interface SearchHit {
  chunk_id: string;
  repository_id: string;
  file_id: string;
  file_path: string;
  language: string | null;
  start_line: number;
  end_line: number;
  token_count: number;
  score: number;
  dense_score: number | null;
  lexical_score: number | null;
  rerank_score: number | null;
  content: string;
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  reranked: boolean;
  took_ms: number;
  hits: SearchHit[];
}

export interface ContextFile {
  repository_id: string;
  file_id: string;
  file_path: string;
  language: string | null;
  chunks: SearchHit[];
}

export interface ContextResponse {
  query: string;
  total_tokens: number;
  max_tokens: number;
  truncated: boolean;
  files: ContextFile[];
}

// ---------- chat (Phase 4) ----------
export type LLMProviderName = "ollama" | "openai";
export type MessageRole = "system" | "user" | "assistant" | "tool";

export interface Conversation {
  id: string;
  owner_id: string;
  title: string;
  repository_ids: string[];
  llm_provider: string;
  llm_model: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview: string | null;
}

export interface ChatCitation {
  repository_id: string;
  file_id: string;
  file_path: string;
  start_line: number;
  end_line: number;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  tool_calls: Array<Record<string, unknown>> | null;
  tool_call_id: string | null;
  citations: ChatCitation[] | null;
  token_count: number;
  created_at: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: ChatMessage[];
}

export type WsEvent =
  | { type: "token"; delta: string }
  | {
      type: "tool_call_start";
      name: string;
      arguments: Record<string, unknown>;
      call_id: string;
    }
  | { type: "tool_call_result"; call_id: string; summary: string }
  | { type: "citations"; citations: ChatCitation[] }
  | { type: "done"; message_id: string }
  | { type: "error"; message: string };

// ---------- memory (Phase 7) ----------
export type MemoryScope = "user" | "project" | "conversation";

export interface Memory {
  id: string;
  owner_id: string;
  scope: MemoryScope;
  repository_id: string | null;
  conversation_id: string | null;
  content: string;
  source: "explicit" | "extracted";
  importance: number;
  access_count: number;
  last_accessed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepoMetrics {
  total_files: number;
  total_lines: number;
  total_bytes: number;
  languages: { language: string; files: number; lines: number }[];
  largest_files: { path: string; lines: number; size_bytes: number }[];
  test_files: number;
  source_files: number;
}

export interface SimilarMatch {
  file_id: string;
  file_path: string;
  language: string | null;
  start_line: number;
  end_line: number;
  score: number;
  content: string;
}

export interface AgentStep {
  title: string;
  finding: string;
  citations: ChatCitation[];
  error: string | null;
}

export interface AgentReview {
  verdict: string;
  notes: string;
}

export interface AgentRunResponse {
  task: string;
  plan: string[];
  steps: AgentStep[];
  synthesis: string;
  review: AgentReview | null;
  model: string;
}

export const api = {
  // ---- auth ----
  register: (email: string, password: string, full_name?: string) =>
    apiRequest<User>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password, full_name },
      auth: false,
    }),

  login: (email: string, password: string) =>
    apiRequest<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    }),

  logout: (refresh_token: string) =>
    apiRequest<void>("/api/v1/auth/logout", {
      method: "POST",
      body: { refresh_token },
    }),

  me: () => apiRequest<User>("/api/v1/users/me"),

  updateProfile: (data: { full_name?: string; password?: string }) =>
    apiRequest<User>("/api/v1/users/me", { method: "PATCH", body: data }),

  ready: () =>
    apiRequest<{ status: string; checks: Record<string, string> }>("/api/v1/ready", {
      auth: false,
    }),

  // ---- repositories ----
  listRepos: () => apiRequest<Repository[]>("/api/v1/repositories"),

  createRepo: (data: {
    name: string;
    url: string;
    source_type?: "git" | "local" | "github";
    default_branch?: string;
  }) =>
    apiRequest<Repository>("/api/v1/repositories", {
      method: "POST",
      body: { source_type: "git", default_branch: "main", ...data },
    }),

  getRepo: (id: string) => apiRequest<Repository>(`/api/v1/repositories/${id}`),

  deleteRepo: (id: string) =>
    apiRequest<void>(`/api/v1/repositories/${id}`, { method: "DELETE" }),

  ingestRepo: (id: string) =>
    apiRequest<IngestJob>(`/api/v1/repositories/${id}/ingest`, { method: "POST" }),

  listJobs: (id: string) =>
    apiRequest<IngestJob[]>(`/api/v1/repositories/${id}/jobs`),

  getJob: (repoId: string, jobId: string) =>
    apiRequest<IngestJob>(`/api/v1/repositories/${repoId}/jobs/${jobId}`),

  listFiles: (repoId: string) =>
    apiRequest<RepositoryFile[]>(`/api/v1/repositories/${repoId}/files`),

  listFileChunks: (repoId: string, fileId: string) =>
    apiRequest<CodeChunkPreview[]>(
      `/api/v1/repositories/${repoId}/files/${fileId}/chunks`,
    ),

  search: (body: {
    query: string;
    repository_ids?: string[];
    k?: number;
    mode?: SearchMode;
    rerank?: boolean;
  }) =>
    apiRequest<SearchResponse>("/api/v1/search", {
      method: "POST",
      body: {
        repository_ids: [],
        k: 10,
        mode: "hybrid" as SearchMode,
        rerank: true,
        ...body,
      },
    }),

  buildContext: (body: {
    query: string;
    repository_ids?: string[];
    max_tokens?: number;
    k?: number;
    rerank?: boolean;
  }) =>
    apiRequest<ContextResponse>("/api/v1/context/build", {
      method: "POST",
      body: {
        repository_ids: [],
        max_tokens: 4096,
        k: 30,
        rerank: true,
        ...body,
      },
    }),

  // SSE URL (consumer opens an EventSource with auth token in the URL or
  // via a same-origin cookie; for now we expose the path + token).
  jobEventsUrl: (repoId: string, jobId: string, token: string) =>
    `${BASE_URL}/api/v1/repositories/${repoId}/jobs/${jobId}/events?access_token=${encodeURIComponent(token)}`,

  // ---- chat ----
  listConversations: () =>
    apiRequest<Conversation[]>("/api/v1/conversations"),

  createConversation: (body: {
    title?: string;
    repository_ids?: string[];
    llm_provider?: LLMProviderName;
    llm_model?: string;
  } = {}) =>
    apiRequest<Conversation>("/api/v1/conversations", {
      method: "POST",
      body,
    }),

  getConversation: (id: string) =>
    apiRequest<ConversationDetail>(`/api/v1/conversations/${id}`),

  renameConversation: (id: string, title: string) =>
    apiRequest<Conversation>(`/api/v1/conversations/${id}`, {
      method: "PATCH",
      body: { title },
    }),

  deleteConversation: (id: string) =>
    apiRequest<void>(`/api/v1/conversations/${id}`, { method: "DELETE" }),

  /** Build a WebSocket URL for streaming a chat reply. */
  conversationWsUrl: (id: string, token: string) => {
    const base = BASE_URL.replace(/^http/, "ws");
    return `${base}/api/v1/conversations/${id}/ws?access_token=${encodeURIComponent(token)}`;
  },

  // ---- memory ----
  listMemories: (scope?: MemoryScope) =>
    apiRequest<Memory[]>(
      `/api/v1/memories${scope ? `?scope=${scope}` : ""}`,
    ),

  createMemory: (body: {
    content: string;
    scope?: MemoryScope;
    repository_id?: string;
    importance?: number;
  }) =>
    apiRequest<Memory>("/api/v1/memories", {
      method: "POST",
      body: { scope: "user" as MemoryScope, ...body },
    }),

  deleteMemory: (id: string) =>
    apiRequest<void>(`/api/v1/memories/${id}`, { method: "DELETE" }),

  // ---- sandbox (Phase 5) ----
  classifyCommand: (command: string) =>
    apiRequest<{ verdict: "allow" | "approval" | "blocked"; reason: string }>(
      "/api/v1/sandbox/classify",
      { method: "POST", body: { command } },
    ),

  sandboxWsUrl: (token: string) => {
    const base = BASE_URL.replace(/^http/, "ws");
    return `${base}/api/v1/sandbox/ws?access_token=${encodeURIComponent(token)}`;
  },

  // ---- github (Phase 6) ----
  githubStatus: () =>
    apiRequest<{ configured: boolean; login: string | null; name: string | null }>(
      "/api/v1/github/status",
    ),

  githubCreatePR: (body: {
    owner: string;
    repo: string;
    base?: string;
    branch: string;
    title: string;
    body?: string;
    draft?: boolean;
    changes: { path: string; content: string }[];
  }) =>
    apiRequest<{ number: number; url: string; branch: string }>(
      "/api/v1/github/pulls",
      { method: "POST", body },
    ),

  githubReviewPR: (body: {
    owner: string;
    repo: string;
    number: number;
    post_comment?: boolean;
  }) =>
    apiRequest<{ review: string; comment_url: string | null; diff_truncated: boolean }>(
      "/api/v1/github/review",
      { method: "POST", body },
    ),

  // ---- repo insights ----
  repoMetrics: (id: string) =>
    apiRequest<RepoMetrics>(`/api/v1/insights/${id}/metrics`),
  repoSimilar: (id: string, fileId: string) =>
    apiRequest<{ matches: SimilarMatch[] }>(
      `/api/v1/insights/${id}/files/${fileId}/similar`,
    ),
  repoDiagram: (id: string) =>
    apiRequest<{ mermaid: string }>(`/api/v1/insights/${id}/diagram`, { method: "POST" }),
  repoDocs: (id: string) =>
    apiRequest<{ markdown: string }>(`/api/v1/insights/${id}/docs`, { method: "POST" }),
  repoCodemap: (id: string) =>
    apiRequest<{ mermaid: string }>(`/api/v1/insights/${id}/codemap`),

  // ---- multi-agent pipeline ----
  runAgents: (body: {
    task: string;
    repository_ids?: string[];
    max_steps?: number;
    model?: string;
    review?: boolean;
  }) =>
    apiRequest<AgentRunResponse>("/api/v1/agents/run", { method: "POST", body }),
};

export type SandboxEvent =
  | { kind: "classify"; verdict: "allow" | "approval" | "blocked"; reason: string }
  | { kind: "needs_approval"; text: string }
  | { kind: "status"; text: string }
  | { kind: "output"; text: string }
  | { kind: "exit"; exit_code: number }
  | { kind: "error"; text: string };
