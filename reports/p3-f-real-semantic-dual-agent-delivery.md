# P3-F：真实语义画像与双角色模拟端到端验收报告

作者：valen MPF
执行日期：2026-10-17 至 2026-10-18（Asia/Shanghai）

## 1. 当前结论

P3-F 已完成真实 Role Agent 接入、逐轮画像/Provider 快照校验、脱敏调用追踪、前端显式模式选择，以及固定合成消息经真实 DeepSeek 进入候选、审核、准入、正式发布和 A/B 对话的完整链路。真实 Provider 为 `deepseek`，模型为服务端目录已验证的 `deepseek-v4-pro`。

受控真实聊天阶段尚未执行。按 P3-F 的新增授权要求，已经向用户输出本次单文件、角色映射、来源门禁、未知安全标记和有界外发策略，正在等待针对本次 P3-F 外发的明确确认。因此“复合”主题真实聊天画像和 52 轮对话当前为 `0/52`，本报告不把合成验收或 Mock 记录描述为该目标已完成。

## 2. 基线与工作区

- 仓库：`MaNongkuxingseng/wechat-character-lab`
- 分支：`feature/p2b-workspace-updates`
- 起始 HEAD：`37591fea5f09a63a28dc6e195dcf6d65e2b08d84`
- 起始远端：`origin/feature/p2b-workspace-updates` 与 HEAD 一致。
- P3-F 实现以单一 checkpoint commit 交付，提交信息为 `feat(p3-f): 接入真实 dual-role agent 与 synthetic acceptance`。
- 执行前已有未跟踪内容：两个 P3-D 临时目录、三份 P3-D 报告；均未删除、清理或覆盖。
- P3-E.1 报告和三个规划文件的未提交追加得到保留。
- 没有运行 `git reset`、`git clean`、rebase；没有连接正式数据库。

## 3. 实际调用链

```text
approved Source + explicit sender mapping + security provenance
  -> source_contract.analyze_and_persist_approved_source()
  -> resolve_provider_config(db).semantic_config()
  -> OpenAICompatibleSemanticAnalyzer / profile-semantic-v1
  -> candidate_persistence (role/evidence/source validation)
  -> candidate_review -> admission -> formal trait review -> publish
  -> consumer.build_role_context()
  -> POST /api/sessions (provider_mode=mock|llm)
  -> session provider/profile snapshots
  -> deterministic Director (A/B rotation)
  -> RealRoleAgent -> OpenAICompatibleLLMProvider
  -> Turn + profile.context_used + turn/message events
```

真实 Agent 不读取候选表和原始证据正文。它只接收已发布画像 consumer 输出的 claim、主题、导演意图和最近 6 条 Turn。每轮先重新构建正式画像上下文；来源撤销、证据失效、画像版本/trait 集变化或 Provider 配置摘要变化都会阻断生成。

## 4. 实现边界

- `backend/app/providers/openai_compatible.py`：真实 Chat Completions 请求、2 MiB 响应上限、超时和错误分类；不自动重试，避免重复计费/回复。
- `backend/app/agents/real_agent.py`：角色隔离系统提示；只生成当前角色的一条回复。
- `backend/app/api/sessions.py`、`backend/app/schemas/session.py`：新增显式 `provider_mode=mock|llm`。默认仍为 Mock；真实模式要求已配置、对话开关开启、连接测试与当前配置摘要一致。
- `backend/app/core/orchestrator.py`：冻结并复核 Provider/model/config digest 和 A/B 画像快照；成功事件记录 provider、model、耗时、trace ID、画像版本和 trait IDs；失败写 `generation.failed`，不回退 Mock。
- `backend/app/api/events.py`：分类返回真实 Provider 错误并进入 `error` 终态。
- `backend/app/api/providers.py`：状态 API 如实报告真实 Agent 已实现及当前可用性。
- `backend/app/profiles/jsonl_service.py`：接受 `authentication_failed`、`model_unavailable` 合法失败状态，防止真实故障被误报为输出契约非法。
- `backend/app/api/imports.py`、`backend/app/schemas/imports.py`：已批准来源预览返回持久化角色映射，修复 UI 显示“不映射”但数据库实际已映射的不一致。
- `frontend/src/`：新增 Mock/真实 LLM 模式和轮数输入，显示真实 Provider 状态，更新 Provider 页面真实 Agent 可用语义。
- `backend/scripts/p3f_synthetic_acceptance.py`：仅接受显式隔离 SQLite 和同目录 JSON 输出；只创建固定合成消息，不读取 Inbox。
- `README.md`：更新真实会话配置、快照、失败和隐私契约。

没有新增对话表或 migration。`sessions.settings` 保存模式及快照，`session_events.payload` 保存逐轮脱敏追踪，复用现有唯一序号约束。

## 5. 真实 Provider 合成全链路

隔离路径：`%TEMP%/wechat-character-lab-p3f-acceptance-20261017/`。Provider 配置数据库由 P3-E.1 隔离数据库复制，不读取或输出 DPAPI 密钥明文。

执行结果：

