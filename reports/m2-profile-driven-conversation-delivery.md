# M2 画像驱动双角色对话工作台交付报告

作者：valen MPF
日期：2026-10-17（Asia/Shanghai）

## 1. 范围与仓库状态

本阶段基于本地仓库 `wechat-character-lab` 的当前分支执行，目标分支为
`feature/p2b-workspace-updates`。执行前 HEAD 为 `b9c4e3b`
（`feat(profile): 完成人物画像引擎 M1 delivery`），执行前工作区干净且分支跟踪
`origin/feature/p2b-workspace-updates`。

本阶段没有连接真实业务数据库，没有执行真实业务库 migration，没有调用外部模型或
网络 API，没有运行 `backend/tests/test_imports.py`，没有触发 ASR/TTS、语音克隆或
真实 LLM。原始数据只读；真实样本的转换输出写入临时目录，未进入 Git。

## 2. M1 审查与本阶段修复

### 已确认的 M1 消费边界

- `backend/app/profiles/consumer.py:build_role_context()` 只选择正式 `approved`
  版本，并过滤非 `accepted`、有冲突、缺少 confidence、认知状态为 `unknown`，或
  缺少 `model_inferred` 推断依据的特征。
- supporting evidence 必须能连接到目标角色的 `ImportedMessage` 和 `approved`
  `Source`；上下文只返回引用 ID、来源状态和检索依据，不复制完整证据正文。
- `record_context_usage()` 写入 `profile.context_used`，只保留角色、画像版本、特征
  ID 和检索元数据。

### 本阶段代码变化

- 创建会话时校验 A/B 角色和正式画像 readiness；任一角色不是 `ready` 时返回
  `409 profile_unavailable`。
- 会话 settings 保存 `provider=mock`、A/B 的 `profile_version_id`、特征 ID、
  readiness，形成明确的会话画像快照。
- 会话创建使用角色级正式画像快照；主题作为独立上下文传给 Agent。现有
  `build_role_context(topic=...)` 只用于显式的只读主题检索接口，不在会话创建时强行
  以词面匹配过滤全部角色特征。
- 每轮生成前重新构建角色上下文并比对快照。来源撤销、画像版本变化、特征集合变化
  或 readiness 下降时抛出 `ProfileContextUnavailable`，WebSocket 暂停会话并返回
  `profile_unavailable`，不继续生成。
- Agent 的文本角色配置由当前角色已审核画像特征构造；原始 `Role.profile` 和
  `Role.style_profile` 不再作为未经正式画像审核的风格回退输入。
- 正式画像统计服务只接受安全标记明确为原生 `False` 的普通文本；unknown、缺失、
  AI 或 system 消息不会进入正式画像统计。
- Mock Director 仍只返回轮次和发言角色决策；Mock Role Agent 才生成台词。每轮事件
  记录角色、会话、画像版本、实际特征 ID 和 `provider=mock`。

## 3. 画像到 Agent 的调用路径

```text
POST /api/sessions
  -> get_roles_by_ids
  -> build_role_context(role_a/role_b)
  -> readiness 门禁 + profile_snapshots 写入 ConversationSession.settings

WebSocket /api/sessions/{id}/events
  -> session.start / pause / resume / stop / user.message
  -> ConversationOrchestrator
  -> MockDirectorAgent.plan_next(topic, role_turn_count, role_ids)
  -> build_role_context(..., session_id=id)
  -> record_context_usage(profile.context_used)
  -> MockRoleAgent.respond(role_profile, structured context)
  -> Turn + turn.created/message.created + session.state
```

用户插话保存为 `speaker_role_id=null` 的独立 Turn，不改变 A/B 轮换计数。最近对话只
作为对话上下文传给 Role Agent；候选表、未发布画像和未审核特征不会被直接读取。

## 4. A/B 隔离与会话状态

- A、B 由请求中的显式 `role_ids` 指定，schema 要求两个不同的角色 ID；前端提供两个
  角色选择框。
- Director 的 `speaker_role_id` 决定当前角色，Role Agent 接收该角色自己的
  `RoleProfile` 和画像特征，不交叉拼接 A/B 特征。
- 会话支持 `created -> initializing -> running -> paused -> running`，以及停止时的
  `stopping -> completed`。暂停和用户插话会取消当前自动生成任务并记录
  `generation.cancelled`；停止后不会重新启动自动轮次。
- `turn_limit` 同时约束角色 Turn 和用户插话 Turn；完成或停止后的会话拒绝再次 start
  和插话。

