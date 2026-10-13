from app.schemas.message import NormalizedMessage


def normalize_message(message: NormalizedMessage) -> NormalizedMessage:
    """清理消息外围空白，保留原始时间、ID 和来源元数据。"""
    return message.model_copy(
        update={"speaker_label": message.speaker_label.strip(), "text": message.text.strip()}
    )