- 固定合成消息：A/B 各 4 条，共 8 条。
- 语义状态：`ready`。
- 候选：16 项（Semantic 与 Observable 合计）。
- 证据映射：8 条，映射问题 0，unmatched 0。
- 明确审核/准入/正式发布：A/B 各选择 1 项证据完整、无冲突的语义候选，各发布 1 个 approved 正式版本。
- 真实对话冒烟：4/4 成功，A/B 各 2 轮，模型 `deepseek-v4-pro`；逐轮画像版本和 trait ID 相互独立。
- 单轮耗时：5,879 ms、6,377 ms、11,717 ms、13,865 ms。
- Provider 失败：0；Mock 回退：0。
- 脱敏摘要：`%TEMP%/wechat-character-lab-p3f-acceptance-20261017/summary.json`。

脚本中的审核身份仅代表固定合成验收决策，不冒充真实聊天的人工作质检。真实样本仍必须通过页面逐项核对和审核。

## 6. 浏览器验收

隔离后端：`http://127.0.0.1:8002`；隔离前端：`http://127.0.0.1:5173/`。

- Provider 页面读取 DeepSeek / `deepseek-v4-pro`，Key 只显示“已配置，不回显”。
- 连接测试、语义协议、语义分析、真实 Role Agent 和 A/B 真实对话均显示可用。
- 页面显式选择“真实 LLM”并创建 2 轮会话：A/B 各 1 轮，状态 `completed`，画像 readiness 均为 `ready`。
- 第二场真实会话完成 A/B 两轮后暂停；暂停态接受用户插话；继续后 A 生成下一轮并响应插话；停止后状态为 `completed`，没有补写额外回复。
- 隔离数据库累计 3 场真实合成会话、10 条 Turn（含 1 条用户插话）、0 条 `generation.failed`、2 条 `generation.cancelled`。
- 候选和正式画像页面可读取真实 Semantic 候选、证据数、模型置信度、审核历史及 approved 正式版本。

完整浏览器输出正文只保留在隔离 SQLite，不复制进 Git 报告。

## 7. 数据与安全

- 未扫描 `data/` 或 `data/inbox/`，未运行 `backend/tests/test_imports.py`。
- 当前真实数据候选文件仅锁定为 `.p3d-ui-inbox-real-20261017/selected-real-sample-attested.zip`；确认前未读取其正文。
- 计划映射：发言人 1 → `role_a`，发言人 2 → `role_b`；不猜测其他发言人。
- 原始 `None` 安全标记必须保持 `None`。只有有效来源可信声明明确覆盖且校验通过时才可放行；显式不安全或冲突标记拒绝。
- Git diff 和文本日志未发现 Key、Authorization header 或 `sk-` 形式凭据。
- 隔离数据库包含 DPAPI 密文和合成生成正文，位于 `%TEMP%`，不会暂存或提交。

## 8. 自动化与工程检查

已实际执行：

```text
cd backend
uv run pytest tests/test_dialogue_provider.py tests/test_m2_profile_conversation.py tests/test_provider_configuration.py -q
20 passed；首次为 19 passed / 1 failed，修正配置变化错误分类后复测通过。

uv run pytest tests --ignore=tests/test_imports.py -q
149 passed, 6 warnings（最终重跑）。

uv run pytest tests/test_p3d_semantic_lifecycle.py tests/test_m2_profile_conversation.py tests/test_dialogue_provider.py -q
19 passed, 2 warnings。

uv run pytest tests/test_dialogue_provider.py -q
7 passed, 2 warnings。

uv run ruff check .
通过。

cd frontend
pnpm typecheck
通过。

pnpm build
通过，39 modules transformed。

git diff --check
通过。
```

警告均为现有 Starlette/httpx、pytest-asyncio 和 Alembic deprecation warning。

## 9. 失败记录与限制

- 合成验收脚本首次以文件路径启动，Python 未包含 `backend/` 模块路径；改用 `python -m scripts.p3f_synthetic_acceptance`。该次未联网。
- 第二次在 Source/Message 同批 flush 时触发 SQLite 外键约束，事务整体回滚；增加 Source 显式 flush 后通过。该次未联网。
- 标准库同步 HTTP 请求通过 `asyncio.to_thread` 执行。取消会阻止结果持久化并记录取消事件，但已经发出的底层 HTTP 请求无法由 Python 线程强制终止，可能仍在 Provider 端完成；当前以“不自动重试、取消后不写 Turn”降低重复计费风险。
- 真实聊天候选、人工审核、正式发布和“复合”52 轮均等待本次外发确认，不能标记完成。
- GPT-SoVITS、ASR、TTS、语音克隆和 WeChatBridge 不在 P3-F 范围。

## 10. 52 轮状态

| 验收项 | 当前结果 |
|---|---:|
| 真实 Provider + 合成画像 | 通过 |
| 真实 Provider + 合成 A/B 对话 | 通过，冒烟 4/4 |
| 浏览器真实 LLM 控制流 | 通过 |
| 真实聊天语义画像 | 未执行，等待本次外发确认 |
| “复合”真实 LLM 52 轮 | 0/52 |
| 本地完整明文 52 轮报告 | 未生成 |

P3-F 当前不能标记完整交付。只有用户确认本次受控真实文本外发，随后真实 A/B 画像通过证据审核并发布，且 52 轮真实 Role Agent 对话完成后，才能更新本节并完成最终提交。
