# P2-C 合成数据端到端验证

作者：valen MPF
日期：2026-10-16（Asia/Shanghai）

## 1. 范围与执行边界

本阶段验证人工合成的规范化消息、画像信号、严格适配、候选输出和拒绝清单之间的可追溯链路。

- 已检查 `AGENTS.md`、当前 Git 状态、P1/P1.1、P2-A、P2-B、P2-B.1、P2-B.2、P2-B.3 报告及相关源码。
- 未读取、枚举或扫描 `data/`，未读取真实聊天正文、音频、视频、图片或凭据。
- 未调用网络、外部 API、Chat2Profile、ChatAnalysis.SKILL、ASR/TTS 或模型；未安装依赖。
- 未修改 Mock Agent 实现和测试断言；未修改 Alembic 迁移版本脚本。
- 保留所有既有未提交修改，未提交或推送。

## 2. 实际检查文件

### 代码与测试

- `backend/app/profiles/synthetic_adapter.py`
- `backend/tests/test_synthetic_adapter.py`
- `backend/tests/test_contracts.py`
- `backend/tests/test_migrations.py`
- `backend/app/ingestion/wechat_normalizer.py`
- `backend/tests/test_wechat_normalizer.py`
- `scripts/convert_wechatauto_export.py`
- `backend/alembic/env.py`

### 报告

- `reports/preflight.md`
- `reports/p1-data-normalization.md`
- `reports/p1.1-bom-fix.md`
- `reports/p2-tool-audit.md`
- `reports/p2-b-synthetic-validation.md`
- `reports/p2-b1-regression-triage.md`
- `reports/p2-b2-validation.md`
- `reports/p2-b3-regression-stability.md`

本地源码未提供可验证的第三方版本提交信息；本阶段没有下载或安装第三方工具。

## 3. 合成数据和测试覆盖

复用 `backend/tests/test_synthetic_adapter.py` 中已有的人工样本，并新增
`test_synthetic_end_to_end_keeps_auditable_candidates_and_rejections`。样本覆盖：

- A/B 两个角色、显式 `sender_role_map`；
- 正向偏好、负向偏好、犹豫表达和较新状态变化；
- 正向证据与反向证据；
- 有效 UTC 时间、缺失/非法 `parsed_utc` 状态和 naive 时间；
- 错误引文、不存在 ID、重复消息 ID；
- 图片媒体占位、AI 消息、缺失安全标记和非布尔安全标记；
- 空证据、非法证据元素、重复证据和正反证据交叉重复；
- 缺失置信度和日志脱敏。

所有内容均为测试文件中的人工构造值，没有从 `data/` 抽样、复制或改写。

## 4. 端到端链路与不变量

数据流为：

```text
synthetic normalized messages
  -> message_id 一对多索引
  -> signal evidence_ids / counter_evidence_ids 严格解析
  -> 唯一 ID、文本资格、显式角色、引文、时间和安全标记校验
  -> ProfileCandidate 或 UnmatchedEvidence
```

验证结论：

- 每个有效候选至少有一个证据引用；引用只能唯一映射到输入消息，重复 ID 进入 `ambiguous_message_id`。
- 引文使用指定消息正文的精确包含匹配；错误引文拒绝整个候选，不使用相似文本或其他消息替代。
- 角色归属只来自 `sender_role_map`；未知角色或角色不匹配拒绝，不根据正文猜测。
- 正向和反向证据分别保留；同一 ID 同时出现在两侧时以 `duplicate_evidence_reference` 拒绝，不降级为只有正向证据。
- 时序信号要求 `timestamp_status == "parsed_utc"`、时间可解析并明确带时区；缺失状态、非法状态、非法时间和 naive timestamp 均拒绝。
- `is_ai_generated`、`is_system` 必须显式存在且为 `bool`；`"false"`、数字、`None` 等不会转换为 `False`。
- 缺失置信度输出 `None`（unknown）；不会伪造默认高置信度。
- 日志仅输出候选和拒绝数量；已有断言确认不包含合成正文、引文或消息 ID。

## 5. 确定性与拒绝行为

新增端到端测试验证：

- 相同输入重复运行，候选和拒绝清单完全一致。
- 消息列表反转、signal 字典键插入顺序反转、角色映射键顺序反转，不改变输出。
- 候选按稳定 `profile_item_id` 排序。
- 每个拒绝 signal 都能在 `unmatched_evidence` 中找到明确原因。
- 统计数量由实际 `candidates` 和 `unmatched_evidence` 结果产生，日志不泄露内容。

当前 `profile_item_id` 是 subject、category、规范化 claim、正向证据 ID 集合和反向证据 ID 集合的 SHA-256 截断值，语义是“画像候选快照”，不是跨证据版本的长期 trait identity；证据集合变化会产生新 ID。

