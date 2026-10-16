# P3-FE.0 前端实测准备度审查与页面冒烟测试

作者：valen MPF
项目：`wechat-character-lab`
分支：`feature/p2b-workspace-updates`
日期：2026-10-16（Asia/Shanghai）

## 1. 结论摘要

本阶段完成前端只读审查和低风险页面冒烟测试，没有修改前端生产代码、后端代码、数据库、迁移或 API，也没有读取 `data/`、真实聊天、媒体或凭据。

当前前端是一个单页工作台（single-page workbench），没有 React Router。页面包含会话、导入、语音和正式画像审核四个主要工作区。Vite 可以启动，TypeScript 检查和生产构建通过；在后端 `8001` 未启动时，页面能显示“后端未连接”以及各数据区的错误/空状态。

可以立即进行的低风险实测：

- 页面加载、静态布局、角色卡片、主题输入禁用态。
- 后端不可达时的连接错误、空会话、导入/画像/语音错误态。
- 以合成测试数据库运行的正式画像 API 与审核流程（已有后端测试覆盖）。

必须等待 P3-B.2 的功能：

- JSONL 候选快照持久化。
- 候选来源消息映射和 `ImportedMessage.id` 准入。
- `needs_review`、反向证据、未匹配证据和审核事件历史的 UI/API。
- 候选接受后生成正式草稿的联调。

## 2. 执行信息与边界

### 2.1 Git 与环境

- 当前分支：`feature/p2b-workspace-updates`
- HEAD：`39542bb docs(profile): 设计候选持久化数据契约`
- 远端：`origin/feature/p2b-workspace-updates`
- 审查开始时工作区：干净
- 前端依赖：现有 `frontend/node_modules`，未安装依赖
- 后端虚拟环境：`backend/.venv/Scripts/python.exe`
- 前端开发服务器冒烟端口：`127.0.0.1:5173`，测试结束后已停止
- 后端 `8001`：本阶段未启动，避免访问可能连接本机数据文件的现有服务

### 2.2 实际检查文件

- `AGENTS.md`
- `reports/p3-b1-profile-persistence-contract.md`
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/.env.example`
- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/types.ts`
- `frontend/src/hooks/useSession.ts`
- `frontend/src/components/ImportWorkbench.tsx`
- `frontend/src/components/ProfileWorkbench.tsx`
- `frontend/src/components/VoiceControls.tsx`
- `frontend/src/components/ChatTimeline.tsx`
- `backend/app/main.py`
- `backend/app/api/profiles.py`
- `backend/app/api/roles.py`
- `backend/app/schemas/profile.py`
- `backend/app/models/profiles.py`
- `backend/app/models/imports.py`
- `backend/app/profiles/service.py`
- `backend/tests/test_profiles.py`
- `backend/tests/test_api.py`

未读取 `data/`、`data/inbox/` 或真实导出文件；未运行 `backend/tests/test_imports.py`；未调用外部服务。

## 3. 前端结构与启动契约

| 项目 | 实际情况 |
|---|---|
| 构建工具 | Vite 6 + React 19 + TypeScript 5.7 |
| 启动命令 | `pnpm run dev`，Vite 默认 `127.0.0.1:5173` |
| 类型检查 | `pnpm run typecheck` |
| 生产构建 | `pnpm run build` |
| API 地址 | `VITE_API_BASE_URL`；代码默认 `http://127.0.0.1:8001` |
| 路由 | 无客户端路由；`App.tsx` 将所有工作区渲染在同一页面 |
| WebSocket | `useSession.ts` 根据会话 ID 连接 `/api/sessions/{id}/events` |
| 错误处理 | `api/client.ts` 将非 2xx 转为中文 `Error`；组件显示 `role=alert` |

`frontend/.env.example` 仍示例指向旧端口 `8000`，而 `client.ts` 默认指向 `8001`。这会造成按示例配置启动时的端口不一致，是当前联调前需要修正或明确文档的配置风险；本阶段不修改生产文件。

## 4. 页面、路由与 API 对照

项目没有独立页面 URL，以下为单页工作区和对应调用。

