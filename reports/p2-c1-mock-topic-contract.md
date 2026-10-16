# P2-C.1 Mock Agent 主题词契约修复

作者：valen MPF
日期：2026-10-16（Asia/Shanghai）

## 1. 范围与边界

- 仅修改 Mock Agent 的测试契约；未修改 `backend/app/agents/mock_agents.py`、公共 Agent 接口、画像适配器、安全标记或规范化器。
- 未读取真实聊天数据，未访问 `data/inbox`，未调用外部 API，未安装依赖。
- 保留所有既有未提交修改，未 reset、checkout、清理、提交或推送。

## 2. 原测试失败根因

原测试 `backend/tests/test_contracts.py::test_mock_agents_keep_director_and_role_output_separate` 使用 `assert "复合" in response`。

真实的 Mock 第 0 轮回复使用“恢复关系”等自然表达，没有出现首选词“复合”，所以断言把“主题相关”错误收窄成了单一字面量匹配。P2-B.3 已确认这不是 Director/Role 隔离失败。

## 3. 主题表达配置与测试变更

在 `backend/tests/test_contracts.py` 增加测试级配置：

```python
TOPIC_EXPRESSIONS = {
    "reconciliation": ("复合", "恢复关系", "重新在一起", "和好", "修复关系"),
}
```

新增 `_matches_topic_expression()`，只验证回复是否命中当前主题的一组可接受表达，并明确注释这不是完整语义理解。

主测试继续使用真实输入主题 `请求复合`，现在验证回复非空、命中“恢复关系”等有效替代表达、不泄漏画像统计、保留 `Mock` 标记；同时保留 Director 的控制字段断言和不得返回 `text` 的断言。

新增偏题负例 `明天一起讨论天气和菜单。`，确认主题表达检查会失败；原有 A/B 角色上下文和立场差异测试未删除。

## 4. 职责隔离结论

- `MockDirectorAgent.plan_next()` 只产生控制计划，不生成角色台词。
- `MockRoleAgent.respond()` 负责角色文本生成。
- A/B 角色使用不同角色 ID 和立场分支，未合并为单一身份。
- 角色回复不包含传入的画像统计字段。

主题关键词命中仅是测试级可解释信号，不代表语义理解、意图识别或真实对话质量。

## 5. 实际测试命令与结果

目标测试与偏题负例：`backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_contracts.py::test_mock_agents_keep_director_and_role_output_separate backend/tests/test_contracts.py::test_topic_expression_check_rejects_an_off_topic_reply` 结果：`2 passed, 2 warnings`。

完整 contracts 测试：`backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_contracts.py` 结果：`8 passed, 2 warnings`。

适配器与迁移测试正向/反向组合：

- `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_synthetic_adapter.py backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles`
- `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_migrations.py::test_initial_migration_creates_schema_and_seed_roles backend/tests/test_synthetic_adapter.py`

两次均为 `9 passed, 3 warnings`。

受限后端回归：`backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests --ignore=backend/tests/test_imports.py`，结果：`50 passed, 3 warnings`。

按项目数据边界未运行 `test_imports.py`，因为它会扫描 `data/inbox`。

相关 Ruff：`backend\\.venv\\Scripts\\ruff.exe check backend/tests/test_contracts.py backend/app/agents/mock_agents.py backend/app/agents/base.py backend/tests/test_synthetic_adapter.py backend/app/profiles/synthetic_adapter.py backend/tests/test_migrations.py backend/alembic/env.py`，结果：`All checks passed!`。

`git diff --check` 通过；仅有 Git 的 LF/CRLF 转换提示。

## 6. 修改文件与工作区状态

本阶段新增修改：

- `backend/tests/test_contracts.py`：主题表达集合、匹配辅助函数、偏题负例和主题断言。
- `reports/p2-c1-mock-topic-contract.md`：本报告。

既有 `backend/alembic/env.py`、画像适配器、迁移测试、合成测试、过程文件和 P2 报告均保留。当前分支为 `feature/p2b-workspace-updates`；未提交、未推送。

## 7. 未解决问题

- 当前检查是关键词覆盖，不是完整语义评估；语义级测试需要另行设计契约。
- `test_imports.py` 未运行，不能据此宣称完整 `backend/tests` 通过。
- 依赖相关弃用警告仍存在，但不影响本阶段断言。

P2-C.1 已完成，现停止等待人工审核；不自动进入 P2-C.2 或真实数据处理。
