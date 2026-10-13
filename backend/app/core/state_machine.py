from enum import StrEnum


class SessionState(StrEnum):
    """会话可持久化状态；状态转换由编排器统一执行。"""

    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"
