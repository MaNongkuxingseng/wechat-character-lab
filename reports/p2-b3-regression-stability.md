# P2-B.3 回归稳定性与测试契约审查

日期：2026-10-16（Asia/Shanghai）
范围：仅处理 P2-B.2 已确认的 logger 顺序依赖，并复核 Mock Agent 测试契约。

## 1. 执行边界

- 已检查 `AGENTS.md`、Git 状态、P2-B.1 和 P2-B.2 报告。
- 保留所有既有未提交修改，未 reset、checkout、清理或提交。
- 未读取真实聊天正文、音频、视频或凭据，未安装依赖。
- 未修改 Alembic 迁移版本脚本，未修改转换器 Ruff 问题。
- `backend/tests/test_imports.py` 会扫描项目 `data/inbox`。为遵守本阶段不得读取真实数据的约束，回归测试使用 `--ignore=backend/tests/test_imports.py`，该限制单独记录。

## 2. Logger 顺序依赖

单项命令均通过：

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_synthetic_adapter.py::test_adapter_logs_only_counts_and_no_message_content
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles
```

修复前的“迁移后日志”组合：

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles backend/tests/test_synthetic_adapter.py::test_adapter_logs_only_counts_and_no_message_content
```

结果为 `1 failed, 1 passed`；反向“日志后迁移”组合结果为 `2 passed`，确认存在顺序依赖。

根因是 `backend/alembic/env.py` 原先调用 `fileConfig(config.config_file_name)`。其默认 `disable_existing_loggers=True` 会禁用已导入的 `app.profiles.synthetic_adapter` logger，导致后续日志断言捕获不到记录。

本阶段仅修改为：

```python
fileConfig(config.config_file_name, disable_existing_loggers=False)
```

这保留应用 logger，继续使用 Alembic 配置，不删除日志断言，也不修改迁移版本脚本。

修复后正向和反向组合均为 `2 passed, 3 warnings`。日志测试仍确认日志不包含合成消息正文、引文、凭据或消息 ID。

## 3. Mock Agent 测试契约

目标测试：`backend/tests/test_contracts.py::test_mock_agents_keep_director_and_role_output_separate`。

测试要求角色回复包含字面量“复合”；`MockRoleAgent._reconciliation_reply` 第 0 轮使用“恢复关系”等自然表达，不保证每轮回显主题关键词。代码和文档没有明确规定“每轮必须出现主题字面量”，因此本轮不修改回复文案、不删除核心断言。

已确认的核心隔离契约仍成立：Director 只返回 `speaker_role_id`、`intent`、`should_end`，不返回 `text`；Role Agent 负责生成台词；回复不回显画像统计；A/B 角色保持独立立场。

Mock 目标测试实际结果：`1 failed, 2 warnings`。该项保留为产品/测试契约待决策。

## 4. 回归与静态检查

不触碰 `data/` 的后端回归命令：

```text
backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests --ignore=backend/tests/test_imports.py
```

结果：`47 passed, 1 failed, 3 warnings`。唯一失败为 Mock Agent 主题字面量断言，logger 顺序依赖已消失。

未运行不带 `--ignore` 的完整命令，因为 `test_imports.py` 会扫描 `data/inbox`，与本阶段禁止读取真实数据的边界冲突，不能将完整 `backend/tests` 描述为已通过。

相关 Ruff：

```text
backend\\.venv\\Scripts\\ruff.exe check backend/alembic/env.py backend/app/profiles/synthetic_adapter.py backend/tests/test_synthetic_adapter.py backend/tests/test_migrations.py backend/app/agents/mock_agents.py backend/tests/test_contracts.py
```

结果：`All checks passed!`

## 5. Git 工作区

已执行 `git diff --check` 和 `git status --short --branch`。`git diff --check` 无空白错误。当前分支为 `feature/p2b-workspace-updates`；工作区保留既有过程文件和 P2-B.2 修改，并新增 `backend/alembic/env.py` 修改及本报告。未提交、未推送。

## 6. 未解决项与停止条件

- Mock Agent 是否要求每轮包含“复合”字面量，需要产品确认；在确认前不改变语义。
- 数据耦合的 `test_imports.py` 尚未运行，避免触碰 `data/inbox`。
- 3 条依赖弃用警告仍存在，不影响本阶段断言。

P2-B.3 已完成当前范围，现停止等待人工审核；不自动开始数据库/API 开发、第三方工具接入或真实聊天分析。
