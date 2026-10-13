export function VoiceControls() {
  return (
    <section className="voice-controls" aria-labelledby="voice-heading">
      <div className="section-heading section-heading--compact">
        <span className="section-index">03</span>
        <div>
          <h2 id="voice-heading">语音</h2>
          <p>ASR / TTS Provider 已预留接口</p>
        </div>
      </div>
      <div className="voice-status">
        <span className="voice-wave" aria-hidden="true"><i /><i /><i /><i /><i /></span>
        <span>尚未连接语音服务</span>
        <button type="button" disabled title="语音录制将在后续阶段实现">按键说话</button>
      </div>
    </section>
  );
}
