import { useCallback, useEffect, useState } from "react";
import {
  getProviderConfig,
  getProviderStatus,
  saveProviderConfig,
  testProviderConnection,
  testSemanticProtocol,
} from "../api/client";
import type { ProviderConfig, ProviderStatus, ProviderTestResult } from "../types";

const initial = {
  provider_type: "deepseek",
  endpoint: "https://api.deepseek.com",
  model: "deepseek-v4-pro",
  timeout_seconds: 60,
  semantic_enabled: false,
  allow_message_content: false,
  dialogue_enabled: false,
};

const statusLabels: Record<string, string> = {
  not_tested: "尚未测试",
  success: "测试成功",
  configuration_missing: "配置不完整",
  invalid_url: "URL 无效",
  endpoint_must_be_base_url: "请填写基础地址",
  authentication_failed: "鉴权失败",
  model_unavailable: "模型不可用",
  timeout: "请求超时",
  dns_error: "DNS 解析失败",
  tls_error: "TLS 验证失败",
  network_error: "网络连接失败",
  rate_limited: "请求受限",
  provider_error: "服务端错误",
  invalid_response: "响应格式无效",
  invalid_output: "语义协议响应不合规",
  provider_disabled: "分析功能未启用",
  provider_rejected_request: "服务拒绝请求",
};

function label(value: string) {
  return statusLabels[value] ?? value;
}

