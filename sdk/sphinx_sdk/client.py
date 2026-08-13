"""SphinxClient - two transports over the same control plane.

- REST:  direct HTTP calls to the Sphinx API (httpx).
- MCP:   calls through the Sphinx MCP server over streamable HTTP.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx


class SphinxError(Exception):
    pass


class SphinxTimeout(SphinxError):
    pass


@dataclass
class ApprovalTicket:
    id: str
    ref: str
    status: str

    def to_dict(self) -> dict:
        return {"id": self.id, "ref": self.ref, "status": self.status}


class BaseTransport:
    def request_approval(self, **kw) -> ApprovalTicket: ...
    def get_status(self, request_id: str) -> dict: ...
    def get_decision(self, request_id: str) -> dict: ...
    def submit_feedback(self, request_id: str, outcome: str, note: str = "", agent_id: str = "") -> dict: ...
    def list_policies(self) -> list[dict]: ...
    def wait_for_decision(self, request_id: str, timeout_s: float = 300, poll_interval_s: float = 1.0) -> dict: ...


class RestTransport(BaseTransport):
    def __init__(self, base_url: str = "http://localhost:8001", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def _post(self, path: str, **body) -> dict:
        r = self._client.post(path, json=body)
        _raise(r)
        return r.json()

    def _get(self, path: str) -> dict:
        r = self._client.get(path)
        _raise(r)
        return r.json()

    def request_approval(self, **kw) -> ApprovalTicket:
        data = self._post("/api/requests", **kw)
        return ApprovalTicket(id=data["id"], ref=data["ref"], status=data["status"])

    def get_status(self, request_id: str) -> dict:
        data = self._get(f"/api/requests/{request_id}")
        return {"id": data["id"], "ref": data["ref"], "status": data["status"], "escalated": data["escalated"]}

    def get_decision(self, request_id: str) -> dict:
        data = self._get(f"/api/requests/{request_id}")
        return {
            "id": data["id"],
            "ref": data["ref"],
            "status": data["status"],
            "approved": data["status"] in ("approved", "auto_approved"),
            "decision_payload": data["decision_payload"],
            "reviewer_id": data["reviewer_id"],
            "reviewer_note": data["reviewer_note"],
            "resolved_by": data["resolved_by"],
            "decided_at": data["decided_at"],
        }

    def submit_feedback(self, request_id: str, outcome: str, note: str = "", agent_id: str = "") -> dict:
        return self._post(f"/api/requests/{request_id}/feedback", outcome=outcome, note=note, agent_id=agent_id)

    def list_policies(self) -> list[dict]:
        return self._get("/api/policies")["items"]

    def wait_for_decision(self, request_id: str, timeout_s: float = 300, poll_interval_s: float = 1.0) -> dict:
        deadline = time.monotonic() + timeout_s
        while True:
            data = self._get(f"/api/requests/{request_id}")
            if data["status"] != "pending":
                return {
                    "id": data["id"],
                    "ref": data["ref"],
                    "status": data["status"],
                    "approved": data["status"] in ("approved", "auto_approved"),
                    "decision_payload": data["decision_payload"],
                    "reviewer_id": data["reviewer_id"],
                    "reviewer_note": data["reviewer_note"],
                    "escalated": data["escalated"],
                }
            if time.monotonic() >= deadline:
                raise SphinxTimeout(f"request {data['ref']} still pending after {timeout_s}s")
            time.sleep(poll_interval_s)


class McpTransport(BaseTransport):
    """Transport over the Sphinx MCP server (streamable HTTP).

    The MCP SDK is async; we bridge it onto a background event loop so the
    client keeps a simple synchronous API.
    """

    def __init__(self, url: str = "http://localhost:8100/mcp"):
        self.url = url
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session = None
        self._thread: threading.Thread | None = None
        self._connected = False

    def _connect(self):
        if self._connected:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        fut = asyncio.run_coroutine_threadsafe(self._open_session(), self._loop)
        fut.result(timeout=30)
        self._connected = True

    async def _open_session(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        self._ctx = streamable_http_client(self.url)
        self._read, self._write = await self._ctx.__aenter__()
        self._session = ClientSession(self._read, self._write)
        await self._session.__aenter__()
        await self._session.initialize()

    def _call(self, tool: str, **kw) -> dict:
        self._connect()
        fut = asyncio.run_coroutine_threadsafe(self._call_async(tool, kw), self._loop)
        result = fut.result(timeout=300)
        content = result.content[0].text if result.content else "{}"
        try:
            return json.loads(content) if isinstance(content, str) else dict(content)
        except json.JSONDecodeError:
            return {"raw": content}

    async def _call_async(self, tool: str, kw: dict):
        return await self._session.call_tool(tool, kw)

    def request_approval(self, **kw) -> ApprovalTicket:
        data = self._call("sphinx_request_approval", **kw)
        return ApprovalTicket(id=data["id"], ref=data["ref"], status=data["status"])

    def get_status(self, request_id: str) -> dict:
        return self._call("sphinx_get_status", request_id=request_id)

    def get_decision(self, request_id: str) -> dict:
        return self._call("sphinx_get_decision", request_id=request_id)

    def submit_feedback(self, request_id: str, outcome: str, note: str = "", agent_id: str = "") -> dict:
        return self._call("sphinx_submit_feedback", request_id=request_id, outcome=outcome, note=note, agent_id=agent_id)

    def list_policies(self) -> list[dict]:
        return self._call("sphinx_list_policies")["items"]

    def wait_for_decision(self, request_id: str, timeout_s: float = 300, poll_interval_s: float = 1.0) -> dict:
        return self._call("sphinx_wait_for_decision", request_id=request_id, timeout_s=int(timeout_s), poll_interval_s=poll_interval_s)

    def close(self):
        if self._connected and self._loop:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._close_session(), self._loop)
                fut.result(timeout=10)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=5)
            self._connected = False

    async def _close_session(self):
        try:
            await self._session.__aexit__(None, None, None)
            await self._ctx.__aexit__(None, None, None)
        except Exception:
            pass


def _raise(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise SphinxError(f"HTTP {resp.status_code}: {detail}")


class SphinxClient:
    """High-level client. transport: 'rest' (default) or 'mcp'."""

    def __init__(
        self,
        *,
        transport: str = "rest",
        base_url: str = "http://localhost:8001",
        mcp_url: str = "http://localhost:8100/mcp",
        agent_id: str = "agent",
        framework: str = "generic",
        session_id: str = "",
    ):
        self.agent_id = agent_id
        self.framework = framework
        self.session_id = session_id
        self._rest_base_url = base_url
        if transport == "mcp":
            self._transport: BaseTransport = McpTransport(url=mcp_url)
        else:
            self._transport = RestTransport(base_url=base_url)

    def request_approval(
        self,
        title: str,
        action_payload: dict,
        *,
        description: str = "",
        risk_level: str = "medium",
        priority: int = 1,
        policy_id: str | None = None,
        metadata: dict | None = None,
        **extra,
    ) -> ApprovalTicket:
        kw = dict(
            agent_id=extra.pop("agent_id", self.agent_id),
            framework=extra.pop("framework", self.framework),
            session_id=extra.pop("session_id", self.session_id),
            title=title,
            action_payload=action_payload,
            description=description,
            risk_level=risk_level,
            priority=priority,
        )
        if policy_id:
            kw["policy_id"] = policy_id
        if metadata:
            kw["metadata"] = metadata
        kw.update(extra)
        return self._transport.request_approval(**kw)

    def check_status(self, request_id: str) -> dict:
        return self._transport.get_status(request_id)

    def get_decision(self, request_id: str) -> dict:
        return self._transport.get_decision(request_id)

    def wait_for_decision(self, request_id: str, timeout_s: float = 300, poll_interval_s: float = 1.0) -> dict:
        return self._transport.wait_for_decision(request_id, timeout_s=timeout_s, poll_interval_s=poll_interval_s)

    def submit_feedback(self, request_id: str, outcome: str, note: str = "") -> dict:
        return self._transport.submit_feedback(request_id, outcome, note=note, agent_id=self.agent_id)

    def list_policies(self) -> list[dict]:
        return self._transport.list_policies()

    def capture_events(self, events: list[dict]) -> dict:
        """Upload a batch of capture events for this client's agent/session.

        Uses the REST API directly (works with both REST and MCP transports).
        """
        if isinstance(self._transport, RestTransport):
            r = self._transport._client.post(
                "/api/capture",
                json={"agent_id": self.agent_id, "session_id": self.session_id, "events": events},
            )
            _raise(r)
            return r.json()
        # MCP transport: capture is an HTTP concern; post to the REST base URL.
        r = httpx.post(
            f"{self._rest_base_url}/api/capture",
            json={"agent_id": self.agent_id, "session_id": self.session_id, "events": events},
            timeout=30.0,
        )
        _raise(r)
        return r.json()

    def close(self) -> None:
        if isinstance(self._transport, McpTransport):
            self._transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
