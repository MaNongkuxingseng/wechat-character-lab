# P2 工具审查报告 / Tool Audit

## 审查范围 / Scope

本次恢复后仅检查 Git 工作区状态，准备本报告，并执行 `git diff --check` 与
`git status --short --branch`。本阶段不运行消息提取候选工具，不解析聊天原文、语音或视频内容。

## Git 状态 / Git Status

- 当前分支：`main`
- 远端关系：`main` 与 `origin/main` 同步
- 工作区：存在既有未提交修改，涉及对话编排、语音分析、导入转换器、前端和测试
- 未跟踪内容：`AGENTS.md`、标准化导入模块、相关测试以及本报告目录
- 本阶段未执行清理、回滚、覆盖或提交操作

## 工具结论 / Findings

- WeChatBridge、wechatauto-replica 和其他消息提取工具：本次未运行，能力未重新验证。
- 视频导出能力：本次未运行工具验证，不能据此报告已提取成功或失败。
- SILK decoder、ASR、TTS：本次未运行；已有代码中的 Mock 或 pending 状态不能当作真实解析结果。
- 后续验证必须使用小样本、只读、可恢复流程，并为每个派生媒体保留来源、哈希和角色映射。

## 隐私与版本控制 / Privacy and Version Control

- 原始聊天、原始音频、视频、SQLite 数据库、模型权重、密钥和日志不得提交 Git。
- 任何转换结果写入独立派生目录，不覆盖原始导出。
- 报告只记录工具边界和 Git 状态，不包含聊天原文或媒体内容。

## 后续建议 / Next Steps

1. 先确认提取工具的安装位置、版本和公开契约。
2. 用单联系人、单批次验证视频资源引用与去重。
3. 在 decoder 可用后再报告 SILK 时长、声学特征或 ASR 结果。
4. 修复对话演示生成器，使其回应主题和上下文；真实 Provider 未配置时必须明确标记 Mock。

---

# P2-A Chat2Profile 与 ChatAnalysis.SKILL 源码及隐私审查

审查日期：2026-10-16（Asia/Shanghai）
审查性质：静态源码、公开契约和适配方案审查；**未执行真实聊天分析**。

## 1. 实际执行范围

已读取：

- `AGENTS.md`
- `README.md`
- `reports/preflight.md`
- `reports/p1-data-normalization.md`
- `reports/p1.1-bom-fix.md`
- 本报告已有内容
- 项目标准化入口 `backend/app/ingestion/wechat_normalizer.py`、契约 `docs/import-format.md`
- 两个候选公开仓库的 README、入口源码、依赖和许可证文件（通过公开 `raw.githubusercontent.com` 只读请求）

未执行：

- 未读取 `data/`、真实聊天正文、原始音频、视频或完整媒体数据库
- 未运行消息提取、ASR、TTS、画像分析或第三方脚本
- 未安装模型、依赖或未知安装脚本
- 未修改全局 Python、CUDA、代理、Codex 或系统配置
- 未提交、回滚、清理或覆盖任何 Git 内容

Git 状态和本报告中的结论分开记录：报告中的“源码审查结论”来自公开文件；不是本项目运行结果。

## 2. 候选工具定位与版本

### 2.1 Chat2Profile

- 官方仓库 URL：`https://github.com/shuweiran/chat2profile`
- 本轮读取分支：`master`
- 本轮 `git ls-remote` 可确认的 master commit：`f6cac87a170f83ae8129f666df88f29c149ba444`
- README 声称的版本：未声明；仓库 release/tag 未在本轮核验，标记为**未验证**。
- 本地源码：不存在；本项目未复制或安装该仓库。
- 证据文件：`README.md`、`SKILL.md`、`requirements.txt`、`src/schemas.py`、`src/importer.py`、`src/importer_weflow.py`、`src/extractor_rules.py`、`src/extractor_llm.py`、`src/pipeline.py`、`src/app.py`。

