# P3-D-R5.1 真实 Provider 合成联调

作者：valen MPF
日期：2026-10-17（Asia/Shanghai）

## 1. 结论

本轮未执行真实网络联调。当前本地安全配置仍缺失：`backend/.env` 不存在，进程环境没有 `SEMANTIC_LLM_*` 变量。根据执行要求，不能从聊天、历史报告或 Git 历史提取 API key，也不能伪造模型目录或 Chat Completions 结果，因此在网络请求前停止。

这不是“鉴权失败”，而是“本地凭据和 Provider 配置未提供”。本轮没有发送合成文本，也没有读取或发送真实聊天正文。

## 2. 基线与工作区

- 分支：`feature/p2b-workspace-updates`
- 起始 HEAD：`c5892bf test(profile): 完成 DeepSeek 真实验收与 52 轮 Mock 记录 (real acceptance)`
- 结束 HEAD：同上；未修改生产代码或测试代码。
- 既有未跟踪目录保持原状：`.p3d-tmp-inbox-e2e-20261017/`、`.p3d-ui-inbox-real-20261017/`。
- 新增文件仅为本报告；没有暂存临时数据库、真实 ZIP、日志或凭据。

## 3. 配置状态

当前应用配置读取自 `backend/app/config.py` 的 `Settings`。启动约定是从 `backend` 目录加载 `.env`；环境变量名称为：

```text
SEMANTIC_LLM_ENABLED
SEMANTIC_LLM_ALLOW_MESSAGE_CONTENT
SEMANTIC_LLM_ENDPOINT
SEMANTIC_LLM_MODEL
SEMANTIC_LLM_API_KEY
```

本轮只检查布尔/存在性状态，不读取或输出秘密值：

| 配置项 | 状态 |
|---|---|
| `backend/.env` | 不存在 |
| `SEMANTIC_LLM_ENABLED` | 未配置，默认 false |
| `SEMANTIC_LLM_ALLOW_MESSAGE_CONTENT` | 未配置，默认 false |
| endpoint | 未配置 |
| model | 未配置 |
| API key | 未配置 |

## 4. 网络联调结果

由于配置不齐全，以下步骤均为“未执行”，不是“通过”：

| 验收项目 | HTTP/解析结果 | 说明 |
|---|---|---|
| 模型目录请求 | 未执行 | 没有本地 endpoint、model、key 配置 |
| 合成 Chat Completions | 未执行 | 没有本地安全凭据 |
| `profile-semantic-v1` 真实响应校验 | 未执行 | 没有真实响应 |
| 真实 Provider 错误分类 | 未执行 | 本轮未发生网络请求 |
| 真实聊天正文发送 | 未执行 | 明确禁止 |

离线测试覆盖了配置关闭、来源未授权、超时重试、HTTP 错误、非法 JSON、证据引用和响应结构校验，但不能替代真实网络联调。

## 5. 实际测试结果

```text
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_semantic_analyzer.py backend/tests/test_p3d_semantic_lifecycle.py
12 passed, 2 warnings, exit code 0

backend\.venv\Scripts\ruff.exe check backend/app/config.py backend/app/profiles/semantic_analyzer.py backend/tests/test_semantic_analyzer.py backend/tests/test_p3d_semantic_lifecycle.py
All checks passed, exit code 0

npm run typecheck
exit code 0

npm run build
exit code 0

git diff --check
exit code 0
```

警告为既有 Starlette/httpx 与 pytest-asyncio deprecation warning。未运行 `backend/tests/test_imports.py`，未扫描真实 Inbox，未连接正式业务数据库。

## 6. 下一步最小条件

请在本机被 `.gitignore` 忽略的 `backend/.env` 中自行配置有效 Provider，或在启动进程前设置等效环境变量。不要在聊天中粘贴 key，也不要把凭据写入报告或 Git。配置完成后，重新运行本阶段时应依次执行：

1. 模型目录请求并记录脱敏 HTTP 状态及服务端模型 ID。
2. 仅使用人工构造的合成文本发送 Chat Completions。
3. 通过现有 `profile-semantic-v1`、证据 ID、角色和安全校验。
4. 记录响应失败时的分类，不以 Mock 结果替代。

只有上述合成联调真实成功后，才能进入 P3-D-R6 的有界 A/B 真实样本分析和候选生命周期。

## 7. 安全确认

- 未读取或提取聊天中的 API key。
- 未读取真实聊天、音频或视频。
- 未发送任何真实聊天正文或合成网络请求。
- 未生成真实候选、审核、准入或正式画像发布。
- 未提交真实数据、临时数据库、日志或凭据。
