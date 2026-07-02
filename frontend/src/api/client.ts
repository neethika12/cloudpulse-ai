const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
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
    let detail = "";
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new Error(detail || `${options?.method ?? "GET"} ${path} failed (${res.status})`);
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

export const api = {
  seedCosts: () => request<{ seeded: boolean; account_id: number; records: number }>(
    "/api/costs/seed",
    { method: "POST" }
  ),
  costsByService: () => request<ServiceTotal[]>("/api/costs/by-service"),
  costsTrend: () => request<DailyTotal[]>("/api/costs/trend"),
  indexChat: () => request<{ indexed: number }>("/api/chat/index", { method: "POST" }),
  ask: (question: string) =>
    request<{ answer: string }>("/api/chat/ask", {
      method: "POST",
      body: JSON.stringify({ question }),
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
