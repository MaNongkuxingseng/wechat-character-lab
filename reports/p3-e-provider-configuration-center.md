# P3-E：LLM / Provider 配置中心交付报告

作者：valen MPF
执行日期：2026-10-17（Asia/Shanghai）

## 基线与状态

- 仓库：`MaNongkuxingseng/wechat-character-lab`
- 分支：`feature/p2b-workspace-updates`
- 起始 HEAD：`b18ae5c73db49582899c9ea15292898efd965326`
- 工作区原有未跟踪内容：`.p3d-tmp-inbox-e2e-20261017/`、`.p3d-ui-inbox-real-20261017/`、三份 P3-D 报告。它们均未被读取、修改、暂存或清理。
- `backend/.env` 不存在。没有从聊天、报告、日志或 Git 历史恢复凭据。
- 没有连接正式数据库；模型迁移只在隔离迁移测试数据库验证。

## 实现

- `GET /api/providers/config`：读取有效配置元数据，不返回 API Key。
- `PUT /api/providers/config`：保存配置；更换密钥时才传输新 Key，`clear_api_key=true` 才清除已有 Key。
- `POST /api/providers/test-connection`：请求配置模型的 `/v1/models` 并确认模型存在。
- `POST /api/providers/test-semantic`：调用现有语义分析器，以固定合成文本校验 `profile-semantic-v1`，不读取聊天数据库。
- `GET /api/providers/status`：返回当前配置状态、语义能力和 Agent 可用性。
- 环境变量/`.env` 中显式提供的 `SEMANTIC_LLM_*` 字段优先于 UI 配置；页面列出覆盖字段。存在覆盖时持久化的旧测试状态按 `not_tested` 展示，避免把旧连接结果当作当前配置证明。
- SQLite 单例配置表由 migration `0008_provider_configuration` 创建，仅保存配置元数据与密钥密文。
- Windows 使用当前用户 DPAPI 保护密钥；非 Windows 环境拒绝从 UI 保存密钥，不回退为明文存储。
- Provider 请求拒绝非 HTTPS、含用户信息、查询串或片段的 Endpoint；复用现有禁止重定向的 HTTP opener。语义状态只在语义与正文传输开关、连接测试及协议测试均满足时才可能显示可用。
- 前端增加 Provider 配置工作区。初始 DeepSeek Endpoint/模型仅为待保存目标；真实 A/B Agent 标记为“尚未接入”，配置开关不会改变 Mock 会话行为。

## 实际修改文件

- `backend/app/models/provider.py`、`backend/app/models/__init__.py`：配置模型与元数据注册。
- `backend/alembic/versions/0008_provider_configuration.py`：Provider 配置表迁移。
- `backend/app/providers/secret_store.py`：Windows DPAPI 密钥封装。
- `backend/app/profiles/provider_runtime.py`：配置优先级解析、Endpoint 校验、连接探测及状态记录。
- `backend/app/api/providers.py`、`backend/app/schemas/providers.py`：配置与状态 API。
- `backend/app/profiles/semantic_analyzer.py`、`backend/app/profiles/source_contract.py`：注入持久化有效配置及细化 Provider 错误状态。
- `backend/app/main.py`：注册 Provider 路由并允许本机前端 CORS PUT。
- `backend/tests/test_provider_configuration.py`、`backend/tests/test_migrations.py`：配置、密钥边界及迁移测试。
- `frontend/src/components/ProviderWorkbench.tsx`、`frontend/src/App.tsx`、`frontend/src/api/client.ts`、`frontend/src/types.ts`、`frontend/src/styles.css`：配置工作区、API 契约和样式。
- `backend/.env.example`、`README.md`：环境覆盖、配置存储、启动和安全说明。
- `task_plan.md`、`findings.md`、`progress.md`：本轮任务跟踪追加记录。

## Provider 联调状态

未执行真实网络请求：`backend/.env` 不存在，且没有其他已验证的本地凭据来源。本轮因此没有请求 DeepSeek 模型目录，也没有发送合成文本至真实 Provider；不会把模拟 HTTP transport 的自动化测试描述为真实联调。真实连接测试与语义协议测试仍需在用户本机配置有效 Provider 后从界面执行。

## 浏览器实测

- 在系统临时目录创建隔离 SQLite：`%TEMP%/wechat-character-lab-p3e-ui/provider.db`，迁移到 `0008_provider_configuration`；未连接或修改正式数据库。
- 启动隔离 FastAPI `http://127.0.0.1:8001` 和前端 `http://127.0.0.1:5175/`，通过 Edge 实际操作配置页。
- 首次读取显示未配置、API Key 未配置、语义不可用、真实 Role Agent 尚未接入、A/B 真实对话不可用；DeepSeek 默认值明确标记为待保存目标。
- 通过页面保存无密钥配置，把模型改为 `deepseek-chat` 后点击“重新加载”，模型值仍为 `deepseek-chat`，确认 UI 与后端持久化配置一致。
- API Key 密码框保持空白，页面没有回显已有或测试凭据。
- 在缺少 API Key 时分别点击“测试连接”和“测试画像协议”，两项均显示“配置不完整”；没有执行真实网络请求。
- 正文外发和真实对话开关默认关闭，页面显示来源审批、可信声明、角色映射与有界样本门禁说明。

## 验证

- `cd backend; uv run pytest tests/test_provider_configuration.py tests/test_migrations.py -q`：通过，11 passed。
- `cd backend; uv run pytest tests --ignore=tests/test_imports.py -q`：通过，136 passed；按安全要求未运行可能访问真实 Inbox 的导入测试。
- `cd backend; uv run ruff check .`：通过。
- `cd frontend; pnpm typecheck`：通过。
- `cd frontend; pnpm build`：通过，Vite production build 成功。
- `git diff --check`：实现整理后复查。

测试中有既有 Starlette/httpx、pytest-asyncio 和 Alembic 配置弃用警告，不影响测试退出结果。

## 限制与后续边界

- 未进行真实 Provider 网络联调；在没有本地凭据时此项为 blocked。
- 本轮未实现 P3-E3。当前真实 A/B Role Agent 及真实对话仍不可用，Mock 不会因 Provider 配置而自动切换。
- UI 密钥保存依赖 Windows 当前用户 DPAPI；跨 Windows 用户或设备迁移数据库时不能解密原密钥，需在目标用户下重新设置。
- 本地 Provider API 当前依赖回环地址部署边界；不要将该服务直接暴露到不可信网络。
- 后续应先在本机保存合法凭据，再从配置页分别运行真实模型目录测试与合成 `profile-semantic-v1` 测试；成功后仍需另行实施 P3-E3，真实聊天正文分析仍需来源级授权。
