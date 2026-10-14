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


ALLOWED_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.CREATED: {SessionState.INITIALIZING, SessionState.RUNNING, SessionState.STOPPING},
    SessionState.INITIALIZING: {SessionState.RUNNING, SessionState.ERROR, SessionState.STOPPING},
    SessionState.RUNNING: {
        SessionState.PAUSED,
        SessionState.STOPPING,
        SessionState.COMPLETED,
        SessionState.ERROR,
    },
    SessionState.PAUSED: {SessionState.RUNNING, SessionState.STOPPING, SessionState.COMPLETED},
    SessionState.STOPPING: {SessionState.COMPLETED, SessionState.ERROR},
    SessionState.COMPLETED: set(),
    SessionState.ERROR: set(),
}


def can_transition(current: str, target: SessionState) -> bool:
    """判断状态转换是否属于会话生命周期允许的边界。"""
    try:
        return target in ALLOWED_TRANSITIONS[SessionState(current)]
    except ValueError:
        return False
