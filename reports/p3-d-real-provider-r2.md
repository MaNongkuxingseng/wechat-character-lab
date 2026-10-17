# P3-D DeepSeek Provider 联调记录 R2

作者：valen MPF

日期：2026-10-17（Asia/Shanghai）

## 1. 联调结论

用户提供的新 DeepSeek key 已通过模型目录鉴权，OpenAI-compatible Provider 的真实网络请求、响应解析和 `profile-semantic-v1` 结构校验均成功。此次只发送合成文本，没有发送真实聊天内容。

| 项目 | 结果 |
|---|---|
| `GET https://api.deepseek.com/v1/models` | HTTP 200 |
| 返回模型 | `deepseek-flash`、`deepseek-v4-pro` |
| `deepseek-flash`，2 条合成消息 | `ready`，0 条 signal |
| `deepseek-flash`，8 条合成消息 | `ready`，0 条 signal |
| `deepseek-v4-pro`，8 条合成消息 | `ready`，2 条 signal |
| 证据引用 | 仅引用本次 8 个合成 message ID |
| supporting/counter 重叠 | 无 |
| 真实聊天发送 | 未执行 |

## 2. 结构校验结果

`deepseek-v4-pro` 返回的 2 条特征均通过现有严格校验：类别属于允许集合，supporting evidence 非空，引用 ID 存在且无重复，未跨角色引用，未出现原文照抄，counter evidence 为空时冲突状态为 `none`。模型返回的 confidence 为 `1.0`；这只是模型输出值，不能替代人工审核或证明事实确定性，真实画像阶段必须重点抽查过高置信度。

`deepseek-flash` 的合法空特征结果也被保留为 0 条 signal，不能把 analyzer `ready` 解释为已经生成画像。

## 3. 安全边界

- API key 仅作为当前进程内存值使用，未写入 `.env`、代码、日志、报告或 Git。
- 请求只包含合成 `message_id` 与合成文本；未访问或发送 inbox 真实正文。
- 未运行真实候选审核、准入、画像发布或 52 轮复合主题对话。
- 真实样本的 `is_ai_generated`/`is_system` 仍为 unknown；不能通过本次 Provider 成功而默认放行。

## 4. 下一步阻断

真实样本验收仍需要：来源级安全标记的可审计人工确认、两个发言人到 A/B 的明确映射、来源正文外发授权，以及对模型输出的证据真实性和置信度人工抽查。当前联调只证明 DeepSeek Provider 可用，不证明真实画像质量或业务闭环已完成。
