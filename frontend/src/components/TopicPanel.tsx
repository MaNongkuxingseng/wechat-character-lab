interface TopicPanelProps {
  topic: string;
  onTopicChange: (value: string) => void;
  onStart: () => void;
  disabled: boolean;
  turnDelay: number;
  onTurnDelayChange: (value: number) => void;
  roles: Array<{ id: string; label: string }>;
  roleIds: [string, string];
  onRoleIdsChange: (value: [string, string]) => void;
}

export function TopicPanel({ topic, onTopicChange, onStart, disabled, turnDelay, onTurnDelayChange, roles, roleIds, onRoleIdsChange }: TopicPanelProps) {
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
        <label className="field-hint">A
          <select aria-label="A 角色" value={roleIds[0]} onChange={(event) => onRoleIdsChange([event.target.value, roleIds[1]])} disabled={disabled}>
            {roles.filter((role) => role.id !== roleIds[1]).map((role) => <option key={role.id} value={role.id}>{role.label}</option>)}
          </select>
        </label>
        <label className="field-hint">B
          <select aria-label="B 角色" value={roleIds[1]} onChange={(event) => onRoleIdsChange([roleIds[0], event.target.value])} disabled={disabled}>
            {roles.filter((role) => role.id !== roleIds[0]).map((role) => <option key={role.id} value={role.id}>{role.label}</option>)}
          </select>
        </label>
        <label className="field-hint">轮间等待
          <select aria-label="轮间等待" value={turnDelay} onChange={(event) => onTurnDelayChange(Number(event.target.value))} disabled={disabled}>
            <option value={2}>2 秒</option><option value={4}>4 秒</option><option value={8}>8 秒</option>
          </select>
        </label>
        <button className="primary-button" type="button" onClick={onStart} disabled={disabled || !topic.trim()}>
          创建会话
          <span aria-hidden="true">→</span>
        </button>
      </div>
    </section>
  );
}
