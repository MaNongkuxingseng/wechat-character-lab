export interface RoleProfile {
  id: string;
  label: string;
  profile: string;
  style_profile: Record<string, unknown>;
  voice_profile: Record<string, unknown>;
  consent_status: string;
}

export interface SessionRead {
  id: string;
  mode: "daily" | "topic";
  topic: string;
  status: string;
  turn_limit: number;
  turn_count: number;
  settings: {
    provider?: string;
    profile_readiness?: Record<string, string>;
    profile_snapshots?: Record<string, { profile_version_id: string | null; trait_ids: string[]; readiness: string }>;
  };
  created_at: string;
}

export interface ProfileEvidence {
  message_id: string;
  speaker_label: string;
  sent_at: string | null;
  excerpt: string;
  rationale: string;
}

export interface ProfileTrait {
  id: string;
  category: string;
  key: string;
  description: string;
  confidence: number;
  confidence_source: "analyzer_measurement" | "reviewer_assessed";
  context: string | null;
  review_status: "pending" | "accepted" | "rejected";
  reviewer_note: string | null;
  evidence: ProfileEvidence[];
}

export interface ProfileVersionSummary {
  id: string;
  role_id: string;
  version: number;
  status: "draft" | "approved" | "superseded";
  analyzer: string;
  sample_count: number;
  created_at: string;
  approved_at: string | null;
}

export interface ProfileVersion extends ProfileVersionSummary {
  traits: ProfileTrait[];
}

export interface ImportSource {
  id: string;
  name: string;
  kind: string;
  status: "pending_review" | "approved" | "parse_error";
  message_count: number;
  error: string | null;
  semantic_llm_authorized: boolean;
}

export interface CandidateEvidence {
  id: string;
  direction: "supporting" | "counter";
  source_dataset_id: string;
  source_message_id: string;
  imported_message_id: string | null;
  match_status: "unmatched" | "matched" | "invalid";
  invalid_reason: string | null;
  rationale: string;
}

export interface CandidateItem {
  id: string;
  profile_item_id: string;
  subject_id: string;
  category: string;
  claim: string;
  cognitive_state: "evidence_backed" | "model_inferred" | "unknown";
  inference_basis: string | null;
  confidence: number | null;
  reviewer_confidence: number | null;
  conflict_status: "none" | "conflict" | "unresolved";
  analyzer_name: string;
  analyzer_version: string;
  review_status: "pending" | "accepted" | "rejected" | "needs_review";
  evidence: CandidateEvidence[];
  review_events: Array<{
    id: string;
    from_status: string | null;
    to_status: string;
    reviewer_id: string | null;
    note: string | null;
    decision_reason_code: string | null;
    created_at: string;
  }>;
}

export interface CandidateSnapshot {
  id: string;
  source_dataset_id: string;
  role_scope: string[];
  status: string;
  analyzer_manifest: Array<{
    subject_id: string;
    analyzer_name: string;
    analyzer_version: string;
    status: string;
    sample_count: number;
  }>;
  items: CandidateItem[];
  unmatched_evidence: Array<{
    signal_id: string;
    evidence_id: string;
    kind: string;
    reason: string;
  }>;
}

export interface CandidateSnapshotSummary {
  id: string;
  source_dataset_id: string;
  status: string;
  role_scope: string[];
  created_at: string;
}

export interface CandidateAnalysisResult {
  source_id: string;
  snapshot_id: string;
  created: boolean;
  status: string;
  semantic_status: string;
  analyzer_statuses: Array<{
    subject_id: string;
    analyzer_name: string;
    analyzer_version: string;
    status: string;
    sample_count: number;
  }>;
  role_statuses: Record<string, string>;
  sample_counts: Record<string, number>;
  candidate_count: number;
  evidence_count: number;
  mapping_count: number;
  mapping_issue_count: number;
  unmatched_count: number;
}

export interface ImportPreview {
  source: ImportSource;
  speakers: Record<string, number>;
  samples: Array<{
    speaker_label: string;
    text: string;
    sent_at: string | null;
  }>;
}

export interface VoiceCapabilities {
  asr: { provider: string; available: boolean; streaming?: boolean };
  tts: { provider: string; available: boolean; streaming?: boolean };
  media_analysis?: {
    provider: string;
    available: boolean;
    silk_decoder: boolean;
    video_audio: boolean;
  };
}

export interface VoiceAsset {
  file: string;
  speaker_label: string;
  sent_at_utc: string;
  bytes: number;
  sha256: string;
}

export interface VoiceAssets {
  available: boolean;
  format: string;
  count: number;
  bytes_total: number;
  files: VoiceAsset[];
}

export interface VoiceAnalysis {
  id: string;
  role_id: string | null;
  source_path: string;
  source_kind: string;
  media_format: string;
  status: string;
  derived_from_video: boolean;
  duration_ms: number | null;
  sample_rate: number | null;
  channels: number | null;
  rms_db: number | null;
  silence_ratio: number | null;
  transcript: string | null;
  sha256: string;
  metadata: Record<string, unknown>;
  error: string | null;
  analyzed_at: string;
}

export type ServerEvent =
  | { type: "generation.cancelled"; reason: string; seq: number }
  | { type: "connection.ready"; session_id: string; seq: number }
  | { type: "connection.pong"; request_id?: string | null; seq: number }
  | { type: "event.accepted"; client_message_id: string; seq: number }
  | { type: "session.state"; status: string; seq: number }
  | {
      type: "turn.created";
      turn_id: string;
      turn: number;
      speaker_role_id: string | null;
      speaker_label: string;
      text: string;
      interrupted: boolean;
      seq: number;
    }
  | {
      type: "message.created";
      turn_id: string;
      turn: number;
      speaker_role_id: string | null;
      speaker_label: string;
      text: string;
      interrupted: boolean;
      seq: number;
    }
  | { type: "protocol.error"; code: string; message: string; seq: number };
