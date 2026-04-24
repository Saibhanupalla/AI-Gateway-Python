/**
 * API client for the AI Gateway backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request(path: string, options: RequestInit = {}) {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
      localStorage.removeItem("username");
      window.location.href = "/";
    }
    throw new Error("Unauthorized");
  }
  return res;
}

export async function login(username: string, password: string) {
  const res = await fetch(`${API_BASE}/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }),
  });
  if (!res.ok) throw new Error("Login failed");
  const data = await res.json();
  localStorage.setItem("token", data.access_token);
  localStorage.setItem("username", username);
  return data;
}

export async function getMe() {
  const res = await request("/users/me/");
  if (!res.ok) throw new Error("Failed to get user");
  return res.json();
}

export async function getAnalyticsSummary() {
  const res = await request("/analytics/summary");
  if (!res.ok) throw new Error("Failed to get analytics");
  return res.json();
}

export async function getAnalyticsRequests(limit = 50) {
  const res = await request(`/analytics/requests?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to get requests");
  return res.json();
}

export async function getAnalyticsUsers() {
  const res = await request("/analytics/users");
  if (!res.ok) throw new Error("Failed to get users");
  return res.json();
}

export async function getAuditLogs() {
  const res = await request("/audit_logs");
  if (!res.ok) throw new Error("Failed to get audit logs");
  return res.json();
}

export async function getPolicies() {
  const res = await request("/admin/policies");
  if (!res.ok) throw new Error("Failed to get policies");
  return res.json();
}

export async function createPolicy(data: Record<string, unknown>) {
  const res = await request("/admin/policies", { method: "POST", body: JSON.stringify(data) });
  if (!res.ok) throw new Error("Failed to create policy");
  return res.json();
}

export async function deletePolicy(id: number) {
  const res = await request(`/admin/policies/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete policy");
  return res.json();
}

export async function getRateLimits() {
  const res = await request("/admin/rate-limits");
  if (!res.ok) throw new Error("Failed to get rate limits");
  return res.json();
}

export async function createRateLimit(data: Record<string, unknown>) {
  const res = await request("/admin/rate-limits", { method: "POST", body: JSON.stringify(data) });
  if (!res.ok) throw new Error("Failed to create rate limit");
  return res.json();
}

export async function deleteRateLimit(id: number) {
  const res = await request(`/admin/rate-limits/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete rate limit");
  return res.json();
}

export async function getGuardrails() {
  const res = await request("/admin/guardrails");
  if (!res.ok) throw new Error("Failed to get guardrails");
  return res.json();
}

export async function createGuardrail(data: Record<string, unknown>) {
  const res = await request("/admin/guardrails", { method: "POST", body: JSON.stringify(data) });
  if (!res.ok) throw new Error("Failed to create guardrail");
  return res.json();
}

export async function deleteGuardrail(id: number) {
  const res = await request(`/admin/guardrails/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete guardrail");
  return res.json();
}

export async function getGatewayConfig() {
  const res = await request("/gateway/config");
  if (!res.ok) throw new Error("Failed to get config");
  return res.json();
}

export async function getTemplates() {
  const res = await request("/templates");
  if (!res.ok) throw new Error("Failed to get templates");
  return res.json();
}

export async function createTemplate(data: Record<string, unknown>) {
  const res = await request("/templates", { method: "POST", body: JSON.stringify(data) });
  if (!res.ok) throw new Error("Failed to create template");
  return res.json();
}

export async function sendPrompt(prompt: string, model?: string) {
  const body: Record<string, unknown> = { prompt };
  if (model) body.model = model;
  const res = await request("/prompt", { method: "POST", body: JSON.stringify(body) });
  if (!res.ok) throw new Error("Failed to send prompt");
  return res.json();
}
