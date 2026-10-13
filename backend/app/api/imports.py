from fastapi import APIRouter

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.get("/capabilities")
def import_capabilities() -> dict[str, object]:
    """报告导入适配器能力；真实 Bridge API 尚未接入。"""
    return {"inbox_enabled": False, "bridge_api_enabled": False, "bridge_api_status": "mock"}
