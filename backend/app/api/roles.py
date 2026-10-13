from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Role
from app.repositories.roles import list_roles
from app.schemas.role import RoleProfile, RoleUpdate

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("", response_model=list[RoleProfile])
def get_roles(db: Session = Depends(get_db)) -> list[RoleProfile]:
    """读取数据库中的角色配置。"""
    return [RoleProfile.model_validate(role) for role in list_roles(db)]


@router.put("/{role_id}", response_model=RoleProfile)
def update_role(role_id: str, payload: RoleUpdate, db: Session = Depends(get_db)) -> RoleProfile:
    """更新角色配置；角色 ID 固定，资料内容由 SQLite 统一保存。"""
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail={"code": "role_not_found"})
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(role, field, value)
    db.commit()
    db.refresh(role)
    return RoleProfile.model_validate(role)
