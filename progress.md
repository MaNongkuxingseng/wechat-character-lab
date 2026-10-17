# 开发进度记录

## 2026-10-17：P3-C 执行启动

- 已完整读取 P3-C 用户计划附件、仓库 `AGENTS.md` 和 `README.md`；已检查现有计划/进度/发现文件。
- 初始状态：`feature/p2b-workspace-updates`，HEAD `b008fd6`，与 origin 跟踪分支一致，工作区干净。
- 已开始检查 `security_flags.py`、`wechat_normalizer.py`、JSONL 服务、候选 API、ZIP/Inbox API；输出量过大导致个别源码片段被截断，后续将按文件分批检查。
- 严格不访问/扫描真实数据目录；当前未运行测试、未修改生产代码、未提交/推送。

## 2026-10-15：恢复执行与修复验收

- 实际执行 Get-Location 与 git status --short：PowerShell 可用；Git 因 PATH 缺失改用 D:/Program Files/Git/cmd/git.exe，初始工作区干净。三份计划文件已读取；项目/上级无 AGENTS.md，全局文件为空。
- Mock 会话：默认 4 秒轮间窗口（UI 2/4/8 秒），支持 pause/resume；后台生成可取消，暂停可插话；终态明确拒绝操作；用户 Turn 不影响 A/B 轮换；Mock 回复回显最近插话。
- 媒体：视频和压缩音频统一提取 PCM WAV，修正 PyAV 数值格式错误及 numpy 缺失；保存派生文件路径与 tool_version；前端刷新后加载已有分析并展示失败原因。
- 浏览器实测 5174/8001：创建→暂停→插话→继续→停止通过。SQLite 会话 0392f8aa-3e42-4b72-ac18-59698fbb6ad4 共 10 条 Turn（9 角色+1 用户），28 个事件的序号均唯一；状态包含 paused/running/stopping/completed，2 次 cancellation。
- 语音实测：现有 5 个 SILK 共 101,164 bytes，仍为 validated_pending_decode；A/B 解码样本 0/0。data 无真实视频；合成 MP4/M4A 的 PyAV/ffmpeg 提取、时长、RMS 和落盘测试通过。
- SILK blocker：pilk 无 Python 3.14 wheel，源码编译又缺少 Microsoft C++ Build Tools；无真实 ASR/TTS，本轮没有外发聊天或音频。
- 验证：后端 37 项测试、Ruff、前端 typecheck/build、git diff --check 通过（保留依赖 deprecation warning）。本机更新版服务运行于 8001/5174；未 commit/push、未创建子代理。

## 2026-10-14：系统重点复盘

- 状态：已完成复盘与路线重排，代码尚未开始角色画像分析阶段。
- 已核实当前实现：工程骨架、角色自由资料更新、通用 ZIP Inbox 扫描/审核/消息导入。
- 确认缺口：无性格/语言风格分析，无证据与置信度，无画像版本/用户审核界面，无个性化韵律 TTS；现有 TTS 只有文本与 voice_id。
- 新路线：画像证据模型 → 分析和审核闭环 → 文本风格评测 → 授权声音/韵律档案 → 多 Agent 与文字插话 → 实时语音 → Bridge API（待文档）。
- 本轮新增：`task_plan.md`、`findings.md`、`progress.md`。

## 阶段状态快照

- 阶段 0 工程与素材基线：完成。
- 阶段 1 画像证据模型：完成，已包含可解释本地统计、草稿 API、逐项审核和发布门槛。
- 阶段 2 分析与用户审核：进行中；画像审核工作台首版已完成，真实风格分析与评测尚未开始。
- 阶段 3 文本风格验证：待开始。
- 阶段 4 韵律画像与语音能力：待开始，需授权音频素材与供应商能力确认。
- 阶段 5 多 Agent 会话与插话：待开始。
- 阶段 6 语音会话与端到端验收：待开始。
- 阶段 7 Bridge 实际连接：等待接口文档/测试环境。

