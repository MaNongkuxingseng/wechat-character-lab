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

export type ServerEvent =
  | { type: "connection.ready"; session_id: string; seq: number }
  | { type: "connection.pong"; request_id?: string | null; seq: number }
  | { type: "event.accepted"; client_message_id: string; seq: number }
  | { type: "protocol.error"; code: string; message: string; seq: number };