### 2.2 ChatAnalysis.SKILL

- 官方仓库 URL：`https://github.com/JularDepick/ChatAnalysis.SKILL`
- 本轮读取分支：`main`
- 本轮 `git ls-remote` 可确认的 main commit：`9cbf64286fed9eb1a0c78072fb9216f42104a41b`
- Skill 元数据版本：`ChatAnalysis/SKILL.md` frontmatter 中为 `1.2`，作者 `JularDepick`，日期 `2026-05-31`。
- 本地源码/注册 Skill：不存在；`C:/Users/Administrator/.codex/skills` 和 `C:/Users/Administrator/.agents/skills` 未找到该 Skill。
- 证据文件：`README.md`、`ChatAnalysis/SKILL.md`、`ChatAnalysis/references/methodology.md`、`ChatAnalysis/references/sensitive_content.md`、`LICENSE`。
- `SKILL.md` 是 Agent 流程规范，不是独立 Python CLI；文档要求运行时生成解析/渲染脚本。

## 3. 许可证与依赖审查

### 3.1 Chat2Profile

README 的“License”章节声称 MIT，但在 `master` 分支尝试读取 `LICENSE`、`LICENSE.md`、`LICENSE.txt` 和 `COPYING` 均返回 HTTP 404。因而：

- 实际许可证全文：**未验证**；不能仅凭 README 的 MIT 字样批准复制、修改或再分发。
- 接入建议：在作者提供可核验 LICENSE 文件或固定 commit 的许可证证明前，只允许内部评估，不纳入发布包。

`requirements.txt` 实际内容为：`pydantic>=2.0`、`httpx>=0.24`、`streamlit>=1.28`。源码还依赖标准库和本地模块；没有 lockfile，传递依赖、哈希和 Python 上限未声明。README 的 `pip install -r requirements.txt` 是文档路径，未在本项目执行。

### 3.2 ChatAnalysis.SKILL

已读取 `LICENSE`，实际为 MIT License，版权为 `JularDepick`，允许复制、修改和再分发，但需保留版权和许可声明。许可证不代表该工具对本项目数据安全或分析正确性作保证。

Skill frontmatter 声称 Python 3.8+，HTML 渲染时建议 `pip install markdown`。它没有固定 `requirements.txt`、lockfile 或可复现依赖清单；解析脚本由 Agent 运行时生成，因此具体依赖和版本取决于执行平台，部分内容为**未验证**。

## 4. Chat2Profile 源码行为

### 4.1 入口与输入输出

- Python 入口：`src/pipeline.py:ProfilePipeline`。
- 文件入口：`run_from_file(file_path, platform="auto")`；文本入口：`run_from_text(text)`；核心入口：`run_from_messages(messages)`。
- Streamlit 入口：`src/app.py:main()`，通过 `streamlit run src/app.py` 启动。
- `src/importer.py` 支持若干文本格式；`src/importer_weflow.py` 支持 WeFlow JSON。README 宣称的多平台支持需要逐一对照 importer，不能视为本轮验证结果。
- 输出是 Pydantic `ProfileSnapshot`，包含偏好、礼物信号、行为模式、未知项和统计；不是本项目候选的 `profile_item_id/subject_id/...` 结构。

### 4.2 消息、证据和画像字段

`src/schemas.py:Message` 要求 `message_id`、`timestamp`、`speaker`、`speaker_role`、`content_type`、`text`、`source_file`、`source_offset`，并支持 `source_kind` 与 `is_ai_generated`。这与本项目标准化消息的 `message_id`、`timestamp`、`sender`、`message_type`、`content`、`source_file`、`source_message_ref` 有可适配部分，但字段名和角色枚举不同。

规则提取路径在 `src/extractor_rules.py`：

- 规则信号引用原始 `Message.message_id`、时间、原文片段、`source_file` 和 `source_offset`。
- 会话上下文窗口默认 10 条；分享内容、意见问题和 AI 标记消息会被限制或排除。
- 负向证据、价格犹豫、购买/使用等信号有独立类型，具备一定反证保留能力。

