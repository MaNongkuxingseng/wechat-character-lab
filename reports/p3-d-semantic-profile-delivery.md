# P3-D 真实语义画像模块交付报告

作者：valen MPF

日期：2026-10-17（Asia/Shanghai）

## 1. 执行范围与 Git 状态

- 仓库：`G:\codex\wechat-character-lab`
- 分支：`feature/p2b-workspace-updates`
- 基线 HEAD：`340f2ff5188932d70e0932b55dd8168ee812b5ce`（`feat(profile): close P3-C source candidate lifecycle`）
- 执行前工作区干净，跟踪 `origin/feature/p2b-workspace-updates`。
- 本阶段保留了全部原有改动；未执行 reset、clean、rebase，也未读取或扫描真实聊天目录。
- 本报告编写时的最终提交 ID 与推送结果在提交后补录。

## 2. 复用实现及新增职责

P3-C 的来源批准、显式发送者到角色映射、安全标记、候选快照持久化、候选审核事件、准入、正式 ProfileVersion/trait 审核和发布均继续作为数据与生命周期边界。本阶段没有创建第二套画像表、ZIP/Inbox 处理链或正式画像发布流程。

- `backend/app/profiles/semantic_analyzer.py`：新增 OpenAI-compatible Chat Completions Provider，使用 Python 标准库传输；增加 `profile-semantic-v1` 输出校验、来源/消息文本传输授权、重试和可审计失败状态；禁用重定向。
- `backend/app/config.py`、`backend/.env.example`：增加语义 Provider 配置，默认关闭。
- `backend/app/profiles/jsonl_service.py`、`source_contract.py`、`candidate_persistence.py`、`synthetic_adapter.py` 及相应 API/schema：将语义输出接入既有角色隔离、消息安全门禁、证据回指和候选生命周期。
- `backend/app/api/imports.py`、`frontend/src/components/ImportWorkbench.tsx`：暴露来源级语义文本授权；授权与 provider 配置同时满足时才允许正文外发。
- `frontend/src/components/CandidateWorkbench.tsx`、`frontend/src/App.tsx`、`frontend/src/api/client.ts`、`frontend/src/types.ts`、`frontend/src/styles.css`：增加候选快照/特征查看、证据审核、状态变更、准入及正式画像审核/发布入口；调用现有 API。
- `backend/tests/test_semantic_analyzer.py`、`test_p3d_semantic_lifecycle.py` 及既有 JSONL 测试：覆盖 Provider 契约、安全边界、候选生命周期和重定向拒绝。
- `docs/semantic-profile-provider.md`：配置和能力边界说明。

## 3. 能力与语义契约

真实语义 Provider 当前实现为 OpenAI-compatible Chat Completions 客户端，不依赖新增 SDK。它默认不发送请求；必须同时具备来源级消息文本授权、`SEMANTIC_LLM_ENABLED=true`、`SEMANTIC_LLM_ALLOW_MESSAGE_CONTENT=true` 和有效 endpoint/model 配置。provider 会将当前角色范围内 `{message_id, content}` 发送至配置 endpoint；不会发送昵称、原始来源元数据、时间戳、数据库 ID 或文件名。API key 不写入日志。

响应必须满足 `profile-semantic-v1` 严格 JSON 结构。分析器验证特征类别、描述/推断依据、不确定性、可空置信度、冲突状态、support/counter ID 唯一性与方向、ID 是否属于本次角色输入，并拒绝来源原文照抄。无效引用、跨角色或虚构 ID、无 support、support/counter 重叠、无效 JSON 和非法字段均返回失败状态，不自动修复、不以 Observable/Fake 结果冒充真实语义结果。对限流、短暂服务错误和超时最多有限重试；最终失败状态保留在分析结果中。

`ObservableAnalyzer` 仍只提供可观测统计；`FakeSemanticAnalyzer` 仅供合成测试/明确本地用途。真实模型语义质量未经真实模型调用验证，因此不能视为已验收。候选审核人与准入状态、正式 trait 审核和 ProfileVersion 发布仍是不同阶段；接受候选不会自动发布。

## 4. 浏览器合成验收

