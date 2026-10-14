import json
import zipfile
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.ingestion.archive_parser import ArchiveParseError, parse_archive
from app.models import ImportedMessage, Role


def _write_archive(directory: Path, rows: list[dict[str, object]], name: str) -> Path:
    path = directory / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("messages.json", json.dumps({"messages": rows}, ensure_ascii=False))
    return path


def test_scan_and_approve_inbox_archive(client, test_session_factory):
    inbox = Path(__file__).resolve().parents[2] / "data" / "inbox"
    archive = _write_archive(
        inbox,
        [{"id": "m-1", "speaker": "朋友", "text": "你好", "sent_at": "2026-10-13T10:00:00Z"}],
        f"test-{uuid4()}.zip",
    )
    try:
        scanned = client.post("/api/imports/inbox/scan")
        assert scanned.status_code == 200
        source = next(item for item in scanned.json()["sources"] if item["name"] == archive.name)
        assert source["status"] == "pending_review"
        assert source["message_count"] == 1

        approved = client.post(f"/api/imports/{source['id']}/approve")
        assert approved.status_code == 200
        assert approved.json()["source"]["status"] == "approved"
        assert approved.json()["imported_messages"] == 1

        rescanned = client.post("/api/imports/inbox/scan")
        matching = [item for item in rescanned.json()["sources"] if item["name"] == archive.name]
        assert len(matching) == 1
        assert matching[0]["status"] == "approved"
    finally:
        archive.unlink(missing_ok=True)


def test_archive_parser_rejects_unknown_format(tmp_path: Path):
    archive = tmp_path / "unsupported.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("README.txt", "not a message export")

    try:
        parse_archive(archive)
    except ArchiveParseError as error:
        assert "messages.json" in str(error)
    else:
        raise AssertionError("未知归档格式应当被拒绝")


def test_archive_parser_preserves_provider_metadata(tmp_path: Path):
    archive = _write_archive(
        tmp_path,
        [
            {
                "external_id": "wx-1",
                "speaker_label": "朋友",
                "text": "[语音]",
                "sent_at": "2024-01-02T03:04:05Z",
                "message_type": "语音",
                "type_code": 34,
                "sender_id": 7,
            }
        ],
        "provider-metadata.zip",
    )

    parsed = parse_archive(archive)

    assert parsed[0].metadata == {
        "message_type": "语音",
        "type_code": 34,
        "sender_id": 7,
        "source_row": 1,
    }


def test_archive_parser_reports_malformed_json_as_import_error(tmp_path: Path):
    archive = tmp_path / "malformed.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("messages.json", "{not valid json")

    try:
        parse_archive(archive)
    except ArchiveParseError as error:
        assert "JSON" in str(error)
    else:
        raise AssertionError("无效 JSON 应当转换为归档格式错误")


def test_upload_preview_and_approve_archive(client, test_session_factory):
    archive = BytesIO()
    rows = [
        {"id": "m-a", "speaker": "我", "text": "今天有空吗？"},
        {"id": "m-b", "speaker": "朋友", "text": "晚上可以。"},
    ]
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("messages.json", json.dumps({"messages": rows}, ensure_ascii=False))
    with test_session_factory.begin() as db:
        for role_id, label in (("role_a", "角色 A"), ("role_b", "角色 B")):
            db.add(
                Role(
                    id=role_id,
                    label=label,
                    profile="",
                    style_profile={},
                    voice_profile={},
                    consent_status="preset",
                )
            )

    uploaded = client.post(
        "/api/imports/upload",
        files={"file": ("聊天导出.zip", archive.getvalue(), "application/zip")},
    )
    assert uploaded.status_code == 201
    source = uploaded.json()
    assert source["status"] == "pending_review"
    assert source["message_count"] == 2
    inbox_archive = Path(__file__).resolve().parents[2] / "data" / "inbox" / source["name"]
    try:
        duplicate = client.post(
            "/api/imports/upload",
            files={"file": ("同一聊天导出.zip", archive.getvalue(), "application/zip")},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == source["id"]

        preview = client.get(f"/api/imports/{source['id']}/preview")
        assert preview.status_code == 200
        assert preview.json()["speakers"] == {"我": 1, "朋友": 1}
        assert len(preview.json()["samples"]) == 2
        with test_session_factory() as db:
            assert list(db.scalars(select(ImportedMessage))) == []

        approved = client.post(
            f"/api/imports/{source['id']}/approve",
            json={"speaker_mapping": {"我": "role_a", "朋友": "role_b"}},
        )
        assert approved.status_code == 200
        assert approved.json()["imported_messages"] == 2
        with test_session_factory() as db:
            imported = list(db.scalars(select(ImportedMessage).order_by(ImportedMessage.id)))
            assert {message.speaker_role_id for message in imported} == {"role_a", "role_b"}
    finally:
        inbox_archive.unlink(missing_ok=True)


def test_upload_rejects_non_zip_file(client):
    response = client.post(
        "/api/imports/upload",
        files={"file": ("messages.csv", b"speaker,text\nA,hello", "text/csv")},
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "zip_required"