## 6. 规范化字段契约核对

`backend/app/ingestion/wechat_normalizer.py` 的实际输出如下：

| 字段 | 实际情况 | 适配器依赖/测试覆盖 |
|---|---|---|
| `message_id` | 实际生成，来源 ID 或确定性 hash，冲突追加后缀 | 适配器依赖；合成测试覆盖唯一/重复 ID |
| `source_local_id` | 实际生成，可为 null | 当前适配器不依赖；标准化测试覆盖来源字段 |
| `source_server_id` | 实际生成，可为 null | 当前适配器不依赖；标准化测试覆盖来源字段 |
| `timestamp` | 实际生成 UTC ISO 字符串或 null | 时序适配依赖；合成测试覆盖合法/非法/naive |
| `timestamp_status` | 实际生成 `parsed_utc/missing/invalid/out_of_range` | 时序适配严格依赖；测试覆盖 |
| `sender` | 实际生成，缺失时为 null | 角色适配依赖；合成测试显式映射 |
| `message_type` | 实际生成文本/媒体/unknown 映射 | 文本资格依赖；合成测试覆盖媒体/AI |
| `content` | 实际保留字符串、null 或缺失状态 | 文本资格和引文依赖；合成测试覆盖 |
| `content_status` | 实际生成 `present/empty/missing/not_text` | 文本资格依赖；合成测试覆盖 present/缺失媒体 |
| `source_file` | 实际生成来源文件标识 | 当前适配器不依赖；标准化契约存在 |
| `source_message_ref` | 实际生成 `messages[n]` | 当前适配器不依赖；用于上游审计 |
| `is_ai_generated` | **规范化器当前不生成** | 适配器严格要求；合成消息显式提供，生产契约待补齐 |
| `is_system` | **规范化器当前不生成** | 适配器严格要求；合成消息显式提供，生产契约待补齐 |

这是确认的端到端契约缺口：直接把当前规范化器输出送入适配器会因安全标记缺失而拒绝候选。本阶段不将缺失值推断为 `False`，也不擅自修改规范化器；进入真实画像前必须增加明确的安全标记 enrichment 规则并补充测试。

## 7. 实际测试命令与结果

### 合成适配器

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_synthetic_adapter.py
```

结果：`8 passed, 2 warnings`。

### 迁移与适配器正向顺序

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles backend/tests/test_synthetic_adapter.py
```

结果：`9 passed, 3 warnings`。

### 适配器与迁移反向顺序

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_synthetic_adapter.py backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles
```

结果：`9 passed, 3 warnings`。

### 受限后端回归

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests --ignore=backend/tests/test_imports.py
```

结果：`48 passed, 1 failed, 3 warnings`。唯一失败是
`backend/tests/test_contracts.py::test_mock_agents_keep_director_and_role_output_separate` 的“复合”字面量断言；按 P2-B.3 决策，本阶段未修改 Mock Agent 或测试断言。

未运行不带 `--ignore` 的完整 `backend/tests`，因为 `test_imports.py` 会扫描 `data/inbox`，与本阶段不得读取真实数据的边界冲突。

### Ruff 与 Git 检查

```text
backend\\.venv\\Scripts\\ruff.exe check backend/app/profiles/synthetic_adapter.py backend/tests/test_synthetic_adapter.py backend/app/ingestion/wechat_normalizer.py backend/tests/test_wechat_normalizer.py backend/tests/test_migrations.py backend/alembic/env.py
git diff --check
```

Ruff：`All checks passed!`。`git diff --check`：通过，仅有 CRLF 转换提示。

## 8. 工作区状态

当前分支：`feature/p2b-workspace-updates`。

本阶段新增或修改：

- `backend/tests/test_synthetic_adapter.py`：新增端到端合成断言。
- `backend/alembic/env.py`：P2-B.3 logger 隔离修复，保留在工作区。
- `reports/p2-c-synthetic-e2e-validation.md`：本报告。

既有未提交修改和 P2-B.2/P2-B.3 报告均保留；未提交、未推送。未纳入任何真实数据、音频、视频、凭据或数据库文件。

## 9. 风险与下一步

- 规范化器缺少 `is_ai_generated`/`is_system` 是进入真实画像链路前的阻断性契约问题，不能通过默认值静默放宽。
- Mock Agent 主题字面量测试仍需产品决定“主题相关”还是“必须回显关键词”。
- `test_imports.py` 的数据耦合测试尚未运行，不能宣称完整后端回归通过。
- 当前验证只证明合成数据契约和适配器边界，不证明真实聊天画像质量或任何外部工具兼容性。

P2-C 已完成，现停止等待人工审核；不自动进入数据库/API 开发、真实聊天分析、第三方工具接入、模型安装或语音克隆。
