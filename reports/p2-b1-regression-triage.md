# P2-B.1 回归失败诊断与适配器验收补充

日期：2026-10-16（Asia/Shanghai）
范围：只诊断 P2-B 全量回归失败，并复核 `synthetic_adapter.py` 边界；未扩大功能范围。

## 1. 执行边界

- 开始前已执行 `git status --short --branch` 并检查相关差异。
- 保留所有既有未提交修改；未清理、回滚、覆盖或提交。
- 未读取 `data/`、真实聊天正文、音频、视频或完整媒体数据库。
- 未安装依赖、修改全局配置或调用外部 API。
- 未修改 Mock Agent、迁移配置、测试断言或适配器实现。

## 2. Mock Agent 失败诊断

### 原始证据

测试：`backend/tests/test_contracts.py::test_mock_agents_keep_director_and_role_output_separate`

断言：

```python
assert "复合" in response
```

实际响应（按 JSON 转义展示，避免终端编码影响）：

```text
[本地演示 / Mock] 我愿意把这次请求当成一次认真沟通，但不会只因为想念就马上恢复关系。先把当初分开的原因和现在是否真的改变说清楚。
```

该回复包含“请求”和“恢复关系”等主题相关内容，但第 0 轮没有字面量“复合”；“复合”只可能在后续阶段的部分固定台词中出现。因此断言失败是真实行为差异，不是输出编码假象。

### 实现与差异

- `backend/app/agents/mock_agents.py:MockRoleAgent.respond`：解析主题、导演意图和最近对话，按角色与轮次选择 deterministic Mock 台词；不直接回显画像统计。
- `backend/app/agents/mock_agents.py:_reconciliation_reply`：第 0 轮角色 A 的台词使用“恢复关系”，没有强制复述主题关键词。
- `backend/app/agents/mock_agents.py:MockDirectorAgent.plan_next`：只返回 `speaker_role_id`、`intent`、`should_end`，不生成台词。
- 当前 Git 差异显示 Mock Agent 与该测试均为既有未提交修改；本轮未创建这些修改。

### 根因分类

结论：**测试契约过时/过窄，兼有契约语义未明确**。

当前实现满足“角色输出不直接泄露画像统计”和“回复围绕请求复合主题”的行为，但测试把“主题相关”收窄为必须包含字面量“复合”。如果产品契约确实要求每轮回复都出现主题词，则实现也需要调整；在未确认契约前不能擅自修改任一方。

### 对双角色隔离契约的影响

无直接破坏证据：Director 仍只返回控制字段，Role Agent 才生成文本；Mock 回复没有回显“消息长度中位数”等画像统计。失败只影响主题关键词断言，不表明 A/B 输出串位或 Director 代替角色发言。

## 3. Alembic 迁移失败诊断

### 实际路径

- 配置：`backend/alembic.ini`
- 环境脚本：`backend/alembic/env.py`
- 迁移目录：`backend/alembic/versions/`
- 迁移脚本：`0001_initial_schema.py`、`0002_profile_evidence.py`、`0003_voice_analysis.py`
- 测试：`backend/tests/test_migrations.py`

测试初始化实际使用：

```python
config = Config("alembic.ini")
command.upgrade(config, "head")
```

### 根目录失败堆栈摘要

从仓库根目录执行单项测试时，`Config("alembic.ini")` 找不到根目录下的配置，`config.get_main_option("script_location")` 为空，随后失败：

```text
alembic.util.exc.CommandError: No 'script_location' key found in configuration.
```

失败位置：`alembic.script.base.ScriptDirectory.from_config`。

### 工作目录验证

- 从 `backend/` 目录执行同一测试：`1 passed`。
- `backend/alembic.ini` 的 `script_location = alembic` 按当前进程工作目录解析，而不是自动按配置文件所在目录解析。
- 从仓库根目录读取 `backend/alembic.ini` 后，`script_location=alembic` 会尝试解析根目录的 `alembic`，实际不存在。

### 根因分类

结论：**配置路径/测试初始化问题**，不是迁移实现失败。

从 `backend/` 运行时，三份迁移能够创建预期表并写入 `role_a`、`role_b`；因此当前没有迁移脚本本身失败的证据。

### 最小修复建议

建议仅修复测试初始化的路径解析，不跳过迁移、不删除断言：

