import type { RoleProfile, SessionRead } from "../types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(`API 请求失败（${response.status}）`);
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<{ status: string }> {
  return request("/health");
}

export function getRoles(): Promise<RoleProfile[]> {
  return request("/api/roles");
}

export function createSession(topic: string): Promise<SessionRead> {
  return request("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ mode: "topic", topic, role_ids: ["role_a", "role_b"] }),
  });
}

export function getEventsUrl(sessionId: string): string {
  const url = new URL(`/api/sessions/${sessionId}/events`, apiBaseUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}