关键缺陷在 `src/pipeline.py:_aggregate_preferences`、`_aggregate_gift_signals` 和 `_aggregate_behavior_patterns`：

- LLM 偏好结果只返回 `evidence_quotes`，聚合时生成 `message_id=f"llm_{pref_counter}"` 和 `timestamp=datetime.now()`，没有把引文匹配回输入消息。
- LLM 行为模式使用固定 `message_id="llm_bp"`，礼物信号的 `evidence_ids` 为空。
- 因此 README 所称“每条结论由原始聊天消息支持”只对规则路径部分成立；LLM 路径不能直接满足本项目的稳定证据追溯要求。
- 置信度是源码中的聚合/校准结果，但 LLM 仍可提供一个输入 confidence；该值不能直接当作经过本项目审核的概率。

### 4.3 在线、离线和数据外传

- `use_llm=False` 时，规则提取、会话切分和本地聚合可以在本地运行；这条离线能力基于源码结构判断，未在本项目运行验证。
- `use_llm=True` 默认构造 `LLMExtractor`，默认 API base 是 `https://api.deepseek.com`。
- `src/extractor_llm.py:LLMExtractor._call_llm` 通过 `httpx.post(f"{api_base}/v1/chat/completions", ...)` 发送 system prompt 和格式化聊天文本，包含时间、speaker 和 text，并带 Authorization header。
- 没有网络隔离、脱敏前置校验、请求审计或出网确认；异常文本会写入 `unknowns`，错误内容可能包含供应商异常字符串。
- Chat2Profile README 的“100% locally”与源码默认 `use_llm=True` 存在条件差异，必须以配置为准，不能作为实际离线验证结果。
- `src/app.py` 直接允许用户填入 API Base、API Key 和开启 LLM；本项目不应复用该 UI 作为生产入口。

### 4.4 推荐用途与禁止用途

结论：**有条件推荐**。

推荐用途：

- 仅在本机隔离环境中使用规则提取器，生成候选事实、偏好、反证和礼物信号草稿。
- 使用固定合成 JSONL 做 schema/规则回归，不接触真实聊天。
- 将 LLM 作为可选的离线本地模型适配器，且输出必须经过消息 ID 对齐和人工审核。

明确禁止：

- 未脱敏地开启默认 DeepSeek/任意外部 API；不得把真实微信聊天直接发送到网络。
- 将 LLM 引文、`llm_*` 占位 ID 或 `datetime.now()` 伪装成真实证据。
- 用其结果直接做人格诊断、心理疾病判断、关系操控或未经授权的声音/身份模拟。

## 5. ChatAnalysis.SKILL 源码/契约行为

### 5.1 真实 Skill 约定

`ChatAnalysis/SKILL.md` frontmatter 定义了 `name: chat-analysis`、触发条件、Python 3.8+ 兼容性和 `metadata.version: 1.2`。它要求 Agent：

- 先确认数据目录、私聊/群聊、焦点用户、输出模式和敏感内容策略。
- 读取 JSONL/文本等输入，运行时生成解析脚本。
- 输出 `.output/chat_stats.json`、Markdown 和可选 HTML 目录。
- 使用相对路径；默认原始数据只读；敏感内容模块有 `.full/.pure/.sensitive/.parts/.whole` 约定。

### 5.2 证据和隐私边界

- `SKILL.md` 和 `references/methodology.md`要求结论附聊天原文引用，但没有强制的标准 `message_id` schema、数据库表或验证器。
- 文档说明 JSONL 可含 `timestamp`、`sender` 等字段，却允许 Agent 根据实际格式运行时生成脚本；这会使稳定 ID、角色映射和异常行为依赖每次生成的脚本，不能直接作为本项目证据库。
- 该 Skill 的“善用子代理”和深度分析流程可能增加数据复制范围；没有本项目级的出网阻断、数据最小化和子任务审计契约。
- `sensitive_content.md`规定严重敏感内容在 HTML 中使用 `<details>` 隐藏，但隐藏不是加密或访问控制；`.full` 仍保留完整敏感内容。
- 文档明确“不负责聊天导出、提取或抓取”，所以不能替代现有 Inbox/WeChatBridge 适配器。

