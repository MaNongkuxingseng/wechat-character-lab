# P2-B.2 输入校验与迁移测试路径修复验证

日期：2026-10-16（Asia/Shanghai）
范围：仅修复合成适配器输入校验和 Alembic 迁移测试路径；未接入真实画像、数据库/API 或第三方服务。

## 1. 执行边界

- 保留工作区既有未提交修改，未清理、回滚、覆盖或提交。
- 未调用外部 API，未安装依赖，未安装模型，未读取真实聊天正文、音频或视频。
- 诊断过程中一次组合命令误包含现有 `test_imports` 测试；它访问了 `data/inbox` 测试路径并失败，该结果未纳入本阶段验收，之后未再运行该测试。
- 未修改 Mock Agent 及其测试断言。
- 未修改 Alembic 迁移版本脚本；仅修复迁移测试的配置定位。
- 本报告中的“测试通过”仅表示命令实际执行结果，不代表真实聊天数据已验证。

## 2. 修改文件

### `backend/app/profiles/synthetic_adapter.py`

- `evidence_ids` 缺失、空值、非 `list/tuple`、包含空字符串或非字符串元素时拒绝整个候选。
- `counter_evidence_ids` 若显式提供，也执行同样的严格校验；正向与反向集合重叠时拒绝。
- 重复 ID、不存在 ID、重复消息 ID、错误引文、角色不匹配、媒体占位和 AI/system 消息继续进入 `unmatched_evidence`，不会被静默过滤。
- `requires_temporal=true` 时，证据和反证都必须满足 `timestamp_status == "parsed_utc"`，时间字符串必须可解析并带有时区；缺失状态、非法状态、非法时间和 naive timestamp 均拒绝。
- `is_ai_generated`、`is_system` 必须显式存在且为 `bool`；字符串、数字及 `source_metadata` 中的非法同名字段均拒绝，不做隐式类型转换。

### `backend/tests/test_synthetic_adapter.py`

- 增加合成测试，覆盖缺失/空/非法/重复证据字段。
- 增加正向证据与反向证据的严格时序状态及时区测试。
- 增加安全标记缺失、字符串、数字及元数据非法类型测试。
- 保留确定性 ID、排序、正反证据保留、日志脱敏等既有断言。

### `backend/tests/test_migrations.py`

- 使用 `Path(__file__).resolve().parents[1]` 定位 `backend` 目录。
- 通过绝对路径加载 `backend/alembic.ini`，并将 `script_location` 显式设置为真实的 `backend/alembic` 目录。
- 保留迁移表集合及 `role_a`、`role_b` seed 断言。

## 3. 非法输入拒绝矩阵

| 输入 | 结果 | 拒绝原因 |
|---|---|---|
| 缺失 `evidence_ids` | 候选拒绝 | `evidence_field_missing` |
| 空列表、字符串等非列表输入 | 候选拒绝 | `evidence_field_empty_or_invalid` |
| 证据元素为空或非字符串 | 候选拒绝 | `invalid_evidence_reference` |
| 同一证据 ID 重复 | 候选拒绝 | `duplicate_evidence_reference` |
| 正向/反向证据交叉重复 | 候选拒绝 | `duplicate_evidence_reference` |
| 不存在、重复消息 ID | 候选拒绝 | `not_found` / `ambiguous_message_id` |
| 角色不匹配、错误引文 | 候选拒绝 | `role_mismatch` / `quote_mismatch` |
| 图片等媒体占位、AI/system 消息 | 候选拒绝 | `message_not_eligible` |
| 缺失或非法安全标记 | 候选拒绝 | `security_flag_missing` / `invalid_security_flag` |
| 时序状态缺失或非 `parsed_utc` | 候选拒绝 | `invalid_timestamp` |
| naive、非法或不可解析时间 | 候选拒绝 | `invalid_timestamp` |

任何一个声明的证据引用无效，整个 signal 不进入 `candidates`；原始 ID 不会被改写或替换。缺失置信度仍为 `None`（unknown）。

## 4. 实际测试结果

### 适配器与迁移专项

命令：

```text
backend\\.venv\\Scripts\\ruff.exe check backend/app/profiles/synthetic_adapter.py backend/tests/test_synthetic_adapter.py backend/tests/test_migrations.py
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_synthetic_adapter.py backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles
```

结果：

```text
All checks passed!
8 passed, 3 warnings in 0.37s
```

警告来自依赖版本弃用提示，不影响本次断言。

### 全量后端回归

命令：

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests
```

结果：`52 passed, 2 failed, 3 warnings`。

1. `backend/tests/test_contracts.py::test_mock_agents_keep_director_and_role_output_separate`：Mock 角色第 0 轮实际使用“恢复关系”，测试要求字面量“复合”。这是 P2-B.1 已确认的 Mock Agent 测试契约待决策项，本轮未修改。
2. `backend/tests/test_synthetic_adapter.py::test_adapter_logs_only_counts_and_no_message_content`：迁移测试执行 `backend/alembic/env.py` 的 `fileConfig` 后，默认 `disable_existing_loggers=True`，导致已导入的适配器 logger 在后续测试中不再产生记录。专项单独运行通过；这是测试环境日志配置耦合，不是证据校验失败。本轮未修改 `env.py`，建议后续评估将 `fileConfig(..., disable_existing_loggers=False)` 作为独立修复。

### 全量 Ruff

命令：

```text
backend\\.venv\\Scripts\\ruff.exe check backend/app backend/tests scripts/convert_wechatauto_export.py
```

结果：发现 `scripts/convert_wechatauto_export.py` 的两个既有问题：未使用的 `# noqa: E402` 和应使用 `TypeError` 而非 `ValueError`。该脚本与本次适配器和迁移路径修复无关，未修改。

## 5. 最终检查

已执行：

```text
git diff --check
git status --short --branch
```

`git diff --check` 无空白错误。工作区仍保留既有过程文件 `findings.md`、`progress.md`、`task_plan.md`，以及本阶段代码、测试和报告修改；未提交、未推送。原始数据目录未纳入本阶段变更。

## 6. 未解决问题与停止条件

- Mock Agent 的“主题相关”与“必须包含主题字面量”契约仍待人工决定。
- Alembic `fileConfig` 对既有 logger 的影响需要单独确定修复位置，避免本阶段扩大范围。
- 全量 Ruff 的转换脚本问题待后续独立清理。

P2-B.2 已完成本阶段范围，现停止等待人工审核；不自动开始数据库/API 开发、第三方工具接入或真实聊天分析。
