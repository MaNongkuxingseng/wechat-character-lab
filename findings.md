# 现状发现与关键决策

## 本轮附件审计：已确认事实（2026-10-15）

- 原始导出共 37,769 条，含 78 条 type_code=43 视频；data 无视频文件不等于聊天无视频。现有转换器未保留视频附件路径，需从本地媒体层提取并关联消息。
- 当前生成直接调用 MockRoleAgent 固定模板；LLMProvider/MemoryRetriever 只是协议或 Mock，没有真实模型、检索实现。统计不是可运行角色设定。
- 当前画像只取按时间排序的前 1,000 条目标角色文字，缺少跨时间抽样、语境、反例、聚合和风格留出评测；已批准统计版本不能据此视为角色复现通过。
- 本轮实际查询 PyPI：pilk 0.2.4 同时有 cp310/cp311 win_amd64 wheel，没有 cp314；独立 3.11 环境是有具体发行依据的候选，尚未安装/验证。

## 2026-10-15：终端恢复、Mock 与媒体处理

- 当前 Node 执行入口可调用 PowerShell 并读取文件；此前“工具完全不可用”的判断已纠正。Get-Location 实际返回项目目录；Git 安装于 D:/Program Files/Git，完整路径 status --short 起始输出为空。
- 项目根目录及上级无 AGENTS.md，C:/Users/Administrator/.codex/AGENTS.md 为空；未创建子代理，既有代码和本地素材保留。
- 对话根因：450ms 自动循环缺少可用插话窗口；接收循环等待 Provider 生成时无法取消；轮换计数混入用户 Turn；终态事件仍 ACK 但不处理。现已增加等待、pause/resume、后台 generation 取消和状态校验。
- 媒体根因：PyAV 分支依赖未安装的 numpy，且错误地将 float/planar 样本统一除以 32768。现经 AudioResampler 统一成 mono s16/16kHz WAV，再计算真实声学摘要。ffmpeg 回退不依赖 ffprobe。
- 视频派生 WAV 使用源 SHA-256 命名并记录源路径、工具与版本；视频不自动映射角色。本机 data 仅 15 个文件，没有视频候选。
- SILK 安装检查：pilk 无 cp314 wheel；源码编译报 Microsoft Visual C++ 14.0+ 缺失。本轮不安装系统编译器、不伪造解码/ASR。

## 仓库现状

- 当前 `main` 包含初始工程骨架与角色资料/Inbox 导入审核阶段；当前工作区干净。
- `ImportedMessage` 有来源、说话人标签、角色映射、文本和时间，可作为后续分析的基础；目前没有读取已审核素材并执行画像分析的服务。
- `Role` 只有自由文本 `profile`、JSON `style_profile`、JSON `voice_profile` 和同意状态。缺少特征证据、置信度、审核状态及版本。
- `Memory` 适合记录事实/经历，不应兼任人格/语言风格画像表。
- `TTSProvider.synthesize(text, voice_id)` 只能选择音色，无法表达语速、停顿、重音、情绪等韵律控制。
- 当前 TTS、ASR 与 LLM 均为 Mock；当前前端没有画像分析审核工作流。
- 导入 parser 定义的是通用 `messages.json/jsonl/ndjson/csv` ZIP 契约，并非已确认的 WeChatBridge 私有格式。

## 已确定的产品判断

- 核心先后顺序应为“真实素材 → 证据化画像草稿 → 用户审核 → 文本行为验证 → 语音韵律还原 → 多 Agent 自动会话”。
- 分析输出必须是可质疑、可修订的判断，不得直接作为关于真人的确定事实。
- 画像类型拆分为事实、稳定性格倾向、语言表达风格、情境行为和声音/韵律；声音维度不能由纯文字生成。
- A/B 的私有素材与画像严格分区；共同经历只有显式共享后才能被两方读取。
- 声音克隆/相似音色必须有授权状态；未授权时用预设合成音色。
- 先做画像域和人工审核闭环，再接真实分析模型，避免让模型输出直接覆盖角色设定。

## 代码边界建议

- 新增独立 `profiles/` 领域和仓储；不要把分析特征塞进现有 `Memory`。
- 画像分析器是可替换的服务/Provider；它只消费明确授权、已审核且映射到角色的样本，返回带证据引用的草稿。
- 审核 API 负责接受、修改、拒绝和形成新版本；Agent 只读取已批准版本。
- 语音档案和 TTS 请求分离：profile 保存期望的韵律，provider 声明实际支持能力，编排层将指令映射到供应商参数。

## 阶段 1 实施决策（2026-10-14）

- 首轮画像分析不接真实 LLM、不自动猜测人格；先实现可解释的文字行为统计观察，如消息长度和问句比例，并标记分析器版本。
- 分析输入只限于 Source.status=approved 且 ImportedMessage.speaker_role_id 等于目标角色的消息；其他角色和未审核来源完全排除。
- 画像数据使用独立 ProfileVersion、ProfileTrait、ProfileEvidence；证据表只引用消息 ID 和说明，展示时再读取必要摘录。
- 特征审核为 pending / accepted / rejected；只有每条特征均被处理、至少一项接受，且接受项仍有有效证据时才能发布。
- 重新分析只创建新草稿，不覆盖旧画像；纯文本分析不生成声音或人格诊断结论。

## 阶段 1 实施决策（2026-10-14）

