import type { ProfileVersion, ProfileVersionSummary, RoleProfile, SessionRead } from "../types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: string | { message?: string; code?: string } }
      | null;
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? detail?.code;
    throw new Error(message ? `请求未完成：${message}` : `API 请求失败（${response.status}）`);
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

export function listProfiles(roleId: string): Promise<ProfileVersionSummary[]> {
  return request(`/api/roles/${roleId}/profiles`);
}

export function analyzeProfile(roleId: string): Promise<ProfileVersion> {
  return request(`/api/roles/${roleId}/profiles/analyze`, { method: "POST" });
}

export function getProfile(roleId: string, versionId: string): Promise<ProfileVersion> {
  return request(`/api/roles/${roleId}/profiles/${versionId}`);
}

export function reviewTrait(
  roleId: string,
  versionId: string,
  traitId: string,
  update: { status: "accepted" | "rejected"; description: string; reviewer_note: string },
): Promise<unknown> {
  return request(
    `/api/roles/${roleId}/profiles/${versionId}/traits/${traitId}/review`,
    { method: "POST", body: JSON.stringify(update) },
  );
}

export function publishProfile(roleId: string, versionId: string): Promise<ProfileVersion> {
  return request(`/api/roles/${roleId}/profiles/${versionId}/publish`, { method: "POST" });
}
