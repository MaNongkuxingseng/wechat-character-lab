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