## 2026-10-14：聊天记录导入工作台

- 发现原后端已具备 Inbox ZIP 扫描/审核导入 API，但前端没有任何上传、来源预览或发言人映射操作，导致本地工作台无法实际导入素材。
- 新增 `POST /api/imports/upload`、`GET /api/imports/{source_id}/preview` 和导入能力描述；保留已有来源列表、Inbox 扫描及确认导入接口。
- 新增 ZIP 上传界面、来源状态列表、发言人计数、最多 10 条消息样例及 A/B 映射审核；未映射消息不参与画像分析。
- 上传归档限制 50 MiB，归档内消息文件解压限制 100 MiB；重复内容通过 SHA-256 去重；预览和确认前校验归档未被替换；损坏 JSON 返回可读格式错误。
- 新增 `python-multipart` 依赖与中文导入格式说明 `docs/import-format.md`。WeChatBridge 自动 API 尚未接入；当前需要 ZIP 符合项目导入契约。
- 测试：后端 23 项通过，Ruff 通过，前端 `pnpm run typecheck` / `pnpm run build` 通过，`uv lock --check` 通过。
- 本机服务：原有 5173/8000 进程保留；更新版启动在 `127.0.0.1:5174` 和 `127.0.0.1:8001`。新版后端健康检查为 `ok`，导入能力报告 ZIP 限制 52,428,800 bytes、Bridge 未连接。

## 2026-10-14：阶段 1 开发启动

- 状态：进行中。
- 方案决策：首版分析器只计算可解释的文字行为统计，不做未经证据支持的性格推断；画像和审核独立于 Memory。
- 输入限制：只用已审核来源且映射到目标 role_id 的消息；画像证据保存消息引用而非复制聊天原文。
- 已交付：版本/特征/证据模型、画像分析草稿与审核 API、迁移与隔离测试。

## 2026-10-14：阶段 1 完成

- 新增画像版本、画像特征与证据引用三类表及 Alembic migration。
- 新增 local_observable_v1，基于已审核且映射给目标角色的消息计算长度中位数、问句比例；分析器不会推断性格或声音。
- 新增创建草稿、版本列表/详情、特征审核、画像发布 API。
- 发布需所有特征均审核且至少接受一项；接受特征必须仍有同角色、已审核来源的有效证据；重新分析产生新版本。
- 测试覆盖未审核来源排除、A/B 隔离、证据失效、审核门槛、发布历史及最小样本数。
- 验证结果：后端 20 项测试通过，Ruff 检查通过，前端 typecheck/build 通过，Alembic 已升级至 0002。

## 2026-10-14：阶段 2 审核工作台首版

- 新增前端画像审核工作台：可切换 A/B、查看画像版本和证据、修订描述、逐项接受/拒绝并发布。
- 页面明确提示当前分析器只统计消息长度和问句比例，不推断人格、音色或语调；A/B 画像列表通过独立 API 加载。
- 修正角色切换时旧画像短暂残留、审核请求期间切换角色/版本导致响应串位，以及“全部拒绝仍可点击发布”的前端状态问题。
- 本机检查：`/health` 返回 `ok`；前端首页 HTTP 200；A/B 画像列表均返回空列表；数据库 migration 当前为 `0002_profile_evidence`。
- 验证结果：前端 `pnpm run typecheck` 和 `pnpm run build` 通过；后端 20 项测试通过；Ruff 检查通过；`git diff --check` 通过。
- 浏览器可视化验收未完成：Windows 浏览器自动化因无法可靠判定现有 Edge 窗口地址而停止；未继续对窗口输入或操作。
- 当前阶段状态：审核 UI 首版已交付，阶段 2 仍进行中。后续应定义可证伪的语言风格指标、情境/时间窗口切分、低置信度展示及留出样本评测，再评估是否引入允许外发素材的真实分析器。

## 2026-10-17：P3-E Provider 配置中心