export function ProviderWorkbench() {
  const [config, setConfig] = useState<ProviderConfig | null>(null);
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [form, setForm] = useState(initial);
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const reload = useCallback(async () => {
    setBusy("reload");
    setError("");
    try {
      const [loaded, currentStatus] = await Promise.all([getProviderConfig(), getProviderStatus()]);
      setConfig(loaded);
      setStatus(currentStatus);
      setForm({
        provider_type: loaded.provider_type || initial.provider_type,
        endpoint: loaded.endpoint || initial.endpoint,
        model: loaded.model || initial.model,
        timeout_seconds: loaded.timeout_seconds || initial.timeout_seconds,
        semantic_enabled: loaded.semantic_enabled,
        allow_message_content: loaded.allow_message_content,
        dialogue_enabled: loaded.dialogue_enabled,
      });
      setApiKey("");
      setClearKey(false);
      setNotice("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "配置加载失败");
    } finally {
      setBusy("");
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  async function save() {
    setBusy("save");
    setError("");
    setNotice("");
    try {
      const saved = await saveProviderConfig({
        ...form,
        ...(apiKey ? { api_key: apiKey } : {}),
        clear_api_key: clearKey,
      });
      setConfig(saved);
      setApiKey("");
      setClearKey(false);
      setNotice("配置已保存；连接和语义协议测试状态已重置。");
      setStatus(await getProviderStatus());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "配置保存失败");
    } finally {
      setBusy("");
    }
  }

  async function runTest(kind: "connection" | "semantic") {
    setBusy(kind);
    setError("");
    setNotice("");
    try {
      const result: ProviderTestResult = kind === "connection"
        ? await testProviderConnection()
        : await testSemanticProtocol();
      setNotice(testSummary(result));
      setConfig(await getProviderConfig());
      setStatus(await getProviderStatus());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Provider 测试失败");
    } finally {
      setBusy("");
    }
  }

  function update<K extends keyof typeof initial>(key: K, value: (typeof initial)[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  return (
    <section className="provider-workbench" aria-labelledby="provider-heading">
      <header className="provider-header">
        <div className="section-heading">
          <span className="section-index">LLM</span>
          <div><h2 id="provider-heading">Provider 配置</h2><p>凭据保存在本机受保护存储中；真实对话必须在新建会话时显式选择。</p></div>
        </div>
        <button className="secondary-button" type="button" onClick={() => void reload()} disabled={Boolean(busy)} title="重新加载配置">重新加载</button>
      </header>

      {error && <div className="error-banner" role="alert">{error}</div>}
      {notice && <div className="provider-notice" role="status">{notice}</div>}

      <div className="provider-grid">
        <form className="provider-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
          <label>Provider 类型
            <select value={form.provider_type} onChange={(event) => update("provider_type", event.target.value)}>
              <option value="deepseek">DeepSeek</option>
              <option value="openai">OpenAI</option>
              <option value="openai_compatible">OpenAI 兼容服务</option>
            </select>
          </label>
          <label>基础 Endpoint
            <input value={form.endpoint} onChange={(event) => update("endpoint", event.target.value)} autoComplete="url" />
          </label>
          <label>模型 ID
            <input value={form.model} onChange={(event) => update("model", event.target.value)} />
          </label>
          <label>API Key <span>{config?.api_key_configured && !clearKey ? "已配置，不回显" : "未配置"}</span>
            <input
              type="password"
              value={apiKey}
              onChange={(event) => { setApiKey(event.target.value); setClearKey(false); }}
              autoComplete="new-password"
              placeholder={config?.api_key_configured && !clearKey ? "输入新 Key 以更换" : "粘贴本地 Provider Key"}
            />
          </label>
          <div className="provider-inline-actions">
            <button className="secondary-button" type="button" onClick={() => { setClearKey(true); setApiKey(""); }} disabled={!config?.api_key_configured || Boolean(busy)}>清除已保存 Key</button>
            <label className="provider-timeout">超时（秒）
              <input type="number" min={1} max={120} value={form.timeout_seconds} onChange={(event) => update("timeout_seconds", Number(event.target.value))} />
            </label>
          </div>

          <label className="provider-toggle"><input type="checkbox" checked={form.semantic_enabled} onChange={(event) => update("semantic_enabled", event.target.checked)} />启用语义画像分析</label>
          <label className="provider-toggle"><input type="checkbox" checked={form.allow_message_content} onChange={(event) => update("allow_message_content", event.target.checked)} />允许授权来源的真实正文外发</label>
          <div className="provider-warning">
            开启正文外发会把经授权范围内的聊天正文发送到外部模型。仍须逐来源审核、可信声明、语义传输授权、明确 A/B 映射及有界样本；此开关不会自动批准来源或启动分析。
          </div>
          <label className="provider-toggle"><input type="checkbox" checked={form.dialogue_enabled} onChange={(event) => update("dialogue_enabled", event.target.checked)} />期望启用 A/B 真实对话</label>
          <p className="provider-unavailable">开启后仍不会自动外发；需通过连接测试，并在新建会话时显式选择真实 LLM。</p>

          <div className="provider-actions">
            <button className="primary-button" type="submit" disabled={Boolean(busy) || !form.endpoint.trim() || !form.model.trim()}>{busy === "save" ? "保存中…" : "保存配置"}</button>
            <button className="secondary-button" type="button" onClick={() => void runTest("connection")} disabled={Boolean(busy)}>{busy === "connection" ? "连接测试中…" : "测试连接"}</button>
            <button className="secondary-button" type="button" onClick={() => void runTest("semantic")} disabled={Boolean(busy)}>{busy === "semantic" ? "协议测试中…" : "测试画像协议"}</button>
          </div>
        </form>

        <aside className="provider-status-panel" aria-label="Provider 功能状态">
          <div className="provider-status-heading"><h3>运行状态</h3><span className={config?.configured ? "status-pill is-ready" : "status-pill"}>{config?.configured ? "已配置" : "未配置"}</span></div>
          <dl className="runtime-list">
            <div><dt>API Key</dt><dd>{config?.api_key_configured ? "已保护保存" : "未配置"}</dd></div>
            <div><dt>连接测试</dt><dd>{label(config?.connection_test_status ?? "not_tested")}</dd></div>
            <div><dt>语义协议</dt><dd>{label(config?.semantic_test_status ?? "not_tested")}</dd></div>
            <div><dt>语义分析实际可用</dt><dd>{status?.semantic_available ? "是" : "否"}</dd></div>
            <div><dt>真实正文外发前置条件</dt><dd>{status?.message_content_transfer_ready ? "配置就绪，仍需来源授权" : "未就绪"}</dd></div>
            <div><dt>真实 Role Agent</dt><dd>{status?.dialogue_agent_implemented ? "已接入" : "尚未接入"}</dd></div>
            <div><dt>A/B 真实对话</dt><dd>{status?.dialogue_available ? "可用" : "不可用"}</dd></div>
            {config?.env_overrides.map((field) => <div key={field}><dt>环境变量覆盖</dt><dd>{field}</dd></div>)}
          </dl>
          {!config?.configured && <p className="provider-empty-note">表单中的 DeepSeek 值只是待保存目标，不代表 Provider 已配置或可用。</p>}
        </aside>
      </div>
    </section>
  );
}

function testSummary(result: ProviderTestResult) {
  const status = label(result.status);
  const http = result.http_status ? `，HTTP ${result.http_status}` : "";
  const models = result.available_models.length ? `；模型目录返回 ${result.available_models.length} 个模型` : "";
  const signals = result.signal_count === undefined || result.signal_count === null ? "" : `；校验信号 ${result.signal_count} 项`;
  return `${status}${http}${models}${signals}`;
}
