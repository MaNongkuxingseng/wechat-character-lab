# P3-B.2.1-R1 候选模型关键约束复核

作者：valen MPF
日期：2026-10-16（Asia/Shanghai）

## 1. 范围与执行边界

本轮只读复核以下文件：

- `backend/app/models/candidates.py`
- `backend/alembic/versions/0004_profile_candidate_persistence.py`
- `backend/tests/test_candidate_persistence_models.py`
- `backend/tests/test_migrations.py`
- `backend/tests/conftest.py`
- `backend/app/models/imports.py`
- `reports/p3-b1-profile-persistence-contract.md`
- `reports/p3-b2-1-candidate-persistence-model.md`

未读取或扫描 `data/`、`data/inbox/`、真实聊天、媒体或凭据；未连接真实数据库，未修改生产代码、模型、migration 或测试，未安装依赖、调用外部服务、提交或推送。

执行前 Git 状态：

```text
## feature/p2b-workspace-updates...origin/feature/p2b-workspace-updates
?? reports/p3-fe0-frontend-readiness.md
```

HEAD：`072d6e9 feat(profile): 增加候选持久化模型与迁移`。既有未跟踪报告已保留。

## 2. 结论摘要

1. 已确认缺陷：`ProfileCandidateEvidence.imported_message_id` 使用 `ON DELETE SET NULL`，但 `match_status='matched'` 时 CHECK 要求该列非空。启用 SQLite 外键后，删除正式消息会因 CHECK 约束失败；当前设计不能实现“删除后自动失效”。
2. 已确认测试缺口：`backend/tests/conftest.py` 的 SQLite fixture 没有设置 `PRAGMA foreign_keys=ON`，现有模型测试和 migration 测试不能验证实际 FK 删除行为。
3. snapshot 的三列唯一键均为 `NOT NULL`，没有 SQLite/SQL NULL 唯一性歧义；完全相同的 dataset/input/analyzer 三元组被拒绝，跨 dataset 或摘要不同可以创建新快照。
4. evidence 的唯一键为 `(candidate_id, source_message_id)`，因此同一候选中 supporting/counter 复用同一来源 ID 被拒绝；不同候选可以使用同一来源 ID。该约束符合当前“每个候选内来源 ID 唯一”的设计，但不表达跨候选全局唯一。
5. Review event 足以保存状态前后值、审核人、说明、原因码和时间，但数据库没有阻止 UPDATE/DELETE，也没有序列号或追加性约束；不可变审计目前依赖服务层。

## 3. `SET NULL` 与 matched CHECK 的实测

### 代码依据

`backend/app/models/candidates.py:115-121,133-135` 和 migration 对应定义：

```sql
FOREIGN KEY (imported_message_id)
  REFERENCES imported_messages(id) ON DELETE SET NULL

(match_status = 'matched' AND imported_message_id IS NOT NULL)
OR (match_status != 'matched' AND imported_message_id IS NULL)
```

`source_message_id` 是普通字符串，不是 `ImportedMessage.id` 外键；`imported_message_id` 才是可选的正式消息映射。

### 隔离验证方法

使用项目 `backend/.venv` 中的 Python，在内存 SQLite 中通过 `Base.metadata.create_all()` 建立合成 schema，插入合成 `Role`、`Source`、`ImportedMessage`、snapshot、item 和一条 `matched + imported_message_id` evidence。分别使用：

- 显式 `PRAGMA foreign_keys=ON` 的连接；
- 默认未启用 SQLite 外键的连接。

脚本未写入仓库或真实数据库。

### 实际结果

```text
FK True  delete=IntegrityError: CHECK constraint failed: ck_candidate_evidence_matched_reference
         evidence={'imported_message_id': 'msg1', 'match_status': 'matched'}
FK False delete=succeeded
          evidence={'imported_message_id': 'msg2', 'match_status': 'matched'}
```

