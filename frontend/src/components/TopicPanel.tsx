interface TopicPanelProps {
  topic: string;
  onTopicChange: (value: string) => void;
  onStart: () => void;
  disabled: boolean;
}

export function TopicPanel({ topic, onTopicChange, onStart, disabled }: TopicPanelProps) {
  return (
    <section className="topic-panel" aria-labelledby="topic-heading">
      <div className="section-heading">
        <span className="section-index">01</span>
        <div>
          <h2 id="topic-heading">新建主题会话</h2>
          <p>设置讨论主题，创建一场模拟会话。</p>
        </div>
      </div>
      <label className="field-label" htmlFor="topic-input">讨论主题</label>
      <textarea
        id="topic-input"
        value={topic}
        onChange={(event) => onTopicChange(event.target.value)}
        placeholder="例如：AI 会怎样改变我们的工作方式？"
        maxLength={500}
        rows={3}
      />
      <div className="topic-actions">
        <span className="field-hint">最多 500 字</span>
        <button className="primary-button" type="button" onClick={onStart} disabled={disabled || !topic.trim()}>
          创建会话
          <span aria-hidden="true">→</span>
        </button>
      </div>
    </section>
  );
}