| 工作区/组件 | 前端调用 | 后端实现 | 当前状态 | 低风险测试 |
|---|---|---|---|---|
| 会话工作台 `App` + `TopicPanel` + `ChatTimeline` | `GET /health`、`GET /api/roles`、`POST /api/sessions`、WebSocket `/api/sessions/{id}/events` | 健康、角色、会话和事件路由已存在 | 已实现；依赖后端运行、角色 seed 和 WebSocket | 用测试 DB 检查健康/角色/会话；浏览器只做页面/错误态 |
| 导入 `ImportWorkbench` | `GET /api/imports`、`POST /api/imports/upload`、`POST /api/imports/inbox/scan`、preview、approve | 导入 API 已存在 | 已实现但会触及本地文件；不适合本阶段真实实测 | 仅用已有后端合成测试或不触发文件按钮 |
| 正式画像 `ProfileWorkbench` | list、analyze、detail、trait review、publish | `backend/app/api/profiles.py` 已存在 | 已实现；仅消费 `ImportedMessage` 正式链路 | 用合成 SQLite 测试数据；不代表 P3-B.1 候选可用 |
| 语音 `VoiceControls` | capabilities、assets、analyze、analyses、transcribe、synthesize | Mock ASR/TTS 与本地媒体 API 已存在 | 已实现但媒体分析可能读取本地素材；本阶段不触发 | 只检查静态/错误态，不调用 analyze/upload |
| 角色编辑 | 无可用调用，按钮 disabled | `PUT /api/roles/{role_id}` 存在，但未接入页面 | 只有后端能力，缺少页面 | 后端 API 已有测试；前端不可实测 |
| JSONL 候选审核 | 无对应前端 API/页面 | 仅有内存 `jsonl_service.py` | 尚未实现 | 等 P3-B.2 候选持久化/API |

## 5. 画像前端现状与 P3-B.1 差距

### 5.1 当前可用的正式画像工作流

`ProfileWorkbench.tsx` 支持：

1. 选择 `role_a` 或 `role_b`。
2. 读取正式画像版本列表和详情。
3. 调用 `POST /api/roles/{role_id}/profiles/analyze` 创建正式 draft。
4. 查看统计特征和数据库证据摘要。
5. 对特征执行 `accepted/rejected` 审核。
6. 所有特征完成审核且至少一项 accepted 后发布正式版本。

后端 `ProfileTrait.confidence` 为必填数值，前端类型也声明为 `number`。当前正式 schema 只接受 `pending/accepted/rejected`，没有 `needs_review`。

### 5.2 P3-B.1 要求但当前前端没有的能力

| P3-B.1 能力 | 当前情况 | 影响 |
|---|---|---|
| 候选快照和角色范围 | 无 API、无组件 | 无法查看一次 JSONL 分析的整体边界 |
| `source_dataset_id` / `source_message_id` | 正式证据只显示 DB `message_id` | 无法审查 JSONL 到 ImportedMessage 的映射 |
| `confidence=None` / unknown | 前端假定 number 并计算百分比 | 候选 unknown 会被错误表示或无法反序列化 |
| supporting/counter evidence | 正式 `ProfileEvidence` 无 direction | 反向证据不能安全地展示或持久化 |
| unmatched evidence | 无字段、无展示 | 映射失败原因不可见 |
| `pending/accepted/rejected/needs_review` | 只支持正式三态 | 无法表达需复核候选 |
| review event history | 无事件 API/组件 | 审核变化不可审计 |
| accepted but not publishable | 仅有正式 draft/publish 状态 | 候选接受和正式发布边界无法表示 |

因此，当前 `ProfileWorkbench` 不应直接接入 JSONL 候选结果。最小前端契约应新增独立 Candidate API 类型和工作区，保持候选 `accepted` 与正式 `publishable` 分离。

## 6. 实际冒烟测试

### 6.1 前端构建

```text
cd frontend
pnpm run typecheck
通过，退出码 0

pnpm run build
通过，Vite 生成 dist/index.html 和静态 assets，退出码 0
```

### 6.2 浏览器页面

使用本地 Vite 开发服务器 `http://127.0.0.1:5173/` 打开页面，检查可见 DOM/Accessibility tree：

- 页面标题为“微信角色实验室”。
- 顶部显示“后端未连接”。
- “对话工作台”“语音”“聊天记录导入与处理”“角色画像与证据”均可见。
- 主题输入框存在；创建会话按钮因未连接后端保持 disabled。
- 导入按钮、扫描 Inbox 按钮因未连接后端保持 disabled。
- 画像“生成统计草稿”按钮因未连接后端保持 disabled。
- 语音区显示 `Failed to fetch`，并显示“未发现 / 清单不可用”的空态。
- 导入和画像区显示 `Failed to fetch`，且导入来源为 0、画像版本为空。
- 页面未出现浏览器脚本崩溃空白页；开发者控制台未返回 error/warning 条目。

这次浏览器测试只覆盖启动、渲染和后端不可达分支，没有触发上传、Inbox 扫描、语音分析、画像生成、审核或发布。

### 6.3 后端正式画像定向测试

```text
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_profiles.py backend/tests/test_api.py
18 passed, 2 warnings, 退出码 0
```

警告为既有 Starlette/httpx 和 pytest-asyncio deprecation warning。测试使用项目测试 fixture 的内存 SQLite，不读取真实数据。