- 开始前确认分支 `feature/p2b-workspace-updates`、HEAD `b18ae5c`；保留未跟踪 P3-D 临时目录和 R4/R5/R6 报告。
- 已完整阅读当前 `AGENTS.md`、planning-with-files 与 git-workflow 技能；计划/发现/进度均通过追加方式记录。
- 当前进行：核实真实 API、模型、迁移与前端结构；之后实现 E1/E2，运行测试、报告并定向提交推送。
- 安全约束：不扫描 Inbox，不读取真实聊天或凭据，不连接正式 DB；未设置有效本地 Provider key 时不作真实网络成功声明。
- 已确认 UI 配置需持久化并接入分析器解析路径；CORS 需要 PUT；无前端测试框架，不新增依赖。采用单例配置模型、DPAPI 加密 key 和环境变量显式覆盖规则。

## 2026-10-14：语音消息完整性核对

- 对照三层来源：原始 wechatauto JSON、微信消息库 `VoiceInfo`/语音消息行、项目导出的 `data/audio/pengna_20261014/manifest.json`。
- 验证结果：5 / 5 / 5 完全一致；原始消息与数据库按 `(local_id, server_id)` 无差集；5 条媒体状态均为 `ok`，导出文件总大小 101,164 bytes。
- 发言人分布：彭娜 1 条、我 4 条。未发现语音记录遗漏；当前没有 SILK 解码器，因此尚未验证可播放时长或音频内容。
- 后续动作：先安装/接入本地 SILK 解码器并做格式校验，再决定是否做 ASR 和韵律特征提取；未经授权不做真人声音克隆。

## 2026-10-14：当前开发状态快照

- 本地素材：1 个已批准来源，37,769 条消息；角色 A（我）16,371 条，角色 B（彭娜）21,398 条。
- 画像域：消息证据已入库，但 `profile_versions=0`、`profile_traits=0`；尚未生成可审核草稿，也没有发布任何画像版本。
- 语音域：5 条语音消息与 5 个 SILK 文件一一对应，共 101,164 bytes；尚未完成 SILK 解码、ASR、韵律特征提取或真实 TTS。
- 服务：更新版 API `127.0.0.1:8001` 和前端 `127.0.0.1:5174` 可用；旧版 `8000/5173` 仍在运行，后续验收应使用更新版端口。
- 工作区：导入器 metadata 兼容、CORS、转换脚本及本次进度文档存在未提交改动；真实聊天 JSON、ZIP、音频文件均被 `.gitignore` 排除。

## 2026-10-14：文字对话与语音模块开发启动

- 用户已审核 A/B 画像，开始阶段 5/6 的可运行闭环。
- 约束：先使用本地 Mock Agent/ASR/TTS，不调用网络、不上传聊天或音频；事件和语音响应必须标注 provider 与可用性。
- 本轮目标：WebSocket 自动轮流对话、用户插话、停止/结束状态、Turn/Event 持久化，以及转写/合成接口和前端可操作状态。

## 2026-10-14：文字对话与语音模块首版完成

- 新增 `ConversationOrchestrator`：Director 只决定 A/B 发言顺序，Role Agent 只生成 Mock 台词；上下文仅包含主题、角色资料和最近 6 条会话 Turn。
- WebSocket 新增 `session.start`、`session.stop`；连接后自动轮流生成 A/B 回复，用户 `user.message` 插话会保存为无角色 Turn 并触发下一轮；停止或断开连接会取消后台轮次任务。
- `Turn` 与 `SessionEvent` 写入 SQLite；客户端收到 `session.state`、`turn.created`、`message.created` 等事件，前端时间线已显示角色、轮次和文本。
- 新增 `POST /api/voice/transcribe`（15 MiB 本地上传限制）和 `POST /api/voice/synthesize`；Mock ASR 返回占位转写，Mock TTS 明确返回 `available=false`，不生成假音频。
- 前端语音面板支持选择 A/B 预设音色、导入音频测试 ASR 和查看 TTS 状态；尚未宣称实时录音、SILK 解码或真人声音克隆已完成。
- 验证：后端 28 项测试通过，Ruff 通过，前端 `pnpm run typecheck` 与 `pnpm run build` 通过。
- 运行环境：已重启项目自己的 `127.0.0.1:8001` 服务加载新代码；验收请打开 `http://127.0.0.1:5174/`，不要使用仍在运行旧代码的 `5173` 页面。
- Git 检查：`wechatauto_logs/` 已加入忽略；聊天 JSON、ZIP、SILK、数据库和本机日志均未进入工作区提交候选。

