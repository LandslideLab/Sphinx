"""Sphinx Capture — automatic interception of every agent step.

Decorators and helpers that wrap tool calls, LLM inferences and state changes
and stream them into the Sphinx capture trail, so every step of an agent run
(tool calls, model inferences, state mutations) is recorded in a
tamper-evident, verifiable chain.

Usage:
    from sphinx_sdk import SphinxClient, Capture

    client = SphinxClient(agent_id="refund-agent", session_id="sess-1")
    cap = Capture(client)

    @cap.tool("lookup_order")
    def lookup_order(order_id: str): ...

    @cap.llm("classify_intent")
    def call_llm(messages): ...

    with cap.state("request_created") as s:
        s.before = {"ref": None}
        s.after = {"ref": "SPH-E126A0"}

    cap.flush()   # send any buffered events
"""
from __future__ import annotations

import functools
import inspect
import threading
import time
from typing import Any, Callable, Optional

from sphinx_sdk import client as _client_module


def _jsonable(value: Any) -> Any:
    """Best-effort coercion into JSON-serializable form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bytes):
        import base64

        return base64.b64encode(value).decode("ascii")
    try:
        return str(value)
    except Exception:
        return "<unserializable>"


def _args_to_payload(args: tuple, kwargs: dict) -> dict:
    payload: dict = {}
    if args:
        payload["args"] = _jsonable(list(args))
    if kwargs:
        payload["kwargs"] = _jsonable(dict(kwargs))
    return payload


class Capture:
    """Records agent steps into the Sphinx capture trail.

    Events are buffered and sent in batches; call `flush()` (or `close()`) to
    guarantee delivery. Failures are logged and swallowed so capture never
    breaks the agent's main path.
    """

    def __init__(
        self,
        client: "_client_module.SphinxClient",
        *,
        batch_size: int = 20,
        auto_flush: bool = True,
        enabled: bool = True,
    ):
        self._client = client
        self._batch_size = max(1, int(batch_size))
        self._auto_flush = auto_flush
        self.enabled = enabled
        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._sent = 0
        self._dropped = 0

    # ------------------------------------------------------------------ #
    # recording primitives
    # ------------------------------------------------------------------ #
    def record(
        self,
        event_type: str,
        event_name: str = "",
        *,
        input_payload: dict | None = None,
        output_payload: dict | None = None,
        metadata: dict | None = None,
        status: str = "ok",
    ) -> None:
        if not self.enabled:
            return
        event = {
            "event_type": event_type,
            "event_name": event_name,
            "input_payload": _jsonable(input_payload or {}),
            "output_payload": _jsonable(output_payload or {}),
            "metadata": _jsonable(metadata or {}),
            "status": status,
        }
        with self._lock:
            self._buffer.append(event)
            if self._auto_flush and len(self._buffer) >= self._batch_size:
                self._flush_locked()

    def state(self, key: str, metadata: dict | None = None):
        """Context manager recording a state change:

            with cap.state("request_created") as s:
                s.before = {...}
                s.after = {...}
        """
        return _StateCapture(self, key, metadata)

    # ------------------------------------------------------------------ #
    # decorators
    # ------------------------------------------------------------------ #
    def tool(
        self,
        name: str | None = None,
        *,
        metadata: dict | None = None,
        capture_args: bool = True,
    ) -> Callable:
        """Wrap a tool function; records input/output on every call."""

        def deco(fn):
            tool_name = name or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                started = time.monotonic()
                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - must not mask the error
                    self.record(
                        "tool_call",
                        tool_name,
                        input_payload=_args_to_payload(args, kwargs) if capture_args else {},
                        output_payload={"error": str(exc), "type": type(exc).__name__},
                        metadata={**(metadata or {}), "duration_ms": _ms(started)},
                        status="error",
                    )
                    raise
                self.record(
                    "tool_call",
                    tool_name,
                    input_payload=_args_to_payload(args, kwargs) if capture_args else {},
                    output_payload={"result": _jsonable(result)},
                    metadata={**(metadata or {}), "duration_ms": _ms(started)},
                )
                return result

            return wrapper

        return deco

    def tools(self, tool_map: dict[str, Callable], *, metadata: dict | None = None) -> dict[str, Callable]:
        """Wrap a whole {name: fn} tool registry in one call."""
        return {name: self.tool(name, metadata=metadata)(fn) for name, fn in tool_map.items()}

    def llm(self, name: str | None = None, *, metadata: dict | None = None) -> Callable:
        """Wrap an LLM call function (messages in, model response out)."""

        def deco(fn):
            llm_name = name or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                started = time.monotonic()
                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    self.record(
                        "llm_inference",
                        llm_name,
                        input_payload=_args_to_payload(args, kwargs),
                        output_payload={"error": str(exc), "type": type(exc).__name__},
                        metadata={**(metadata or {}), "duration_ms": _ms(started)},
                        status="error",
                    )
                    raise
                self.record(
                    "llm_inference",
                    llm_name,
                    input_payload=_args_to_payload(args, kwargs),
                    output_payload={"response": _jsonable(result)},
                    metadata={**(metadata or {}), "duration_ms": _ms(started)},
                )
                return result

            return wrapper

        return deco

    # ------------------------------------------------------------------ #
    # transport
    # ------------------------------------------------------------------ #
    def flush(self) -> int:
        """Send buffered events. Returns the number of events sent."""
        with self._lock:
            if not self._buffer:
                return 0
            return self._flush_locked()

    def _flush_locked(self) -> int:
        if not self._buffer:
            return 0
        batch = self._buffer
        self._buffer = []
        try:
            self._client.capture_events(batch)
            self._sent += len(batch)
            return len(batch)
        except Exception as exc:  # noqa: BLE001 - capture must never break the agent
            self._dropped += len(batch)
            import logging

            logging.getLogger("sphinx.capture").warning(
                "capture batch dropped (%d events): %s", len(batch), exc
            )
            return 0

    def close(self) -> None:
        self.flush()

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "buffered": len(self._buffer),
                "sent": self._sent,
                "dropped": self._dropped,
                "enabled": self.enabled,
            }

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


class _StateCapture:
    """Context manager backing `Capture.state(...)`."""

    def __init__(self, cap: Capture, key: str, metadata: dict | None):
        self._cap = cap
        self._key = key
        self._metadata = metadata
        self.before: Any = None
        self.after: Any = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        status = "error" if exc_type is not None else "ok"
        output = {"after": _jsonable(self.after)}
        if exc_type is not None:
            output = {"error": str(exc), "type": exc_type.__name__}
        self._cap.record(
            "state_change",
            self._key,
            input_payload={"before": _jsonable(self.before)},
            output_payload=output,
            metadata=self._metadata,
            status=status,
        )
        return False
