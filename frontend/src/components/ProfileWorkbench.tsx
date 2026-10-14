import { useCallback, useEffect, useMemo, useState } from "react";
import {
  analyzeProfile,
  getProfile,
  listProfiles,
  publishProfile,
  reviewTrait,
} from "../api/client";
import type { ProfileVersion, ProfileVersionSummary, RoleProfile } from "../types";

interface ProfileWorkbenchProps {
  roles: RoleProfile[];
  connected: boolean;
}

const categoryLabels: Record<string, string> = {
  fact: "事实",
  personality_tendency: "性格倾向",
  language_style: "语言表现",
  contextual_behavior: "情境表现",
};

const statusLabels: Record<string, string> = {
  pending: "待审核",
  accepted: "已接受",
  rejected: "已拒绝",
  draft: "草稿",
  approved: "当前版本",
  superseded: "历史版本",
};

export function ProfileWorkbench({ roles, connected }: ProfileWorkbenchProps) {
  const [roleId, setRoleId] = useState("role_a");
  const [versions, setVersions] = useState<ProfileVersionSummary[]>([]);
  const [profile, setProfile] = useState<ProfileVersion | null>(null);
  const [descriptions, setDescriptions] = useState<Record<string, string>>({});
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selectedRole = useMemo(
    () => roles.find((role) => role.id === roleId),
    [roles, roleId],
  );

  const refreshVersions = useCallback(async (preferredId?: string) => {
    const nextVersions = await listProfiles(roleId);
    setVersions(nextVersions);
    const nextId = preferredId ?? nextVersions[0]?.id;
    if (nextId) {
      setProfile(await getProfile(roleId, nextId));
    } else {
      setProfile(null);
    }
    setDescriptions({});
    setReviewNotes({});
  }, [roleId]);

  useEffect(() => {
    let active = true;
    setError(null);
    setNotice(null);
    setProfile(null);
    setVersions([]);
    setDescriptions({});
    setReviewNotes({});
    listProfiles(roleId)
      .then(async (nextVersions) => {
        if (!active) return;
        setVersions(nextVersions);
        if (nextVersions[0]) {
          const nextProfile = await getProfile(roleId, nextVersions[0].id);
          if (active) setProfile(nextProfile);
        }
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "读取画像失败。");
      });
    return () => {
      active = false;
    };
  }, [roleId]);

  async function runAnalysis() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await analyzeProfile(roleId);
      await refreshVersions(created.id);
      setNotice("已生成新的本地统计草稿；请核对每项观察及其聊天证据。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "生成画像草稿失败。");
    } finally {
      setBusy(false);
    }
  }

  async function decideTrait(traitId: string, status: "accepted" | "rejected") {
    if (!profile) return;
    setBusy(true);
    setError(null);
    try {
      const trait = profile.traits.find((item) => item.id === traitId);
      await reviewTrait(roleId, profile.id, traitId, {
        status,
        description: descriptions[traitId] ?? trait?.description ?? "",
        reviewer_note: reviewNotes[traitId] ?? "",
      });
      await refreshVersions(profile.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存审核结果失败。");
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!profile) return;
    setBusy(true);
    setError(null);
    try {
      await publishProfile(roleId, profile.id);
      await refreshVersions(profile.id);
      setNotice("画像版本已发布。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "发布画像失败。");
    } finally {
      setBusy(false);
    }
  }

  async function selectVersion(versionId: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setProfile(await getProfile(roleId, versionId));
      setDescriptions({});
      setReviewNotes({});
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "读取画像版本失败。");
    } finally {
      setBusy(false);
    }
  }

  const editable = profile?.status === "draft";
  const hasPendingTraits = profile?.traits.some((trait) => trait.review_status === "pending") ?? true;
  const hasAcceptedTraits = profile?.traits.some((trait) => trait.review_status === "accepted") ?? false;
  const canPublish = Boolean(editable && !hasPendingTraits && hasAcceptedTraits);

  return (
    <section className="profile-workbench" aria-labelledby="profile-heading">
      <div className="profile-header">
        <div className="section-heading section-heading--compact">
          <span className="section-index">06</span>
          <div>
            <h2 id="profile-heading">角色画像与证据</h2>
            <p>{selectedRole?.label ?? "选择角色"} · 逐项审核后才会发布</p>
          </div>
        </div>
        <div className="profile-controls">
          <div className="role-switch" role="group" aria-label="选择画像角色">
            {roles.map((role) => (
              <button
                className={roleId === role.id ? "is-selected" : ""}
                type="button"
                key={role.id}
                onClick={() => setRoleId(role.id)}
                disabled={busy}
              >
                {role.label}
              </button>
            ))}
          </div>
          <button
            className="secondary-button"
            type="button"
            onClick={() => void runAnalysis()}
            disabled={!connected || busy}
          >
            {busy ? "处理中…" : "生成统计草稿"}
          </button>
        </div>
      </div>

      <div className="analysis-disclosure">
        <span className="disclosure-mark">i</span>
        <span>当前分析器只统计消息长度与问句比例，不判断人格，也不推断音色或语调。</span>
        {profile && <span className="analyzer-label">{profile.analyzer}</span>}
      </div>

      {error && <div className="error-banner" role="alert">{error}</div>}
      {notice && <div className="notice-banner" role="status">{notice}</div>}

      <div className="profile-version-row">
        <label htmlFor="profile-version">画像版本</label>
        <select
          id="profile-version"
          value={profile?.id ?? ""}
          onChange={(event) => void selectVersion(event.target.value)}
          disabled={versions.length === 0 || busy}
        >
          {versions.length === 0 && <option value="">暂无画像版本</option>}
          {versions.map((version) => (
            <option value={version.id} key={version.id}>
              v{version.version} · {statusLabels[version.status]} · {version.sample_count} 条样本
            </option>
          ))}
        </select>
        {profile && <span className="sample-count">样本 {profile.sample_count}</span>}
      </div>

      {!profile ? (
        <div className="profile-empty">
          <span className="empty-mark" aria-hidden="true">◎</span>
          <p>该角色还没有画像草稿。至少需要 3 条已审核并映射给该角色的消息。</p>
        </div>
      ) : (
        <>
          <div className="trait-list">
            {profile.traits.map((trait) => (
              <article className="trait-item" key={trait.id}>
                <div className="trait-title-row">
                  <div className="trait-heading">
                    <span className="trait-category">{categoryLabels[trait.category] ?? trait.category}</span>
                    <h3>{trait.key === "message_length_median" ? "消息长度" : trait.key === "question_ratio" ? "问句比例" : trait.key}</h3>
                  </div>
                  <span className={`review-state review-state--${trait.review_status}`}>
                    {statusLabels[trait.review_status]}
                  </span>
                </div>
                <label className="field-label" htmlFor={`trait-${trait.id}`}>观察描述</label>
                <textarea
                  id={`trait-${trait.id}`}
                  value={descriptions[trait.id] ?? trait.description}
                  onChange={(event) => setDescriptions((current) => ({ ...current, [trait.id]: event.target.value }))}
                  rows={2}
                  disabled={!editable || busy}
                />
                <div className="trait-meta">
                  <span>样本支撑度 {Math.round(trait.confidence * 100)}%</span>
                  <details>
                    <summary>查看证据 · {trait.evidence.length}</summary>
                    <div className="evidence-list">
                      {trait.evidence.map((evidence) => (
                        <blockquote key={evidence.message_id}>
                          <p>“{evidence.excerpt}”</p>
                          <footer>{evidence.speaker_label} · {evidence.rationale}</footer>
                        </blockquote>
                      ))}
                    </div>
                  </details>
                </div>
                {editable && (
                  <div className="trait-review-row">
                    <input
                      aria-label="审核备注"
                      placeholder="审核备注（可选）"
                      value={reviewNotes[trait.id] ?? ""}
                      onChange={(event) => setReviewNotes((current) => ({ ...current, [trait.id]: event.target.value }))}
                    />
                    <button type="button" className="reject-button" disabled={busy} onClick={() => void decideTrait(trait.id, "rejected")}>
                      拒绝
                    </button>
                    <button type="button" className="accept-button" disabled={busy} onClick={() => void decideTrait(trait.id, "accepted")}>
                      接受
                    </button>
                  </div>
                )}
              </article>
            ))}
          </div>
          {editable && (
            <div className="publish-row">
              <span>
                {hasPendingTraits
                  ? "完成所有特征审核后可发布"
                  : hasAcceptedTraits
                    ? "发布后该画像版本将作为当前角色画像"
                    : "至少接受一项有证据支撑的特征后才能发布"}
              </span>
              <button type="button" className="primary-button" onClick={() => void publish()} disabled={busy || !canPublish}>
                发布画像版本 <span aria-hidden="true">→</span>
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
