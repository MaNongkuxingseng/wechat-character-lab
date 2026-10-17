# P3-F 真实语义画像与 52 轮真实对话最终验收

作者：valen MPF
执行日期：2026-10-18（Asia/Shanghai）

## 1. 结果结论

本轮真实验收已完成真实 Provider 网络调用、真实样本 A/B 语义分析、候选人工审核、候选准入、正式画像发布以及“复合”主题 52 轮真实 LLM 对话。协议失败不是被静默降级处理，而是定位并修复后重新执行。

- Provider：`deepseek` / `deepseek-v4-pro`
- 隔离数据库：`C:\Users\Administrator\AppData\Local\Temp\wechat-character-lab-p3f-real-20261018\acceptance.db`
- 真实消息：仅使用此前已授权、已批准来源和既定 `发言人 1 -> role_a`、`发言人 2 -> role_b` 映射的有界样本；本报告不包含原始聊天正文。
- 语义分析输入：A 发送 507 条，B 发送 502 条；原始有效文本计数分别为 18,698 / 14,020。
- 候选：30 条（A/B 各 15）；其中真实语义候选 16 条（A/B 各 8），统计候选 14 条。
- 审核：真实语义候选 16 条接受；统计候选 14 条因冲突、缺少人工置信度或不属于本次真实语义发布范围而拒绝。
- 准入：16 条成功。
- 正式发布：16 个候选版本逐项完成 trait review 和 publish；当前 Profile consumer 按既有版本规则读取每个角色最新 approved 版本。
- 对话：`session_id=5ab917a2-0294-40ff-a119-525e22778c17`，52/52 轮成功，A/B 各 26 轮，失败 0，全部 `provider=deepseek`，未使用 Mock 补齐。
- 明文对话文件（不入 Git）：`C:\Users\Administrator\AppData\Local\Temp\wechat-character-lab-p3f-real-20261018\p3f-real-composite-52-dialogue.md`

## 2. 协议校验失败的真实原因

### 2.1 `reasoning_exhausted_before_content`

首次失败时外层 Chat Completions 响应合法，但 `choices[0].message.content` 为空，`reasoning_content` 存在，`finish_reason=length`。原请求 `max_tokens=1200`，DeepSeek reasoning 消耗了 completion budget，未留下 `profile-semantic-v1` JSON。该文本不能作为画像证据或候选输入。

### 2.2 `content_truncated`

关闭 reasoning 后，全量 A 的 `content` 以 JSON 开始但仍以 `finish_reason=length` 结束，JSON 在内容层被截断。此前的 `content_json_decode` 只是最终解析症状，不是角色映射或证据数据库错误。

### 2.3 `semantic_evidence_reference_invalid`

B 的一次响应 JSON 语法合法，但引用了不属于本次发送样本的 evidence ID。第二次对同一 B 输入成功，证明是模型输出的瞬时证据引用幻觉；不能接受该响应或将其转为候选。

### 2.4 候选数量为 0 的第二个根因

真实消息保留了正确的 `is_ai_generated=None` / `is_system=None`。候选适配器此前把 `None` 一律判为 `invalid_security_flag`，导致即使语义 Provider 成功，signal 也在适配阶段全部丢弃。这不是把未知改成安全，而是错误地把未知当成拒绝。现已改为：只有完整可信人工声明、`unknown:*` provenance 且无已确认不安全标记时，才允许有界证据回指；原始 `None` 仍保持不变。

## 3. 实施修复

- `semantic_analyzer.py`
  - 请求增加 `thinking: {"type": "disabled"}`，避免 reasoning 吃完严格 JSON 的 completion budget。
  - `max_tokens` 从 1200 提升到 4096。
  - 增加空 content、reasoning 耗尽、length 截断、外层 JSON 和内容 JSON 的脱敏错误分类。
  - 对结构/证据校验失败最多进行 2 次有限重试，不放宽 schema、角色或 evidence 校验。
  - Prompt 限制最多 8 个高信号 trait，缩短 claim/rationale/uncertainty。
  - 记录 `semantic_retry_count`，不记录 reasoning 或聊天正文。
