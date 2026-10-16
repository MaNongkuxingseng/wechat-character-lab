# P2-B 合成数据适配器与证据追溯验证

日期：2026-10-16（Asia/Shanghai）
范围：仅验证标准化消息 JSONL 到统一画像候选结构的最小适配链路。

## 1. 执行边界

- 已读取 `AGENTS.md`、`docs/import-format.md`、P1/P1.1 报告和 `reports/p2-tool-audit.md`。
- 已检查 Git 状态，保留所有既有未提交修改；未清理、回滚、覆盖或提交。
- 未读取 `data/`、真实聊天正文、原始音频、视频或完整媒体数据库。
- 未下载或安装 Chat2Profile、ChatAnalysis.SKILL、模型或第三方依赖。
- 未调用外部 LLM/API、ASR、TTS 或聊天提取工具。

## 2. 新增模块与接口

### 文件

- `backend/app/profiles/synthetic_adapter.py`
  - `adapt_synthetic_signals(messages, signals, *, sender_role_map, updated_at)`：离线适配入口。
  - `ProfileCandidate`：统一候选结构，包含 `profile_item_id`、`subject_id`、`category`、`claim`、`evidence_refs`、`confidence`、`counter_evidence_refs`、`observed_at`、`updated_at`。
  - `UnmatchedEvidence`：拒绝入库的证据引用及原因。
  - `AdaptationResult`：候选和拒绝清单的稳定序列化结果。
- `backend/tests/test_synthetic_adapter.py`
  - 10 条人工构造的标准化消息和 11 个候选信号，仅用于测试适配契约。

### 证据匹配策略

1. 用输入中的原始 `message_id` 建立一对多索引，绝不改写 ID。
2. 只有 ID 存在且唯一、消息是可用文本、发送方经显式 `sender_role_map` 映射到候选 `subject_id` 时，才允许作为证据。
3. 可选 `evidence_quotes`/`counter_evidence_quotes` 必须能在对应消息正文中匹配；不匹配写入 `quote_mismatch`。
4. 不存在、重复 ID、角色不一致、媒体占位、AI/system 标记和引文不匹配均进入 `unmatched_evidence`，不猜测、不生成候选。
5. `requires_temporal=true` 时，所有正反证据都必须具有合法 `timestamp_status=parsed_utc` 和可解析 ISO-8601 时间；否则拒绝为时序证据。
6. 正向候选和负向/反向证据独立保留；较新证据不会覆盖旧证据。
7. `profile_item_id` 对 subject、category、规范化 claim 和证据 ID 集合做稳定 SHA-256 截断；候选和拒绝项按稳定键排序。
8. 缺失或非法置信度输出 `null`，表示 `unknown`，不自动填高置信度。
9. 日志仅输出 candidates/unmatched 数量，不包含消息正文、密钥、媒体字节或证据 ID。

## 3. 合成样本覆盖范围

样本完全人工构造，覆盖：

- 明确正向偏好、明确负向偏好、犹豫表达；
- 同一主题的较新状态变化及旧反证；
- 两个角色和显式角色映射；
- 图片占位消息；
- `is_ai_generated=true` 的 AI 消息；
- 无效时间戳；
- 重复 `message_id`；
- 不存在的证据 ID；
- 引文不匹配；
- 缺少置信度。

## 4. 实际测试结果

### 通过

命令：

```text
backend\.venv\Scripts\ruff.exe check backend/app/profiles/synthetic_adapter.py backend/tests/test_synthetic_adapter.py
```

结果：`All checks passed!`

命令：

```text
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_synthetic_adapter.py
```

结果：`4 passed, 2 warnings`。警告为既有 Starlette/httpx 和 pytest-asyncio 弃用提示。

专项测试确认：

- 原始 ID 和角色映射保持不变；
- 正反证据同时保留；
- 媒体、AI、无效时间、重复 ID、不存在 ID 和错误引文均被拒绝；
- 相同输入和固定 `updated_at` 重复运行结果完全一致；
- 缺失置信度为 `None`；
- 日志不包含合成消息正文或消息 ID。

### 全量回归

命令：

```text
backend\.venv\Scripts\python.exe -m pytest -q backend/tests
```

结果：`49 passed, 2 failed, 2 warnings`。

失败项与本次新增适配器无直接调用关系，尚未归因：

1. `backend/tests/test_contracts.py::test_mock_agents_keep_director_and_role_output_separate`：现有 Mock Agent 文本断言失败。
2. `backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles`：从仓库根目录运行时 Alembic 配置缺少 `script_location`。

本报告不把上述两项描述为本阶段通过，也未修改相关既有模块。

## 5. 未解决问题与进入条件

- 当前模块是候选适配原型，不负责从自然语言自动提取信号，也不写入画像数据库。
- `evidence_quotes` 目前采用简单包含匹配；真实工具的引文需要先转换为稳定消息 ID，歧义时必须拒绝。
- 尚未接入 Chat2Profile 或 ChatAnalysis.SKILL；其源码、许可证和网络边界仍以 P2-A 审查为准。
- 进入下一阶段前，应先人工审核本报告，另行决定是否增加数据库仓储/API；不得直接把未审核候选用于角色提示词。

## 6. 本阶段停止条件

已完成合成数据适配与专项自动化验证。本阶段不读取真实聊天数据、不安装模型、不开始真实画像分析，并在最终 Git 检查后停止等待人工审核。
