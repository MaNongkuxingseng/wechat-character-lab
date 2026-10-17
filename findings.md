# 现状发现与关键决策

## 2026-10-18：P3-F 真实数据外发确认

- 用户已明确确认本次外发；授权对象仅为 `.p3d-ui-inbox-real-20261017/selected-real-sample-attested.zip`，SHA-256 为 `6BF4E68A9F805590110EE4CA7EEC6544DA4D65661D6C8A1A86CFEF2C4810729E`。
- 角色映射固定为发言人 1 → `role_a`、发言人 2 → `role_b`，不得根据正文或昵称重新猜测。
- 只向已配置 DeepSeek Provider 发送通过来源授权、安全门禁且角色隔离的有界必要文本；不发送整份归档、媒体或无关第三方消息。
- 完整对话正文和隔离 SQLite 仅保存在 `%TEMP%`，不得提交 Git。
- 页面从隔离 Inbox 扫描到唯一 ZIP：37,769 条消息、两位发言人；预览能解析时间戳和文本。报告仅保留匿名角色与聚合计数，不记录发言人身份或原始正文。
- 首次上传暴露仓库外 Inbox 路径注册缺陷；修复后由页面扫描已有只读副本成功登记，未重复发送或删除原文件。

## 2026-10-17 P3-C 执行准备

- 执行前 Git：分支 `feature/p2b-workspace-updates`，HEAD `b008fd6`，工作区干净并跟踪 `origin/feature/p2b-workspace-updates`。
- 用户提供的 P3-C 附件要求复用现有模型与状态机，不提交/推送；仅在授权明确的单个真实文件上才可做隔离验证，否则不得伪造真实闭环结果。
- 本地报告目录中存在 M1、M2、P3-B.1、P3-B.2.1 和 R1 报告；未发现 `reports/p3-a-profile-generation-mvp.md`。待逐文件核实其余依赖报告。
- 当前在只读检查中看到 `security_flags.py` 与 `wechat_normalizer.py` 已保留三态安全值及来源输入；ZIP/Inbox 导入使用独立 `normalize_message()` 路径，完整字段保留能力仍待检查导入解析、metadata 写入与候选验证。
- 现有工具 `task_plan.md`、`findings.md`、`progress.md` 属于仓库工作文件且内容已有历史记录，本阶段只追加，不覆盖历史。

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

## 2026-10-17 P3-C 源码发现（第一轮）