### 5.3 推荐用途与禁止用途

结论：**有条件推荐，不能作为生产画像主链路**。

推荐用途：

- 仅对经审核的合成小样本做报告结构、统计维度和 HTML 渲染原型评估。
- 借鉴其“事实/推断/未知”“反证保留”“敏感输出分层”等文档规范，转化为本项目的显式 schema 和审核流程。

明确禁止：

- 未注册为本项目兼容 Skill 前，直接把真实数据目录交给运行时生成脚本。
- 把报告中的自然语言引文当作可审计的 `evidence_refs`，或把 HTML 隐藏当作隐私保护。
- 允许自动子代理跨角色、跨会话复制原文；不得用于未经授权的关系或人格推断。

## 6. 与本项目标准化 JSONL 的适配方案

### 6.1 输入映射

本项目标准化记录由 `backend/app/ingestion/wechat_normalizer.py` 产生，字段包括：
`message_id`、`source_local_id`、`source_server_id`、`timestamp`、`sender`、`message_type`、`content`、`content_status`、`source_file` 和 `source_message_ref`。

建议新增独立 adapter（不修改第三方源码）：

| 本项目字段 | Chat2Profile `Message` | ChatAnalysis.SKILL 运行时输入 | 处理规则 |
|---|---|---|---|
| `message_id` | `message_id` | 需写入生成 JSONL 的 `id/message_id` | 原值保留；禁止用文本+时间重新哈希覆盖 |
| `timestamp` | `timestamp` | `timestamp` | ISO-8601 解析失败保留 `timestamp_status`，该记录不得作为时序证据 |
| `sender` | `speaker` | `sender/speaker` | 通过已审核映射转换为 `self/target/other`，未映射标记 unknown |
| `message_type` | `content_type` | `type/content_type` | `text/image/video/voice/...` 显式映射；媒体默认不作为文字偏好证据 |
| `content` | `text` | `text/content` | `content_status != present` 时传占位元数据，不伪造文本 |
| `source_file` + `source_message_ref` | `source_file` + `source_offset` | 自定义 `source_ref` | `source_ref` 必须包含稳定 `message_id`，而不是仅依赖行号 |
| `source_metadata` | `attachments/source_kind` | 自定义 metadata | 仅保留必要元数据，不复制原始媒体和身份数据 |

### 6.2 候选画像记录

本项目统一采用以下中间结构，第三方输出必须经过 adapter：

```json
{
  "profile_item_id": "pi_<stable-id>",
  "subject_id": "role_b",
  "category": "language_style|preference|behavior|fact",
  "claim": "候选结论文本",
  "evidence_refs": ["wechat:<local>:<server>"],
  "confidence": 0.0,
  "counter_evidence_refs": [],
  "observed_at": "2026-10-16T00:00:00Z",
  "updated_at": "2026-10-16T00:00:00Z"
}
```

字段能力判断：

- `subject_id`：可由已审核 `sender -> role_id` 映射补齐；第三方原始昵称不能直接作为角色事实。
- `category`、`claim`：规则工具可直接产生候选；ChatAnalysis 报告需解析/人工确认后产生。
- `evidence_refs`：Chat2Profile 规则路径可直接映射；Chat2Profile LLM 路径和 ChatAnalysis 自由格式均需 adapter 通过引文/时间/发送者匹配回稳定 `message_id`。匹配不唯一时必须拒绝该结论，不能宣称可追溯。
- `confidence`：可保留第三方分数作为 `raw_score`，但需由本项目校准器重新计算；缺失时标记 unknown，不默认 0.9。
- `counter_evidence_refs`：Chat2Profile 规则/冲突路径可提供候选；ChatAnalysis 需从报告和证据记录中显式抽取，否则为空并标注未验证。
- `observed_at`：使用证据消息的 `timestamp` 范围或明确分析时间；不能用 `datetime.now()` 冒充观察时间。
- `updated_at`：adapter 生成/审核时间，不是聊天发生时间。
- `profile_item_id`：由 subject/category/规范化 claim/证据 ID 集合的稳定哈希生成，禁止依赖第三方自增计数。

