import json
import zipfile
from pathlib import Path
from uuid import uuid4

from app.ingestion.archive_parser import ArchiveParseError, parse_archive


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