- `candidate_persistence.persist_profile_result()` 的 `source_dataset_id`、`input_digest`、`analyzer_digest`、`message_mapping` 都由调用方传入；角色范围被加入输入摘要，但没有受控的调用入口计算数据集身份/摘要，也没有把 JSONL source ID 与 ImportedMessage 的实际来源身份核对。
- 当前映射校验覆盖 ImportedMessage 存在、角色一致、其 Source 为 approved；但没有验证该 ImportedMessage 来自与 `source_dataset_id` 对应的已批准 Source，也没有比对 JSONL 消息来源 ID/内容摘要/时间戳与映射目标，因此映射可能错误但“合法”。
- `jsonl_analyzer.py` 中 Observable 和 Fake Semantic 信号都给 `confidence=None`；FakeSemantic 明确是确定性词项规则，不是语义模型。`admission.py` 是否拒绝 null confidence 及其具体理由待下一轮检查。
- `synthetic_adapter._is_eligible_text()` 只验证显式 security flag 为 bool、拒绝 True；没有重算完整 `security_flag_sources` 冲突关系。JSONL 服务另有 `_validate_security_provenance()`，需核实其输入来源和 ZIP/Inbox 映射的兼容性。
- 报告存在 `reports/p3-a-profile-generation-mvp.md`、M1/M2、P3-B.1、P3-B.2.1、R1、P2 工具审计；报告不能替代本轮源码实测。
- 没有本轮显式指定真实样本路径/范围，且不应从 `data/` 目录发现样本；本轮将先完成纯合成与隔离测试。若后续仍无用户明确选定/授权文件，则真实样本生命周期应记为阻断，不能伪称完成。
- `convert(... --format jsonl)` 调用 `normalize_payload()`，而 ZIP `convert()` 独立组装通用 `messages.json`，仅保留 raw `type_code` 等零散 metadata；它没有携带 canonical message ID、canonical message type 或安全三态/`security_flag_inputs`/来源审计。`archive_parser` 会把非 schema 字段拷入 `NormalizedMessage.metadata`，是可用的最小兼容承载点；规范化 JSONL 走 ZIP JSONL importer 时，`message_id` 当前会用作 external ID，但因属于 known field 而从 metadata 丢失。
- `persist_profile_result()` 低层映射只校验目标消息存在、role 与 Source approved，未核对 `message.source_id == source_dataset_id`；修复方向是新增只接受已批准 `Source.id` 的受控源分析入口，内部构造 canonical rows、dataset/input/analyzer 摘要和唯一映射，并为低层写入增加来源一致性校验。
- 正式准入明确拒绝 `confidence=None`（`confidence_required_for_formal_profile`）。现行候选审核请求没有人工置信度字段，导致 Observable 候选不能经正常审核准入；拟以 nullable reviewer-supplied confidence 与 review event before/after 字段审计，强校验仅接受数值 0..1，必须附审核说明，绝不覆盖分析器原值或自动填充。
- 默认 `analyze_normalized_messages()` 会运行 FakeSemantic 词项规则，但该实现只用于测试。受控生产入口将明确只启用 Observable + disabled LLM，保留可解释统计和外部关闭状态，不把 Fake 输出混作实际语义候选。
- `backend/tests/test_imports.py` 的两个测试会向仓库 `data/inbox` 写 ZIP、调用全目录 Inbox 扫描并删除该文件；按 P3-C 边界跳过，不执行。可在 `tmp_path` + 隔离 SQLite 对 `convert -> parse_archive -> Source/ImportedMessage -> analyze/persist` 做合成链路验证。
- 已新增 `backend/app/profiles/source_contract.py`：仅从 canonical records 计算 dataset/input digest，分析器 digest 固定纳入版本/运行状态、pipeline contract 和 Observable sample thresholds；来源持久化入口要求 approved `Source.id`，从已审核 `ImportedMessage` 的 explicit `speaker_role_id` 产生角色映射，匹配需核验 source、canonical ID、label/role、timestamp、canonical type、安全来源一致性和内容回指。
- 已新增受控 API `POST /api/candidate/sources/{source_id}/analyze`，只针对选定已批准 Source 运行 Observable + disabled LLM；输出脱敏统计，不回传正文。候选审核、准入仍走原有 API。
- ZIP 转换新增 `wechat-canonical-v1` 元数据并保留历史 external_id 格式；安全 flag 来源信息会通过 `NormalizedMessage.metadata -> ImportedMessage.metadata_json` 保存。普通文本 type_code 不被推断为安全 False，缺失证据仍 unknown。
- 准入置信度问题经隔离合成端到端复现并修正：CandidateItem 的原始 `confidence` 仍可为 NULL；新增 `reviewer_confidence`，严格要求显式审核、有效数值和审核说明，事件审计 before/after，准入只在此值存在时映射为正式非空 confidence。新增正式特征 `confidence_source`，区分可解释测量与人工评级。
- 初次 migration 探试 `op.create_check_constraint` 在 SQLite 失败（SQLite 不支持直接 ALTER CHECK）；已改成新增列时带 inline CHECK 的原地 ALTER，避免 batch-recreate 影响证据子表。迁移升级基础测试复通过，仍需增加“存在候选/evidence 数据时 upgrade/downgrade 保留”专测。
- 定向验证新增 `test_p3c_source_contract.py`，覆盖 JSONL/ZIP canonical 字段等价、来源映射、幂等、角色不匹配拒绝、未批准来源拒绝及候选审核→准入 draft→正式审核发布→consumer context 的合成闭环。
- 续接复核：当前分支 `feature/p2b-workspace-updates`，HEAD 与 `origin/feature/p2b-workspace-updates` 同为 `b008fd6e1b8e9f48fcc514c181e368c4ff40a953`；已有 P3-C 工作区修改共存于当前分支，不做清理、暂存或提交。
- `backend/tests/test_imports.py` 会创建仓库 `data/inbox/` 下的 ZIP，调用 inbox 全目录扫描并在 finally 中删除该文件；本轮按不扫描真实数据边界跳过，改以 tmp_path 合成转换测试覆盖解析逻辑。
- 本轮未发现用户明确选定且授权的真实导出文件路径；不枚举数据目录，不执行真实样本分析、审核或发布。
- 受控 Analyzer 入口实际构造 `ObservableAnalyzer()` 与 `DisabledLLMSemanticAnalyzer()`；后者只回报 `provider_disabled`，不会联网。`FakeSemanticAnalyzer` 明确标注为确定性词项规则，不代表语义理解。
- `backend/tests/test_migrations.py` 通过 `tmp_path` 文件 SQLite，Alembic 从初始 revision 升至 head；候选来源 ID 与正式 ImportedMessage 外键边界有专项检查。该测试没有覆盖在 0005 已存在候选记录上的 0006/0007 数据保留/降级场景，本报告将列为未覆盖项。
- 首次 Ruff 检查发现 `test_p3c_source_contract.py` 存在多余空行，按 `ruff check --diff` 修正；后续定向 Ruff 与 `ruff check backend scripts/convert_wechatauto_export.py` 通过。
- 定向 P3-C、转换器、M1 profile engine 与 migration 测试合计 17 项通过；全受限后端回归 `backend/tests --ignore=backend/tests/test_imports.py` 为 116 项通过。Starlette/httpx、pytest-asyncio、Alembic 存在 6 条弃用告警。
- 前端 `pnpm run typecheck` 和 `pnpm run build` 均通过；Vite 构建生成的 `frontend/dist` 未出现在 Git 状态中。

