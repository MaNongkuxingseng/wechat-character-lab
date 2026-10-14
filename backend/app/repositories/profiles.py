from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProfileEvidence, ProfileTrait, ProfileVersion


def list_versions(db: Session, role_id: str) -> list[ProfileVersion]:
    """按版本号倒序列出角色画像。"""
    statement = (
        select(ProfileVersion)
        .where(ProfileVersion.role_id == role_id)
        .order_by(ProfileVersion.version.desc())
    )
    return list(db.scalars(statement))


def get_version(db: Session, role_id: str, version_id: str) -> ProfileVersion | None:
    """按角色和版本 ID 共同限制查询，避免跨角色读取。"""
    statement = select(ProfileVersion).where(
        ProfileVersion.id == version_id,
        ProfileVersion.role_id == role_id,
    )
    return db.scalar(statement)


def list_traits(db: Session, version_id: str) -> list[ProfileTrait]:
    """按创建顺序列出单个画像版本的特征。"""
    statement = (
        select(ProfileTrait)
        .where(ProfileTrait.profile_version_id == version_id)
        .order_by(ProfileTrait.created_at, ProfileTrait.id)
    )
    return list(db.scalars(statement))


def list_evidence(db: Session, trait_id: str) -> list[ProfileEvidence]:
    """读取特征关联的证据引用。"""
    return list(
        db.scalars(
            select(ProfileEvidence)
            .where(ProfileEvidence.trait_id == trait_id)
            .order_by(ProfileEvidence.message_id)
        )
    )
