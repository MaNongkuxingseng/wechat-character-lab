import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from app.profiles.semantic_analyzer import (
    OUTPUT_SCHEMA_VERSION,
    OpenAICompatibleSemanticAnalyzer,
    SemanticProviderConfig,
)


def _messages():
    return [
        {
            "message_id": "a-1",
            "sender": "private-label",
            "content": "我喜欢周末去公园散步。",
        },
        {
            "message_id": "a-2",
            "sender": "private-label",
            "content": "通常会提前安排路线和时间。",
        },
        {
            "message_id": "a-3",
            "sender": "private-label",
            "content": "下雨时会改成在家阅读。",
        },
    ]


def _config() -> SemanticProviderConfig:
    return SemanticProviderConfig(
        enabled=True,
        allow_message_content=True,
        endpoint="http://127.0.0.1:9999/v1/chat/completions",
        model="synthetic-semantic",
        api_key="test-only",
        timeout_seconds=1,
    )


def _response(payload: dict[str, object]) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
        ensure_ascii=False,
    ).encode("utf-8")


def _payload(*, evidence_ids=None, counter_evidence_ids=None):
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "subject_id": "role_a",
        "traits": [
            {
                "category": "behavior_pattern",
                "claim": "倾向提前安排活动并准备替代方案",
                "evidence_ids": evidence_ids or ["a-1", "a-2"],
                "counter_evidence_ids": counter_evidence_ids or [],
                "rationale": "多条消息都呈现计划和替代安排的线索",
                "uncertainty": "样本只覆盖有限的周末活动，不能代表所有场景",
                "confidence": 0.72,
                "conflict_status": "none" if not counter_evidence_ids else "conflict",
            }
        ],
    }


def test_provider_refuses_content_transfer_without_approved_source_even_when_configured():
    analyzer = OpenAICompatibleSemanticAnalyzer(_config())
    output = analyzer.analyze("role_a", _messages())
    assert output.status == "source_transfer_not_authorized"


def test_provider_validates_structured_output_and_does_not_send_sender_labels():
    captured: dict[str, object] = {}

    def transport(endpoint, body, headers, timeout):
        captured["endpoint"] = endpoint
        captured["body"] = body.decode("utf-8")
        captured["headers"] = dict(headers)
        captured["timeout"] = timeout
        return _response(_payload())

    analyzer = OpenAICompatibleSemanticAnalyzer(
        _config(), approved_source=True, transport=transport
    )
    output = analyzer.analyze("role_a", _messages())
    assert output.status == "ready"
    assert output.sample_count == 3
    assert output.signals[0]["evidence_ids"] == ["a-1", "a-2"]
    assert output.signals[0]["category"] == "semantic.behavior_pattern"
    assert "private-label" not in str(captured["body"])
    assert "test-only" not in str(captured["body"])


def test_provider_rejects_unknown_or_cross_direction_evidence():
    def transport(endpoint, body, headers, timeout):
        return _response(_payload(evidence_ids=["not-in-input"]))

    analyzer = OpenAICompatibleSemanticAnalyzer(
        _config(), approved_source=True, transport=transport
    )
    assert analyzer.analyze("role_a", _messages()).status == "invalid_output"

    def overlap_transport(endpoint, body, headers, timeout):
        return _response(_payload(evidence_ids=["a-1"], counter_evidence_ids=["a-1"]))

    analyzer = OpenAICompatibleSemanticAnalyzer(
        _config(), approved_source=True, transport=overlap_transport
    )
    assert analyzer.analyze("role_a", _messages()).status == "invalid_output"


def test_provider_retries_timeout_without_logging_or_fabricating_result():
    attempts = {"count": 0}

    def transport(endpoint, body, headers, timeout):
        attempts["count"] += 1
        raise TimeoutError("synthetic timeout")

    analyzer = OpenAICompatibleSemanticAnalyzer(
        _config(), approved_source=True, transport=transport, sleeper=lambda _: None
    )
    output = analyzer.analyze("role_a", _messages())
    assert attempts["count"] == 3
    assert output.status == "timeout"
    assert output.signals == ()


def test_provider_rejects_redirect_without_forwarding_payload():
    requests = {"count": 0}

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests["count"] += 1
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/collect")
            self.end_headers()

        def log_message(self, _format, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = SemanticProviderConfig(
            enabled=True,
            allow_message_content=True,
            endpoint=f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
            model="synthetic-semantic",
            timeout_seconds=1,
        )
        output = OpenAICompatibleSemanticAnalyzer(
            config, approved_source=True, sleeper=lambda _: None
        ).analyze("role_a", _messages())
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert output.status == "provider_rejected_request"
    assert output.signals == ()
    assert requests["count"] == 1


def test_provider_bounds_large_role_input_and_keeps_full_sample_count():
    captured: dict[str, object] = {}

    def transport(endpoint, body, headers, timeout):
        records = json.loads(json.loads(body.decode("utf-8"))["messages"][1]["content"])
        captured["records"] = records
        return _response(_payload(evidence_ids=[records[0]["message_id"]]))

    messages = [
        {"message_id": f"a-{index}", "content": "x" * 30}
        for index in range(100)
    ]
    config = SemanticProviderConfig(
        enabled=True,
        allow_message_content=True,
        endpoint="http://127.0.0.1:9999/v1/chat/completions",
        model="synthetic-semantic",
        max_input_chars=500,
    )
    analyzer = OpenAICompatibleSemanticAnalyzer(
        config, approved_source=True, transport=transport
    )
    output = analyzer.analyze("role_a", messages)
    assert output.status == "ready"
    assert output.sample_count == 100
    assert 1 < len(captured["records"]) < 100
    assert output.metadata["input_available_count"] == 100
