from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories.roles import list_roles
from app.schemas.role import RoleProfile

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("", response_model=list[RoleProfile])
def get_roles(db: Session = Depends(get_db)) -> list[RoleProfile]:
    """读取数据库中的角色配置。"""
    return [RoleProfile.model_validate(role) for role in list_roles(db)]
