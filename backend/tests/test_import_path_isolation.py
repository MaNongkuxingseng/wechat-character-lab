import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

from app.api import imports
from app.models import Source


def test_archive_registration_supports_inbox_outside_repository(
    test_session_factory, tmp_path: Path, monkeypatch
):
    root = tmp_path / "repository"
    inbox = tmp_path / "isolated-inbox"
    root.mkdir()
    inbox.mkdir()
    archive = inbox / "synthetic.zip"
    messages = [
        {"id": "m1", "speaker": "speaker-1", "text": "synthetic one"},
        {"id": "m2", "speaker": "speaker-2", "text": "synthetic two"},
    ]
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("messages.json", json.dumps(messages))

    monkeypatch.setattr(
        imports,
        "get_settings",
        lambda: SimpleNamespace(inbox_path=str(inbox)),
    )
    with test_session_factory() as db:
        registered = imports._register_archive(db, root, archive)
        source = db.get(Source, registered.id)
        assert source is not None
        assert source.metadata_json["inbox_relative_path"] == "synthetic.zip"
        assert "relative_path" not in source.metadata_json
        assert imports._source_path(source) == archive.resolve()
