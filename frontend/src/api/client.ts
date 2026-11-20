const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}

async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.clone().json();
    return body.detail ?? JSON.stringify(body);
  } catch {
    return (await res.text().catch(() => "")) || fallback;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  // Only set Content-Type when actually sending a body. Setting it on GETs turns
  // them into "non-simple" cross-origin requests, forcing an unnecessary CORS
  // preflight (OPTIONS) before every GET, since the frontend (5173) and backend
  // (8000) are different origins.
  const headers: Record<string, string> = {};
  if (options?.body) headers["Content-Type"] = "application/json";
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

  const res = await fetch(`${API_URL}${path}`, {
    headers,
    ...options,
  });
  if (!res.ok) {
    throw new Error(await errorDetail(res, `${options?.method ?? "GET"} ${path} failed (${res.status})`));
  }
  return res.json() as Promise<T>;
}

export interface ServiceTotal {
  service: string;
  total_usd: number;
}

export interface DailyTotal {
  date: string;
  total_usd: number;
}

export interface Anomaly {
  service: string;
  date: string;
  amount_usd: number;
}

export interface AlertResponse {
  sent: boolean;
  count: number;
  detail: string;
}

export interface AuthUser {
  id: number;
  email: string;
  full_name: string | null;
  slack_webhook_url: string | null;
  onboarding_completed: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface CloudAccountInfo {
  id: number;
  name: string;
  provider: string;
  aws_account_id: string;
  is_connected: boolean;
  aws_region: string | null;
}

export type ChatRole = "user" | "assistant";

export interface Citation {
  ref: string;
  source: string;
  title: string;
  section: string;
  snippet: string;
}

export interface ToolStep {
  id: string;
  name: string;
  args: Record<string, unknown>;
  summary?: string;
  latency_ms?: number;
  refs?: string[];
}

export interface ChatUsage {
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number | null;
  latency_ms: number;
}

export type ChatEvent =
  | ({ type: "tool_call" } & ToolStep)
  | ({ type: "tool_result" } & ToolStep)
  | { type: "token"; text: string }
  | {
      type: "done";
      answer: string;
      citations: Citation[];
      sources: Citation[];
      steps: ToolStep[];
      usage: ChatUsage;
    }
  | { type: "error"; detail: string };

/** POSTs a question and calls onEvent for each Server-Sent Event as it arrives.
 * (EventSource only supports GET, so the stream is read from fetch directly.) */
export async function streamChat(
  question: string,
  history: { role: ChatRole; content: string }[],
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  const res = await fetch(`${API_URL}/api/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ question, history }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(await errorDetail(res, `Chat request failed (${res.status})`));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("\n");
      if (data) onEvent(JSON.parse(data) as ChatEvent);
    }
  }
}

export interface UsageSummary {
  requests: number;
  errors: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  unpriced_requests: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  avg_tool_calls: number;
  cited_answers: number;
}

export interface TraceRow {
  id: number;
  question: string;
  status: string;
  model: string;
  tools: string[];
  citations: number;
  tokens: number;
  cost_usd: number | null;
  latency_ms: number;
  created_at: string;
}

export interface UsageReport {
  summary: UsageSummary;
  tools: { name: string; calls: number }[];
  recent: TraceRow[];
}

export interface KnowledgeStatus {
  chunks: number;
  documents: number;
  documents_on_disk: number;
  sources: string[];
  embedding_model: string;
}

export const api = {
  seedCosts: () => request<{ seeded: boolean; account_id: number; records: number }>(
    "/api/costs/seed",
    { method: "POST" }
  ),
  costsByService: () => request<ServiceTotal[]>("/api/costs/by-service"),
  costsTrend: () => request<DailyTotal[]>("/api/costs/trend"),
  llmUsage: () => request<UsageReport>("/api/llm/usage"),
  knowledgeStatus: () => request<KnowledgeStatus>("/api/knowledge/status"),
  reindexKnowledge: () =>
    request<{ added: number; unchanged: number; removed: number }>("/api/knowledge/reindex", {
      method: "POST",
    }),
  detectAnomalies: () => request<Anomaly[]>("/api/anomalies/detect", { method: "POST" }),
  listAnomalies: () => request<Anomaly[]>("/api/anomalies"),
  sendAlert: () => request<AlertResponse>("/api/anomalies/alert", { method: "POST" }),

  signup: (email: string, password: string, fullName?: string) =>
    request<TokenResponse>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName || null }),
    }),
  login: (email: string, password: string) =>
    request<TokenResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<AuthUser>("/api/auth/me"),
  updateProfile: (payload: {
    full_name?: string;
    slack_webhook_url?: string | null;
    onboarding_completed?: boolean;
  }) =>
    request<AuthUser>("/api/auth/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  myAccount: () => request<CloudAccountInfo | null>("/api/accounts/me"),
  connectAws: (accessKeyId: string, secretAccessKey: string, region: string) =>
    request<CloudAccountInfo>("/api/accounts/connect-aws", {
      method: "POST",
      body: JSON.stringify({
        access_key_id: accessKeyId,
        secret_access_key: secretAccessKey,
        region,
      }),
    }),
  syncAwsCosts: () =>
    request<{ synced_records: number }>("/api/accounts/sync", { method: "POST" }),
};
