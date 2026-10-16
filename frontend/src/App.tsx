import { useState } from "react";
import { ChatTimeline } from "./components/ChatTimeline";
import { ImportWorkbench } from "./components/ImportWorkbench";
import { ProfileWorkbench } from "./components/ProfileWorkbench";
import { RoleBadge } from "./components/RoleBadge";
import { TopicPanel } from "./components/TopicPanel";
import { VoiceControls } from "./components/VoiceControls";
import { useSession } from "./hooks/useSession";

export default function App() {
  const [topic, setTopic] = useState("");
  const [turnDelay, setTurnDelay] = useState(4);
  const { roles, session, connection, events, error, startSession, sendMessage, stopSession, pauseOrResumeSession } = useSession();
  const connected = connection === "connected";

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="微信角色实验室首页">
          <span className="brand-mark" aria-hidden="true"><i /><i /></span>
          <span>微信角色实验室</span>
          <span className="brand-version">LOCAL LAB / 0.1</span>
        </a>
        <div className={`backend-status ${connected ? "is-connected" : ""}`}>
          <span className="status-led" />
          {connection === "checking" ? "检查后端" : connected ? "本机服务已连接" : "后端未连接"}
        </div>
      </header>

      <div className="workspace" id="top">
        <aside className="sidebar">
          <div className="sidebar-label">参与角色 <span>2</span></div>
          <div className="role-card">
            <div className="role-avatar role-avatar--a">A</div>
            <div className="role-copy">
              <RoleBadge label={roles.find((role) => role.id === "role_a")?.label ?? "角色 A"} tone="green" />
              <span>{roles.find((role) => role.id === "role_a")?.profile || "等待填写角色资料"}</span>
            </div>
            <button className="more-button" type="button" disabled title="角色编辑将在后续阶段实现" aria-label="编辑角色 A">···</button>
          </div>
          <div className="role-card">
            <div className="role-avatar role-avatar--b">B</div>
            <div className="role-copy">
              <RoleBadge label={roles.find((role) => role.id === "role_b")?.label ?? "角色 B"} tone="coral" />
              <span>{roles.find((role) => role.id === "role_b")?.profile || "等待填写角色资料"}</span>
            </div>
            <button className="more-button" type="button" disabled title="角色编辑将在后续阶段实现" aria-label="编辑角色 B">···</button>
          </div>

          <div className="sidebar-divider" />
          <div className="sidebar-label">素材来源</div>
          <button className="source-row" type="button" onClick={() => document.getElementById("import-heading")?.scrollIntoView({ behavior: "smooth" })}>
            <span className="source-icon">＋</span>
            <span>导入聊天记录</span>
            <span className="coming-soon">ZIP</span>
          </button>

          <div className="sidebar-note">
            <span className="note-symbol">i</span>
            <p>本机优先存储。聊天素材须经审核后才可用于角色记忆。</p>
          </div>
        </aside>

        <section className="main-column">
          <div className="page-heading">
            <div>
              <div className="eyebrow">CONVERSATION STUDIO</div>
              <h1>对话工作台</h1>
            </div>
            <div className="mode-chip"><span /> 双角色模拟</div>
          </div>

          <div className="workbench-grid">
            <div className="primary-column">
              <TopicPanel
                topic={topic}
                onTopicChange={setTopic}
                onStart={() => void startSession(topic.trim(), turnDelay)}
                turnDelay={turnDelay}
                onTurnDelayChange={setTurnDelay}
                disabled={!connected || Boolean(session && ["created", "initializing", "running", "paused", "stopping"].includes(session.status))}
              />
              {error && <div className="error-banner" role="alert">{error}</div>}
              <ChatTimeline session={session} events={events} onSend={sendMessage} onStop={stopSession} onPauseOrResume={pauseOrResumeSession} />
            </div>
            <aside className="detail-column">
              <VoiceControls />
              <section className="runtime-panel">
                <div className="section-heading section-heading--compact">
                  <span className="section-index">04</span>
                  <div><h2>运行状态</h2><p>本地工程骨架</p></div>
                </div>
                <dl className="runtime-list">
                  <div><dt>会话引擎</dt><dd>Mock / 待接入</dd></div>
                  <div><dt>资料库</dt><dd>SQLite</dd></div>
                  <div><dt>导入适配器</dt><dd>WeChat ZIP / 本地</dd></div>
                  <div><dt>分析器</dt><dd>点击生成草稿</dd></div>
                </dl>
              </section>
            </aside>
          </div>
          <ImportWorkbench roles={roles} connected={connected} />
          <ProfileWorkbench roles={roles} connected={connected} />
          <footer className="page-footer"><span>WECHAT CHARACTER LAB</span><span>个人本地工作区</span></footer>
        </section>
      </div>
    </main>
  );
}