## 5. 前端与 API 契约

修改后的前端工作台支持：

- 选择 A/B 角色、设置主题和轮间等待；调用 `POST /api/sessions` 时显式传递角色 ID。
- 通过 WebSocket 接收 `connection.ready`、`session.state`、`turn.created`、
  `message.created`、`profile.context_used` 对应的可见结果和错误事件。
- 展示 Mock Provider、每个角色的 readiness、A/B 消息顺序和用户插话。
- 在 running/paused 状态提供插话、暂停/继续和停止；completed/error 状态禁用相关
  控件，避免过期会话事件污染当前页面。
- API 错误以 `profile_unavailable`、连接失败或生成失败提示，不把 Mock 输出标记为真实
  LLM。

## 6. 修改文件

### 后端

- `backend/app/profiles/consumer.py`：正式画像可消费特征过滤、证据状态和使用记录。
- `backend/app/profiles/service.py`：正式画像统计的安全标记门禁。
- `backend/app/api/sessions.py`：创建会话时的角色画像 readiness 和快照。
- `backend/app/core/orchestrator.py`：每轮画像校验、上下文使用记录、A/B 轮换和事件
  元数据；生成输入仅使用已审核的角色画像特征。
- `backend/app/api/events.py`：画像失效时暂停并返回可恢复错误。
- `backend/app/schemas/session.py`：返回会话 settings。

### 测试和前端

- `backend/tests/test_m2_profile_conversation.py`：无画像拒绝、A/B 快照、画像使用事件、
  来源撤销阻断。
- `backend/tests/test_api.py`、`test_m1_profile_engine.py`、`test_profiles.py`：补齐
  显式安全标记并覆盖暂停、继续、插话和取消生成的现有夹具。
- `frontend/src/App.tsx`、`frontend/src/components/TopicPanel.tsx`、
  `frontend/src/hooks/useSession.ts`、`frontend/src/api/client.ts`、
  `frontend/src/types.ts`：角色选择、画像状态和会话快照展示。
- `task_plan.md`、`progress.md`：记录本阶段完成状态和实测结论。

## 7. 合成数据自动化测试

本轮实际执行：

| 命令 | 结果 |
|---|---|
| `backend\\.venv\\Scripts\\python.exe -m pytest -q backend\\tests --ignore=backend\\tests\\test_imports.py` | 110 passed, 6 warnings，退出码 0 |
| `backend\\.venv\\Scripts\\ruff.exe check backend\\app backend\\tests` | All checks passed，退出码 0 |
| `pnpm run typecheck` | 通过，退出码 0 |
| `pnpm run build` | 通过，Vite production build 成功，退出码 0 |
| `git diff --check` | 通过，退出码 0 |

定向测试还覆盖了 `test_api.py`、`test_m2_profile_conversation.py`、
`test_profiles.py` 和 `test_m1_profile_engine.py`。自动化测试验证了：

- 没有正式画像时创建会话被拒绝；
- A/B 各自使用正确的 `profile_version_id` 和 `trait_ids`；
- Mock 输出使用对应的审核特征，不回退到角色表中的未审核 profile/style 文本；
- `profile.context_used` 不含完整证据正文；
- 来源撤销后下一轮生成被阻断；
- 暂停期间插话不改变 A/B 轮换，继续后恢复正确角色；
- 慢 Provider 在暂停或停止时被取消，分别进入 `paused`/`completed`，不写入迟到的角色 Turn；
- 停止、重复 start、完成后插话等非法状态得到协议错误。

未运行 `backend/tests/test_imports.py`，因此没有把受限回归描述为未排除导入扫描的
全量后端测试。

## 8. 真实导出数据解析与映射测试

根据补充要求，仅显式选择一个本地真实 JSON 导出文件；原始文件名、聊天正文、发言人
身份和真实 message ID 不写入本报告。实际转换命令的路径参数已在记录中脱敏，命令形状为：

```text
backend\\.venv\\Scripts\\python.exe scripts\\convert_wechatauto_export.py <selected-local-json> <temporary-jsonl-output> --format jsonl
```

转换结果：

- 输入/输出 37,769 条记录；唯一 message ID 37,769；转换错误 0；ID 碰撞 0。
- 已确认存在文本、图片、视频、语音、表情、位置、联系人及未知类型记录；文本记录
  32,718 条。
- 规范化输出包含 `message_id`、来源本地/服务端 ID、时间戳状态、sender、
  `message_type`、正文状态、`is_ai_generated`、`is_system`、
  `security_flag_sources`、`security_flag_inputs` 和来源引用字段。
