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
