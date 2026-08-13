"""Unit tests for the tamper-evident capture chain (hashing + signing)."""
from __future__ import annotations

import base64

import pytest
from nacl.signing import SigningKey

from sphinx.core import capture_chain


def _sample_content(**over) -> dict:
    base = dict(
        event_type="tool_call",
        event_name="lookup_order",
        sequence=1,
        input_payload={"order_id": "ORD-1"},
        output_payload={"order": {"id": "ORD-1"}},
        metadata={"duration_ms": 12},
        status="ok",
    )
    base.update(over)
    return base


class TestCanonicalAndHash:
    def test_canonical_is_deterministic(self):
        a = {"b": 2, "a": {"y": [1, 2], "x": "z"}, "c": None}
        b = {"c": None, "a": {"x": "z", "y": [1, 2]}, "b": 2}
        assert capture_chain.canonical(a) == capture_chain.canonical(b)

    def test_hash_differs_on_any_field(self):
        h1 = capture_chain.hash_content(_sample_content())
        h2 = capture_chain.hash_content(_sample_content(sequence=2))
        h3 = capture_chain.hash_content(_sample_content(input_payload={"order_id": "ORD-2"}))
        assert h1 != h2 != h3
        assert len(h1) == 64  # sha3-256 hex

    def test_unicode_stable(self):
        c = _sample_content(event_name="审批")
        assert capture_chain.hash_content(c) == capture_chain.hash_content(c)


class TestSigning:
    def test_sign_verify_roundtrip(self):
        key = SigningKey.generate()
        ch = capture_chain.hash_content(_sample_content())
        sig = capture_chain.sign_message(key, None, ch)
        assert capture_chain.verify_signature(key.verify_key, None, ch, sig)

    def test_signature_rejects_wrong_hash(self):
        key = SigningKey.generate()
        ch = capture_chain.hash_content(_sample_content())
        sig = capture_chain.sign_message(key, None, ch)
        other = capture_chain.hash_content(_sample_content(sequence=99))
        assert not capture_chain.verify_signature(key.verify_key, None, other, sig)

    def test_signature_rejects_wrong_key(self):
        key_a = SigningKey.generate()
        key_b = SigningKey.generate()
        ch = capture_chain.hash_content(_sample_content())
        sig = capture_chain.sign_message(key_a, None, ch)
        assert not capture_chain.verify_signature(key_b.verify_key, None, ch, sig)

    def test_signature_covers_prev_hash_link(self):
        key = SigningKey.generate()
        prev = "a" * 64
        ch = capture_chain.hash_content(_sample_content())
        sig = capture_chain.sign_message(key, prev, ch)
        # valid for the same prev
        assert capture_chain.verify_signature(key.verify_key, prev, ch, sig)
        # invalid when the link is tampered
        assert not capture_chain.verify_signature(key.verify_key, None, ch, sig)
        assert not capture_chain.verify_signature(key.verify_key, "b" * 64, ch, sig)

    def test_seed_roundtrip(self):
        key = SigningKey.generate()
        seed = capture_chain.seed_to_b64(key)
        restored = capture_chain.load_signing_key(seed)
        assert bytes(restored) == bytes(key)

    def test_load_signing_key_rejects_bad_seed(self):
        with pytest.raises(ValueError):
            capture_chain.load_signing_key(base64.b64encode(b"short").decode())


class TestVerifyChain:
    def _event(self, key, *, seq, prev, agent="agent-a", session="sess-1", **content_over):
        content = _sample_content(sequence=seq, **content_over)
        ch = capture_chain.hash_content(content)
        sig = capture_chain.sign_message(key, prev, ch)
        return {
            "agent_id": agent,
            "session_id": session,
            "event_type": content["event_type"],
            "event_name": content["event_name"],
            "sequence": content["sequence"],
            "input_payload": content["input_payload"],
            "output_payload": content["output_payload"],
            "metadata": content["metadata"],
            "status": content["status"],
            "content_hash": ch,
            "prev_hash": prev,
            "signature": sig,
            "created_at": "2026-08-13T00:00:00+00:00",
        }

    def test_valid_chain_passes(self):
        key = SigningKey.generate()
        e1 = self._event(key, seq=1, prev=None)
        e2 = self._event(key, seq=2, prev=e1["content_hash"])
        e3 = self._event(key, seq=3, prev=e2["content_hash"])
        result = capture_chain.verify_chain([e1, e2, e3], key.verify_key)
        assert result["valid"] is True
        assert result["checked"] == 3
        assert result["errors"] == []

    def test_detects_payload_tamper(self):
        key = SigningKey.generate()
        e1 = self._event(key, seq=1, prev=None)
        e2 = self._event(key, seq=2, prev=e1["content_hash"])
        # tamper with e2's output without recomputing the hash
        e2["output_payload"] = {"order": {"id": "ORD-EVIL"}}
        result = capture_chain.verify_chain([e1, e2], key.verify_key)
        assert result["valid"] is False
        assert any("content hash mismatch" in e for e in result["errors"])

    def test_detects_broken_link(self):
        key = SigningKey.generate()
        e1 = self._event(key, seq=1, prev=None)
        e2 = self._event(key, seq=2, prev=None)  # wrong: should link to e1
        result = capture_chain.verify_chain([e1, e2], key.verify_key)
        assert result["valid"] is False
        assert any("chain broken" in e for e in result["errors"])

    def test_detects_forged_signature(self):
        key = SigningKey.generate()
        e1 = self._event(key, seq=1, prev=None)
        e2 = self._event(key, seq=2, prev=e1["content_hash"])
        e2["signature"] = base64.b64encode(b"\x00" * 64).decode()
        result = capture_chain.verify_chain([e1, e2], key.verify_key)
        assert result["valid"] is False
        assert any("invalid Ed25519 signature" in e for e in result["errors"])

    def test_multiple_chains_isolated(self):
        key = SigningKey.generate()
        a1 = self._event(key, seq=1, prev=None, agent="agent-a")
        a2 = self._event(key, seq=2, prev=a1["content_hash"], agent="agent-a")
        b1 = self._event(key, seq=1, prev=None, agent="agent-b")
        result = capture_chain.verify_chain([a1, b1, a2], key.verify_key)
        assert result["valid"] is True
        assert result["checked"] == 3
