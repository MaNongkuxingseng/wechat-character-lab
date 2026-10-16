# P1 微信聊天数据标准化与完整性测试

审计日期：2026-10-15（Asia/Shanghai）
范围：只实现数据标准化、验证和测试；未执行画像分析、模型安装、语音克隆或新视频处理。

## 结果摘要

- 已确认实际工具环境：`C:/Users/Administrator/AppData/Local/wechatauto-replica-venv/Scripts/python.exe`，Python 3.10.11，`wechatauto-replica 1.2.6.1`，许可证 Apache-2.0。
- 用户示例中的 `%USERPROFILE%/WeChatArchive/.venv312` 在本机不存在；已使用实际存在的隔离环境，不修改现有 Python 3.14 后端环境。
- `python -m wechatauto --help` 显示 `export` 只能导出会话文本，媒体下载需读取微信本地库。`doctor` 和 `sessions --json` 均因“未找到微信数据库目录，请通过 db_dir 参数手动指定”退出；本阶段未猜测 `db_dir`，未导出或处理新视频。
- 原始输入是本地单会话 JSON；标准化输出为独立 JSONL，每行对应一条消息。

## 文件变更

本次新增或修改：

- `backend/app/ingestion/wechat_normalizer.py`：标准化适配层。
- `scripts/convert_wechatauto_export.py`：保留原有 ZIP 转换，并增加 `--format jsonl`；拒绝覆盖已有输出。
- `backend/tests/test_wechat_normalizer.py`：合成边界测试 5 项。
- `data/processed/wechat_messages_normalized_20261015.jsonl`：真实输入验证输出；本地数据目录受 Git 忽略保护。
- 另有本轮前已存在的用户改动未触碰，Git 状态以最终检查为准。

## 标准化格式

每条 JSONL 记录包含：

- `message_id`：优先 `wechat:<local_id>:<server_id>`；缺少两者时使用规范化整行 JSON 的 SHA-256 前 24 位。
- `source_local_id`、`source_server_id`：原始值或 null，不伪造。
- `timestamp`：Unix 秒在 2000-2100 UTC 范围内时转为 ISO-8601 UTC；否则为 null。
- `timestamp_raw`、`timestamp_status`：保留原值并标记 `parsed_utc/missing/invalid/out_of_range`。
- `sender`：原始 `sender_name` 的脱空白值；缺失时为 null。
- `message_type`：已知码映射为 `text/image/voice/video/contact/emoji/location`；未知码保留为 `unknown:<type_code>`。
- `source_type_code`：原始数值或 null。
- `content`：只有原始 `content` 是字符串时填充；null/非字符串不解码、不推断。
- `content_status`：`present/empty/missing/not_text`。
- `source_file`：项目内相对标识。
- `source_message_ref`：`messages[行号]`，可回指原始 JSON。
- `source_metadata`：保留类型名、媒体 md5、发送者内部数值和排序字段；不复制聊天正文。

## ID、重复与时间规则

- 有任一原始 ID 时使用 local/server 组合；不把相同文本合并。
- 同一来源内组合重复时保留全部记录，并在后续记录上追加 `#2`、`#3`，标记 `id_collision=true`；本次真实数据冲突数为 0。
- 无原始 ID 时使用确定性 JSON 哈希；同样输入和规则可重复生成同一 ID。
- 时间只接受可转为整数且处于 2000-2100 UTC 的 Unix 秒；异常时间原值保留、状态标记，不静默删除记录。

## 真实数据验证

输入和输出均为 37,769 条；转换错误 0；ID 冲突 0。脱敏类型统计：

`text=32718`、`image=1426`、`voice=5`、`video=78`、`emoji=1760`、`location=41`、`contact=2`，以及保留的未知类型码若干；报告不包含聊天正文或真实联系人身份。

重复运行结果：第一次与第二次 JSONL SHA-256 一致；两次均为 37,769 行。

## 自动化测试

- `backend/.venv/Scripts/python.exe -m pytest -q`：42 passed，3 个既有依赖弃用警告。
- `backend/.venv/Scripts/python.exe -m ruff check app tests`：All checks passed。
- 合成标准化测试覆盖：顶层字段、稳定 ID、哈希回退、ID 冲突、异常时间、未知类型、空内容、重复文本、坏记录计数和追溯引用。
- 真实验证命令：`backend/.venv/Scripts/python.exe scripts/convert_wechatauto_export.py <raw-json> <new-jsonl> --format jsonl`；使用版本化新输出，未覆盖已有文件。

## 数据追溯与隐私

- 原始 JSON 只读；未重命名、移动、覆盖或删除。
- 输出写入 `data/processed/` 独立目录，已有目标不存在时才创建；重复验证使用独立临时文件。
- 日志和测试输出只包含数量、类型、状态和错误行号，不输出聊天正文、完整联系人标识、令牌或音频字节。
- 原始数据、数据库、音频和处理结果均受现有 `.gitignore` 规则保护；未提交数据文件。

## 未解决问题与 P2 影响

- `wechatauto-replica` 已安装但无法定位微信数据库目录，视频导出仍需用户提供/确认实际 `db_dir` 或登录后的可用微信运行态；P1 不绕过此阻塞。
- 标准化层保留视频/语音等消息元数据，但不声称附件已获取；后续画像阶段只能使用审核后、明确允许的文字内容。
- 原始未知类型码未擅自映射为具体业务含义；如 P2 需要细分，应基于工具文档或小样本证据补充映射。
- 本阶段已停止，不自动进入 P2。
