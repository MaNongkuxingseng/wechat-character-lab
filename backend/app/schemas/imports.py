from datetime import datetime

from pydantic import BaseModel, Field


class ImportSourceRead(BaseModel):
    """待审核或已处理的本地导入来源摘要。"""

    id: str
    name: str
    kind: str
    status: str
    message_count: int = 0
    error: str | None = None


class ImportScanResponse(BaseModel):
    """一次 Inbox 扫描的结果。"""

    discovered: int
    sources: list[ImportSourceRead]


class ImportPreviewMessage(BaseModel):
    """用于人工核对的有限消息摘录，不作为画像分析输入。"""

    speaker_label: str
    text: str
    sent_at: datetime | None = None


class ImportPreviewRead(BaseModel):
    """归档中的发言人统计和少量样本预览。"""

    source: ImportSourceRead
    speakers: dict[str, int] = Field(default_factory=dict)
    samples: list[ImportPreviewMessage] = Field(default_factory=list)


class ImportSourceSummary(BaseModel):
    """当前版本支持的导入来源类型。"""

    inbox_enabled: bool = True
    bridge_api_enabled: bool = False
    bridge_api_status: str = "not_connected"
    upload_max_bytes: int
    accepted_extensions: list[str] = Field(default_factory=lambda: [".zip"])


class ImportApprovalResponse(BaseModel):
    """审核导入后的来源结果。"""

    source: ImportSourceRead
    imported_messages: int


class ImportApprovalRequest(BaseModel):
    """审核确认及可选的发言人到角色映射。"""

    speaker_mapping: dict[str, str] = Field(default_factory=dict)


class ImportCapabilities(BaseModel):
    """导入适配器能力；不向客户端暴露本机文件系统路径。"""

    inbox_enabled: bool = False
    bridge_api_enabled: bool = False
    bridge_api_status: str = "mock"
