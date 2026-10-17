# P3-D 真实语义画像验收记录

作者：valen MPF

日期：2026-10-17（Asia/Shanghai）

## 1. 结论

本轮真实语义验收被两个明确条件阻断，未标记为完整交付：

1. 当前运行环境没有配置可用的语义 Provider endpoint、model 或 API key，因此没有真实 LLM 请求。
2. 真实样本的 `is_ai_generated` 与 `is_system` 均为 `unknown:no_reliable_source`；现有严格安全门禁禁止把 unknown 默认转换为 `False`，所以样本不能进入普通画像候选。

因此没有伪造真实语义特征、审核发布结果或“复合”主题 52 轮对话。当前 ChatGPT 会话本身不是应用内 Provider，不能替代 DeepSeek/OpenAI-compatible endpoint 的可复现联调。

## 2. 运行条件检查

检查了当前分支、HEAD、P3-D 报告、Provider 文档、`.env.example` 和配置读取逻辑。未输出任何密钥值；只记录存在性和配置状态：

| 项目 | 实际结果 |
|---|---|
| 分支 | `feature/p2b-workspace-updates` |
| HEAD | `1d008831167c389e49ab2b0ba352e353c6062f22` |
| `SEMANTIC_LLM_ENABLED` | 未配置/等价于关闭 |
| `SEMANTIC_LLM_ALLOW_MESSAGE_CONTENT` | 未配置/等价于关闭 |
| endpoint | 未配置 |
| model | 未配置 |
| API key | 未配置；未读取明文 |
| 重试/超时 | 代码已配置有限重试与超时；本轮未发生真实网络调用 |

现有适配器已经兼容 DeepSeek：建议使用 `https://api.deepseek.com/chat/completions` 与 `deepseek-chat`，配置说明已补入 `docs/semantic-profile-provider.md`。必须在忽略的 `backend/.env` 中设置，不提交密钥。

## 3. 真实样本选择与解析

只选择了 inbox 中一份显式 JSON 样本，并写出到系统临时目录的派生 ZIP；未扫描其他真实归档，也未读取音频/视频目录。原始文件只读，没有覆盖或移动。为避免个人标识进入版本库，报告不记录原始文件名、昵称或正文。

仅记录不含正文的摘要：

- 消息总数：37,769。
- 会话数：1。
- 发言人：2 个匿名桶；桶标识只在本地摘要中使用 SHA-256 前缀 `81f2f74f9525` 与 `b358da00a591`，不记录昵称或正文。
- 两个桶的消息数：21,398 与 16,371。
- 非空文本消息：32,718；媒体/其他类型保留为非文本，不进入普通文本画像。
- `external_id`：37,769 个，唯一无重复。
- `canonical_message_id` 与 `source_message_ref`：均存在且来源内唯一；`source_local_id` 有 1 个重复，这是转换器允许的本地 ID 情况，最终 external ID 仍唯一。
- 时间戳：37,769 条均为 `parsed_utc`。
- `is_ai_generated`：37,769 条均为 `None`，来源状态均为 `unknown:no_reliable_source`。
- `is_system`：37,769 条均为 `None`，来源状态均为 `unknown:no_reliable_source`。

这组来源证据不足以证明普通用户消息，不能将其安全放行为画像输入。发言人到角色 A/B 的映射也尚未由用户逐一确认；本轮没有根据昵称、频次或内容猜测角色。

## 4. 已执行的本地真实数据检查

| 检查 | 结果 |
|---|---|
| 选定样本 JSON 解码 | 通过 |
| canonical 转换为派生 ZIP | 通过，37,769 条保持一致 |
| message type / 空正文 / 时间戳摘要 | 通过 |
| source ID 唯一性摘要 | 通过 |
| 安全标记来源审计 | 阻断：全部 unknown |
| 真实 LLM Provider 联调 | 未执行：endpoint/model/key 缺失 |
| 候选生成/审核/准入/发布 | 未执行：安全门禁不允许进入候选 |
| 浏览器真实画像读取 | 未执行：没有已发布真实画像 |