## 2026-10-18：P3-F 协议失败根因复核

- 真实样本结果的错误码为 `content_json_decode`，代码路径位于 `OpenAICompatibleSemanticAnalyzer.analyze()`：外层响应 JSON、`choices`、`message.content` 已经通过，随后 `_parse_provider_json(content)` 失败。
- 因此当前失败不是角色映射、证据 ID、support/counter 重叠或 `profile-semantic-v1` schema 拒绝；候选数为 0 是安全拒绝的结果。
- 现有解析器只接受纯 JSON 或首尾完整的 Markdown JSON fence；真实模型可能返回 reasoning 标签、前置说明、代码 fence 变体或 JSON 后置说明，需要先确认实际形态，不能直接放宽为“截取任意大括号”。
- 后续修复必须做到：只接受唯一可解析 JSON object；拒绝多对象/歧义内容；继续执行 schema、角色、证据引用和原文照抄校验；诊断只记录长度/包装类别，不记录聊天或模型正文。

## P3-E Provider 配置中心基线（2026-10-17）

- 当前分支 `feature/p2b-workspace-updates`，HEAD `b18ae5c`；执行前只有已有未跟踪的 P3-D 临时目录和 R4/R5/R6 报告，没有 tracked diff/staged changes。
- `backend/app/config.py` 使用 `pydantic-settings` 的 `.env` 和环境变量；README 要求从 `backend/` 工作目录启动。provider `.env` 文件当前不存在，不从聊天或历史恢复 key。
- `backend/.env.example` 已包含语义开关、endpoint、model、key、timeout 和输入上限字段；P3-E 需据此确认是否补 provider UI 所需默认/注释。
- Semantic Provider 当前使用完整 Chat Completions endpoint；模型目录、协议测试和 UI 配置服务尚需实际检索确认。
- `ConversationOrchestrator` 和 agents 当前仍是 Mock；P3-E 不更改此行为，状态 API 必须诚实报告真实 dialogue agent 未接入。
- 设计决策待代码核查：配置保存应与运行时单一解析器共享；secret 采用 Windows OS-protected storage 或可验证的 DPAPI 封装，不得明文入 DB/报告/log。
- 已确认 `backend/app/main.py` 的 CORS methods 目前只有 GET/POST/OPTIONS，P3-E 的配置 PUT 必须同步允许；`models.py` 实际为 `app/models/__init__.py` 聚合模型。
- `create_semantic_analyzer()` 当前通过 `SemanticProviderConfig.from_settings()` 读取 `get_settings()` 缓存；需给它注入解析后的运行配置，确保 UI 保存值与分析器运行时一致。
- semantic analyzer 已有严格结构/证据校验及 no-redirect opener；错误 HTTP 分类目前只有 429、5xx 和其他拒绝，需扩充鉴权/模型不可用/TLS/DNS 分类。
- 前端是 React 19 + Vite，无现成测试框架；以组件 API 行为实现、typecheck 和生产构建验证，不添加依赖。
- 新增 `provider_configuration` 单例模型与 0008 migration；密文列为 BLOB，不存明文 secret。Windows DPAPI 不可用的平台拒绝保存新 key，保留安全失败。
## P3-E.1 Provider 冒烟初始发现（2026-10-17）

