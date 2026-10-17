from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ImportedMessage, ProfileEvidence, ProfileTrait, ProfileVersion, Source
from app.profiles.analyzer import ObservableTextAnalyzer

ANALYZER = ObservableTextAnalyzer()


def create_draft(db: Session, role_id: str) -> ProfileVersion:
    """仅用已审核且映射给目标角色的消息创建新的独立草稿版本。"""
    candidate_messages = list(
        db.scalars(
            select(ImportedMessage)
            .join(Source, Source.id == ImportedMessage.source_id)
            .where(
                Source.status == "approved",
                ImportedMessage.speaker_role_id == role_id,
            )
            .order_by(ImportedMessage.sent_at, ImportedMessage.id)
        )
    )
    # 画像只使用文字消息；媒体/系统占位符会扭曲长度和标点统计。
    messages = [message for message in candidate_messages if _is_text_message(message)][
        : ANALYZER.maximum_sample_count
    ]
    drafts = ANALYZER.analyze(messages)
    latest_version = db.scalar(
        select(func.max(ProfileVersion.version)).where(ProfileVersion.role_id == role_id)
    )
    version = ProfileVersion(
        id=str(uuid4()),
        role_id=role_id,
        version=(latest_version or 0) + 1,
        status="draft",
        analyzer=ANALYZER.name,
        sample_count=min(len(messages), ANALYZER.maximum_sample_count),
        created_at=datetime.now(UTC),
    )
    db.add(version)
    db.flush()

    for draft in drafts:
        created_at = datetime.now(UTC)
        trait = ProfileTrait(
            id=str(uuid4()),
            profile_version_id=version.id,
            category=draft.category,
            trait_key=draft.key,
            description=draft.description,
            confidence=draft.confidence,
            cognitive_state="evidence_backed",
            inference_basis="deterministic observable analyzer output",
            conflict_status="none",
            context=None,
            review_status="pending",
            created_at=created_at,
        )
        db.add(trait)
        db.flush()
        for message_id in draft.message_ids:
            db.add(
                ProfileEvidence(
                    id=str(uuid4()),
                    trait_id=trait.id,
                    message_id=message_id,
                    rationale=draft.rationale,
                )
            )
    db.commit()
    db.refresh(version)
    return version


def _is_text_message(message: ImportedMessage) -> bool:
    """判断导入消息是否为可用于文字风格分析的文本记录。"""
    metadata = message.metadata_json or {}
    if metadata.get("is_ai_generated") is not False or metadata.get("is_system") is not False:
        return False
    message_type = metadata.get("message_type")
    type_code = metadata.get("type_code")
    if message_type is not None and str(message_type) not in {"文本", "text", "Text"}:
        return False
    if type_code is not None:
        try:
            return int(type_code) == 1
        except (TypeError, ValueError):
            return False
    return bool(message.text.strip())


def approve_version(db: Session, version: ProfileVersion) -> None:
    """发布已逐项处理且至少有一条接受特征的画像版本。"""
    traits = list(
        db.scalars(select(ProfileTrait).where(ProfileTrait.profile_version_id == version.id))
    )
    if not traits or any(trait.review_status == "pending" for trait in traits):
        raise ValueError("发布前必须逐项审核所有画像特征")
    if not any(trait.review_status == "accepted" for trait in traits):
        raise ValueError("至少接受一项画像特征后才能发布")
    for trait in traits:
        if trait.review_status != "accepted":
            continue
        valid_evidence = db.scalar(
            select(ProfileEvidence.id)
            .join(ImportedMessage, ImportedMessage.id == ProfileEvidence.message_id)
            .join(Source, Source.id == ImportedMessage.source_id)
            .where(
                ProfileEvidence.trait_id == trait.id,
                ImportedMessage.speaker_role_id == version.role_id,
                Source.status == "approved",
            )
            .limit(1)
        )
        if valid_evidence is None:
            raise ValueError("每项接受的特征都必须保留至少一条有效来源证据")
    current_versions = list(
        db.scalars(
            select(ProfileVersion).where(
                ProfileVersion.role_id == version.role_id,
                ProfileVersion.status == "approved",
            )
        )
    )
    for current in current_versions:
        current.status = "superseded"
    version.status = "approved"
    version.approved_at = datetime.now(UTC)
    db.commit()