- `synthetic_adapter.py`
  - 支持有完整人工可信声明的未知安全标记进入有界证据适配；不改写 `None`。
- 回归测试
  - 覆盖 reasoning 预算耗尽、JSON 截断、非法 evidence 重试和未知安全标记人工声明。

## 4. 画像生命周期实际结果

最新真实快照：`27017c72-fcaf-4b0e-b704-412d83ee742a`。A/B 各 8 个语义 trait 均为 `model_inferred`，有 inference basis、matched supporting evidence、无 counter evidence、`conflict_status=none`。14 个统计候选未被静默提升为真实语义画像。

候选审核使用 reviewer ID `valen-mpf-real-review`，每个接受项均写入 reviewer confidence 和审核说明；拒绝项也写入拒绝原因。准入仅处理 accepted、具备置信度、证据有效且角色一致的候选。

现有正式画像模型的发布规则是“同一角色最新 approved 版本取代旧 approved 版本”。因此本次 16 个候选均有独立的准入/发布审计记录，但最终 consumer 按当前仓库契约读取每个角色最新 approved 版本；52 轮会话快照固定记录了当时实际使用的 A/B 版本和 trait ID，未发生跨角色串扰。

## 5. 52 轮真实对话验收

- 创建参数：topic=`复合`、turn_limit=52、provider_mode=`llm`、role_ids=`role_a`,`role_b`。
- 冒烟：前 2 轮真实成功，A/B 各收到自己的 profile version 和 trait ID。
- 完整执行：52 条 `message.created` 事件，A=26、B=26，严格交替；所有事件 `generation_status=success`、`provider=deepseek`、模型为 `deepseek-v4-pro`。
- 会话终态：`completed`；无失败轮次、无 Mock 回退、无用户插话、无重复 Turn。
- 每轮事件保留 role、turn、profile version、trait IDs、trace ID、latency 和 token 统计；不保存 API key、认证头或原始画像证据正文。

## 6. 测试与检查

本轮代码回归命令和结果：

| 命令 | 结果 |
|---|---|
| `cd backend; uv run pytest tests/test_semantic_analyzer.py tests/test_security_flags.py -q` | 11 + 28 passed |
| 真实隔离 DB 候选审核/准入/发布脚本 | 16 accepted / 14 rejected / 16 admitted / 16 published |
| 真实隔离 DB 会话检查 | 52 turns，A/B 各 26，provider 全为 deepseek |
| `uv run pytest tests --ignore=tests/test_imports.py -q` | 157 passed, 6 warnings |
| `uv run ruff check .` | passed |
| `pnpm typecheck` | passed |
| `pnpm build` | passed |
| `git diff --check` | passed |

## 7. 安全与 Git 边界

- 真实数据库和明文 52 轮文件均位于系统临时隔离目录，不进入 Git。
- 未运行 `backend/tests/test_imports.py`，未连接正式业务数据库，未读取音频/视频。
- 报告不包含 API key、认证头、原始聊天正文或模型 reasoning 正文。
- 真实 Provider 失败不会回退 Mock；本次 52 轮未发生失败。
- 工作区已有 `findings.md`、`progress.md`、`task_plan.md` 和历史临时目录均保留，不清理、不覆盖。

## 8. 剩余限制

1. 当前正式画像历史模型按角色保留最新 approved 版本，多个候选的长期聚合仍需后续产品化设计；本轮严格按现有契约执行并记录版本快照。
2. 本次质量验收确认了证据 ID、角色隔离和生命周期门禁，但不将模型推断等同于事实；真实语义质量仍需人工抽查和后续重复运行比较。
3. 本地明文对话仅用于本次人工验收，后续如需保留应采用受控存储和访问审计。
