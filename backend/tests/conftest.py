"""Test fixtures. Isolated SQLite DB per pytest session for unit tests, plus a
module-scoped live API+MCP stack on a dedicated DB for integration tests.
"""
from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass

import pytest

# Must be set before any sphinx import.
_TEST_DB = tempfile.mktemp(prefix="sphinx_test_", suffix=".db")
os.environ["SPHINX_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["SPHINX_SCHEDULER_INTERVAL_SECONDS"] = "0.5"
os.environ["SPHINX_CORS_ORIGINS"] = '["*"]'

from sphinx.db import Base, engine, init_db  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def db():
    """Per-test in-process DB: tables wiped and recreated for each unit test."""
    from sphinx.db import SessionLocal

    Base.metadata.drop_all(bind=engine)
    init_db()
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_session():
    yield
    Base.metadata.drop_all(bind=engine)
    for p in ("sphinx.db", "sphinx.db-shm", "sphinx.db-wal"):
        path = os.path.join(os.path.dirname(_TEST_DB), p)
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


def _venv_python() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".venv", "bin", "python")


def _wait_http(url: str, timeout_s: float = 30.0) -> None:
    import httpx

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/api/health", timeout=2).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.3)
    raise TimeoutError(f"server at {url} did not become ready")


def _wait_mcp(url: str, timeout_s: float = 30.0) -> None:
    import httpx

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, timeout=2)
            if r.status_code < 500:
                return
        except Exception:
            pass
        time.sleep(0.3)
    raise TimeoutError(f"MCP server at {url} did not become ready")


@dataclass
class LiveStack:
    api_url: str
    mcp_url: str
    db_path: str
    _procs: list

    def stop(self) -> None:
        for proc in self._procs:
            proc.terminate()
        for proc in self._procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.fixture(scope="module")
def live() -> LiveStack:
    """A fully running API + MCP stack on a dedicated temp DB, seeded with demo data.

    Integration tests (REST, WS, MCP, SDK, demo agent) run against this stack so
    they never interfere with the per-test unit DB.
    """
    db_path = tempfile.mktemp(prefix="sphinx_live_", suffix=".db")
    env = dict(os.environ)
    env["SPHINX_DATABASE_URL"] = f"sqlite:///{db_path}"
    env["SPHINX_SEED_DEMO_DATA"] = "1"
    env["SPHINX_DEFAULT_POLICY_SEED"] = "1"
    env["SPHINX_SCHEDULER_INTERVAL_SECONDS"] = "0.2"

    api_port = _free_port()
    mcp_port = _free_port()
    venv = _venv_python()
    procs = []
    try:
        api_proc = subprocess.Popen(
            [venv, "-m", "uvicorn", "sphinx.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(api_proc)
        mcp_proc = subprocess.Popen(
            [venv, "-m", "sphinx.mcp.server", "--http", "--port", str(mcp_port)],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(mcp_proc)

        api_url = f"http://127.0.0.1:{api_port}"
        mcp_url = f"http://127.0.0.1:{mcp_port}/mcp"
        _wait_http(api_url)
        _wait_mcp(mcp_url)
        yield LiveStack(api_url=api_url, mcp_url=mcp_url, db_path=db_path, _procs=procs)
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