曾尝试使用隔离 SQLite 通过导入 API 验证外部临时 Inbox；当前导入实现要求 `INBOX_PATH` 能相对仓库根目录解析，绝对临时路径会在来源登记阶段触发 `relative_to(root)` 错误。该问题只影响本轮隔离 API 上传尝试，没有修改生产代码，也没有连接真实数据库。转换器和规范化器的本地检查已完成。

## 5. “复合”主题 52 轮对话记录

本项未生成，原因是：没有合法真实 Provider、没有显式 A/B 角色映射、真实消息安全标记全部 unknown。生成 52 轮内容会把未经安全放行的真实数据和未验证模型输出伪装成正式验收结果，违反当前契约，因此本报告不填充占位对话或虚构通过数字。

要执行该项，至少需要在下一次运行前完成：

1. 用户在界面或请求中明确指定两个匿名 sender bucket 分别对应角色 A、角色 B。
2. 在 `backend/.env` 配置并验证 DeepSeek endpoint/model/key，或提供其他已授权 OpenAI-compatible endpoint；先用合成文本验证真实请求和结构化响应。
3. 对该来源明确授权消息正文传输，并确认 Provider 的数据保留与使用边界。
4. 解决来源安全标记：转换器必须从原始来源取得可靠的 `is_ai_generated`/`is_system` 证据，或由人工审核逐条/按可审计规则完成安全标记；不得默认 `False`。

完成后，52 轮报告应只记录脱敏的轮次、角色、画像版本、特征 ID、证据 ID 摘要和审核状态；原始正文不写入 Git、日志或报告。

## 6. 质量门槛与未完成项

执行前固定质量门槛：证据真实可回指、A/B 不串扰、事实与推断分离、unknown/低置信度保留、supporting/counter 不丢失、同输入结构可重复、未审核或失效证据不能进入上下文。因样本未通过安全门禁，本轮没有声称这些门槛通过。

尚未完成：真实 Provider 网络联调、真实语义画像、候选审核与正式发布、真实画像驱动浏览器对话、复合主题 52 轮报告。已完成的只是单一真实样本的本地解析与安全阻断验证，以及现有合成测试回归（此前记录为 44 条定向通过、125 条受限后端回归通过）。

## 7. 本轮实际命令

| 命令/操作 | 实际结果 |
|---|---|
| `backend\\.venv\\Scripts\\python.exe scripts/convert_wechatauto_export.py <选定 inbox JSON> <系统临时 ZIP>` | 退出码 0；37,769 条消息、2 个发言人桶、转换前后数量一致 |
| 系统临时 ZIP 的离线字段摘要脚本 | 退出码 0；external ID 37,769/37,769 唯一，时间戳 37,769/37,769 有效，安全标记 37,769/37,769 unknown |
| 隔离 SQLite + TestClient 导入尝试 | 未通过：绝对临时 `INBOX_PATH` 不满足当前来源相对路径契约，触发 `relative_to(root)`；未连接真实数据库，未修改生产代码 |
| `backend\\.venv\\Scripts\\python.exe -m pytest -q tests/test_semantic_analyzer.py tests/test_p3d_semantic_lifecycle.py tests/test_jsonl_profile_generation.py tests/test_candidate_persistence_models.py tests/test_m1_profile_engine.py` | 44 passed，2 warnings，退出码 0（P3-D 复核结果） |
| `backend\\.venv\\Scripts\\python.exe -m pytest -q tests --ignore=tests/test_imports.py` | 125 passed，6 warnings，退出码 0（P3-D 复核结果） |
| DeepSeek/真实 endpoint 请求 | 未执行：endpoint、model、API key 均未配置 |

## 8. Git 与边界

- 未读取真实正文写入报告；未输出密钥。
- 未访问音频/视频目录，未连接真实数据库，未运行 `test_imports.py`。
- 现有未跟踪目录 `.p3d-tmp-inbox-e2e-20261017/` 来自上一轮合成验收，未纳入本轮提交。
- 本报告和 DeepSeek 配置说明只记录阻断与下一步条件，不把真实验收描述为已完成。