1. 用 `Path(__file__).resolve().parents[1] / "alembic.ini"` 构造配置文件绝对路径；
2. 同时将 `script_location` 设置为 `backend/alembic` 的绝对路径，或在测试中显式设置工作目录；
3. 保留现有表集合与 seed role 断言。

影响范围仅限迁移测试启动方式和可复现性；不需要修改迁移版本脚本。此建议尚未实施，等待人工确认。

## 4. 合成适配器验收复核

检查对象：

- `backend/app/profiles/synthetic_adapter.py`
- `backend/tests/test_synthetic_adapter.py`

### 已确认通过的边界

- 输入中重复 `message_id` 会形成多重索引，引用被标记 `ambiguous_message_id`，不会进入有效证据。
- 不存在的 ID、引文不匹配、角色不匹配都会进入 `unmatched_evidence`。
- `message_type != text`、媒体占位、`is_ai_generated`/`is_system` 标记不会作为普通文本证据。
- `requires_temporal=true` 时，显式 `timestamp_status=invalid` 会拒绝为时序证据。
- 缺失置信度保持 `None`，没有自动填入高置信度。
- 正向证据和 `counter_evidence_refs` 同时保留，较新候选不会删除旧反证。
- 日志只输出 candidates/unmatched 数量；专项测试确认不含合成正文或消息 ID。
- 固定 `updated_at` 时，候选 ID 和排序可重复。

### 已确认缺陷与建议

1. **空/非字符串证据被静默过滤**

   `_string_tuple()` 只保留字符串；`evidence_ids=[]` 或 `[1]` 会变成空 tuple，但信号仍生成无证据候选。实测两种输入均为 `candidates=1, unmatched=[]`。

   建议：原始 evidence 字段存在但为空或含非法元素时，生成 `invalid_evidence_reference` 并拒绝该候选；候选至少需要一个唯一有效证据。

2. **时序时间戳校验不够严格**

   `_timestamp()` 允许 `timestamp_status` 缺失（`None`），只要 ISO 字符串可解析就可作为时序证据。实测缺失状态的 `2026-01-01T00:00:00Z` 被接受。

   建议：时序证据必须严格要求 `timestamp_status == "parsed_utc"`、可解析且带时区；缺失或 naive timestamp 应拒绝并写入 `invalid_timestamp`。

3. **`profile_item_id` 的身份语义需要明确**

   当前 ID 包含规范化 claim、正向证据 ID 和反证 ID，属于“结论+证据集合”的稳定 ID；同一语义结论增加一条新证据会得到新 ID，且证据列表顺序会影响 ID。它不是跨版本的 trait identity。

   建议：在进入数据库前明确采用“证据快照 ID”还是“语义 trait ID”。若需要语义稳定，应对证据引用排序并另设版本/证据集合字段；本轮不改实现。

4. **其他输入类型的标记规范**

   当前排除逻辑主要识别布尔 `is_ai_generated`/`is_system`。若上游输出字符串标记（如 `"true"`），不会自动排除。进入真实适配前应固定标准化字段类型或显式拒绝非布尔标记。

## 5. 实际执行命令与结果

```text
git status --short --branch
```

结果：`main...origin/main`，存在既有修改和未跟踪文件；未清理。

```text
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_contracts.py::test_mock_agents_keep_director_and_role_output_separate -vv
```

结果：`1 failed`，失败为主题字面量断言。

```text
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles -vv
```

从仓库根目录：`1 failed`，配置找不到 `script_location`。

从 `backend/` 目录：`1 passed, 3 warnings`，确认迁移实现可运行。

```text
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_synthetic_adapter.py
```

结果：`4 passed`。

```text
backend\.venv\Scripts\ruff.exe check backend/app/profiles/synthetic_adapter.py backend/tests/test_synthetic_adapter.py
```

结果：`All checks passed!`

## 6. 最终 Git 检查与停止条件

已执行 `git diff --check`，通过；仅出现既有 LF/CRLF 转换提示。

最终状态摘要仍为：

```text
## main...origin/main
M  README.md
M  backend/app/agents/mock_agents.py
M  backend/tests/test_contracts.py
M  ...（其余既有修改）
?? backend/app/profiles/synthetic_adapter.py
?? backend/tests/test_synthetic_adapter.py
?? reports/
```

本报告未修改无关模块，未提交任何内容。P2-B.1 到此停止，等待人工审核；不自动开始数据库/API 开发、第三方工具接入或真实聊天分析。
