from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """返回进程存活状态；不触发外部服务调用。"""
    return {"status": "ok"}
