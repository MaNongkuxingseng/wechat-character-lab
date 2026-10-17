# P3-D 真实语义画像验收记录 R3

作者：valen MPF
日期：2026-10-17（Asia/Shanghai）

## 1. 结论摘要

本轮完成了经用户授权的单个 Inbox 样本的界面导入、来源批准、显式角色映射、隔离数据库画像验证，以及主题为“复合”的 52 轮本地对话流程验证。真实来源和页面流程可运行，但真实 DeepSeek 语义画像没有通过：本轮使用的 DeepSeek 凭据请求模型目录返回 HTTP 401 `Authentication Fails`。因此不能把本轮结果标记为“真实语义画像完整交付”。

已确认的结果分开如下：

| 验收类别 | 结果 | 说明 |
|---|---|---|
| 真实样本界面导入 | 通过 | 仅选择一个授权样本；原始文件只读，使用隔离副本和隔离 SQLite |
| 来源批准与可信声明 | 通过 | 用户声明为人工聊天，且不含 AI/system 消息；声明被写入来源元数据 |
| A/B 角色映射 | 通过 | 发言人 1 → `role_a`，发言人 2 → `role_b`；未按昵称或正文猜测 |
| 本地统计画像 | 通过 | A/B 各生成并发布 `local_observable_v1` 画像；这是统计画像，不是语义画像 |
| DeepSeek Provider 联调 | 未通过 | `GET https://api.deepseek.com/v1/models` 返回 HTTP 401 |
| DeepSeek 真实候选 | 未通过 | 两个角色均为 `provider_rejected_request`，候选数为 0 |
| 真实语义候选审核/准入 | 未完成 | 没有可审核的 DeepSeek 候选，不能伪造审核或准入结果 |
| 52 轮工作台流程 | 通过 | 52 个唯一轮次，A/B 各 26 轮，Provider 明确为本地 Mock |
| DeepSeek 驱动的 52 轮对话 | 未完成 | Provider 认证失败，未将 Mock 结果冒充 DeepSeek |

## 2. 执行边界与环境

- 分支：`feature/p2b-workspace-updates`
- 执行时 HEAD：`a0c781c docs(profile): 记录 DeepSeek Provider 联调 (DeepSeek provider test)`
- 所有真实样本操作在隔离目录和隔离 SQLite 中完成；没有连接正式业务数据库。
- 没有读取音频、视频或凭据文件，没有向报告、日志或 Git 写入 API key。
- 未运行 `backend/tests/test_imports.py`，未调用 Chat2Profile、ChatAnalysis.SKILL、ASR、TTS 或语音克隆。
- DeepSeek 请求只验证认证和 Provider 行为；由于认证失败，没有发送真实聊天正文。

本报告不记录真实文件名、发言人姓名、聊天正文、证据片段或 API key。用户此前在对话中暴露过的密钥应立即撤销并重新生成。

## 3. 真实样本导入与规范化

通过现有 Import Workbench 完成以下操作：

1. 在 Inbox 中显式选择一个样本，并使用隔离副本执行导入。
2. 勾选文本传输授权和可信声明。
3. 记录审核人 `authorized-reviewer-2026-10-17` 及声明理由。
4. 显式设置 `发言人 1 -> role_a`、`发言人 2 -> role_b`。
5. 提交导入并在隔离数据库中检查来源状态。

脱敏统计结果：

- 消息总数：37,769。
- 两个主要发言人；角色桶分别为 21,398 和 16,371 条消息。
- 非空文本消息约 32,718 条；媒体和其他非文本消息未进入普通文本画像。
- `external_id` 唯一；时间戳均解析为有效 UTC 时间。
- 导入后的来源状态为 `approved`，来源元数据包含 `security_attestation` 和 `semantic_llm_authorized`。
- 原始消息级 `is_ai_generated`、`is_system` 保持 `None`，未通过默认 `False` 绕过安全门禁；可信声明作为可审计的来源级证据参与放行。

## 4. DeepSeek Provider 实测

目标 Provider：DeepSeek OpenAI-compatible API。请求使用模型目录接口进行非敏感认证检查，实际结果：

```text
GET https://api.deepseek.com/v1/models
HTTP 401
invalid_request_error: Authentication Fails
```

随后通过页面对真实来源分别触发 A/B 语义分析，结果均为：

```text
semantic_status: provider_rejected_request
candidate_count: 0
analyzer: llm_semantic_openai_compatible
```

这证明失败被显式返回，没有静默降级为 Fake、Mock 或 Observable 结果。需要新的有效凭据后才能重新执行真实语义候选链路；本报告不保存或重复输出任何密钥。

## 5. 真实来源上的本地统计画像

在 DeepSeek 阻断后，使用现有确定性 `local_observable_v1` 对同一已批准来源进行本地分析。该结果只证明统计管线和发布流程可用，不证明语义人物画像质量。

| 角色 | ProfileVersion | 状态 | Analyzer | 样本报告 |
|---|---:|---|---|---:|
| `role_a` | 1 | `approved` | `local_observable_v1` | 1000 |
| `role_b` | 1 | `approved` | `local_observable_v1` | 1000 |

