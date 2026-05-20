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

  // SSE URL (consumer opens an EventSource with auth token in the URL or
  // via a same-origin cookie; for now we expose the path + token).
  jobEventsUrl: (repoId: string, jobId: string, token: string) =>
    `${BASE_URL}/api/v1/repositories/${repoId}/jobs/${jobId}/events?access_token=${encodeURIComponent(token)}`,
};
