import { useEffect, useState } from "react";
import { analyzeVoiceAssets, getVoiceAssets, getVoiceCapabilities, listVoiceAnalyses, transcribeAudio, synthesizeAudio } from "../api/client";
import type { VoiceAnalysis, VoiceAssets, VoiceCapabilities } from "../types";

export function VoiceControls() {
  const [capabilities, setCapabilities] = useState<VoiceCapabilities | null>(null);
  const [assets, setAssets] = useState<VoiceAssets | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [role, setRole] = useState("role_a");
  const [transcript, setTranscript] = useState("");
  const [busy, setBusy] = useState(false);
  const [analyses, setAnalyses] = useState<VoiceAnalysis[]>([]);
  const [analysisNotice, setAnalysisNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([getVoiceCapabilities(), getVoiceAssets(), listVoiceAnalyses()])
      .then(([nextCapabilities, nextAssets, savedAnalyses]) => {
        if (!active) return;
        setCapabilities(nextCapabilities);
        setAssets(nextAssets);
        setAnalyses(savedAnalyses.items);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "读取语音状态失败。");
      });
    return () => {
      active = false;
    };
  }, []);

  const providerReady = Boolean(capabilities?.asr.available && capabilities?.tts.available);
  const handleAudio = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await transcribeAudio(file);
      setTranscript(result.text);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "语音转写失败。");
    } finally {
      setBusy(false);
    }
  };
  const handleSynthesis = async () => {
    if (!transcript.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await synthesizeAudio(transcript, role === "role_a" ? "preset-a" : "preset-b");
      setTranscript(result.notice);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "语音合成失败。");
    } finally {
      setBusy(false);
    }
  };
  const handleAnalysis = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await analyzeVoiceAssets(true);
      setAnalyses(result.all_analyses);
      setAnalysisNotice(
        result.video_tool_available
          ? `已完成语音解析；角色 A/B 可用解码样本 ${result.role_counts.role_a}/${result.role_counts.role_b}。`
          : `已完成本地校验；角色 A/B 可用解码样本 ${result.role_counts.role_a}/${result.role_counts.role_b}，视频音轨需安装 ffmpeg。`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "语音素材分析失败。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="voice-controls" aria-labelledby="voice-heading">
      <div className="section-heading section-heading--compact">
        <span className="section-index">03</span>
        <div>
          <h2 id="voice-heading">语音</h2>
          <p>本地素材与 Provider 状态</p>
        </div>
      </div>
      <div className="voice-status">
        <span className="voice-wave" aria-hidden="true"><i /><i /><i /><i /><i /></span>
        <span>{error ?? (providerReady ? "ASR / TTS 仍为 Mock" : "ASR 可测试，TTS 尚未配置")}</span>
        <label className="voice-upload-button">
          导入音频
          <input type="file" accept="audio/*,.silk" disabled={busy} onChange={(event) => void handleAudio(event.target.files?.[0])} />
        </label>
      </div>
      <button type="button" className="secondary-button voice-analysis-button" disabled={busy} onClick={() => void handleAnalysis()}>
        {busy ? "分析中…" : "解析语音与视频音轨"}
      </button>
      {analysisNotice && <div className="voice-analysis-notice">{analysisNotice}</div>}
      {analyses.length > 0 && (
        <ul className="voice-analysis-list">
          {analyses.map((item) => (
            <li key={item.id}>
              <span>{item.source_path.split("/").pop()}</span>
              <strong>{item.status === "decoded" ? `${item.duration_ms ?? 0} ms` : item.status}</strong>
              {item.derived_from_video && <small>视频派生音轨 / derived audio</small>}
              {item.error && <small>{item.error}</small>}
            </li>
          ))}
        </ul>
      )}
      <div className="voice-test-row">
        <select value={role} onChange={(event) => setRole(event.target.value)} aria-label="选择语音角色">
          <option value="role_a">角色 A 预设音色</option>
          <option value="role_b">角色 B 预设音色</option>
        </select>
        <button type="button" className="secondary-button" disabled={busy || !transcript.trim()} onClick={() => void handleSynthesis()}>测试合成</button>
      </div>
      {transcript && <div className="voice-transcript">{transcript}</div>}
      <div className="voice-summary">
        <span>本地语音素材</span>
        <strong>{assets?.available ? `${assets.count} 段 ${assets.format}` : "未发现"}</strong>
        <small>{assets?.available ? `${assets.bytes_total.toLocaleString()} bytes，尚未解码` : "清单不可用"}</small>
      </div>
    </section>
  );
}