- 此样本的两个安全标记均为 `None`/unknown；没有依据把普通文本或发送者名称推断为
  `False`。

在隔离内存 SQLite 中只取转换结果的前 200 条窗口，并筛选 40 条文本记录映射到两个
合成角色。40 条消息全部因 unknown 安全标记不能进入正式画像资格；A/B 画像生成均被
安全门禁阻断并返回样本不足。没有伪造候选、审核、准入或发布成功结果。该结果证明了
真实导出解析和字段映射可执行，但也证明当前真实来源尚不能满足正式画像的安全来源契约。

## 9. 候选、审核、准入和发布

真实样本部分没有进入候选生命周期：原因是安全标记 unknown，严格门禁在候选生成前
拒绝。这样避免把 unknown 默认成普通用户消息，也避免把 Observable/Fake 结果冒充真实
语义画像。

浏览器隔离场景使用的是临时 SQLite 中预置的合成、已发布画像，仅验证工作台消费和
审核后画像的对话链路，不代表真实样本已经完成候选审核、正式准入或发布。

## 10. 浏览器场景验收

在本地前端和临时后端数据库上完成的可见操作：

| 项目 | 结果 | 说明 |
|---|---|---|
| 页面打开/后端连接 | 通过 | 页面显示本机服务已连接 |
| A/B 角色和 readiness | 通过 | `role_a ready`、`role_b ready` |
| Provider 标识 | 通过 | 页面显示 `Mock Provider` |
| 创建主题会话 | 通过 | 主题会话创建，WebSocket 连接成功 |
| A/B 轮流生成 | 通过 | 时间线显示交替的 A/B Turn |
| 暂停 | 通过 | 页面状态显示 `paused`，自动生成被取消 |
| 用户插话 | 通过 | 时间线出现独立的用户插话 Turn |
| 继续 | 通过 | 状态回到 running，A/B 继续生成并回应插话上下文 |
| 停止 | 部分通过 | 发送停止请求后最终进入 `completed`；当时接近轮次上限，浏览器显示存在自然完成竞态。停止的取消和终态由后端自动化测试确定覆盖 |

首次只读访问旧的默认业务页面时发现其数据库 schema 与当前 ORM 不一致，错误为
`no such column: profile_versions.source_candidate_item_id`。没有对该数据库写入或执行
migration；后续浏览器验收改用临时隔离 SQLite 和合成已发布画像。

## 11. Mock 与真实 LLM 状态

- 当前工作台明确使用本地 deterministic Mock Director/Role Agent；其输出用于验证角色
  隔离、画像上下文拼接、事件持久化和控制流程，不代表真实人物语义模拟。
- 真实 LLM Provider 未配置、未调用，未向外部服务发送任何真实聊天数据。Chat2Profile、
  ChatAnalysis.SKILL 和 GPT-SoVITS 未在本阶段下载、安装或执行。
- Observable 分析器只提供可解释的文字统计能力，不能声称已经完成完整人物画像或语义
  特征提炼。

## 12. 未解决问题与前置条件

1. 真实导出中的 `is_ai_generated`/`is_system` 目前为 unknown；进入正式画像前必须由
   受控来源提供可审计的显式标记或经过批准的类型映射，不能默认填充 `False`。
2. ZIP/Inbox 路径仍与 JSONL canonical contract 不完全一致，尤其缺少安全字段和部分
   来源审计字段；本阶段没有修改该链路。
3. 真实语义分析、真实 LLM 联调和外部数据发送边界尚未完成，需要单独的脱敏、授权、
   Provider 配置和输出证据校验阶段。
4. 默认业务数据库需要先完成与当前 migration/ORM 的 schema 对齐，才能作为正式浏览器
   环境使用；本阶段只使用隔离临时数据库。
5. 浏览器停止动作应在未来加入更长轮次或可控延迟的专门 E2E 场景，以消除自然完成与
   stop 请求的时序竞态。

## 13. Git 与交付边界

本阶段只准备提交后端画像消费/会话编排、前端工作台、相关回归测试、计划文件和本报告。
临时数据库、临时 JSONL、构建产物、真实聊天、媒体、凭据和本地日志均未纳入提交候选。
提交前再次检查 `git status --short --branch`、`git diff --check` 和 staged diff；提交
后推送到 `origin/feature/p2b-workspace-updates`，最终提交哈希在交付消息中给出。

本阶段完成后停止，不自动开始 M3。
