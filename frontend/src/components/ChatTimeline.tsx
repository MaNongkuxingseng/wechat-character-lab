import { useMemo, useState } from "react";
import type { ServerEvent, SessionRead } from "../types";

interface ChatTimelineProps {
  session: SessionRead | null;
  events: ServerEvent[];
  onSend: (text: string) => boolean;
  onStop: () => boolean;
}

export function ChatTimeline({ session, events, onSend, onStop }: ChatTimelineProps) {
  const [draft, setDraft] = useState("");
  const messages = useMemo(
    () => events.filter((event): event is Extract<ServerEvent, { type: "message.created" }> => event.type === "message.created"),
    [events],
  );
  const state = [...events].reverse().find((event) => event.type === "session.state");
  const submit = () => {
    if (onSend(draft)) setDraft("");
  };
  return (
    <section className="timeline" aria-labelledby="timeline-heading">
      <div className="section-heading section-heading--compact">
        <span className="section-index">02</span>
        <div>
          <h2 id="timeline-heading">会话时间线</h2>
          <p>{session ? `主题：${session.topic}` : "尚未创建会话"}</p>
        </div>
        {session && <span className="state-label">{state?.type === "session.state" ? state.status : session.status}</span>}
      </div>
      <div className="timeline-body" aria-live="polite">
        {!session ? (
          <div className="empty-state">
            <div className="empty-mark" aria-hidden="true">↗</div>
            <p>创建主题会话后，连接与事件状态会显示在这里。</p>
          </div>
        ) : events.length === 0 ? (
          <div className="empty-state">
            <div className="loading-mark" aria-hidden="true" />
            <p>正在等待会话事件连接…</p>
          </div>
        ) : messages.length === 0 ? (
          <div className="empty-state"><p>会话已连接，等待第一轮角色发言…</p></div>
        ) : (
          <ol className="message-list">
            {messages.map((event) => (
              <li className={`message-bubble message-bubble--${event.speaker_role_id ?? "user"}`} key={event.turn_id}>
                <div className="message-meta"><strong>{event.speaker_label}</strong><span>第 {event.turn} 轮</span></div>
                <p>{event.text}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
      <div className="timeline-footer">
        {session ? (
          <div className="message-compose">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") submit(); }}
              placeholder="插话…"
              maxLength={4000}
              aria-label="输入插话"
            />
            <button type="button" className="icon-button" onClick={submit} disabled={!draft.trim()} title="发送插话" aria-label="发送插话">↑</button>
            <button type="button" className="stop-button" onClick={onStop} title="停止自动对话">停止</button>
          </div>
        ) : <span>创建主题会话后可开始文字对话</span>}
      </div>
    </section>
  );
}
