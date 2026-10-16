# P3-A.1 画像生成状态语义修正

作者：valen MPF
日期：2026-10-16（Asia/Shanghai）

## 1. 执行信息

- 目标分支：`feature/p2b-workspace-updates`
- 执行前 HEAD：`77b330f feat(profile): 实现 JSONL 角色特征生成 MVP`
- 执行前工作区：干净；分支跟踪 `origin/feature/p2b-workspace-updates`
- 修改文件：`backend/app/profiles/jsonl_service.py`、`backend/tests/test_jsonl_profile_generation.py`、本报告
- 本阶段不推送；本次执行完成后创建本地 commit。

## 2. 问题与状态契约

### 修复前

`analyze_normalized_messages()` 原来使用 `any(item["status"] == "ready" for item in statuses)` 聚合整体状态。`statuses` 中每项代表一个角色上的一个分析器；因此只要 A 的一个分析器 ready，B 样本不足或同角色另一分析器未就绪，整体仍会被标记为 `ready`。返回对象没有角色级状态。

代码检索确认 `JsonlProfileResult` 仅由此 JSONL 服务和对应测试使用，没有 REST/API 或前端调用方依赖旧的整体状态；现有 ImportedMessage 画像 API 与该独立 JSONL 候选服务不是同一调用链。README 对已持久化画像的审核/发布说明不定义此 JSONL 服务的状态语义。

### 修正后

- 分析器级：保留 Provider 原始状态，逐角色逐分析器独立记录，不将一种状态复制到其他项。
- 角色级：`role_statuses[role_id]` 根据该角色所有必需分析器推导。全部 ready 为 `ready`；ready 与非 ready 混合为 `partial`；没有 ready 为 `insufficient_samples`。状态为 `provider_disabled` 的可选 Provider（当前默认关闭的 LLM）不阻断角色就绪。
- 整体级：只覆盖 `sender_role_map` 显式列出的角色。所有这些角色 ready 时整体 `ready`；只有部分角色/分析器就绪时为 `partial`；没有任何角色就绪时为 `insufficient_samples`。
- 单角色调用保持有效：映射只包含 `role_a` 时不要求未映射的 `role_b`；该显式范围内样本充分仍为整体 `ready`。
- 有效样本数只统计安全门禁后的唯一文本消息。Provider 声称的 `sample_count` 必须与传入有效消息数一致，0 样本不能报 ready。

没有新增“角色未映射”状态：未列入显式映射的角色不属于本次调用范围；映射中存在但没有合格消息的角色显示 `insufficient_samples`。这使状态与当前输入契约一致，不改变候选审核或 `publishable=False`。

## 3. 代码变更

### `backend/app/profiles/jsonl_service.py`

- 在 `JsonlProfileResult` 增加 `role_statuses` 并纳入稳定序列化。
- 以分析器输出的有效样本数为依据汇总角色与整体状态，替代 `any(ready)`。
- 校验 Analyzer 报告的 `sample_count` 等于实际传入该角色的合格消息数，并拒绝零样本 ready。
- 单角色映射继续支持；默认禁用的 LLM Provider 是可选项，不会让本地分析永远 partial。

### `backend/tests/test_jsonl_profile_generation.py`

新增状态回归：A/B 双角色就绪、仅 A 就绪、仅 B 就绪、A/B 都不足、同角色多分析器状态不一致、重复/媒体/不安全消息不能凑足样本门槛，以及只映射单个角色的兼容场景。原有证据回指、角色隔离、安全门禁、审核预览和 LLM 禁用测试继续保留。

返回 JSON 新增 `role_statuses`，属于既有独立 JSONL 服务的向后兼容扩展；没有 API/schema 消费者。整体 `status` 在部分角色就绪时从错误的 `ready` 改为 `partial`，这是本阶段预期语义修正。

## 4. 测试结果

以下均使用项目现有 `backend\\.venv`，未安装依赖：

| 命令 | 实际结果 |
|---|---|
| `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_jsonl_profile_generation.py` | 28 passed, 2 warnings；退出码 0 |
| `backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_jsonl_profile_generation.py backend/tests/test_synthetic_adapter.py backend/tests/test_profiles.py backend/tests/test_contracts.py backend/tests/test_api.py` | 62 passed, 2 warnings；退出码 0 |
| `backend\\.venv\\Scripts\\ruff.exe check backend/app/profiles/jsonl_service.py backend/tests/test_jsonl_profile_generation.py` | All checks passed；退出码 0 |
| `git diff --check` | 通过；退出码 0 |

警告为既有 Starlette TestClient/httpx 与 pytest-asyncio deprecation warning。未运行 `backend/tests/test_imports.py`，也未运行全后端测试集。定向 API 和 contract 测试覆盖了既有画像 API、Mock A/B 角色契约及暂停插话相关测试；P3-A.1 未修改这些模块。

## 5. 安全与范围核验

- 未访问、枚举或扫描 `data/`、真实聊天或媒体。
- 未调用外部模型、网络 API 或语音服务。
- 未修改数据库、Alembic migration、REST API、语音模块或前端。
- 未安装依赖。
- 未推送；本次执行按用户要求提交本地 commit。
- 候选审核状态和 `publishable=False` 保持不变。

## 6. 当前工作区状态

```text
## feature/p2b-workspace-updates...origin/feature/p2b-workspace-updates
 M backend/app/profiles/jsonl_service.py
 M backend/tests/test_jsonl_profile_generation.py
?? reports/p3-a1-readiness-semantics.md
```

以上为提交前工作区状态；`git diff --check` 通过。未发现本阶段范围外文件改动。

## 7. 风险与后续建议

- `partial` 是新增整体状态；未来 API/UI 接入时应明确展示，并且不能把它当作双角色画像完整可用。
- 角色就绪目前代表所有配置的必需 Analyzer 已达到各自条件，不代表候选已被审核、画像已发布或语义质量已验证。
- 整体范围来自显式 `sender_role_map`；若产品后续要求每次必须同时分析 A/B，应在 API 请求契约中显式声明必需角色，而不是从昵称或默认映射猜测。
- 未执行 P3-B.1、持久化、API/UI 集成、真实数据分析或模型接入。

P3-A.1 定向修正和验证已完成，等待人工审核。
