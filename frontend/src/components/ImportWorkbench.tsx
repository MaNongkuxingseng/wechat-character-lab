import { useEffect, useState } from "react";
import {
  approveImport,
  getImportPreview,
  listImportSources,
  scanImportInbox,
  uploadArchive,
} from "../api/client";
import type { ImportPreview, ImportSource, RoleProfile } from "../types";

interface ImportWorkbenchProps {
  roles: RoleProfile[];
  connected: boolean;
}

const statusLabels: Record<string, string> = {
  pending_review: "待审核",
  approved: "已导入",
  parse_error: "格式错误",
};

export function ImportWorkbench({ roles, connected }: ImportWorkbenchProps) {
  const [sources, setSources] = useState<ImportSource[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [speakerMapping, setSpeakerMapping] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [semanticLlmAuthorized, setSemanticLlmAuthorized] = useState(false);
  const [trustedHumanAttestation, setTrustedHumanAttestation] = useState(false);
  const [attestationReviewerId, setAttestationReviewerId] = useState("");
  const [attestationReason, setAttestationReason] = useState("");

  async function refreshSources(preferredId?: string) {
    const nextSources = await listImportSources();
    setSources(nextSources);
    const nextId = preferredId ?? nextSources.find((item) => item.status === "pending_review")?.id ?? nextSources[0]?.id ?? "";
    setSelectedId(nextId);
  }

  useEffect(() => {
    let active = true;
    listImportSources()
      .then((nextSources) => {
        if (!active) return;
        setSources(nextSources);
        setSelectedId(
          nextSources.find((item) => item.status === "pending_review")?.id ?? nextSources[0]?.id ?? "",
        );
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "读取导入来源失败。");
      });
    return () => {
      active = false;
    };
  }, [connected]);

  useEffect(() => {
    if (!selectedId || !connected) {
      setPreview(null);
      return;
    }
    let active = true;
    setPreview(null);
    setSpeakerMapping({});
    getImportPreview(selectedId)
      .then((nextPreview) => {
        if (!active) return;
        setPreview(nextPreview);
        setSpeakerMapping((current) =>
          Object.fromEntries(
            Object.keys(nextPreview.speakers).map((speaker) => [speaker, current[speaker] ?? ""]),
          ),
        );
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "读取归档预览失败。");
      });
    return () => {
      active = false;
    };
  }, [selectedId, connected]);

  async function handleUpload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const uploaded = await uploadArchive(file);
      await refreshSources(uploaded.id);
      setNotice(
        uploaded.status === "pending_review"
          ? "归档已保存在本机，尚未写入消息；请检查发言人和样例后确认导入。"
          : uploaded.error ?? "该归档无法解析。",
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "上传归档失败。");
    } finally {
      setBusy(false);
    }
  }

  async function scanInbox() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await scanImportInbox();
      await refreshSources();
      setNotice(`扫描完成：发现 ${result.discovered} 个 ZIP 归档。`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "扫描本机 Inbox 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function confirmImport() {
    if (!selectedId || !preview) return;
    const mapping = Object.fromEntries(
      Object.entries(speakerMapping).filter(([, roleId]) => roleId.length > 0),
    );
    if (Object.keys(mapping).length === 0) {
      setError("至少将一位发言人映射到角色 A 或角色 B 后再导入。");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await approveImport(
        selectedId,
        mapping,
        semanticLlmAuthorized,
        trustedHumanAttestation,
        attestationReviewerId,
        attestationReason,
      );
      await refreshSources(selectedId);
      setPreview(await getImportPreview(selectedId));
      setNotice(`已导入 ${result.imported_messages} 条消息；未映射发言人的消息不会用于角色画像。`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "确认导入失败。");
    } finally {
      setBusy(false);
    }
  }

  const selectedSource = sources.find((source) => source.id === selectedId);
  const canApprove = selectedSource?.status === "pending_review" &&
    Object.values(speakerMapping).some((roleId) => roleId.length > 0);

  return (
    <section className="import-workbench" aria-labelledby="import-heading">
      <div className="import-header">
        <div className="section-heading section-heading--compact">
          <span className="section-index">05</span>
          <div>
            <h2 id="import-heading">聊天记录导入与处理</h2>
            <p>只保存于本机；确认发言人映射后才会写入消息库</p>
          </div>
        </div>
        <div className="import-actions">
          <label className="semantic-consent">
            <input
              type="checkbox"
              checked={semanticLlmAuthorized}
              disabled={!selectedId || selectedSource?.status !== "pending_review" || busy}
              onChange={(event) => setSemanticLlmAuthorized(event.target.checked)}
            />
            允许后续语义 Provider 发送来源文本（默认关闭）
          </label>
          <label className="semantic-consent">
            <input
              type="checkbox"
              checked={trustedHumanAttestation}
              disabled={!selectedId || selectedSource?.status !== "pending_review" || busy}
              onChange={(event) => setTrustedHumanAttestation(event.target.checked)}
            />
            我确认样本为人工聊天，且不含 AI 或系统消息
          </label>
          {trustedHumanAttestation && (
            <div className="attestation-fields">
              <input
                aria-label="可信声明审核人"
                placeholder="审核人标识"
                value={attestationReviewerId}
                disabled={busy}
                onChange={(event) => setAttestationReviewerId(event.target.value)}
              />
              <input
                aria-label="可信声明理由"
                placeholder="声明理由"
                value={attestationReason}
                disabled={busy}
                onChange={(event) => setAttestationReason(event.target.value)}
              />
            </div>
          )}
          <label className="secondary-button upload-button">
            {busy ? "处理中…" : "选择 ZIP 导出包"}
            <input
              type="file"
              accept=".zip,application/zip"
              disabled={!connected || busy}
              onChange={(event) => {
                void handleUpload(event.currentTarget.files?.[0]);
                event.currentTarget.value = "";
              }}
            />
          </label>
          <button className="secondary-button" type="button" disabled={!connected || busy} onClick={() => void scanInbox()}>
            扫描 Inbox
          </button>
        </div>
      </div>

      <div className="import-disclosure">
        <span className="disclosure-mark" aria-hidden="true">i</span>
        <span>支持 ZIP 内的 messages.json、messages.jsonl、messages.ndjson 或 messages.csv；上限 50 MiB。未审核素材不会参与画像分析。</span>
      </div>

      {error && <div className="error-banner" role="alert">{error}</div>}
      {notice && <div className="notice-banner" role="status">{notice}</div>}

      <div className="import-layout">
        <div className="source-list-panel">
          <div className="import-subheading">
            <h3>导入来源</h3>
            <span>{sources.length} 个归档</span>
          </div>
          {sources.length === 0 ? (
            <div className="import-empty">尚无导入来源。选择微信导出 ZIP 后，会先进入待审核状态。</div>
          ) : (
            <ul className="source-list">
              {sources.map((source) => (
                <li key={source.id}>
                  <button
                    className={`source-item ${source.id === selectedId ? "is-selected" : ""}`}
                    type="button"
                    onClick={() => {
                      setSelectedId(source.id);
                      setSemanticLlmAuthorized(false);
                      setTrustedHumanAttestation(false);
                      setAttestationReviewerId("");
                      setAttestationReason("");
                      setError(null);
                      setNotice(null);
                    }}
                    disabled={busy}
                  >
                    <span className={`source-state source-state--${source.status}`} />
                    <span className="source-item-copy">
                      <strong>{source.name}</strong>
                      <small>{source.message_count} 条 · {statusLabels[source.status] ?? source.status}</small>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="import-detail-panel">
          {!selectedSource ? (
            <div className="import-empty import-empty--detail">选择或上传一个归档以查看内容。</div>
          ) : selectedSource.status === "parse_error" ? (
            <div className="error-banner" role="alert">{selectedSource.error || "无法读取该 ZIP 归档。"}</div>
          ) : !preview ? (
            <div className="import-empty import-empty--detail">正在读取归档预览…</div>
          ) : (
            <>
              <div className="import-subheading import-subheading--preview">
                <div><h3>发言人映射</h3><p>把聊天导出中的名字映射到角色；其他发言人可留空。</p></div>
                <span>{preview.source.message_count} 条消息</span>
              </div>
              <div className="speaker-mapping-list">
                {Object.entries(preview.speakers).map(([speaker, count]) => (
                  <label className="speaker-mapping-row" key={speaker}>
                    <span className="speaker-name">{speaker}<small>{count} 条消息</small></span>
                    <select
                      aria-label={`${speaker} 映射到角色`}
                      value={speakerMapping[speaker] ?? ""}
                      disabled={selectedSource.status !== "pending_review" || busy}
                      onChange={(event) => setSpeakerMapping((current) => ({ ...current, [speaker]: event.target.value }))}
                    >
                      <option value="">不映射</option>
                      {roles.map((role) => <option value={role.id} key={role.id}>{role.label}</option>)}
                    </select>
                  </label>
                ))}
              </div>

              <div className="sample-heading"><h3>消息样例</h3><span>最多显示 10 条，每条截取 240 字</span></div>
              <div className="message-samples">
                {preview.samples.length === 0 ? (
                  <p className="import-empty">该归档没有可预览的消息。</p>
                ) : preview.samples.map((sample, index) => (
                  <article className="message-sample" key={`${sample.speaker_label}-${index}`}>
                    <div><strong>{sample.speaker_label}</strong><time>{sample.sent_at ? new Date(sample.sent_at).toLocaleString() : "无时间戳"}</time></div>
                    <p>{sample.text}</p>
                  </article>
                ))}
              </div>

              {selectedSource.status === "pending_review" ? (
                <div className="import-confirm-row">
                  <span>归档只会在确认后写入本地消息库。</span>
                  <button className="primary-button" type="button" disabled={!connected || busy || !canApprove} onClick={() => void confirmImport()}>
                    确认映射并导入 <span aria-hidden="true">→</span>
                  </button>
                </div>
              ) : (
                <div className="import-approved-note">该来源已导入。未映射发言人的消息未参与 A/B 画像。</div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
