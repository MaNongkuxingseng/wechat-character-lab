# 微信角色实验室（WeChat Character Lab）

这是一个本地优先（local-first）的双角色社交模拟系统工程骨架。当前版本提供 API/WebSocket 契约、SQLite 持久化、Mock Provider 边界和基础前端工作台；尚未实现真实对话生成或真实 WeChatBridge 导入。

## 环境要求

- Python 3.12 或更高版本
- `uv`
- Node.js 20 或更高版本
- `pnpm`

## 启动后端

```powershell
cd backend
uv sync --extra dev
Copy-Item .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API 文档地址为 `http://127.0.0.1:8000/docs`。后端默认只监听本机回环地址，不暴露到局域网。

## 启动前端

另开一个终端运行：

```powershell
cd frontend
pnpm install
pnpm dev
```

前端默认连接 `http://127.0.0.1:8000`；如需调整，可设置 `VITE_API_BASE_URL`。

## 验证

```powershell
cd backend
uv run pytest
uv run ruff check .
```

```powershell
cd frontend
pnpm typecheck
pnpm build
```

## 第二阶段导入流程

将 WeChatBridge 导出的 ZIP 文件放入 `data/inbox/`，归档内应包含以下任一文件：
`messages.json`、`messages.jsonl`、`messages.ndjson` 或 `messages.csv`。消息至少需要
`speaker`（或 `speaker_label`）和 `text` 字段，可选 `id`、`sent_at`。

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/imports/inbox/scan
Invoke-RestMethod -Method Get http://127.0.0.1:8000/api/imports
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/imports/{source_id}/approve
```

扫描只创建 `pending_review` 来源，不会自动写入消息或记忆；审核接口支持传入
`{"speaker_mapping":{"我":"role_a","朋友":"role_b"}}`，未知归档格式、重复消息 ID、归档被替换或路径越界都会被拒绝。

角色资料可通过 `PUT /api/roles/{role_id}` 更新，SQLite 是唯一主存储：

```json
{
  "label": "角色 A",
  "profile": "偏好简短、直接的表达",
  "style_profile": {"reply_length": "short"}
}
```

## 画像分析与审核（本地统计版）

导入来源审核通过并完成说话人映射后，可为指定角色生成画像草稿：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/roles/role_a/profiles/analyze
Invoke-RestMethod -Method Get http://127.0.0.1:8000/api/roles/role_a/profiles
```

当前 local_observable_v1 只统计文字消息长度和问句比例，不做人格诊断，也不推断声音。
每条观察包含来源消息引用、样本支撑度和审核状态；至少需要 3 条已审核且明确映射到
该角色的消息。逐项调用
POST /api/roles/{role_id}/profiles/{version_id}/traits/{trait_id}/review，
请求示例为 {"status":"accepted","reviewer_note":"已核对证据"}；
全部特征都处理后，再调用 POST /api/roles/{role_id}/profiles/{version_id}/publish 发布版本。
重新分析会创建新草稿，不覆盖当前已发布画像。

## 模块边界

- `core/` 管理编排契约和内部事件，不解析导入归档。
- `agents/` 管理角色与导演接口，不访问浏览器、音频设备或文件系统。
- `providers/` 适配模型与语音服务，不决定发言角色或轮次。
- `ingestion/` 管理导入适配器、归档解析和消息标准化。
- `memory/` 管理记忆检索契约；数据库访问由 repositories（仓储层）承担。
- `schemas/` 定义经过校验的 HTTP 与 WebSocket 数据结构。
- SQLite 是角色和会话数据的唯一事实来源（source of truth）；`data/profiles/` 仅预留给可导入的角色模板。

## 数据与隐私

本地 `data/` 目录和 `.env` 文件已加入 Git 忽略规则。不要提交聊天归档、逐字稿、音频、数据库文件或 Provider 凭证。当前 Bridge、LLM、ASR 和 TTS 实现均为 Mock，不会访问外部服务。
