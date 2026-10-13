import type { ServerEvent, SessionRead } from "../types";

interface ChatTimelineProps {
  session: SessionRead | null;
  events: ServerEvent[];
}

export function ChatTimeline({ session, events }: ChatTimelineProps) {
  return (
    <section className="timeline" aria-labelledby="timeline-heading">
      <div className="section-heading section-heading--compact">
        <span className="section-index">02</span>
        <div>
          <h2 id="timeline-heading">会话时间线</h2>
          <p>{session ? `主题：${session.topic}` : "尚未创建会话"}</p>
        </div>
        {session && <span className="state-label">{session.status}</span>}
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
        ) : (
          <ol className="event-list">
            {events.map((event, index) => (
              <li className="event-row" key={`${event.type}-${index}`}>
                <span className="event-dot" />
                <span className="event-name">{event.type}</span>
                <span className="event-meta">seq {event.seq}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
      <div className="timeline-footer">
        <span>文字与实时语音控制将在后续阶段接入</span>
        <button type="button" className="icon-button" disabled title="当前骨架尚未接入消息发送" aria-label="发送消息">↑</button>
      </div>
    </section>
  );
}
