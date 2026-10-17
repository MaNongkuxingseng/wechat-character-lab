# P3-D 仓库发现

## 初始核实

- 分支：`feature/p2b-workspace-updates`
- HEAD：`340f2ff51889` (`feat(profile): close P3-C source candidate lifecycle`)
- 执行前工作区：干净；跟踪 `origin/feature/p2b-workspace-updates`
- 既有 `task_plan.md`、`findings.md`、`progress.md` 包含既往阶段记录；不覆盖。
- P3-C 报告路径存在：`reports/p3-c-real-source-candidate-closure.md`。
- 关键源码实际存在：`source_contract.py`、`jsonl_analyzer.py`、候选持久化/审核/准入/消费服务、候选 API 与前端 App/API client。

## 待核实

- 实际候选 API 对语义 Provider 的注入/状态返回契约。
- 来源批准、消息映射、角色分离、安全门禁的数据结构。
- 现有正式画像审核/发布 UI 覆盖程度。
- 后端、前端环境以及 LLM Provider 配置是否存在。不得输出密钥或敏感值。

## 已确认的代码事实

- `POST /api/candidate/sources/{source_id}/analyze` 调用 `analyze_and_persist_approved_source()`；该入口以已批准 Source 重建规范化记录与明确的 A/B 映射，再用 `ObservableAnalyzer` + `DisabledLLMSemanticAnalyzer` 分析并复用候选持久化。
- `FakeSemanticAnalyzer` 是固定中文词项规则，代码明确不代表语义理解；`DisabledLLMSemanticAnalyzer` 当前配置 enabled 会直接报错，未实现网络客户端。
- `AnalyzerOutput` 当前有 analyzer 名称/版本/状态/样本数/signals；合法状态仅允许 ready/insufficient_samples/provider_disabled。JSONL 服务对所有 analyzer 输出作统一证据适配，并允许 disabled analyzer 不阻断角色 readiness。
- `source_contract` 校验输出角色范围、候选角色、支持/反向证据分离、message ID 存在和 sender->role 对应；持久化层重新核对 message->ImportedMessage、来源审批、安全元数据及角色映射。
- 候选审核 API 已提供快照查询、review event、review、admit；正式画像 API 支持 trait review 与 publish。候选 UI 尚未发现，正式 ProfileWorkbench 仅覆盖正式版本的规则统计候选审核。
- `ProfileCandidateItem` 已有 cognitive_state、inference_basis、conflict_status、confidence/source reviewer confidence、analyzer 名称/版本、review status；matched supporting evidence 是正式准入前提，counter evidence 当前会阻止 admission。
- 后端依赖没有必需 LLM SDK；Python 标准库可实现 OpenAI-compatible REST 客户端，不安装依赖。项目配置通过 Pydantic Settings 从环境变量/.env 读取。
- 当前 `test_imports.py` 风险已由既有计划记录；本阶段不得运行。当前只读操作没有访问 `data/`。

## P3-D 实施与复核结论

- 新增 `OpenAICompatibleSemanticAnalyzer`，使用标准库 HTTP 客户端；默认关闭，必须同时获得来源级消息文本授权、启用 provider 和消息内容传输配置。仅提交 role-scoped `message_id/content`，不发送昵称、数据库 ID、时间戳或原始 source metadata。
- 输出契约版本为 `profile-semantic-v1`；对字段形状、类别、置信度、support/counter 证据 ID、角色范围、未知引用、重复引用、证据方向冲突及原文照抄执行拒绝式校验。Provider 失败不会伪装成统计语义成功。
- 审查发现标准库 opener 默认会跟随 HTTP 重定向；已禁用重定向，并有 loopback 合成测试复现/防回归，避免授权正文被转发至另一个主机。
- 前端增加候选审核工作台和来源授权状态交互；候选审核、准入、正式画像特征审核/发布复用 P3-C/P1 API，不形成第二套画像表或 API。
- 浏览器验收以合成 ZIP 和隔离 SQLite 完成：导入、显式 A/B 映射、来源批准、分析、证据回指、候选审核、准入、正式特征审核和发布；最终 8 条来源消息，supporting evidence 4/4 matched。此结果仅证明规则/统计和候选生命周期，不证明真实 LLM 语义质量。
- 真实 LLM 未调用，真实聊天数据未读取，`test_imports.py` 未运行。首次页面加载读取了音频 manifest 聚合清单（未读媒体字节），发现后隔离语音路由并完成后续流程；属于边界偏离，已写入报告。
- 候选 workbench 的 reviewer ID 当前是调用者填写值，系统没有认证身份，不能视为已验证用户身份。