## 7. 可以立即实测与必须等待事项

### 7.1 可以立即实测

- 5173 页面加载、连接状态、空态和错误态。
- 在隔离测试数据库中验证正式画像 API 的分析、逐项审核、发布门禁和跨角色访问保护。
- 使用合成消息验证 `ProfileWorkbench` 的正式 `ProfileVersion` 展示和证据折叠。
- 使用合成 API 响应做前端候选列表原型，不连接真实数据。

### 7.2 必须先完成的后端依赖

- P3-B.2.1：候选 snapshot/item/evidence/review-event 数据结构和 migration。
- P3-B.2.2：幂等候选仓储、fingerprint 和脱敏日志。
- P3-B.2.3：`source_message_id -> imported_message_id` 显式映射与重新安全校验。
- P3-B.2.4：候选审核 API、证据方向和配置 diff。
- P3-B.2.5：接受候选到正式 draft 的准入适配。

### 7.3 可以用合成数据提前开发的 UI

- 候选快照列表：角色范围、分析器清单、状态和样本数。
- 候选详情：claim/category、`confidence` 的 unknown 展示、分析器版本。
- 证据分组：supporting、counter、unmatched，显示映射状态和拒绝原因。
- 审核操作：pending、accepted、rejected、needs_review，带 reviewer note。
- 预览 diff：候选配置相对当前角色配置的新增/删除变化。
- 明确的“已接受但尚未进入正式画像”提示。

### 7.4 暂不应接入真实数据的操作

- 将 JSONL `message_id` 直接提交到正式画像 evidence API。
- 在没有来源映射和安全复核时显示“可发布”或自动写入 `ProfileVersion`。
- 触发 `Inbox` 扫描、ZIP 上传、真实语音分析或真实媒体上传作为候选画像输入。
- 将 `confidence=None` 以 0%、100% 或默认数值展示。
- 将统计分析标签显示为人格、音色或语调结论。

## 8. 最小前端联调验收标准

进入 P3-B.2 后，建议以以下顺序验收：

1. `GET /api/profile-candidates` 能返回确定性排序的 snapshot/item/evidence 结构。
2. 页面能区分 `source_message_id`、`imported_message_id` 和 unmatched 状态。
3. unknown confidence 不被转换为百分比数值，且候选不能直接发布。
4. A/B 角色范围和证据归属在 UI 中可见，交叉证据被拒绝并显示原因。
5. supporting/counter evidence 不交叉，未匹配证据不会被静默隐藏。
6. 审核操作写入状态和 reviewer note，并能读取 review event history。
7. accepted 候选只能生成正式 draft，不能绕过正式 trait review 或 publish 门禁。
8. source 被撤销 approved、消息角色改变或安全标记变为 unknown 时，候选显示失效并禁止准入。
9. 页面错误态、加载态、空态和重复提交幂等态均有可见反馈。
10. 以上均使用合成数据和隔离测试数据库完成后，才考虑脱敏小样本联调。

## 9. 风险、未解决项与建议

### 已确认问题

- `frontend/.env.example` 的默认 API 端口是 `8000`，而源码默认 API 端口是 `8001`，存在新环境按示例配置后连接错误的风险。
- 单页没有 URL 路由，无法直接链接到画像审核或候选详情；后续页面增长时可考虑引入路由，但不应在 P3-B.2 之前扩大范围。
- 前端当前只消费正式画像模型，不能表示 P3-B.1 的候选层。
- 语音和导入组件在后端不可达时直接显示英文 `Failed to fetch`，与整体中文界面不一致；属于 UI polish 问题，不影响本阶段契约审查。

### 未确认事项

- 真实后端 `8001` 启动时是否存在已批准角色和可读数据库状态，本阶段未启动服务验证。
- 前端现有页面在真实导入源、真实媒体和真实候选 API 下的响应性能，本阶段未测试。
- 未来候选 API 的最终路径、分页和权限契约，需 P3-B.2 决策。

### 建议

1. P3-B.2 先确定 Candidate API schema，再为前端增加独立候选工作区，不修改现有正式画像工作区的语义。
2. 统一 `.env.example` 与 `client.ts` 的 API 端口，并在启动说明中明确后端端口。
3. 将 `Failed to fetch` 映射为统一中文错误分类，例如“后端未连接”“读取候选失败”“来源已失效”。
4. 候选 UI 先用 8–12 条人工合成消息和固定映射响应开发，禁止直接绑定 `data/`。

## 10. Git 与交付状态

本阶段只新增本报告；未修改 `task_plan.md`、`findings.md`、`progress.md` 或任何生产文件。报告完成后将执行 `git diff --check` 和 `git status --short --branch`，并在本阶段停止，不提交、不推送。