## 2026-10-14：语音解析与视频音轨分析完成

- 新增 `voice_analyses` 表和 `0003_voice_analysis` migration；仅保存媒体相对路径、SHA-256、格式、状态、声学摘要和错误，不保存音频字节。
- 新增 `MediaAnalyzer`：标准库 WAV 可计算真实时长、采样率、声道、RMS dB、静音比例；SILK 支持带 `0x02` 包前缀的 `#!SILK_V3` 结构校验并标记 `validated_pending_decode`。
- 新增 `POST /api/voice/analyze`、`GET /api/voice/analyses`；角色 A/B 样本隔离，默认低于 3 个可解码样本时扫描 data 下的视频。
- 视频解析优先使用系统 `ffprobe/ffmpeg`，否则可选 `PyAV` 读取音轨元数据；依赖组为 `uv sync --extra media`。无工具时返回 `video_audio_pending_tool`，不伪造特征。
- 实际分析现有素材：原始语音覆盖 A=4、B=1；5/5 SILK 文件均为 `validated_pending_decode`，可解码声学样本 A=0、B=0；当前 data 下未发现视频候选。已安装 PyAV 17.1.0 与 bundled ffmpeg 7.1，可在发现视频后进行音轨帧分析。
- 验证：后端 31 项测试、Ruff、前端生产构建全部通过；Alembic 已升级至 `0003_voice_analysis`。

## 2026-10-14：语音解析与视频音轨分析启动

- 当前真实语音样本为 5 个 SILK 文件（彭娜 1、我 4），尚无可直接播放的 WAV/MP3；本机未发现 `ffmpeg/ffprobe` 或音频 Python 库。
- 本轮将增加本地媒体分析器和 SQLite 记录：能解析的格式提供实际时长/采样率/声道/能量摘要，SILK 先做容器和帧结构校验并标记待解码。
- 当某角色可用语音样本低于阈值时，扫描本地视频文件；只有检测到可用 `ffprobe/ffmpeg` 才提取音轨，工具缺失不伪造分析结果。

## 2026-10-14：前端数据可用性修复与画像草稿

- 修复前端 API 默认地址：从旧的 `8000` 改为新版 `8001`，保留 `VITE_API_BASE_URL` 覆盖能力；`5173` 与 `5174` 页面均返回 HTTP 200。
- 新增 `GET /api/voice/assets`，只返回本地 SILK 清单元数据，不返回音频字节、不触发上传；语音面板现在显示 5 段素材和总字节数，并明确 ASR/TTS 仍为 Mock。
- 画像分析明确排除图片、语音、视频和系统消息，只使用文字记录；补充媒体排除回归测试。
- 修复画像特征 `created_at` 未赋值导致 SQLite 500 的问题。
- 已为角色 A/B 生成各一个 `v1 draft`：每个 1,000 条文字样本、2 项统计特征，等待前端逐项审核；未自动发布。
- 验证结果：后端 26 项测试、Ruff、前端 typecheck/build 均通过；API 可读到 approved 来源、A/B 草稿和 5 个语音资产。

## 2026-10-14：请求复合主题实测

- 使用新版页面 `5174` 创建主题为“请求复合”的会话，WebSocket 成功连接，A/B 自动轮流生成 12 轮，状态正常变为 `completed`。
- 回复包含角色 A/B 不同的已审核画像统计上下文（消息长度中位数、问句比例），证明画像上下文已进入 Mock Agent 请求。
- 插话实测未通过：创建后约 1 秒内自动完成 12 轮；用户随后输入并点击发送，时间线未出现 `user.message`。根因是自动轮次没有用户可用窗口，且已完成会话仍保留输入框但发送不会生效。
- 当前语音 UI 已显示 5 段 SILK、101,164 bytes、尚未解码；ASR 可测试，TTS 尚未配置。待完成语音解析按钮与本地音频上传测试。