启用外键时，SQLite 先执行 `SET NULL`，随后行状态违反 matched CHECK，整个删除回滚，证据仍保留原映射。未启用外键时，删除不触发 `SET NULL`，留下引用已不存在的正式消息 ID，同时状态仍为 `matched`；这是测试配置造成的假阴性/漏检风险，不是可接受的业务行为。

### 判断与建议

这是已确认的模型设计冲突，不是未验证事项。P3-B.2.2 应选择并明确实现一种策略：

- 将正式消息删除建模为证据失效，并在同一事务将 `match_status` 改为 `invalid`/`unmatched` 后再解除映射；或
- 使用 `RESTRICT`/`NO ACTION`，要求先显式使证据失效，再删除正式消息。

不建议保持当前 `SET NULL + matched CHECK` 不变。后续应增加启用 SQLite 外键的定向测试；本轮按要求不修改测试。

## 4. 外键、删除规则、CHECK、唯一约束和索引

以下结果由 SQLAlchemy `inspect()` 对隔离 SQLite metadata 实测，并与 `0004_profile_candidate_persistence.py` 逐项对照。

| 表 | 外键与删除规则 | 唯一约束 | 索引 | CHECK |
|---|---|---|---|---|
| `profile_candidate_snapshots` | 无 FK | `(source_dataset_id,input_digest,analyzer_digest)` | `source_dataset_id` | `status` 为 `draft/under_review/accepted/rejected/expired` |
| `profile_candidate_items` | `snapshot_id -> snapshots` `CASCADE`；`subject_id -> roles`，未声明 ondelete | `(snapshot_id,profile_item_id)`；`(snapshot_id,candidate_fingerprint)` | `snapshot_id`、`subject_id` | confidence 为 NULL 或 `[0,1]`；审核状态为 `pending/accepted/rejected/needs_review` |
| `profile_candidate_evidence` | `candidate_id -> items` `CASCADE`；`imported_message_id -> imported_messages` `SET NULL` | `(candidate_id,source_message_id)` | `candidate_id`、`source_dataset_id`、`imported_message_id` | direction；match_status；matched 与 imported ID 的配对规则 |
| `profile_candidate_review_events` | `candidate_id -> items` `CASCADE` | 无 | `candidate_id` | from/to status 只能为候选审核状态 |

Snapshot、item、evidence 的子表级联删除符合候选层内部清理语义，且没有把候选 FK 指向正式 `ProfileTrait/ProfileVersion`。`subject_id` 的角色 FK 未声明删除规则，实际数据库默认行为由数据库方言决定，P3-B.2.2 前应明确是否允许角色删除。

## 5. Snapshot 幂等与跨快照语义

实现依据：`ProfileCandidateSnapshot.__table_args__` 和 migration 的 `uq_candidate_snapshot_input`。三列均 `nullable=False`，因此没有可空列重复绕过唯一约束的问题。

隔离 SQLite 插入验证结果：

```text
相同 dataset + input_digest + analyzer_digest：IntegrityError
不同 input_digest：ok
不同 source_dataset_id（其余摘要相同）：ok
```

结论：当前唯一键表达的是同一数据集、同一输入摘要和同一分析器摘要的快照幂等；数据集或任一摘要变化即允许新快照。它没有限制不同快照复用相同 `profile_item_id` 或证据来源，这是预期的“snapshot 内去重”语义。应用层仍需定义摘要规范化、版本变更和重试时的 upsert 行为。

## 6. Evidence 唯一性与正反方向

隔离 SQLite 插入验证：

```text
同一 candidate + source_message_id，先 supporting 后 counter：首条 ok，第二条 IntegrityError
不同 candidate 复用同一 source_message_id：ok
```

因此同一候选不能把一条来源消息同时作为正向和反向证据，也不能重复插入同一来源；但数据库不阻止两个不同候选引用相同来源，也不要求 supporting/counter 集合在 item 之外做交叉检查。若 P3-B.2.2 需要“候选内部正反集合绝不交叉”，当前唯一键已提供基础保护；服务层仍应在批量写入前报告明确拒绝原因。