- 首轮画像分析不接真实 LLM、不自动猜测人格；先实现可解释的文字行为统计观察，诸如消息长度区间、问句比例，并将分析器标记为 `local_observable_v1`。
- 分析输入只限于 `Source.status=approved` 且 `ImportedMessage.speaker_role_id` 等于目标角色的消息；其他角色和未审核来源完全排除。
- 画像数据使用独立 ProfileVersion / ProfileTrait / ProfileEvidence；证据表只引用消息 ID 和说明，展示时从已导入消息读取必要原文，不重复长期保存摘录。
- 特征审核为 pending / accepted / rejected；只有每条特征均被处理且至少一条被接受时才能发布版本。重新分析创建新草稿，不覆盖现有已批准版本。
- 当前通用导入 JSON/CSV 契约只建立了来源审核状态；阶段 1 会显式把说话人映射作为分析的必要前置，不自动从标签猜角色。

## 聊天记录导入工作台核对（2026-10-14）

- 后端已有 Inbox ZIP 扫描、来源待审核、SHA-256 去重和确认时写入标准化消息的流程；前端此前没有任何上传、扫描、预览或审核映射入口。
- 当前归档契约是 ZIP 内包含 `messages.json`、`messages.jsonl`、`messages.ndjson` 或 `messages.csv`；不是对微信本地数据库或任意 WeChatBridge API 的直连。
- 新界面应在写入消息前展示发言人计数及有限样例，由用户显式映射 A/B；未映射消息虽可保留在来源中，但不能进入角色画像样本。
- 上传边界：只收 ZIP，限制压缩文件 50 MiB，解析器限制单个消息文件 100 MiB；原始文件保存在本机 `data/inbox/`，上传只创建待审核来源。
- `GET /api/imports/{source_id}/preview` 仅为用户提供最多 10 条、每条最多 240 字符的核对样例；批准后从已规范化消息读取。
- 已实现导入工作台：浏览器上传/扫描来源、发言人 A/B 映射、样例预览和人工确认；新接口只适配本项目 ZIP 契约，不代表已接通 WeChatBridge 自动 API。
- 为使新版与此前手动启动的 API 并存，本轮没有停止现有服务；新版单独监听 `127.0.0.1:8001`，配套前端监听 `127.0.0.1:5174`。

## 彭娜会话语音完整性核对（2026-10-14）

- 原始 JSON 中 `type_code=34` 的语音消息为 5 条；微信消息库 `get_voice_rows` 返回 5 条，按 `(local_id, server_id)` 对比无缺失、无多余。
- 5 条语音的媒体状态全部为 `available=true`、`reason=ok`；没有 `audio_not_downloaded`、`audio_missing_from_media_db` 或 `session_not_in_media_index`。
- 本地 SILK 导出清单包含 5 个文件、共 101,164 bytes，与 5 条语音逐条对应；文件清单中彭娜 1 条、我 4 条，目标文件均存在且 SHA-256 已记录。
- 当前结论仅证明“消息记录和微信本地媒体库完整对应”，不证明 SILK 内容能被当前电脑播放，也不包含服务器端未同步到本机的历史语音。图片/视频/文件需要分别做媒体库盘点，不能从语音统计推断。
## 2026-10-14：对话与语音首版边界

- WebSocket 首版采用显式 `session.start` / `session.stop`，避免连接建立时隐式启动导致前端事件竞态。
- 自动轮次任务由连接级 `asyncio.Task` 管理，并通过锁保护 SQLite 写入；停止和断开连接会等待任务取消，避免迟到的角色事件。
- `Turn` 中 `speaker_role_id=null` 表示用户插话；角色 A/B 始终使用各自 role_id，Director 不生成文本。
- Mock TTS 返回空字节时，API 必须返回 `available=false` 和 `audio_url=null`；空字节不能伪装成可播放音频。
- 当前运行中的旧端口服务不会自动热更新，源码改动后需重启项目服务；本轮已刷新 `8001`。

## 2026-10-14：媒体解析边界

- SILK 文件头包含 `#!SILK_V3`，但没有本地 SILK decoder；不能仅凭文件大小推断真实时长或音高。
- 音频分析应区分 `decoded`、`validated_pending_decode`、`unsupported` 三类状态；只有 `decoded` 结果才能参与时长、能量和韵律统计。
- 视频补充样本必须记录 `derived_from_video=true`、原视频路径和提取工具版本，避免把视频音轨误当作微信语音消息原件。
- 所有媒体路径必须限制在项目 `data/` 目录内；分析结果保存摘要，不复制原始音频字节到数据库。

## 2026-10-14：请求复合前端实测（进行中）

- 当前验收地址为新版前端 `http://127.0.0.1:5174/`，后端为 `http://127.0.0.1:8001/`。
- 页面能够展示已完成的“请求复合”会话，A/B 角色按奇偶轮次交替，状态为 `completed`；角色回复带有各自已审核画像的统计上下文。
- 当前页面默认自动轮次很快完成 12 轮，需在新会话创建后立即插话，才能验证 `user.message` 是否能打断或插入自动流程。
- 语音区域可见 5 段 SILK 与总大小 101,164 bytes，当前仍属于容器校验通过但未解码；TTS 明确未配置，不能宣称浏览器已有真实播放。

## 2026-10-16 P2-A 工具定位（未执行真实分析）

- 在项目代码、文档和 `C:/Users/Administrator/.codex/skills`、`C:/Users/Administrator/.agents/skills` 中未发现 `Chat2Profile` 或 `ChatAnalysis.SKILL` 的本地源码、`SKILL.md` 或可执行入口。
- 既有 `reports/preflight.md` 记录的候选公开来源为 `shuweiran/chat2profile` 与 `JularDepick/ChatAnalysis.SKILL`；本轮尚未读取其远程内容，版本、许可证实际条款和依赖均待公开仓库核验。
- 本阶段不读取 `data/`，不运行消息提取、ASR、TTS 或画像任务；任何 README 能力描述在源码核验前均标记为未验证。
