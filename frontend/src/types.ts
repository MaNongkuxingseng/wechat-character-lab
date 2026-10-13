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

export type ServerEvent =
  | { type: "connection.ready"; session_id: string; seq: number }
  | { type: "connection.pong"; request_id?: string | null; seq: number }
  | { type: "event.accepted"; client_message_id: string; seq: number }
  | { type: "protocol.error"; code: string; message: string; seq: number };