- 基线：`feature/p2b-workspace-updates` / `37591fe`，与远端一致；工作区仅有执行前已有的两个 P3-D 临时目录和三份未跟踪报告。
- `backend/.env` 不存在；隔离后端使用 `%TEMP%/wechat-character-lab-p3e-ui/provider.db`。
- 状态 API 安全返回：DeepSeek Endpoint、`deepseek-chat`、60 秒、Key 已配置、无环境变量覆盖；未返回密钥。
- 当前连接状态为 `model_unavailable`，语义协议尚未测试；需用真实模型目录响应确认实际可用 ID，不能先验假定 `deepseek-v4-pro`。
- 真实模型目录请求 HTTP 200，返回 `deepseek-flash`、`deepseek-v4-pro`；原 `deepseek-chat` 被正确分类为 `model_unavailable`。
- UI 保存 `deepseek-v4-pro` 后，真实连接测试为 `success` / HTTP 200。
- 固定合成文本的真实语义请求返回 `success`，通过 `profile-semantic-v1` 校验，产生 2 个信号。
- 页面和状态 API 均显示连接/协议成功、语义可用；真实 Role Agent 与 A/B 对话继续为未接入/不可用。
- Uvicorn 日志仅包含本机路由与 HTTP 状态，不含 Key、Authorization、合成消息或 Provider 响应正文。
## P3-F 阶段 A 初步调用链（2026-10-17）

- 真实语义路径已存在：`source_contract.analyze_and_persist_jsonl()` 从 approved Source 构造角色限定消息，调用 `resolve_provider_config(db).semantic_config()` 和 `OpenAICompatibleSemanticAnalyzer`，再由现有 candidate persistence 写入候选。
- 候选审核、准入、正式画像 consumer 已存在，`ConversationOrchestrator._profile_context()` 每轮调用 `build_role_context()`，并与创建会话时保存的 `profile_snapshots` 比对，来源/证据失效会阻断后续生成。
- 会话真实 Agent 缺失：`ConversationOrchestrator.__init__()` 固定实例化 `MockDirectorAgent` 和 `MockRoleAgent`；`create_role_turn()` 事件固定写 `provider=mock`。
- P3-F 选择不新增会话表或迁移：`sessions.settings` 冻结 provider/model/config digest 与 A/B 画像快照，`session_events.payload` 记录逐轮 provider/model/status/latency/trace/profile version/trait IDs。
- 真实会话必须由创建请求显式选择 `provider_mode=llm`；默认仍为 Mock。创建与每轮执行都会校验 Provider 配置，配置变化、失效或调用失败均不回退 Mock。
- Director 保持确定性交替控制，Role Agent 才调用真实 Provider；这样保留既有暂停/继续/停止状态机，并避免让 LLM 决定角色归属。
- 现有 Turn/SessionEvent 表可复用；无需创建第二套对话消息表。需要在现有 session settings/turn event 中记录真实 provider/model/latency/error/画像版本。
- P3-F 应保持 director 为确定性轮换也可行，真实生成只需替换 RoleAgent；前端/API 必须区分 mode 并禁止真实失败回退 Mock。
