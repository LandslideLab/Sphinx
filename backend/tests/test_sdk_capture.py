"""Tests for the SDK Capture interception layer (decorators, batching, transport)."""
from __future__ import annotations

import pytest

from sphinx_sdk import Capture, SphinxClient


class _FakeClient:
    """In-memory stand-in for SphinxClient so unit tests don't need a server."""

    def __init__(self):
        self.sent: list[list[dict]] = []
        self.agent_id = "fake-agent"
        self.session_id = "fake-sess"

    def capture_events(self, events: list[dict]) -> dict:
        self.sent.append(list(events))
        return {"received": len(events)}


@pytest.fixture()
def cap():
    return Capture(_FakeClient(), batch_size=100)


class TestToolDecorator:
    def test_records_input_output(self, cap):
        @cap.tool("lookup_order")
        def lookup_order(order_id: str) -> dict:
            return {"id": order_id, "status": "delivered"}

        result = lookup_order(order_id="ORD-1")
        assert result["status"] == "delivered"
        cap.flush()
        batch = cap._client.sent[-1]
        assert len(batch) == 1
        ev = batch[0]
        assert ev["event_type"] == "tool_call"
        assert ev["event_name"] == "lookup_order"
        assert ev["input_payload"] == {"kwargs": {"order_id": "ORD-1"}}
        assert ev["output_payload"] == {"result": {"id": "ORD-1", "status": "delivered"}}
        assert ev["status"] == "ok"

    def test_records_exception_and_re_raises(self, cap):
        @cap.tool("flaky")
        def flaky():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            flaky()
        cap.flush()
        ev = cap._client.sent[-1][0]
        assert ev["status"] == "error"
        assert ev["output_payload"]["error"] == "boom"
        assert ev["output_payload"]["type"] == "RuntimeError"

    def test_default_name_is_function_name(self, cap):
        @cap.tool()
        def my_tool():
            return 1

        my_tool()
        cap.flush()
        assert cap._client.sent[-1][0]["event_name"] == "my_tool"

    def test_metadata_attached(self, cap):
        @cap.tool("t", metadata={"team": "ops"})
        def t():
            return 1

        t()
        cap.flush()
        ev = cap._client.sent[-1][0]
        assert ev["metadata"]["team"] == "ops"
        assert "duration_ms" in ev["metadata"]

    def test_tools_batch_wrap(self, cap):
        registry = {"a": lambda: 1, "b": lambda: 2}
        wrapped = cap.tools(registry)
        wrapped["a"]()
        wrapped["b"]()
        cap.flush()
        assert len(cap._client.sent[-1]) == 2


class TestLlmDecorator:
    def test_records_prompt_response(self, cap):
        @cap.llm("classify")
        def call_llm(messages: list[dict]) -> str:
            return "refund_request"

        out = call_llm(messages=[{"role": "user", "content": "hi"}])
        assert out == "refund_request"
        cap.flush()
        ev = cap._client.sent[-1][0]
        assert ev["event_type"] == "llm_inference"
        assert ev["event_name"] == "classify"
        assert ev["input_payload"]["kwargs"]["messages"][0]["content"] == "hi"
        assert ev["output_payload"]["response"] == "refund_request"

    def test_records_llm_error(self, cap):
        @cap.llm("broken_llm")
        def broken_llm():
            raise ValueError("rate limited")

        with pytest.raises(ValueError):
            broken_llm()
        cap.flush()
        ev = cap._client.sent[-1][0]
        assert ev["status"] == "error"
        assert ev["output_payload"]["type"] == "ValueError"


class TestStateCapture:
    def test_state_context_manager(self, cap):
        with cap.state("request_created") as s:
            s.before = {"ref": None}
            s.after = {"ref": "SPH-ABC"}
        cap.flush()
        ev = cap._client.sent[-1][0]
        assert ev["event_type"] == "state_change"
        assert ev["event_name"] == "request_created"
        assert ev["input_payload"] == {"before": {"ref": None}}
        assert ev["output_payload"] == {"after": {"ref": "SPH-ABC"}}
        assert ev["status"] == "ok"

    def test_state_error_records_error_status(self, cap):
        with pytest.raises(ZeroDivisionError):
            with cap.state("calc") as s:
                s.before = {"x": 1}
                1 / 0
        cap.flush()
        ev = cap._client.sent[-1][0]
        assert ev["status"] == "error"
        assert ev["output_payload"]["type"] == "ZeroDivisionError"


class TestBatching:
    def test_flush_sends_all(self, cap):
        cap.record("tool_call", "a", input_payload={}, output_payload={})
        cap.record("tool_call", "b", input_payload={}, output_payload={})
        assert len(cap._client.sent) == 0  # nothing sent until flush
        n = cap.flush()
        assert n == 2
        assert len(cap._client.sent[-1]) == 2

    def test_auto_flush_at_batch_size(self):
        client = _FakeClient()
        cap = Capture(client, batch_size=2)
        cap.record("tool_call", "a", input_payload={}, output_payload={})
        assert len(client.sent) == 0
        cap.record("tool_call", "b", input_payload={}, output_payload={})
        assert len(client.sent) == 1  # auto-flushed at batch_size
        assert len(client.sent[0]) == 2

    def test_close_flushes(self):
        client = _FakeClient()
        cap = Capture(client, batch_size=100)
        cap.record("tool_call", "a", input_payload={}, output_payload={})
        cap.close()
        assert len(client.sent) == 1

    def test_disabled_drops_events(self):
        client = _FakeClient()
        cap = Capture(client, enabled=False)
        cap.record("tool_call", "a", input_payload={}, output_payload={})
        cap.flush()
        assert client.sent == []
        assert cap.stats["dropped"] == 0


class TestFailureIsolation:
    def test_server_error_does_not_break_agent(self):
        class _BrokenClient:
            def capture_events(self, events):
                raise RuntimeError("server down")

        cap = Capture(_BrokenClient())
        cap.record("tool_call", "a", input_payload={}, output_payload={})
        # flush swallows the error; agent code continues
        assert cap.flush() == 0
        assert cap.stats["dropped"] == 1

    def test_non_jsonable_args_are_coerced(self, cap):
        class Thing:
            def __str__(self):
                return "thing-str"

        @cap.tool("t")
        def t(x):
            return x

        t(Thing())
        cap.flush()
        ev = cap._client.sent[-1][0]
        assert ev["input_payload"]["args"][0] == "thing-str"


class TestRealTransport:
    def test_rest_transport_roundtrip(self, live):
        """End-to-end: SDK Capture over REST into the live stack + verify."""
        client = SphinxClient(transport="rest", base_url=live.api_url, agent_id="sdk-e2e", session_id="sdk-sess")
        cap = Capture(client)

        @cap.tool("lookup_order")
        def lookup_order(order_id: str) -> dict:
            return {"id": order_id, "ok": True}

        with cap.state("ticket") as s:
            s.before = {"ref": None}
            s.after = {"ref": "SPH-E2E"}

        lookup_order("ORD-9")
        cap.flush()
        assert cap.stats["sent"] == 2

        import httpx

        r = httpx.get(f"{live.api_url}/api/capture", params={"agent_id": "sdk-e2e"})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        types = {ev["event_type"] for ev in body["items"]}
        assert types == {"tool_call", "state_change"}

        v = httpx.get(f"{live.api_url}/api/capture/verify", params={"agent_id": "sdk-e2e"}).json()
        assert v["valid"] is True
        assert v["checked"] == 2
