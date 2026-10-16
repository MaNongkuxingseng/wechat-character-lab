from app.ingestion.wechat_normalizer import normalize_payload


def _message(**overrides):
    row = {
        "local_id": 1,
        "server_id": 2,
        "create_time": 1700000000,
        "sender_name": "A",
        "type_code": 1,
        "type": "文本",
        "content": "same",
    }
    row.update(overrides)
    return row


def test_normalizes_supported_fields_and_traceability():
    records, summary = normalize_payload(
        {"messages": [_message()]}, source_file="data/inbox/sample.json"
    )
    assert summary["input_messages"] == summary["output_records"] == 1
    assert records[0]["message_id"] == "wechat:1:2"
    assert records[0]["timestamp"] == "2023-11-14T22:13:20Z"
    assert records[0]["timestamp_status"] == "parsed_utc"
    assert records[0]["source_message_ref"] == "messages[1]"
    assert records[0]["content_status"] == "present"


def test_preserves_empty_content_unknown_types_and_duplicate_text():
    rows = [
        _message(content="", type_code=999),
        _message(local_id=3, server_id=4, sender_name="B"),
    ]
    records, summary = normalize_payload({"messages": rows}, source_file="sample.json")
    assert len(records) == 2
    assert records[0]["message_type"] == "unknown:999"
    assert records[0]["content"] == ""
    assert records[0]["content_status"] == "empty"
    assert records[1]["content"] == "same"
    assert records[0]["sender"] != records[1]["sender"]
    assert summary["id_collision_count"] == 0


def test_detects_id_collisions_without_merging_records():
    rows = [_message(content="one"), _message(content="two")]
    records, summary = normalize_payload({"messages": rows}, source_file="sample.json")
    assert len(records) == 2
    assert records[0]["message_id"] == "wechat:1:2"
    assert records[1]["message_id"] == "wechat:1:2#2"
    assert summary["id_collision_count"] == 1


def test_missing_ids_use_deterministic_hash_and_bad_time_is_retained():
    row = _message(local_id=None, server_id=None, create_time="not-a-time")
    first, first_summary = normalize_payload({"messages": [row]}, source_file="sample.json")
    second, second_summary = normalize_payload({"messages": [row]}, source_file="sample.json")
    assert first == second
    assert first_summary == second_summary
    assert first[0]["message_id_status"] == "content_hash_fallback"
    assert first[0]["timestamp"] is None
    assert first[0]["timestamp_raw"] == "not-a-time"
    assert first[0]["timestamp_status"] == "invalid"


def test_bad_record_is_counted_and_not_silently_dropped():
    records, summary = normalize_payload(
        {"messages": [_message(), None]}, source_file="sample.json"
    )
    assert len(records) == 1
    assert summary["input_messages"] == 2
    assert summary["error_count"] == 1
    assert summary["errors"][0]["row"] == 2
