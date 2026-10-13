from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role


def list_roles(db: Session) -> list[Role]:
    """按角色 ID 稳定排序返回角色配置。"""
    return list(db.scalars(select(Role).order_by(Role.id)))


def get_roles_by_ids(db: Session, role_ids: list[str]) -> list[Role]:
    """查询指定角色；返回结果顺序与请求 ID 顺序一致。"""
    roles = {role.id: role for role in db.scalars(select(Role).where(Role.id.in_(role_ids)))}
    return [roles[role_id] for role_id in role_ids if role_id in roles]
