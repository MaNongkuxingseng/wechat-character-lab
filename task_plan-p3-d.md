# P3-D 真实语义画像模块交付计划

## 目标

在当前分支复用 P3-C 候选生命周期，交付真实 LLM Provider 的安全可运行边界、结构化画像校验、审核/发布前端入口、隔离合成测试和诚实的能力报告。无模型配置或真实样本授权时，不发送真实数据；本阶段仍需完成可复现实现与测试。

## 阶段

1. [完成] 核实仓库、P3-C 来源契约、候选服务、API、UI、配置与测试。
2. [完成] 实现默认关闭的真实语义 Provider 与版本化输出/证据/角色校验，接入受控来源候选流程。
3. [完成] 补足前端真实来源分析、候选审核、准入、正式审核/发布闭环。
4. [完成] 执行隔离合成 DB 集成、后端回归、Ruff、前端类型检查/构建、浏览器合成验收及敏感信息审查。
5. [进行中] 生成唯一最终报告，复核 diff 与 Git 范围，仅提交本阶段文件并推送当前分支。

## 约束

- 不读取/扫描 data、data/inbox 或真实聊天、媒体、凭据；不运行 test_imports.py。
- 无外部 LLM 调用、无依赖安装、无真实数据库连接/迁移。
- Provider 默认禁用；真实语义结果不可由统计或 Fake 结果冒充。
- 保留已有修改；禁止 reset、clean、覆盖式重写。
- 只报告实际测试结果；真实模型/真实样本验收若无配置/授权则明确阻塞。

## 错误记录

| 错误 | 处理 |
|---|---|
| 尝试用编码错配的上下文编辑已有 task_plan.md 未命中 | 保留原文件；另建 P3-D 专属计划、发现和进度文件 |

## 当前设计决定

- 保留现有 `ObservableAnalyzer`；`FakeSemanticAnalyzer` 只在测试/显式本地设置时可选，禁止作为默认语义实现。
- 新增 OpenAI-compatible Chat Completions Provider（Python 标准库），配置默认关闭；必须同时启用 Provider 和 `SEMANTIC_LLM_ALLOW_MESSAGE_CONTENT=true` 才允许把规范化消息文本发给配置 endpoint。
- 语义输出采用版本化 JSON contract；任何未知 message ID、跨角色引用、无 supporting evidence、support/counter 重叠、结构/字段非法均拒绝该输出，不做自动修复或降级。
- 统计和语义分析器状态/名称各自保留；语义 Provider 失败可保留统计候选，但顶层 semantic status 必须体现失败/禁用，不能把 Observable ready 等同语义 ready。
- 证据片段不写入候选 DB 或日志。模型请求仅含显式 source role 下的 message_id 与 content，不发送 sender 昵称、原始 source metadata、时间戳、文件名或 database ID。
- HTTP 重定向被显式禁用，防止带消息正文的请求被重定向到其他主机；增加 loopback 合成回归测试。
- 首次浏览器页面加载曾触发 `/api/voice/assets` 并读取 `data/audio/.../manifest.json` 的聚合清单；未读取媒体字节。发现后停止并以未挂载语音路由的隔离服务继续验收。此偏离在最终报告中披露。
- 浏览器扩展阻止文件选择器设置合成 ZIP；未变更扩展权限，改由本机合成导入 API 上传，并在浏览器完成后续流程。
- 严格证据校验曾将含 `canonical_message_id: null` 的合成记录判为 invalid；修正合成夹具后来源证据全部正确回指。
- 临时 Inbox 目录只含两份合成 ZIP；受工具策略限制，删除操作被拒绝，未纳入提交。相关服务停止命令已执行。