## 7. Review event 审计模型

`ProfileCandidateReviewEvent`（`candidates.py:143-165`）包含：

- `candidate_id`：候选 FK，候选删除时 `CASCADE`；
- `from_status`、`to_status`：前后状态，CHECK 限定候选审核状态；
- `reviewer_id`：审核人，可空；
- `note`、`decision_reason_code`：说明和结构化原因码，可空；
- `created_at`：事件时间，非空、数据库默认当前时间。

模型足以表达 P3-B.2.2 所需的状态变更记录。限制是：没有 `event_sequence`/唯一时间序列，没有数据库 trigger 或权限约束阻止历史事件被 UPDATE/DELETE，也没有把 `to_status` 与当前 `ProfileCandidateItem.review_status` 做一致性约束。因此“不可变、只追加、事件与当前状态一致”尚未由数据库保证，建议在审核服务层采用 insert-only，并增加审计事件最小测试；如需要数据库级不可变性，另行设计，不在本轮实现。

## 8. 现有测试夹具的外键状态

`backend/tests/conftest.py:13-18` 仅创建：

```python
create_engine("sqlite+pysqlite:///:memory:", ...)
```

没有连接事件监听，也没有执行 `PRAGMA foreign_keys=ON`。`backend/tests/test_candidate_persistence_models.py` 和 `test_migrations.py` 当前能验证元数据、CHECK、UNIQUE、表存在性和 FK 声明；不能验证 SQLite 执行 `CASCADE`、`SET NULL` 或 FK 拒绝行为。现有 `6 passed, 6 warnings` 不能解读为删除规则已验收。

## 9. 实际测试命令与结果

本轮实际执行：

```text
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_candidate_persistence_models.py backend/tests/test_migrations.py
```

结果：`6 passed, 6 warnings`，退出码 `0`。警告为既有 Starlette/httpx、pytest-asyncio 和 Alembic `path_separator` deprecation warnings。

本轮还执行了只读隔离 SQLite 约束脚本，覆盖：

- 外键开启/关闭时删除 matched ImportedMessage；
- inspector 读取 FK、ondelete、UNIQUE、index、CHECK；
- snapshot 重复/跨快照插入；
- evidence supporting/counter 重复和跨 candidate 复用。

未运行 `backend/tests/test_imports.py`，未连接真实数据库，未运行真实 migration against business data。

## 10. 问题分级与 P3-B.2.2 建议

### 已确认问题

1. `SET NULL` 与 matched CHECK 冲突，启用真实外键时会阻止正式消息删除，未启用外键时会留下语义悬空映射。
2. 现有 SQLite 测试夹具没有启用 FK，删除行为没有回归保护。

### 潜在问题

1. Review event 的“不可变/只追加”仅是注释和模型意图，数据库未强制。
2. `subject_id -> roles.id` 未声明 ondelete，角色删除策略未明确。
3. 事件没有序列号，完全相同时间戳下的排序需依赖主键或服务层写入顺序。
4. snapshot 唯一键不包含 `role_scope`；同 dataset/input/analyzer 下角色范围变化会被视为同一快照，是否符合产品幂等语义需确认。当前代码和报告没有证明需要把 role scope 纳入摘要或唯一键。

### 建议的最小后续验收条件

- 先确定证据映射失效策略，再调整 FK/CHECK 或增加事务性失效逻辑；
- 在隔离 SQLite fixture 显式开启 FK，并覆盖删除 matched/unmatched evidence 的行为；
- 为 review event 增加服务层 insert-only 与状态一致性测试；
- 明确角色删除规则和 snapshot `role_scope` 是否参与输入摘要；
- 再进入 P3-B.2.2 的幂等持久化服务，不把当前模型测试通过当作删除语义已完成。

## 11. 收尾状态

本轮只新增本报告；未修改模型、migration 或测试，未提交或推送。报告写入后应执行 `git diff --check` 和 `git status --short --branch`，并等待人工审核。
