# P3-B.2.1 画像候选持久化模型与迁移

作者：valen MPF
项目：`wechat-character-lab`
分支：`feature/p2b-workspace-updates`
日期：2026-10-16（Asia/Shanghai）

## 1. 执行摘要

本阶段新增 JSONL 画像候选的独立持久化模型及 Alembic migration。候选层包含快照、候选项、候选证据和审核事件，与正式 `ProfileVersion`、`ProfileTrait`、`ProfileEvidence` 分离。没有实现持久化服务、审核 API、前端或正式画像转换，也没有执行真实数据库迁移。

关键边界：JSONL `source_message_id` 是候选证据表中的普通字符串，不设为 `ImportedMessage.id` 外键；只有显式映射成功时，才填写独立的可空 `imported_message_id` 外键。候选 confidence 可为 SQL `NULL`，状态通过 CHECK 约束限制。

## 2. 执行信息与 Git 状态

- 当前分支：`feature/p2b-workspace-updates`
- 执行前 HEAD：`39542bb docs(profile): 设计候选持久化数据契约`
- 执行前工作区：已有未跟踪 `reports/p3-fe0-frontend-readiness.md`，本阶段未读取、覆盖或暂存该文件。
- 原始数据目录：未读取、枚举或扫描 `data/` / `data/inbox/`。
- 真实业务数据库：未连接、未迁移、未修改。
- 外部服务、模型及依赖安装：均未调用/执行。

实际检查：

- `AGENTS.md`
- `reports/p3-b1-profile-persistence-contract.md`
- `reports/p3-fe0-frontend-readiness.md`
- `reports/p3-a-profile-generation-mvp.md`
- `reports/p3-a1-readiness-semantics.md`
- `backend/app/models/base.py`
- `backend/app/models/__init__.py`
- `backend/app/models/profiles.py`
- `backend/app/models/imports.py`
- `backend/app/models/role.py`
- `backend/alembic/env.py`
- `backend/alembic/versions/0001_initial_schema.py`
- `backend/alembic/versions/0002_profile_evidence.py`
- `backend/alembic/versions/0003_voice_analysis.py`
- `backend/tests/test_migrations.py`
- `backend/tests/conftest.py`
- `backend/pyproject.toml`

## 3. 当前架构核验与模型取舍

现有正式画像模型中，`ProfileEvidence.message_id` 强制外键到 `imported_messages.id`；`ProfileTrait.confidence` 非空；正式审核状态为 `pending/accepted/rejected`。因此不能让 JSONL 原始 ID 或 unknown confidence 直接进入正式表。

本阶段采用四个候选模型：

| 模型 | 用途 | 关键字段/约束 |
|---|---|---|
| `ProfileCandidateSnapshot` | 一次数据集输入和分析器集合的快照 | `source_dataset_id`、JSON `role_scope`、JSON `analyzer_manifest`、输入/分析器摘要、快照状态；来源+摘要唯一 |
| `ProfileCandidateItem` | 候选特征和单项审核 | 角色 FK、候选快照内 `profile_item_id`、category/claim、可空 confidence、Analyzer 名称/版本、审核状态、内容 fingerprint；快照内候选 ID 与 fingerprint 唯一 |
| `ProfileCandidateEvidence` | 正向/反向证据与正式消息映射 | dataset ID、原始 `source_message_id`、direction、映射状态/失效原因、可空 `imported_message_id` FK；每候选 source ID 唯一 |
| `ProfileCandidateReviewEvent` | 记录审核状态变化 | 候选 FK、前后状态、reviewer、说明、原因码和时间 |

合并/拆分理由：snapshot 与 item 分开，使同一分析批次可承载多项候选且可整体幂等识别；evidence 独立存储支持一项候选多条 supporting/counter 引用和逐条映射；review event 独立存储避免候选当前状态覆盖历史。role scope 与 analyzer manifest 使用 JSON，因为它们是一次快照的有序/结构化声明，而不是独立生命周期实体；候选 item 的 `subject_id` 仍以 `roles.id` 外键约束。没有增加长期 `ProfileTrait` 身份字段，候选 fingerprint 仅用于快照内去重。

## 4. 约束和隔离

