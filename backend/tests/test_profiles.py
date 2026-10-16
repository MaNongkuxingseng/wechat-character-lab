from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import ImportedMessage, ProfileVersion, Role, Source


def seed_profile_messages(factory: sessionmaker[Session]) -> None:
    """建立已审核、待审核和另一角色的样本，验证分析边界。"""
    now = datetime.now(UTC)
    with factory.begin() as db:
        for role_id, label in (("role_a", "角色 A"), ("role_b", "角色 B")):
            db.add(
                Role(
                    id=role_id,
                    label=label,
                    profile="",
                    style_profile={},
                    voice_profile={},
                    consent_status="preset",
                    created_at=now,
                    updated_at=now,
                )
            )
        approved = Source(
            id="approved-source",
            kind="inbox_archive",
            name="approved.zip",
            status="approved",
            metadata_json={},
            imported_at=now,
        )
        pending = Source(
            id="pending-source",
            kind="inbox_archive",
            name="pending.zip",
            status="pending_review",
            metadata_json={},
            imported_at=now,
        )
        db.add_all([approved, pending])
        db.flush()
        rows = [
            ("a-1", "role_a", "今天忙吗？"),
            ("a-2", "role_a", "还好，刚下班。"),
            ("a-3", "role_a", "晚上一起吃饭吧。"),
            ("b-1", "role_b", "这条不能进入 A 的样本。"),
        ]
        for message_id, role_id, text in rows:
            db.add(
                ImportedMessage(
                    id=message_id,
                    source_id=approved.id,
                    external_id=message_id,
                    speaker_label=role_id,
                    speaker_role_id=role_id,
                    text=text,
                    sent_at=now,
                    metadata_json={},
                )
            )
        for index in range(3):
            db.add(
                ImportedMessage(
                    id=f"p-{index}",
                    source_id=pending.id,
                    external_id=f"p-{index}",
                    speaker_label="角色 A",
                    speaker_role_id="role_a",
                    text="待审核消息不能参与分析",
                    sent_at=now,
                    metadata_json={},
                )
            )


def test_profile_analysis_uses_only_approved_role_mapped_messages(client, test_session_factory):
    seed_profile_messages(test_session_factory)

    response = client.post("/api/roles/role_a/profiles/analyze")

    assert response.status_code == 201
    profile = response.json()
    assert profile["sample_count"] == 3
    assert profile["analyzer"] == "local_observable_v1"
    assert {trait["key"] for trait in profile["traits"]} == {
        "message_length_median",
        "question_ratio",
    }
    for trait in profile["traits"]:
        assert trait["review_status"] == "pending"
        assert trait["evidence"]
        assert all(item["message_id"].startswith("a-") for item in trait["evidence"])
        assert all("不能进入 A" not in item["excerpt"] for item in trait["evidence"])


def test_analysis_requires_three_approved_mapped_messages(client, test_session_factory):
    with test_session_factory.begin() as db:
        db.add(
            Role(
                id="role_a",
                label="角色 A",
                profile="",
                style_profile={},
                voice_profile={},
                consent_status="preset",
            )
        )

    response = client.post("/api/roles/role_a/profiles/analyze")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "insufficient_samples"


def test_profile_analysis_excludes_media_messages(client, test_session_factory):
    seed_profile_messages(test_session_factory)
    with test_session_factory.begin() as db:
        db.add(
            ImportedMessage(
                id="a-image",
                source_id="approved-source",
                external_id="a-image",
                speaker_label="role_a",
                speaker_role_id="role_a",
                text="[图片]",
                sent_at=datetime.now(UTC),
                metadata_json={"message_type": "图片", "type_code": 3},
            )
        )

    response = client.post("/api/roles/role_a/profiles/analyze")

    assert response.status_code == 201
    assert response.json()["sample_count"] == 3


def test_profile_publish_requires_review_and_keeps_history(client, test_session_factory):
    seed_profile_messages(test_session_factory)
    first = client.post("/api/roles/role_a/profiles/analyze").json()
    version_id = first["id"]

    assert client.post(f"/api/roles/role_a/profiles/{version_id}/publish").status_code == 409
    for index, trait in enumerate(first["traits"]):
        reviewed = client.post(
            f"/api/roles/role_a/profiles/{version_id}/traits/{trait['id']}/review",
            json={
                "status": "accepted" if index == 0 else "rejected",
                "reviewer_note": "基于证据确认",
            },
        )
        assert reviewed.status_code == 200

    published = client.post(f"/api/roles/role_a/profiles/{version_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "approved"
    assert published.json()["approved_at"] is not None
    listed = client.get("/api/roles/role_a/profiles")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == version_id
    assert listed.json()[0]["status"] == "approved"

    second = client.post("/api/roles/role_a/profiles/analyze").json()
    assert second["version"] == 2
    assert second["status"] == "draft"
    assert second["id"] != version_id
    with test_session_factory() as db:
        versions = list(
            db.scalars(
                select(ProfileVersion)
                .where(ProfileVersion.role_id == "role_a")
                .order_by(ProfileVersion.version)
            )
        )
    assert [version.status for version in versions] == ["approved", "draft"]


def test_cross_role_profile_read_is_not_found(client, test_session_factory):
    seed_profile_messages(test_session_factory)
    profile = client.post("/api/roles/role_a/profiles/analyze").json()

    response = client.get(f"/api/roles/role_b/profiles/{profile['id']}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "profile_version_not_found"


def test_evidence_is_hidden_if_source_is_no_longer_approved(client, test_session_factory):
    seed_profile_messages(test_session_factory)
    profile = client.post("/api/roles/role_a/profiles/analyze").json()
    with test_session_factory.begin() as db:
        source = db.get(Source, "approved-source")
        source.status = "pending_review"

    response = client.get(f"/api/roles/role_a/profiles/{profile['id']}")

    assert response.status_code == 200
    assert all(trait["evidence"] == [] for trait in response.json()["traits"])


def test_profile_cannot_publish_after_accepted_evidence_is_invalidated(
    client, test_session_factory
):
    seed_profile_messages(test_session_factory)
    profile = client.post("/api/roles/role_a/profiles/analyze").json()
    version_id = profile["id"]
    for index, trait in enumerate(profile["traits"]):
        client.post(
            f"/api/roles/role_a/profiles/{version_id}/traits/{trait['id']}/review",
            json={"status": "accepted" if index == 0 else "rejected"},
        )
    with test_session_factory.begin() as db:
        db.get(Source, "approved-source").status = "pending_review"

    response = client.post(f"/api/roles/role_a/profiles/{version_id}/publish")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "profile_review_incomplete"
