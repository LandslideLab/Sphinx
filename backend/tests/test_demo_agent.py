"""End-to-end tests: run the demo agent script against a live stack."""
from __future__ import annotations

import os
import subprocess

import httpx

DEMO = os.path.join(os.path.dirname(__file__), "..", "..", "sdk", "examples", "demo_agent.py")
PYTHON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".venv", "bin", "python")


def _run_demo(live, transport: str):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.join(os.path.dirname(__file__), "..", "..", "sdk"), env.get("PYTHONPATH", "")]
    )
    proc = subprocess.Popen(
        [
            PYTHON,
            DEMO,
            "--transport",
            transport,
            "--api-url",
            live.api_url,
            "--mcp-url",
            live.mcp_url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    try:
        out, _ = proc.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        raise AssertionError(f"demo agent timed out:\n{out}")

    assert proc.returncode == 0, f"demo agent failed rc={proc.returncode}:\n{out}"
    return out


def _refs_from(out: str) -> list[str]:
    refs = []
    for line in out.splitlines():
        if "ticket" in line and "status=" in line:
            refs.append(line.split("ticket ")[1].split(" ")[0])
    return refs


class TestDemoAgent:
    def test_rest_transport(self, live):
        out = _run_demo(live, "rest")
        assert "feedback outcome=success" in out
        refs = _refs_from(out)
        assert len(refs) == 3
        # low-risk scenario auto-approved
        assert "status=auto_approved" in out

    def test_mcp_transport(self, live):
        out = _run_demo(live, "mcp")
        assert "feedback outcome=success" in out
        refs = _refs_from(out)
        assert len(refs) == 3

    def test_demo_tickets_visible_via_api(self, live):
        out = _run_demo(live, "rest")
        refs = _refs_from(out)
        r = httpx.get(f"{live.api_url}/api/requests", params={"agent_id": "refund-agent", "limit": 100}, timeout=5)
        items = r.json()["items"]
        found = {i["ref"] for i in items if i["ref"] in refs}
        assert found == set(refs)
        for it in items:
            if it["ref"] in refs:
                assert it["outcome"] is not None  # feedback loop closed

    def test_demo_capture_trail_verifiable(self, live):
        """The demo agent's capture events form a valid, verifiable chain.

        The live stack is module-scoped and shared, so earlier demo runs may
        have added events too; assert every event is valid and the run adds
        exactly 9 (3 steps × state/tool/llm) per execution.
        """
        before = httpx.get(
            f"{live.api_url}/api/capture",
            params={"agent_id": "refund-agent", "session_id": "sess-refund-01", "limit": 1},
            timeout=5,
        ).json()["total"]
        _run_demo(live, "rest")
        r = httpx.get(
            f"{live.api_url}/api/capture",
            params={"agent_id": "refund-agent", "session_id": "sess-refund-01", "limit": 200},
            timeout=5,
        )
        body = r.json()
        items = body["items"]
        assert body["total"] == before + 9, f"expected +9 capture events, got +{body['total'] - before}"
        types = {ev["event_type"] for ev in items}
        assert types == {"tool_call", "llm_inference", "state_change"}
        v = httpx.get(
            f"{live.api_url}/api/capture/verify",
            params={"agent_id": "refund-agent", "session_id": "sess-refund-01"},
            timeout=5,
        ).json()
        assert v["valid"] is True
        assert v["checked"] == body["total"]