### 6.3 适配器最小契约

适配器必须：

1. 只接收脱敏、已审核、单一会话的标准化 JSONL。
2. 输出候选记录和 `unmatched_evidence` 清单；任何无法唯一回指的引文进入失败清单。
3. 保留 `source_message_ref` 和 `message_id`，不把原文复制到日志。
4. 对 AI/系统/媒体占位消息默认排除，除非人工明确批准其作为证据。
5. 分离规则事实、行为推断、弱推断和未知；不产出人格诊断。
6. 默认离线；任何网络 Provider 必须通过显式配置、出网提示和脱敏检查。

## 7. 接入决策矩阵

| 工具 | 决策 | 可用范围 | 主要风险 | 进入下一阶段条件 |
|---|---|---|---|---|
| Chat2Profile | 有条件推荐 | 规则提取器 + 结构化候选草稿；LLM 仅本地/已授权 Provider | LLM 默认出网；LLM 证据 ID 伪造；无 lockfile；LICENSE 文件缺失 | 固定 commit、许可证补证；adapter 完成引文到稳定 ID 的唯一匹配；合成数据回归通过 |
| ChatAnalysis.SKILL | 有条件推荐（报告原型） | 借鉴方法论、统计和 HTML 输出；仅合成小样本 | 运行时生成脚本；证据 schema 不固定；子代理/模型数据边界不清；HTML 隐藏不等于访问控制 | 复制 `ChatAnalysis/SKILL.md` 到项目受控适配层并补本地执行契约；关闭真实数据和外网；证据 ID 验证器通过 |

两者均不推荐直接作为本项目“画像事实库”的写入器，也不推荐直接驱动 A/B 角色提示词。角色提示词只能读取已审核、版本化且可追溯的 `ProfileTrait`。

## 8. 最小合成数据验证方案（未执行）

使用 8-12 条完全虚构、无真实身份和无真实媒体的 JSONL，覆盖：

- 一条明确喜欢、一条明确不喜欢、一条价格犹豫；
- 同一对象的一条反证和一条时间较新的变化；
- 一条链接/图片占位消息、一条 AI/system 标记消息；
- 两个角色各自一条消息，包含稳定 `message_id` 和 ISO-8601 时间。

验收：

1. 规则路径的每个候选 `evidence_refs` 都能唯一回到输入 `message_id`。
2. LLM 路径关闭或使用本地 stub；不得真实出网。
3. 引文匹配 0 个歧义；无法匹配时记录 `unmatched_evidence`，不写入画像库。
4. 反证保留，较新证据只影响状态/置信度，不删除旧证据。
5. 重复运行产生相同 `profile_item_id` 和排序。
6. 日志只包含计数、ID 和状态，不包含原文、密钥或媒体字节。

## 9. 未验证事项与停止条件

- Chat2Profile 的 release/tag、精确 Python 版本上限、完整依赖哈希、实际 LICENSE 文件：未验证。
- ChatAnalysis.SKILL 的全部运行时脚本、Agent 平台权限、子代理实际数据流和网络行为：未验证。
- 两个工具对本项目 JSONL 的实际运行兼容性：未验证；本轮没有运行它们。
- 本项目未新增适配器、未安装工具、未处理真实聊天数据。

本报告完成后按用户要求停止，不自动进入 P2-B。