在隔离 SQLite 和合成 ZIP 上完成页面闭环：导入合成来源、显式 A/B 映射、来源批准、候选分析、证据回指检查、人工审核、正式准入、正式 trait 审核及 ProfileVersion 发布。验收数据为 8 条合成来源消息，最终 supporting evidence 为 4/4 matched。数据库迁移只对隔离数据库执行，迁移到 `0007`。

此浏览器流程没有调用真实 LLM，也未使用真实聊天数据。一次导入夹具明确写入 `canonical_message_id: null`，严格来源校验将其判 invalid；修正合成夹具后，最终证据均回指成功。浏览器文件选择器自动化受扩展限制，因此合成 ZIP 通过本机导入 API 上传，之后在浏览器内完成审核和发布流程；没有修改扩展权限。

边界偏离：首次加载页面触发 `/api/voice/assets`，该端点读取了 `data/audio/.../manifest.json` 并返回聚合音频统计；没有读取音频/视频媒体字节、真实聊天正文或凭据。发现后立即停止该验收路径，改用不挂载语音路由的隔离服务完成后续测试。该次 manifest 访问超出了本阶段原定不接触媒体目录的边界，特此记录。

真实数据导入、真实语义分析、真实候选审核/发布和真实画像驱动浏览器对话均未执行；真实 LLM 联调未完成。没有用户提供的真实样本授权或已确认的真实 endpoint 发送边界，本阶段不向外部发送任何聊天内容。

## 5. 验证结果

以下为本次可复现执行结果。路径均从 `backend` 或 `frontend` 子目录执行。

| 命令 | 结果 |
|---|---|
| `backend\.venv\Scripts\python.exe -m pytest -q tests/test_semantic_analyzer.py tests/test_p3d_semantic_lifecycle.py tests/test_jsonl_profile_generation.py tests/test_candidate_persistence_models.py tests/test_m1_profile_engine.py` | 44 passed，2 warnings，退出码 0 |
| `backend\.venv\Scripts\python.exe -m pytest -q tests --ignore=tests/test_imports.py` | 125 passed，6 warnings，退出码 0；`test_imports.py` 未运行 |
| `backend\.venv\Scripts\ruff.exe check app tests` | All checks passed，退出码 0 |
| `frontend` 下 `npm run typecheck` | 通过，退出码 0 |
| `frontend` 下 `npm run build` | 通过，Vite 生产构建成功，退出码 0 |
| 隔离 SQLite 的 Alembic `upgrade head` | 成功，升级至 `0007`；未连接真实业务数据库 |
| `git diff --check` | 通过，退出码 0 |

警告来自既有 Starlette/httpx TestClient、pytest-asyncio 和 Alembic 配置弃用提示。曾从 `backend` 子目录误运行一次 `..\.venv\Scripts\python.exe`，因虚拟环境实际为当前目录 `.venv` 而退出码 1；随后使用上表正确路径重跑并通过，该路径错误不影响测试结果。

## 6. 安全审查与剩余风险

- Provider 默认关闭；没有调用真实 LLM、网络 API 或语音服务。
- Endpoint 只允许 HTTPS 或 loopback HTTP；禁用 HTTP 重定向，避免请求正文被转发至其他主机。loopback 合成测试验证服务端返回重定向时不会跟随。
- 日志只记录脱敏状态码/失败类别，不记录消息正文、证据片段或 API key。
- 当前系统没有认证用户身份。候选 workbench 收集的 reviewer ID 是调用者输入值，并非经身份系统验证的账户。
- 只有在来源已批准且明确授权消息正文传输、Provider 配置双开时才会将正文发送到设置的 endpoint。上线真实 Provider 前仍需核实 endpoint 运营方、保留政策、辖区和授权范围。
- 首次浏览器检查触及音频 manifest 的偏离已在上文披露；未读媒体字节。仓库内 `.p3d-tmp-inbox-e2e-20261017` 只含两份本轮合成 ZIP。服务停止命令已执行，但工具策略拒绝删除操作，因此目录保留且不纳入提交。
- 尚未用真实样本验证来源字段可信度、角色映射质量、重复记录和语义结果质量；这些是后续真实数据小样本验收的前置项。

## 7. 提交与推送

本阶段仅提交 P3-D 实现、测试和报告文件，并推送至 `origin/feature/p2b-workspace-updates`。提交 ID 由 Git 历史记录，远端结果见执行交付摘要。
