# P2-C.2 规范化消息安全标记契约补齐

作者：valen MPF
日期：2026-10-16（Asia/Shanghai）

## 1. 范围与边界

- 仅补齐规范化消息的安全标记三态契约和合成测试。
- 未读取、枚举或扫描 `data/`、`data/inbox`，未读取真实聊天正文、媒体或凭据。
- 未调用网络/外部 API，未安装依赖或模型，未修改 Mock Agent、迁移版本脚本、数据库或 API。
- 保留所有既有未提交修改，未提交或推送。

## 2. 字段来源分析

当前转换器和规范化器实际可见的来源包括：`type_code`、`type`、`sender_name`、`sender_id`、`content`、`message_type`、`source_metadata`，以及输入中可能显式存在的 `is_ai_generated`、`is_system`。

结论：

- 显式布尔字段是最可靠来源；`True` 或 `False` 均保留。
- `message_type` 或来源 `type` 精确等于 `system` 时，只能确认 `is_system=True`；AI 标记仍为 unknown。
- `message_type` 或来源 `type` 精确等于 `ai`/`assistant` 时，只能确认 `is_ai_generated=True`；system 标记仍为 unknown。
- 普通文本、普通发送者名称、已知文本/图片/语音/视频 `type_code` 不能证明“不是 AI”或“不是系统消息”，因此不能生成 `False`。
- 当前 `TYPE_NAMES` 没有专门的 AI/system type code；未知类型也不能自动推断安全属性。
- 来源缺失、非法类型或来源互相冲突时必须保持 unknown，并记录来源状态。

## 3. 三态契约

| 字段 | 类型 | `true` 来源 | `false` 来源 | unknown/缺失策略 | 画像资格 |
|---|---|---|---|---|---|
| `is_ai_generated` | `bool | None` | 显式布尔 true，或精确 `ai/assistant` 类型 | 仅显式布尔 false | `None`，来源为 unknown/invalid/conflict | `None` 不能绕过适配器；true 不是普通文本证据 |
| `is_system` | `bool | None` | 显式布尔 true，或精确 `system` 类型 | 仅显式布尔 false | `None`，来源为 unknown/invalid/conflict | `None` 不能绕过适配器；true 不是普通文本证据 |

实现不使用 Python truthiness、字符串转换或数字转换。`security_flag_sources` 保存每个字段的判定依据，不伪装为原始来源字段。

## 4. 最小实现

新增 `backend/app/ingestion/security_flags.py`：

- `SecurityFlags`：保存两个三态值和稳定来源映射。
- `derive_security_flags(message)`：纯函数，仅接受显式布尔或明确类型标记。
- 非法值输出 `None`/`invalid_type`；显式值和类型标记冲突输出 `None`/`conflict`。

修改 `backend/app/ingestion/wechat_normalizer.py`：

- 每条规范化记录新增 `is_ai_generated`、`is_system` 和 `security_flag_sources`。
- 普通合成文本没有可靠来源时输出两个 `None`，不默认输出 `False`。
- 显式安全标记和精确 system/AI 类型标记按上述规则输出。

下游 `synthetic_adapter.py` 未放宽：`None` 或其他非 `bool` 仍产生 `invalid_security_flag` 并拒绝候选。

## 5. 合成测试矩阵

新增 `backend/tests/test_security_flags.py`，覆盖：

- 显式 `True/False` 保留及来源记录；
- 明确 `system`、`assistant` 类型只确认对应属性；
- 普通文本和未知来源保持 `None`；
- 字符串 `"false"`、数字 `0` 等非法类型不被转换；
- 顶层与 `source_metadata` 同名标记冲突时保持 unknown；
- 规范化器输出三态字段和来源映射；
- unknown 标记不能绕过适配器；
- 显式 `False/False` 普通消息可以通过原有证据、角色和正文校验；
- 明确 AI/system 消息不作为普通画像证据。

## 6. 转换器、规范化器与适配器差异

- `--format jsonl` 路径直接调用 `normalize_payload`，现在会产生三态安全字段。
- `scripts/convert_wechatauto_export.py` 的 ZIP `convert()` 路径写出另一套 `messages.json` 结构，只保留 `external_id/speaker_label/text` 等导入字段，不携带安全标记字段；该路径后续需要独立 enrichment/映射，不能直接宣称与 JSONL 画像链路等价。
- 规范化器能保留显式输入安全字段，但现有原始类型映射通常无法证明普通消息的两个 false 状态。
- 适配器继续要求两个字段必须是真正的 `bool`，unknown 不得作为普通文本证据。

## 7. 实际测试结果

安全标记、规范化器、适配器：`22 passed, 2 warnings`。

迁移与适配器正向组合：`17 passed, 3 warnings`。
迁移与适配器反向组合：`17 passed, 3 warnings`。

受限后端回归：

`backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests --ignore=backend/tests/test_imports.py`

结果：`58 passed, 3 warnings`。未运行 `test_imports.py`，因为它会扫描 `data/inbox`。

相关 Ruff：`All checks passed!`。`git diff --check`：通过，仅有 LF/CRLF 转换提示。

## 8. 工作区与修改文件

本阶段新增或修改：

- `backend/app/ingestion/security_flags.py`
- `backend/app/ingestion/wechat_normalizer.py`
- `backend/tests/test_security_flags.py`
- `reports/p2-c2-security-flags-contract.md`

当前分支为 `feature/p2b-workspace-updates`。既有适配器、测试、Mock Agent 契约、迁移环境和过程报告修改均保留；未提交、未推送。

## 9. 未解决问题与真实数据前置条件

- 当前普通消息的安全属性仍可能是 unknown；真实画像前必须由导入来源提供可审计的显式安全标记或受控类型映射。
- ZIP 转换路径尚未携带三态安全字段，需要单独设计兼容 enrichment，不能用默认 false 代替。
- 未验证真实 WeChatBridge/wechatauto 导出是否提供安全标记字段；该事项必须使用脱敏小样本和人工审核验证。
- 本阶段只证明字段契约和拒绝策略，不证明真实聊天画像质量。

P2-C.2 已完成，现停止等待人工审核；不自动进入真实数据处理、数据库/API、第三方工具或语音模块。

## 10. 最终复核记录（2026-10-16）

本次仅复核代码与合成测试，未读取 `data/`，未运行会扫描真实导出的 `test_imports.py`，未调用外部服务。

- 定向安全标记、规范化器和适配器：`21 passed, 2 warnings`。
- 迁移与适配器正序组合：`9 passed, 3 warnings`。
- 适配器与迁移逆序组合：与正序相同，`9 passed, 3 warnings`。
- 受限后端回归：`58 passed, 3 warnings`。
- 相关 Ruff：`All checks passed!`。
- `git diff --check`：通过；仅报告现有 LF/CRLF 转换提示。

警告均来自现有依赖的弃用提示，不影响本阶段断言。工作区仍保留既有未提交修改，未执行提交、推送或清理操作。
