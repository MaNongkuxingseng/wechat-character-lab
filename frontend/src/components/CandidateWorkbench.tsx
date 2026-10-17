import { useEffect, useMemo, useState } from "react";
import {
  admitCandidateItem,
  analyzeCandidateSource,
  getCandidateSnapshot,
  listCandidateSnapshots,
  listImportSources,
  reviewCandidateItem,
  updateSemanticTransferConsent,
} from "../api/client";
import type { CandidateSnapshot, ImportSource, RoleProfile } from "../types";

interface CandidateWorkbenchProps {
  roles: RoleProfile[];
  connected: boolean;
  onProfileDraftCreated: () => void;
}

const reviewLabels: Record<string, string> = {
  pending: "待审核",
  accepted: "已接受",
  rejected: "已拒绝",
  needs_review: "需复核",
};

const cognitiveLabels: Record<string, string> = {
  evidence_backed: "证据支持",
  model_inferred: "模型推断",
  unknown: "未知",
};

export function CandidateWorkbench({ roles, connected, onProfileDraftCreated }: CandidateWorkbenchProps) {
  const [sources, setSources] = useState<ImportSource[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [snapshot, setSnapshot] = useState<CandidateSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reviewerId, setReviewerId] = useState("");
  const [reviewerConfidence, setReviewerConfidence] = useState<Record<string, string>>({});

  const approvedSources = useMemo(
    () => sources.filter((source) => source.status === "approved"),
    [sources],
  );
  const selectedSource = approvedSources.find((source) => source.id === sourceId);

  useEffect(() => {
    if (!connected) return;
    Promise.all([listImportSources(), listCandidateSnapshots()])
      .then(([items, snapshots]) => {
        setSources(items);
        const preferredId = items.find((item) => item.status === "approved")?.id || "";
        setSourceId((current) => current || preferredId);
        const latest = snapshots[0];
        if (latest) void getCandidateSnapshot(latest.id).then(setSnapshot);
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "读取来源失败"));
  }, [connected]);

  async function analyze() {
    if (!sourceId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await analyzeCandidateSource(sourceId);
      setSnapshot(await getCandidateSnapshot(result.snapshot_id));
      setNotice(
        `候选分析完成：${result.semantic_status === "ready" ? "真实语义 Provider" : "语义 Provider 未就绪"}；` +
        `统计状态 ${result.status}，候选 ${result.candidate_count} 项。`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "候选分析失败");
    } finally {
      setBusy(false);
    }
  }

  async function setTransferConsent(authorized: boolean) {
    if (!sourceId || !reviewerId.trim()) {
      setError("请先选择来源并填写审核人标识。");
      return;
    }
    if (!window.confirm(authorized
      ? "授权后，该来源中通过安全与角色门禁的文本可能被发送到已配置的外部语义 Provider。确认授权？"
      : "撤销该来源的 Provider 文本传输授权？")) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateSemanticTransferConsent(sourceId, authorized, reviewerId.trim());
      setSources((current) => current.map((source) => source.id === updated.id ? updated : source));
      setNotice(authorized ? "已记录此来源的语义 Provider 文本传输授权。" : "已撤销此来源的语义 Provider 文本传输授权。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存来源授权失败");
    } finally {
      setBusy(false);
    }
  }

  async function review(
    itemId: string,
    currentStatus: string,
    status: "accepted" | "rejected" | "needs_review",
    analyzerConfidence: number | null,
  ) {
    const rawConfidence = reviewerConfidence[itemId]?.trim();
    const confidence = rawConfidence ? Number(rawConfidence) : undefined;
    if (status === "accepted" && analyzerConfidence === null && confidence === undefined) {
      setError("模型置信度未知，请填写人工审核置信度后再接受。");
      return;
    }
    if (confidence !== undefined && (!Number.isFinite(confidence) || confidence < 0 || confidence > 1)) {
      setError("人工审核置信度必须是 0 到 1 之间的数字。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (!reviewerId.trim()) {
        setError("审核事件需要填写审核人标识；本地应用目前未启用身份认证。");
        return;
      }
      await reviewCandidateItem(itemId, {
        to_status: status,
        expected_from_status: currentStatus,
        ...(reviewerId.trim() ? { reviewer_id: reviewerId.trim() } : {}),
        note: `P3-D 本地审核：${reviewLabels[status]}`,
        decision_reason_code: status === "accepted" ? "evidence_reviewed" : "requires_review",
        ...(status === "accepted" && confidence !== undefined ? { reviewer_confidence: confidence } : {}),
      });
      if (snapshot) setSnapshot(await getCandidateSnapshot(snapshot.id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存审核结果失败");
    } finally {
      setBusy(false);
    }
  }

  async function admit(itemId: string) {
    setBusy(true);
    setError(null);
    try {
      const result = await admitCandidateItem(itemId);
      setNotice(`已生成正式画像草稿 v${result.version}；仍需正式画像审核和发布。`);
      onProfileDraftCreated();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "正式画像准入失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="candidate-workbench" aria-labelledby="candidate-heading">
      <div className="profile-header">
        <div className="section-heading section-heading--compact">
          <span className="section-index">07</span>
          <div>
            <h2 id="candidate-heading">语义候选审核</h2>
            <p>
              仅使用已批准来源；当前来源的文本外发授权：
              {selectedSource?.semantic_llm_authorized ? "已授权" : "未授权"}。
              未授权时只运行本地统计。
            </p>
          </div>
        </div>
        <div className="profile-controls">
          <select
            aria-label="选择已批准来源"
            value={sourceId}
            onChange={(event) => setSourceId(event.target.value)}
            disabled={busy || approvedSources.length === 0}
          >
            <option value="">选择已批准来源</option>
            {approvedSources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
          </select>
          <input
            aria-label="审核人标识（可选；本地应用未启用身份认证）"
            placeholder="审核人标识（可选）"
            value={reviewerId}
            onChange={(event) => setReviewerId(event.target.value)}
            disabled={busy}
          />
          <button className="secondary-button" type="button" onClick={() => void analyze()} disabled={!connected || busy || !sourceId}>
            {busy ? "处理中…" : "运行语义分析"}
          </button>
          {approvedSources.some((source) => source.id === sourceId) && (
            <button
              className="secondary-button"
              type="button"
              onClick={() => void setTransferConsent(!approvedSources.find((source) => source.id === sourceId)?.semantic_llm_authorized)}
              disabled={!connected || busy || !reviewerId.trim()}
            >
              {approvedSources.find((source) => source.id === sourceId)?.semantic_llm_authorized ? "撤销文本传输授权" : "授权 Provider 文本传输"}
            </button>
          )}
        </div>
      </div>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {notice && <div className="notice-banner" role="status">{notice}</div>}
      {!snapshot ? (
        <div className="profile-empty"><p>选择已批准来源并运行分析后，这里显示候选、证据方向和审核状态。</p></div>
      ) : (
        <>
          <div className="analysis-disclosure">
            <span className="disclosure-mark">i</span>
            <span>快照 {snapshot.id} · 分析器 {snapshot.analyzer_manifest.map((item) => `${item.analyzer_name}:${item.status}`).join(" / ")}</span>
          </div>
          <div className="candidate-list">
            {snapshot.items.length === 0 ? <div className="profile-empty"><p>没有通过证据门禁的候选。</p></div> : snapshot.items.map((item) => {
              const role = roles.find((candidate) => candidate.id === item.subject_id);
              const matchedSupporting = item.evidence.filter((evidence) => evidence.direction === "supporting" && evidence.match_status === "matched").length;
              return (
                <article className="candidate-item" key={item.id}>
                  <div className="trait-title-row">
                    <div className="trait-heading">
                      <span className="trait-category">{role?.label ?? item.subject_id} · {cognitiveLabels[item.cognitive_state]}</span>
                      <h3>{item.category}</h3>
                    </div>
                    <span className={`review-state review-state--${item.review_status}`}>{reviewLabels[item.review_status]}</span>
                  </div>
                  <p className="candidate-claim">{item.claim}</p>
                  <div className="trait-meta">
                    <span>模型置信度 {item.confidence === null ? "未知" : `${Math.round(item.confidence * 100)}%`}</span>
                    <span>支持证据 {matchedSupporting} 条</span>
                    <span>冲突 {item.conflict_status}</span>
                    <details><summary>证据引用 · {item.evidence.length}</summary><ul className="candidate-evidence-list">{item.evidence.map((evidence) => <li key={evidence.id}>{evidence.direction} · {evidence.source_message_id} · {evidence.match_status}{evidence.invalid_reason ? ` · ${evidence.invalid_reason}` : ""} · {evidence.rationale}</li>)}</ul></details>
                    <details><summary>审核历史 · {item.review_events.length}</summary><ul className="candidate-evidence-list">{item.review_events.map((event) => <li key={event.id}>{event.from_status ?? "初始"} → {event.to_status} · {event.reviewer_id ?? "未提供审核人"} · {event.note ?? "无说明"}</li>)}</ul></details>
                  </div>
                  {item.inference_basis && <p className="candidate-basis">{item.inference_basis}</p>}
                  {item.review_status !== "accepted" && item.review_status !== "rejected" && item.confidence === null && (
                    <label className="candidate-confidence-label">
                      人工审核置信度（可选）
                      <input
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        value={reviewerConfidence[item.id] ?? ""}
                        onChange={(event) => setReviewerConfidence((current) => ({ ...current, [item.id]: event.target.value }))}
                      />
                    </label>
                  )}
                  {item.review_status !== "accepted" && item.review_status !== "rejected" && (
                    <div className="trait-review-row">
                      <button type="button" className="accept-button" disabled={busy} onClick={() => void review(item.id, item.review_status, "accepted", item.confidence)}>接受</button>
                      <button type="button" className="secondary-button" disabled={busy} onClick={() => void review(item.id, item.review_status, "needs_review", item.confidence)}>待复核</button>
                      <button type="button" className="reject-button" disabled={busy} onClick={() => void review(item.id, item.review_status, "rejected", item.confidence)}>拒绝</button>
                    </div>
                  )}
                  {item.review_status === "accepted" && item.cognitive_state !== "unknown" && item.conflict_status === "none" && matchedSupporting > 0 && (item.confidence !== null || item.reviewer_confidence !== null) && (item.cognitive_state !== "model_inferred" || Boolean(item.inference_basis)) && (
                    <div className="trait-review-row"><button type="button" className="primary-button" disabled={busy} onClick={() => void admit(item.id)}>准入正式画像草稿</button></div>
                  )}
                </article>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}
