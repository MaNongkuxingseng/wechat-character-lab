import type {
  ImportPreview,
  ImportSource,
  CandidateAnalysisResult,
  CandidateSnapshot,
  CandidateSnapshotSummary,
  ProfileVersion,
  ProfileVersionSummary,
  RoleProfile,
  SessionRead,
  VoiceAssets,
  VoiceAnalysis,
  VoiceCapabilities,
  ProviderConfig,
  ProviderStatus,
  ProviderTestResult,
} from "../types";

// 开发环境默认连接新版本地 API；可用 VITE_API_BASE_URL 覆盖。
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: init?.body instanceof FormData
      ? init.headers
      : { "Content-Type": "application/json", ...init?.headers },
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

export function getProviderConfig(): Promise<ProviderConfig> {
  return request("/api/providers/config");
}

export function saveProviderConfig(payload: {
  provider_type: string;
  endpoint: string;
  model: string;
  api_key?: string;
  clear_api_key?: boolean;
  timeout_seconds: number;
  semantic_enabled: boolean;
  allow_message_content: boolean;
  dialogue_enabled: boolean;
}): Promise<ProviderConfig> {
  return request("/api/providers/config", { method: "PUT", body: JSON.stringify(payload) });
}

export function testProviderConnection(): Promise<ProviderTestResult> {
  return request("/api/providers/test-connection", { method: "POST" });
}

export function testSemanticProtocol(): Promise<ProviderTestResult> {
  return request("/api/providers/test-semantic", { method: "POST" });
}

export function getProviderStatus(): Promise<ProviderStatus> {
  return request("/api/providers/status");
}

export function getRoles(): Promise<RoleProfile[]> {
  return request("/api/roles");
}

export function createSession(topic: string, turnDelaySeconds = 4, roleIds = ["role_a", "role_b"]): Promise<SessionRead> {
  return request("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ mode: "topic", topic, role_ids: roleIds, turn_delay_seconds: turnDelaySeconds }),
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

export function listImportSources(): Promise<ImportSource[]> {
  return request("/api/imports");
}

export function uploadArchive(file: File): Promise<ImportSource> {
  const form = new FormData();
  form.append("file", file);
  return request("/api/imports/upload", { method: "POST", body: form });
}

export function scanImportInbox(): Promise<{ discovered: number; sources: ImportSource[] }> {
  return request("/api/imports/inbox/scan", { method: "POST" });
}

export function getImportPreview(sourceId: string): Promise<ImportPreview> {
  return request(`/api/imports/${sourceId}/preview`);
}

export function approveImport(
  sourceId: string,
  speakerMapping: Record<string, string>,
  semanticLlmAuthorized = false,
  trustedHumanAttestation = false,
  attestationReviewerId = "",
  attestationReason = "",
): Promise<{ source: ImportSource; imported_messages: number }> {
  return request(`/api/imports/${sourceId}/approve`, {
    method: "POST",
    body: JSON.stringify({
      speaker_mapping: speakerMapping,
      semantic_llm_authorized: semanticLlmAuthorized,
      trusted_human_attestation: trustedHumanAttestation,
      attestation_reviewer_id: attestationReviewerId,
      attestation_reason: attestationReason,
    }),
  });
}

export function analyzeCandidateSource(sourceId: string): Promise<CandidateAnalysisResult> {
  return request(`/api/candidate/sources/${encodeURIComponent(sourceId)}/analyze`, {
    method: "POST",
  });
}

export function getCandidateSnapshot(snapshotId: string): Promise<CandidateSnapshot> {
  return request(`/api/candidate/snapshots/${encodeURIComponent(snapshotId)}`);
}

export function listCandidateSnapshots(): Promise<CandidateSnapshotSummary[]> {
  return request("/api/candidate/snapshots");
}

export function reviewCandidateItem(
  candidateId: string,
  payload: {
    to_status: "pending" | "accepted" | "rejected" | "needs_review";
    expected_from_status: string;
    reviewer_id?: string;
    note: string;
    decision_reason_code?: string;
    reviewer_confidence?: number;
  },
): Promise<unknown> {
  return request(`/api/candidate/items/${encodeURIComponent(candidateId)}/review`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function admitCandidateItem(candidateId: string): Promise<{
  profile_version_id: string;
  role_id: string;
  version: number;
  status: string;
}> {
  return request(`/api/candidate/items/${encodeURIComponent(candidateId)}/admit`, {
    method: "POST",
  });
}

export function updateSemanticTransferConsent(
  sourceId: string,
  authorized: boolean,
  reviewerId: string,
): Promise<ImportSource> {
  return request(`/api/imports/${encodeURIComponent(sourceId)}/semantic-transfer-consent`, {
    method: "POST",
    body: JSON.stringify({ authorized, reviewer_id: reviewerId }),
  });
}

export function getVoiceCapabilities(): Promise<VoiceCapabilities> {
  return request("/api/voice/capabilities");
}

export function getVoiceAssets(): Promise<VoiceAssets> {
  return request("/api/voice/assets");
}

export function analyzeVoiceAssets(includeVideos = true): Promise<{
  minimum_samples: number;
  role_counts: Record<string, number>;
  voice_assets: VoiceAnalysis[];
  video_candidates: VoiceAnalysis[];
  all_analyses: VoiceAnalysis[];
  video_tool_available: boolean;
}> {
  return request("/api/voice/analyze", {
    method: "POST",
    body: JSON.stringify({ include_videos: includeVideos, minimum_samples: 3 }),
  });
}

export function listVoiceAnalyses(roleId?: string): Promise<{ items: VoiceAnalysis[] }> {
  return request(`/api/voice/analyses${roleId ? `?role_id=${encodeURIComponent(roleId)}` : ""}`);
}

export interface TranscriptionResult {
  provider: string;
  available: boolean;
  filename: string | null;
  content_type: string;
  text: string;
  notice: string;
}

export interface SynthesisResult {
  provider: string;
  available: boolean;
  voice_id: string;
  text: string;
  audio_url: string | null;
  notice: string;
}

export function transcribeAudio(file: File): Promise<TranscriptionResult> {
  const form = new FormData();
  form.append("file", file);
  return request("/api/voice/transcribe", { method: "POST", body: form });
}

export function synthesizeAudio(text: string, voiceId: string): Promise<SynthesisResult> {
  return request("/api/voice/synthesize", {
    method: "POST",
    body: JSON.stringify({ text, voice_id: voiceId }),
  });
}