两个角色的 readiness 均为 `ready`。每个角色的两个统计特征已在页面逐项接受并发布。由于它们不是 DeepSeek 语义候选，本节结果不能替代真实语义候选审核、准入和语义 trait 发布。

## 6. “复合”主题 52 轮对话记录

会话在隔离环境中创建，主题为“复合”，轮数限制为 52。会话使用已发布的本地统计画像快照，但生成 Provider 为明确标记的 `MockDirectorAgent/MockRoleAgent`。以下是从隔离数据库导出的结构化记录；正文全部按安全边界脱敏，不包含真实聊天内容或完整模型输出。

会话摘要：

- 会话 ID：`2d9816ad-4684-4374-b705-d11ed667f7b6`。
- 状态序列：`initializing` → `running` → `completed`。
- 唯一轮次：52；`role_a` 26 轮，`role_b` 26 轮。
- 重复轮次：0；轮次按 1 至 52 连续递增。
- Provider：全部为 `Mock`；不是 DeepSeek，不代表真实语义生成质量。

| 轮次 | 发言角色 | Provider | 状态 | 正文处理 |
|---:|---|---|---|---|
| 1 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 2 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 3 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 4 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 5 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 6 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 7 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 8 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 9 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 10 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 11 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 12 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 13 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 14 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 15 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 16 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 17 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 18 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 19 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 20 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 21 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 22 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 23 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 24 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 25 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 26 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 27 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 28 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 29 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 30 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 31 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 32 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 33 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 34 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 35 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 36 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 37 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 38 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 39 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 40 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 41 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 42 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 43 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 44 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 45 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 46 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 47 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 48 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 49 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 50 | `role_b` | Mock | completed | 已记录，正文脱敏 |
| 51 | `role_a` | Mock | completed | 已记录，正文脱敏 |
| 52 | `role_b` | Mock | completed | 已记录，正文脱敏 |

这 52 轮证明了工作台的轮次、角色交替、状态完成和隔离画像快照流程；它们不证明 DeepSeek 已生成消息，也不证明本地统计特征驱动了真实人物语义。

## 7. 质量检查表

| 检查项 | 本轮结果 |
|---|---|
| 证据可回指 | 真实来源导入和消息 ID 映射通过；DeepSeek 候选为 0，未产生可审核语义证据 |
| A/B 角色隔离 | 导入映射和 Mock 会话角色计数通过；没有 DeepSeek 特征可抽查 |
| 事实与推断区分 | 本地 Observable 结果按统计画像标记；未将其写成语义事实 |
| 不确定性 | 未知安全标记不被消息级默认 `False` 替代；DeepSeek 失败显式返回 |
| 矛盾处理 | 未生成 DeepSeek 候选，因此没有虚构 supporting/counter 结论 |
| 语言风格证据 | 本地统计仅提供可观察统计，不宣称语义风格判断 |
| 重复运行稳定性 | Observable 和 52 轮结构测试通过；真实模型重复一致性未验证 |
| 生命周期 | 本地画像发布状态可读取；DeepSeek 未审核、未准入、未发布 |

## 8. 实际检查命令

本轮及前置实现实际使用项目虚拟环境，未安装依赖：

```text
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_semantic_analyzer.py backend/tests/test_profiles.py backend/tests/test_p3d_semantic_lifecycle.py backend/tests/test_jsonl_profile_generation.py
47 passed, 2 warnings, exit code 0

backend\.venv\Scripts\ruff.exe check backend/app/profiles backend/app/api/imports.py backend/app/schemas/imports.py backend/tests/test_semantic_analyzer.py backend/tests/test_p3d_semantic_lifecycle.py
All checks passed, exit code 0

npm run typecheck
exit code 0

npm run build
exit code 0

git diff --check
passed; existing/new EOF blank-line warning was observed in test output and did not indicate whitespace corruption
```

未运行 `backend/tests/test_imports.py`，未运行会自动扫描真实数据的全量导入命令，未运行真实业务数据库迁移。

## 9. 当前限制与下一步

1. 需要撤销已暴露的 DeepSeek key，并配置新的有效 key；重新完成非敏感合成联调后，再对同一隔离样本运行 A/B 语义分析。
2. 只有真实 Provider 返回并通过结构校验的候选，才能进入候选审核、准入、正式 trait 审核和发布；本轮不能以本地 Observable 结果替代。
3. 新的真实语义候选必须逐项人工检查证据回指、A/B 隔离、supporting/counter、置信度和 unknown 状态。
4. 真实 Provider 通过后，才能重复“复合”主题 52 轮并将 Provider 标记为 DeepSeek；当前报告中的 52 轮只能作为 Mock 工作台验收记录。

## 10. Git 状态与提交边界

本轮不提交以下临时产物：

- `.p3d-tmp-inbox-e2e-20261017/`
- `.p3d-ui-inbox-real-20261017/`
- 隔离 SQLite、日志和任何前端构建产物

代码、测试和本报告可作为后续提交候选；真实聊天正文、原始 ZIP、凭据和敏感日志不进入 Git。
