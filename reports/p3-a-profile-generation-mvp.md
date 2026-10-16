# P3-A JSONL 角色特征生成 MVP

作者：valen MPF
日期：2026-10-16（Asia/Shanghai）

## 1. 范围与执行边界

本阶段实现了仅基于内存中的规范化 JSONL 记录的角色特征生成 MVP。数据流为：

```text
规范化消息 Mapping
  -> 显式 sender_role_map 与安全来源复核
  -> A/B 角色消息分组
  -> Observable / Fake Semantic / Disabled LLM Analyzer
  -> synthetic_adapter 严格证据校验
  -> pending ProfileCandidate
  -> 人工审核快照
  -> 角色配置预览（不发布）
```

本阶段没有读取、枚举或扫描 `data/`、`data/inbox/`、真实聊天、音频、视频或凭据；没有调用外部 API、LLM、Chat2Profile 或 GPT-SoVITS；没有安装依赖；没有修改 ZIP/Inbox、数据库 schema、Alembic migration、Mock Agent 或前端。没有提交或推送。

## 2. 实际检查的文件

启动前阅读了：

- `AGENTS.md`
- `README.md`
- `reports/p2-d2-security-provenance-fix.md`
- `backend/app/ingestion/wechat_normalizer.py`
- `backend/app/ingestion/security_flags.py`
- `backend/app/profiles/synthetic_adapter.py`
- `backend/app/profiles/analyzer.py`
- `backend/app/profiles/service.py`
- `backend/app/models/profiles.py`
- `backend/app/models/imports.py`
- `backend/app/schemas/profile.py`
- `backend/app/api/profiles.py`
- `backend/tests/test_profiles.py`
- `backend/tests/test_synthetic_adapter.py`
- `backend/tests/conftest.py`

现有 `ProfileVersion/ProfileTrait/ProfileEvidence` 与 API 只消费已审核数据库中的 `ImportedMessage`。因此本阶段没有强行改造该持久化流程，新增独立、可测试的 JSONL 内存服务，并明确其结果不能直接发布。

## 3. 新增模块和契约

### `backend/app/profiles/jsonl_analyzer.py`

- `AnalyzerOutput`：`analyzer_name`、`analyzer_version`、`status`、`sample_count`、`signals`。
- `ProfileAnalyzer`：可替换 Analyzer Provider 协议。
- `ObservableAnalyzer`：统计消息长度中位数、问句比例、常见标点、emoji 和有限口语表达；少于 3 条返回 `insufficient_samples`，不做性格或声音推断。
- `FakeSemanticAnalyzer`：仅使用合成词项规则演示正向/反向证据，不代表语义理解；置信度保持 `None`。
- `DisabledLLMSemanticAnalyzer` 与 `LLMProviderConfig`：真实 LLM 默认关闭；尝试启用会明确失败，避免测试或默认服务外发数据。

### `backend/app/profiles/jsonl_service.py`

- `parse_normalized_jsonl(text)`：只解析传入字符串，不访问文件系统；非法 JSONL 明确报告行号。
- `analyze_normalized_messages(messages, sender_role_map, analyzers)`：
  - 要求显式 sender 到 `role_a`/`role_b` 映射，不猜昵称；
  - 重算并比对 `security_flag_inputs`、`security_flag_sources` 和三态安全字段；unknown、冲突、非法来源、AI/system 消息均拒绝；
  - 排除重复/非法 message ID、未映射 sender、媒体、空正文和非文本消息；
  - 按角色分组后调用 Analyzer，再把所有信号交给现有 `adapt_synthetic_signals(...)`；
  - 输出稳定 `snapshot_id`、样本统计、Analyzer 状态、候选和拒绝原因；
  - 日志只输出数量，不输出正文、引文、完整消息 ID或凭据。
- `ReviewedCandidate`：在现有 `ProfileCandidate` 外包裹 `analyzer_name/version`、`review_status` 和 `reviewer_note`。
- `review_candidate(...)`：返回新审核快照，状态限定为 `pending/accepted/rejected/needs_review`，不写库。
- `build_role_config_preview(...)`：只把已接受候选组装为预览，返回与旧配置的 added/removed 差异，并固定 `publishable=false`。

`profile_item_id` 继续复用 adapter 的稳定候选快照语义；`snapshot_id` 是本次输入和分析器结果的快照 ID，二者均不宣称为跨版本持久化特征 ID。

## 4. 合成数据覆盖

`backend/tests/test_jsonl_profile_generation.py` 使用人工构造的 6 条消息：A/B 各 3 条，包含正向偏好、反向/回避表达、问句、标点、emoji、口语词项。另构造了以下拒绝样本：

