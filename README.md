# 微信角色实验室（WeChat Character Lab）

这是一个本地优先（local-first）的双角色社交模拟系统。当前版本已提供本地 Mock 与显式选择的真实 LLM A/B 对话、用户文字插话、会话控制、SQLite 事件持久化、LLM Provider 配置中心和语义画像 Provider 接口，以及 ASR/TTS 语音接口骨架；ASR、TTS 和 WeChatBridge 仍未接入真实服务。

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
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

API 文档地址为 `http://127.0.0.1:8001/docs`。后端默认只监听本机回环地址，不暴露到局域网。

## LLM Provider 配置

打开工作台右上角的“LLM 配置”，可保存 Provider 类型、HTTPS 基础 Endpoint、模型 ID、超时和功能开关。首次加载时表单建议值（DeepSeek、`https://api.deepseek.com`、`deepseek-v4-pro`）只是待保存目标，不代表服务端支持该模型。保存后可分别执行模型目录连接测试和 `profile-semantic-v1` 协议测试；协议测试只发送固定合成文本，不读取聊天数据库。配置接口不会回传 API Key。

日常配置保存在本地 SQLite 的 Provider 配置表中。Windows 上 API Key 使用当前 Windows 用户的 DPAPI 加密后保存；其他操作系统会拒绝通过界面保存 API Key。请从运行后端的 Windows 用户上下文访问其配置数据库。不要手工把密钥写入仓库。若部署时改用进程环境变量或 `backend/.env`，显式设置的 `SEMANTIC_LLM_*` 字段（包括显式的 `false`）优先覆盖 UI 配置，页面会列出覆盖字段；覆盖生效时先前的测试状态显示为“尚未测试”。`.env.example` 中这些字段保持注释状态，因此复制模板不会意外锁定 UI 配置。按 README 中的后端启动方式从 `backend/` 目录启动，`.env` 才会按预期从该目录加载。

语义画像运行还需同时开启语义分析和真实正文外发开关，并满足来源审批、可信声明、角色映射和来源级传输授权。Provider 配置页中的全局正文开关不替代这些来源级门禁。`dialogue_enabled` 允许用户在新建会话时显式选择“真实 LLM”，但保存配置不会自动切换既有或默认 Mock 会话。

## 启动前端

另开一个终端运行：

```powershell
cd frontend
pnpm install
pnpm dev
```

前端开发地址通常为 `http://127.0.0.1:5174/`，默认连接 `http://127.0.0.1:8001`；如需调整，可设置 `VITE_API_BASE_URL`。如果 `5173` 上仍有旧进程，请使用 `5174` 验收本轮功能。

## 文字对话

在工作台输入主题并创建会话后，前端会自动建立
`/api/sessions/{session_id}/events` WebSocket，并发送 `session.start`。确定性 Director
按 A/B 轮流选择发言角色；默认 Mock Role Agent 生成明确标识的本地演示文本。选择“真实 LLM”时，后端要求 Provider 已配置、`dialogue_enabled=true` 且连接测试仍与当前配置摘要一致，再调用 OpenAI-compatible Role Agent。
用户可在时间线底部发送 `user.message` 插话，或发送 `session.stop` 停止后续轮次。每条 `Turn`
和 `SessionEvent` 均写入 SQLite。真实会话在创建时冻结 Provider/model 与 A/B 正式画像版本、trait ID；每轮重新校验 Provider 配置和画像证据有效性。配置或画像变化、来源撤销及 Provider 错误都会明确失败，不会静默回退 Mock。

默认轮间等待 4 秒，界面可选择 2/4/8 秒；创建 API 的 `turn_delay_seconds` 支持 0.5–60 秒。
`session.pause` 暂停、`session.resume` 继续；暂停期间仍可插话。插话/暂停/停止会取消后台
generation 并记录 `generation.cancelled`；用户消息不改变 A/B 轮换顺序。轮次上限统计所有
Turn（含用户插话）。已结束会话拒绝插话与重新启动；界面需新建会话。断线时自动暂停。

当前事件类型包括：`connection.ready`、`session.state`、`turn.created`、`message.created`、
`generation.failed`、`generation.cancelled`、`event.accepted`、`protocol.error`。真实成功事件记录 provider、model、耗时、trace ID、画像版本和 trait ID，但不记录 API Key、认证头或画像证据正文。Mock 台词不代表已经完成真实性格复现。

