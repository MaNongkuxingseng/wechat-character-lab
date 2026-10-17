# P3-D 真实 Provider 联调追加记录 R1

作者：valen MPF

日期：2026-10-17（Asia/Shanghai）

## 结果

本次使用用户提供的 OpenAI-compatible 网关进行脱敏联调，未发送真实聊天内容，也未写入或提交 API key。结果为认证失败，不能进入真实语义画像验收。

| 检查 | 结果 |
|---|---|
| 模型目录 | `https://aihub.top/v1/models` 返回 HTTP `401 Unauthorized` |
| 合成聊天请求 | `https://aihub.top/v1/chat/completions` 返回适配器状态 `provider_rejected_request` |
| 真实样本发送 | 未执行 |
| 候选生成、审核、准入、发布 | 未执行 |
| 52 轮复合主题对话 | 未生成 |

测试使用了两个本地合成消息，仅验证网关认证路径；没有把真实样本正文放入请求。模型目录在鉴权阶段即失败，因此不能据此判断模型名、JSON 输出契约或画像质量。

## 配置解释

给定配置的聊天 endpoint 应为：

```text
https://aihub.top/v1/chat/completions
```

模型名必须从该网关成功返回的 `/v1/models` 中选择。当前仓库 Provider 使用 `Authorization: Bearer <key>`，并要求 HTTPS、明确 model 和来源级正文授权。

## 安全结论

- API key 未写入仓库、`.env`、日志或报告。
- 用户在聊天中暴露了完整 key；建议立即在网关侧撤销并重新生成。
- 未尝试猜测其他认证头、未轮换多个模型、未向网关发送真实消息。
- 当前分支代码未修改，工作区只保留既有未跟踪合成临时目录。

## 下一步阻断条件

需要一个已撤销旧 key 后的新 key，并确认该 key 对 `https://aihub.top/v1/models` 有效。模型目录成功后，先使用合成消息验证结构化响应，再由用户明确确认真实样本的 A/B 映射、来源安全放行和正文外发授权，最后才可执行真实画像与 52 轮对话验收。
