from pydantic import BaseModel


class ImportCapabilities(BaseModel):
    """导入适配器能力；不向客户端暴露本机文件系统路径。"""

    inbox_enabled: bool = False
    bridge_api_enabled: bool = False
    bridge_api_status: str = "mock"
