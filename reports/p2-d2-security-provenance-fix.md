# P2-D.2 安全来源冲突修复与角色画像 MVP 准备

作者：valen MPF
日期：2026-10-16（Asia/Shanghai）

## 1. 范围与边界

本阶段仅修复 JSONL 规范化路径的安全来源保留问题，并补充合成测试。未读取、枚举或扫描 `data/`、`data/inbox/`，未读取真实聊天、媒体或凭据；未调用外部 API/LLM/Chat2Profile/GPT-SoVITS，未安装依赖，未修改 ZIP 转换、Inbox 导入、数据库 schema、迁移、Mock Agent 或前端。

执行前分支为 `feature/p2b-workspace-updates`，HEAD 为 `19f0c29`，工作区干净。本阶段修改仅限规范化器、安全标记测试和本报告。

## 2. 问题与修复

### 修复前

`backend/app/ingestion/wechat_normalizer.py` 原先通过 `security_metadata.update(type=..., message_type=...)` 合并安全来源，会覆盖原始 `source_metadata.type` / `source_metadata.message_type`。人工输入顶层 `type="text"`、嵌套 `source_metadata.type="system"` 时，嵌套类型证据丢失，无法审计来源。

### 修复后

1. 将原始 `message` 直接传给 `derive_security_flags()`，不再合并或覆盖 `source_metadata`。
2. 新增 `security_flag_inputs`，分别保留 `top_level` 与 `source_metadata` 中参与安全判断的原始字段：`type`、`message_type`、`type_code`、`is_ai_generated`、`is_system`。
3. 规范化 `message_type` 仍由 `type_code` 映射生成，ID、时间、正文和角色映射语义不变。
4. `security_flag_sources` 继续稳定记录显式、类型、unknown、invalid/conflict 来源；没有默认 `False`。

## 3. 来源规则矩阵

| 来源组合 | 结果 | 审计结果 |
|---|---|---|
| 顶层与 metadata 同名原生布尔一致 | 保留布尔值 | `explicit:*`，两处输入均保留 |
| 顶层与 metadata 同名原生布尔冲突 | `None` | `conflict:...` |
| 精确 `ai`/`assistant` 类型 | `is_ai_generated=True` | `type:*@来源路径` |
| 精确 `system` 类型 | `is_system=True` | `type:system@来源路径` |
| AI 与 system 类型来源同时存在 | 两个字段均 `None` | `conflict:type_markers:*` |
| 显式布尔与相反类型标记冲突 | 对应字段 `None` | 显式和类型来源均保留 |
| 普通文本、昵称、常规 `type_code` | 不推断否定属性 | `unknown:no_reliable_source` |
| 字符串、数字、列表、对象等非法标记 | `None` | `invalid_type:<source>` |
| 来源缺失 | `None` | `unknown:no_reliable_source` |

`security_flag_inputs` 只保存安全判定字段，不含正文；适配器日志仍只输出数量，不输出证据正文或完整消息 ID。

## 4. 测试覆盖

新增合成测试覆盖：顶层 `type="text"` 与嵌套 `source_metadata.type="system"` 的来源保留；顶层 system 与嵌套 assistant 冲突；显式布尔与类型标记冲突；缺失和非法字符串、数字、列表、对象；来源顺序确定性；普通文本 unknown 不回归；unknown、AI、system 消息继续被适配器拒绝；日志不包含正文或证据 ID。

未修改 `security_flags.py`、`synthetic_adapter.py`、ZIP 链路或数据库模型；现有严格拒绝策略保持不变。

## 5. 实际验证

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_security_flags.py backend/tests/test_wechat_normalizer.py backend/tests/test_synthetic_adapter.py
32 passed, 2 warnings；退出码 0
```

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_synthetic_adapter.py backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles
9 passed, 3 warnings；退出码 0
```

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles backend/tests/test_synthetic_adapter.py
9 passed, 3 warnings；退出码 0
```

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests --ignore=backend/tests/test_imports.py
69 passed, 3 warnings；退出码 0
```

```text
backend\\.venv\\Scripts\\ruff.exe check backend/app/ingestion/security_flags.py backend/app/ingestion/wechat_normalizer.py backend/app/profiles/synthetic_adapter.py backend/tests/test_security_flags.py backend/tests/test_wechat_normalizer.py backend/tests/test_synthetic_adapter.py backend/tests/test_migrations.py backend/alembic/env.py
All checks passed；退出码 0
```

```text
git diff --check
通过；仅有现有文件的 LF/CRLF 转换提示；退出码 0
```

未运行 `backend/tests/test_imports.py`，未执行真实数据命令。

## 6. P3 角色画像 MVP 准备（仅设计）

建议接口：

```python
def generate_profile_signals(
    messages: Iterable[Mapping[str, object]],
    *, subject_id: str,
    sender_role_map: Mapping[str, str],
    analyzer_version: str,
) -> Sequence[Mapping[str, object]]:
    """生成带 evidence_ids 的候选信号，不写库、不调用外部模型。"""
```

建议输出复用现有适配器：`signal_id`、`subject_id`、`category`、`claim`、`evidence_ids`、`counter_evidence_ids`、`confidence`、`analyzer_version`。输入限定为已规范化且通过安全门禁的 JSONL；分析器不猜角色，不消费媒体/AI/system/unknown 消息，候选进入人工审核而不是直接成为角色提示。

P3 最小测试清单：A/B 显式角色隔离；唯一证据 ID 可回指；缺失/非法/冲突安全字段拒绝；媒体、AI/system、空正文和非文本排除；正反证据保留且交叉引用拒绝；缺失置信度保持 `None`；重复运行输出和排序稳定；日志不含正文；固定留出样本不反写画像。

上述接口和清单仅用于下一阶段准备，本阶段未实现 P3。

## 7. 风险与前置条件

- ZIP `convert()`/Inbox/SQLite 路径仍缺少安全字段和 `security_flag_inputs`，本阶段明确不修改；P3 应先限定 JSONL canonical 输入。
- `security_flag_inputs` 是规范化阶段审计快照，不等同于导出方已经可靠证明安全属性；真实 WeChatBridge 字段仍未确认。
- 普通消息安全属性仍可能 unknown，未有可靠来源前不得默认 `False`。
- 下一阶段先用人工合成 JSONL 验证可审核候选生成，再决定是否进入脱敏真实小样本。

## 8. Git 状态

报告生成后的预期状态：

```text
## feature/p2b-workspace-updates
 M backend/app/ingestion/wechat_normalizer.py
 M backend/tests/test_security_flags.py
?? reports/p2-d2-security-provenance-fix.md
```

本阶段未提交、未推送、未清理或回滚任何已有修改。P2-D.2 完成，停止等待人工审核，不自动开始 P3 或 ZIP 兼容实现。
