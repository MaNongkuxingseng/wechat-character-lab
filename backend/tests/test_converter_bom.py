import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.convert_wechatauto_export import _read_json, convert, main  # noqa: E402


def _payload() -> dict:
    return {
        "messages": [
            {
                "local_id": 1,
                "server_id": 2,
                "create_time": 1700000000,
                "sender_name": "A",
                "type_code": 1,
                "type": "text",
                "content": "hello",
            },
            {
                "local_id": 3,
                "server_id": 4,
                "create_time": 1700000001,
                "sender_name": "B",
                "type_code": 3,
                "type": "image",
                "content": "image",
            },
        ]
    }


def _write_json(path: Path, payload: object, *, bom: bool) -> None:
    encoding = "utf-8-sig" if bom else "utf-8"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding=encoding)


def test_read_json_accepts_bom_and_no_bom_with_same_payload(tmp_path: Path):
    payload = _payload()
    plain = tmp_path / "plain.json"
    bom = tmp_path / "bom.json"
    _write_json(plain, payload, bom=False)
    _write_json(bom, payload, bom=True)

    assert _read_json(plain) == _read_json(bom) == payload


def test_jsonl_conversion_is_semantically_equal_and_repeatable(tmp_path: Path, monkeypatch, capsys):
    payload = _payload()
    outputs = []
    source = tmp_path / "source.json"
    for index, has_bom in enumerate((False, True, True), start=1):
        destination = tmp_path / f"output-{index}.jsonl"
        _write_json(source, payload, bom=has_bom)
        monkeypatch.setattr(
            sys,
            "argv",
            ["convert_wechatauto_export.py", str(source), str(destination), "--format", "jsonl"],
        )
        main()
        capsys.readouterr()
        parsed = [
            json.loads(line)
            for line in destination.read_text(encoding="utf-8").splitlines()
        ]
        outputs.append((destination.read_bytes(), parsed))

    assert outputs[0][1] == outputs[1][1] == outputs[2][1]
    assert outputs[1][0] == outputs[2][0]


def test_zip_conversion_accepts_bom_without_changing_contract(tmp_path: Path):
    payload = {
        "chats": [{"username": "synthetic"}],
        "nick_name": "A",
        "messages": [
            {
                "create_time": 1700000000,
                "sender_name": "A",
                "type": "text",
                "content": "hello",
                "local_id": 1,
                "server_id": 2,
                "sort_seq": 1,
            },
            {
                "create_time": 1700000001,
                "sender_name": "B",
                "type": "text",
                "content": "world",
                "local_id": 2,
                "server_id": 3,
                "sort_seq": 2,
            },
        ],
    }
    source = tmp_path / "bom-export.json"
    destination = tmp_path / "out.zip"
    _write_json(source, payload, bom=True)

    summary = convert(source, destination)

    assert summary["messages"] == 2
    assert destination.exists()


def test_invalid_json_still_raises_json_decode_error(tmp_path: Path, monkeypatch):
    source = tmp_path / "invalid.json"
    destination = tmp_path / "out.jsonl"
    source.write_bytes(b"\xef\xbb\xbf{not-json")
    monkeypatch.setattr(
        sys,
        "argv",
        ["convert_wechatauto_export.py", str(source), str(destination), "--format", "jsonl"],
    )

    with pytest.raises(json.JSONDecodeError):
        main()
