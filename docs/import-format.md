# 聊天记录导入格式

当前版本通过本机网页上传 ZIP 导出包，不连接 WeChatBridge 私有 API，也不会把聊天数据发送到云端。

## 归档结构

ZIP 根目录或任意子目录内放置以下一种消息文件：

- `messages.json`
- `messages.jsonl` 或 `messages.ndjson`
- `messages.csv`

ZIP 上传上限为 50 MiB；单个消息文件解压后上限为 100 MiB。超限或格式错误的归档会显示错误，不会导入消息。

## JSON 示例

```json
{
  "messages": [
    {
      "id": "message-001",
      "speaker": "我",
      "text": "今天下班后一起吃饭吗？",
      "sent_at": "2026-10-13T18:30:00+08:00"
    },
    {
      "id": "message-002",
      "speaker": "朋友",
      "text": "可以，去上次那家店。",
      "sent_at": "2026-10-13T18:31:00+08:00"
    }
  ]
}
```

必需字段是发言人和文本。发言人可使用 `speaker_label`、`speaker`、`sender` 或 `from`；文本可使用 `text`、`content` 或 `message`。消息 ID 可使用 `external_id`、`message_id` 或 `id`；没有 ID 时会按文件顺序生成。时间字段可使用 `sent_at`、`timestamp` 或 `created_at`，支持 ISO 8601。

## JSONL 与 CSV

JSONL 每行是一条与 JSON 示例相同的消息对象。CSV 首行为字段名，例如：

```csv
id,speaker,text,sent_at
message-001,我,今天下班后一起吃饭吗？,2026-10-13T18:30:00+08:00
message-002,朋友,可以，去上次那家店。,2026-10-13T18:31:00+08:00
```

## 审核与映射

上传后系统先保存原始 ZIP 到本机 `data/inbox/` 并创建待审核来源，不会立即写入消息库。界面展示发言人数量和最多 10 条消息摘录；由用户将发言人映射到角色 A/B 后确认导入。未映射消息会保留在导入来源中，但不参与任一角色的画像分析。

系统按 ZIP 内容计算 SHA-256 用于重复检测。当前版本没有来源删除界面；不要上传不希望保存在本机工程 `data/inbox/` 的归档。