- unknown、非法字符串、AI/system 标记和缺失/伪造安全来源；
- 图片占位、空正文、非文本消息；
- 重复 message ID 与未映射 sender；
- 不存在的模型证据 ID、跨角色证据 ID、格式错误模型输出；
- 缺失或非法时间状态的时序证据；
- 缺失置信度、正向/反向证据和交叉引用；
- 不同输入顺序、不同映射插入顺序和固定留出样本。

所有证据引用必须精确回指输入的唯一 `message_id`。原始 ID 不改写；无效引用由 `unmatched_evidence` 保留拒绝原因，不降级为有效候选。

## 5. 安全门禁与审核结果

- `is_ai_generated`、`is_system` 必须是真实 `bool=False`；unknown、`None`、字符串或数字不能通过。
- `security_flag_inputs` 必须存在，并由 `derive_security_flags()` 重算；其结果必须与 `security_flag_sources` 一致，不能只伪造输出字段。
- 只有 `message_type=text`、`content_status=present` 且正文为非空字符串的消息可作为普通文本证据。
- 显式 sender-role 映射决定归属；角色 A 的信号引用 B 的消息会被 adapter 拒绝。
- `requires_temporal=true` 的信号仍由现有 adapter 要求 `timestamp_status=parsed_utc`、带时区且可解析；无效时间被拒绝。
- 候选初始为 `pending`；只有审核为 `accepted` 的候选进入配置预览。预览始终不可发布，未接入数据库发布流程。

## 6. 实际测试结果

使用项目现有 `backend\\.venv`，没有安装或升级依赖。

| 命令 | 结果 |
|---|---|
| `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_jsonl_profile_generation.py` | 22 passed, 2 warnings，退出码 0 |
| `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_jsonl_profile_generation.py backend/tests/test_synthetic_adapter.py backend/tests/test_profiles.py` | 36 passed, 2 warnings，退出码 0 |
| `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_jsonl_profile_generation.py backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles` | 22 passed, 3 warnings，退出码 0 |
| `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests --ignore=backend/tests/test_imports.py` | 90 passed, 3 warnings，退出码 0 |
| `backend\\.venv\\Scripts\\ruff.exe check backend/app/profiles/jsonl_analyzer.py backend/app/profiles/jsonl_service.py backend/tests/test_jsonl_profile_generation.py` | All checks passed，退出码 0 |
| `backend\\.venv\\Scripts\\ruff.exe check backend/app backend/tests --exclude backend/tests/test_imports.py` | All checks passed，退出码 0 |
| `git diff --check` | 通过，退出码 0 |

警告为既有依赖的 `Starlette TestClient`、`pytest-asyncio` 和 Alembic deprecation warning；未修改或隐藏这些警告。未运行 `backend/tests/test_imports.py`，因为该测试可能扫描真实 Inbox。

## 7. 当前 Git 状态

```text
## feature/p2b-workspace-updates...origin/feature/p2b-workspace-updates
?? backend/app/profiles/jsonl_analyzer.py
?? backend/app/profiles/jsonl_service.py
?? backend/tests/test_jsonl_profile_generation.py
?? reports/p3-a-profile-generation-mvp.md
```

本阶段新增文件只有上述 4 个；没有 `data/`、数据库、媒体、JSONL 原始文件、ZIP、`.env` 或密钥进入工作区变更。

## 8. 当前边界与下一步条件

已完成的是可审核的本地 JSONL 候选生成链路，不是生产画像发布，也不是完整语义画像。Observable 结果只描述文字行为统计；Fake Semantic 仅用于契约测试，不能替代真实模型。当前 JSONL 服务没有 REST API、数据库持久化或前端入口，避免绕过现有审核/发布门槛。

进入下一阶段前需要：

1. 设计 JSONL 候选到现有 `ProfileVersion/ProfileTrait/ProfileEvidence` 的最小持久化适配，明确来源消息能否映射为 `ImportedMessage`。
2. 增加候选审核 API/UI，保持 pending/accepted/rejected/needs_review 和证据失效检查。
3. 用固定留出样本建立语言风格评测，不把模型生成质量描述成事实复现。
4. 单独审查真实 LLM 的输出 schema、证据回指、日志脱敏和数据发送边界；默认仍保持 disabled。
5. 画像发布后才允许角色 Agent 读取；不得把候选快照直接写入生产 role profile。
6. ZIP/Inbox 兼容和真实数据处理仍不在 P3-A 范围内。

完成本报告后停止，等待人工审核；未开始 P3-B、真实聊天分析或语音模型训练。