- 快照状态仅允许 `draft/under_review/accepted/rejected/expired`。
- 候选审核状态仅允许 `pending/accepted/rejected/needs_review`。
- Confidence 允许 `NULL`；非空值限制在 `[0,1]`。
- 证据 direction 仅允许 `supporting/counter`；同一候选相同 `source_message_id` 唯一，因此不能同时作为正反证据。
- `match_status` 仅允许 `unmatched/matched/invalid`。
- 只有 `match_status=matched` 才允许且要求 `imported_message_id` 非空；unmatched/invalid 不能带正式消息 ID。
- `source_message_id` 不设外键；`imported_message_id` 单独引用 `ImportedMessage.id`，删除正式消息时 `SET NULL`，候选原始引用仍保留。
- 候选表仅 FK 到 roles、候选父表和（映射字段）ImportedMessage；不 FK 到 ProfileVersion/ProfileTrait，不会自动进入正式画像或发布。
- 候选子表对所属快照/候选采用 `ON DELETE CASCADE`；这是候选记录内部清理规则，不影响正式画像。
- 证据 rationale 限长 500；不保存聊天原文、媒体字节或音频/视频。
- 审核事件是追加记录模型；本阶段没有数据库 trigger 阻止更新/删除，未来服务层应只追加并在必要时以数据库权限/审计策略加强不可变性。

## 5. Migration 内容与回滚

新增 `backend/alembic/versions/0004_profile_candidate_persistence.py`，链路为：

```text
0003_voice_analysis -> 0004_profile_candidate_persistence
```

Migration 创建四张表和必要的 source dataset、snapshot、role、candidate、imported message、review event 索引；包含上述 CHECK、UNIQUE、FK 约束。`downgrade()` 按依赖反序删除索引和四张候选表，不动现有正式画像或导入表。

回滚是破坏性的：候选数据和审核事件将一并删除。真实部署前应先备份候选库或导出审计记录；本阶段只在 `tmp_path` 隔离 SQLite 文件上执行 upgrade/downgrade。

## 6. 修改文件

- `backend/app/models/candidates.py`：四类候选持久化模型和声明式约束。
- `backend/app/models/__init__.py`：导出新模型，确保 `Base.metadata` 注册。
- `backend/alembic/versions/0004_profile_candidate_persistence.py`：创建/回滚候选表。
- `backend/tests/test_migrations.py`：迁移 schema 断言，并增加候选 migration downgrade 隔离检查。
- `backend/tests/test_candidate_persistence_models.py`：内存 SQLite 测试 metadata、NULL confidence、原始 ID 与正式 ID 分离、状态/范围/证据交叉约束。
- `reports/p3-b2-1-candidate-persistence-model.md`：本报告。

没有修改正式画像 API、服务、schemas、数据库旧 migration、前端或 P3-A 分析算法。

## 7. 实际测试结果

使用已有 `backend/.venv`，未安装依赖。

| 命令 | 实际结果 |
|---|---|
| `backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_candidate_persistence_models.py backend/tests/test_migrations.py` | 6 passed, 6 warnings，退出码 0 |
| `backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_candidate_persistence_models.py backend/tests/test_migrations.py backend/tests/test_profiles.py` | 13 passed, 6 warnings，退出码 0 |
| `backend\.venv\Scripts\ruff.exe check backend/app/models/candidates.py backend/app/models/__init__.py backend/alembic/versions/0004_profile_candidate_persistence.py backend/tests/test_candidate_persistence_models.py backend/tests/test_migrations.py` | All checks passed，退出码 0 |
| `git diff --check` | 通过，退出码 0 |

Warnings 为现有 Starlette/httpx 与 pytest-asyncio deprecation，以及 Alembic `path_separator` deprecation；本阶段没有更改全局或 Alembic 配置。

测试验证了：migration `head` 创建所有候选表；候选 migration downgrade 到 `0003_voice_analysis` 只移除候选表并保留原正式画像/语音表；置信度 NULL 合法；非法状态和越界 confidence 被拒绝；同一证据 ID 不得跨正反方向重复；原始 JSONL ID 不要求数据库 ImportedMessage 记录。

## 8. 风险与未解决项

1. SQLite CHECK/外键能力已通过本地隔离迁移测试验证；其他数据库方言尚未验证。
2. `role_scope` 和 `analyzer_manifest` 的 JSON 内容结构需在 P3-B.2.2 持久化服务中做 schema 校验。
3. `source_dataset_id` 与快照 ID 的生成责任尚待 P3-B.2.2 明确。
4. CandidateEvidence 重复 ID 约束按一个候选中原始 message ID 唯一设计；如果产品要允许同一消息对同一 claim 同时承担两种方向，应先解决契约冲突，不能删除约束绕过。
5. 当前无业务服务/API，因此状态迁移合法性只限制状态值，不限制状态转换路径；后续审核服务需实现状态机与事件追加。
6. 候选接受、来源映射和正式画像准入仍未实现；这些表本身不能证明候选可发布。
7. 本阶段未运行完整后端测试集，且明确未运行 `backend/tests/test_imports.py`。

## 9. 阶段状态

P3-B.2.1 模型、migration 与隔离验证完成。没有开始 P3-B.2.2、真实数据持久化或 API/UI。按用户要求整理提交并推送后停止等待人工审核。