## 2026-10-17：M2 画像驱动对话工作台交付收尾

- 已完成正式画像消费门禁：只读取 approved 版本中 accepted、无冲突且有有效证据的特征；会话创建保存 A/B 画像版本、特征 ID、readiness 和 `provider=mock` 快照。
- 已完成每轮画像重新校验和 `profile.context_used` 事件记录；来源撤销、画像版本变化或特征集合变化会阻断后续生成并返回 `profile_unavailable`。
- 合成回归、受限后端回归、Ruff、前端 typecheck/build 均在本轮复核通过；未运行 `backend/tests/test_imports.py`。
- 真实样本仅选择一个明确文件，转换得到 37,769 条记录、0 个转换错误和 0 个 ID 碰撞；隔离窗口中的 40 条文本消息安全标记均为 unknown，正式画像生成按安全门禁阻断，未伪造候选或发布结果。
- 隔离浏览器中已验证页面连接、A/B 画像 readiness、Mock 标识、A/B 轮流生成、暂停、用户插话和继续；停止请求最终进入 `completed`，但浏览器时序与自然轮次完成存在竞态，停止专项以自动化测试为确定证据。

## 2026-10-17：P3-C 执行续接

- 执行前分支/HEAD：`feature/p2b-workspace-updates` / `b008fd6e1b8e9f48fcc514c181e368c4ff40a953`，与远端跟踪分支一致；工作区包含已有 P3-C 代码、测试和规划文件改动，均保留。
- 已阅读 P3-C 附件及当前 P3-C 规划状态；初始 `git diff --check` 通过。
- 检查 `backend/tests/test_imports.py` 后确认它会写入、扫描和删除仓库 `data/inbox/` 下的文件，因此不运行。
- 未指定真实样本路径/授权证明；真实导入与候选生命周期留待有明确单文件选择和隔离条件后执行。本轮只验证合成输入与隔离测试数据库。
- 待办：重跑迁移/P3-C/M1 定向测试、受限后端回归、Ruff、前端 typecheck/build、diff 检查，并生成独立的 P3-C 交付报告；不提交/推送。
- 定向结果：`test_p3c_source_contract.py`、`test_converter_bom.py`、`test_m1_profile_engine.py`、`test_migrations.py` 共 17 passed；Ruff 定向检查经修复 import/空行格式后通过。
- 受限回归：`backend\.venv\Scripts\python.exe -m pytest -q backend\tests --ignore=backend\tests\test_imports.py`，116 passed, 6 warnings；迁移测试使用临时文件 SQLite。
- 静态检查：`backend\.venv\Scripts\ruff.exe check backend scripts/convert_wechatauto_export.py` 通过；前端 `pnpm run typecheck`、`pnpm run build` 均通过。
- 风险：定向迁移测试虽在隔离 SQLite 里升级至 head，但未覆盖已有 0005 候选记录经 0006/0007 升级和降级后的数据保留；需在报告中明确。
- 最终核对：`git diff --check` 退出码 0；分支/HEAD 未变化，20 个已跟踪文件修改、5 个未跟踪文件，包含 P3-C 报告；无 stage/commit/push。Git 仅提示部分文件后续写入时 LF 会被转换为 CRLF。
- 对未跟踪报告单独运行行尾空白扫描时发现并删除标题作者行空格；最终复查无尾随空白，`git diff --check` 退出码 0。
- P3-C 报告已完成，列出真实样本未执行、Inbox HTTP 路径未由自动测试覆盖、迁移已有候选数据回滚路径缺少专项测试以及消息删除 helper 尚无生产调用方等风险。任务停止等待人工 Review。