## 语音接口（Mock）

能力查询：`GET /api/voice/capabilities`；本地音频测试转写：
`POST /api/voice/transcribe`（multipart 字段 `file`，最大 15 MiB）；TTS 请求：
`POST /api/voice/synthesize`，请求体为 `{"text":"你好","voice_id":"preset-a"}`。
当前 ASR 返回明确的 Mock 文本，TTS 返回 `available=false` 和 `audio_url=null`，不会生成假音频。
前端语音面板可导入音频测试 ASR、选择 A/B 预设音色并查看 TTS 未配置提示；尚未实现浏览器
MediaRecorder、SILK 解码、流式播放或真人声音克隆。

## 语音解析与视频音轨分析

执行 `cd backend; uv sync --extra media` 安装本地媒体依赖后，可调用
`POST /api/voice/analyze`。服务会先分析 `data/audio/` 中的微信语音，再检查每个角色的
可用解码样本是否低于默认 3 条；样本不足时扫描 `data/` 下的 MP4/MOV/MKV 等视频。
视频结果会带 `derived_from_video=true`，不会混入微信语音原件统计。

解析状态分为 `decoded`（可计算时长、采样率、声道、RMS 与静音比例）、
`decoded_metadata`（仅能读取视频音轨元数据）、`validated_pending_decode`（SILK 文件头和
封装已校验，但当前没有专用 SILK decoder）、`video_audio_pending_tool` 和错误状态。
SILK 不能仅凭字节数推断时长或音高；安装专用 decoder 后可替换对应 Provider。分析摘要写入
SQLite 的 `voice_analyses` 表，不保存音频字节。

视频和 MP3/M4A 等压缩音频优先用 PyAV，回退到 ffmpeg（无需 ffprobe），统一提取
16 kHz / mono / s16 PCM。派生 WAV 保存于 `data/derived/audio/<SHA-256>.wav`，
结果记录 `decoded_path`、`original_source_path`、`extracted_by` 和 `tool_version`；
原始素材保留，视频候选不自动归属 A/B。本机没有视频时不会生成虚构视频结果。

当前 Python 3.14 没有可用的 pilk 预编译 wheel，源码构建又缺少 Microsoft C++ Build Tools；
因此 5 条 SILK 仍为 `validated_pending_decode`。ASR 仍为 Mock，没有真实逐字稿。

## Windows 工具路径排障

若 PowerShell 能执行但 `git` 提示无法识别，先用完整路径验证：

```powershell
Get-Location
& "D:\Program Files\Git\cmd\git.exe" status --short
```

这属于进程 PATH 问题，不需要放宽文件权限。当前项目也可直接使用
`backend/.venv/Scripts/python.exe` 运行后端检查；应用重启后再核对新终端 PATH。

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

## 聊天记录导入与处理

打开前端“聊天记录导入与处理”，上传微信侧导出的 ZIP 包。归档内需包含
`messages.json`、`messages.jsonl`、`messages.ndjson` 或 `messages.csv`。上传只会在本机
`data/inbox/` 保存原始归档并创建待审核来源；检查发言人和样例后，将发言人映射到角色 A/B，
再确认导入。未映射的消息不参与角色画像分析。上传限制为 50 MiB，解析后的消息文件限制为
100 MiB。详细字段和示例见 [docs/import-format.md](docs/import-format.md)。

对应接口：`POST /api/imports/upload`（multipart ZIP 上传）、`GET /api/imports`（来源列表）、
`GET /api/imports/{source_id}/preview`（有限样例预览）、`POST /api/imports/{source_id}/approve`
（映射并确认导入）、`POST /api/imports/inbox/scan`（扫描手动放入 Inbox 的 ZIP）。

当前没有真实 WeChatBridge 私有 API 接入；ZIP 结构需符合本项目公开契约。来源重复检测、文件变更
校验和审核后导入仍由后端执行。

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

本地 `data/` 目录和 `.env` 文件已加入 Git 忽略规则。不要提交聊天归档、逐字稿、音频、数据库文件、完整生成对话或 Provider 凭证。真实语义分析只在显式配置并通过来源授权门禁后发送有界消息正文；真实 Role Agent 使用已发布画像 claim 和有限会话历史，不读取候选表或原始画像证据。Bridge、ASR 和 TTS 仍未接入真实服务。
