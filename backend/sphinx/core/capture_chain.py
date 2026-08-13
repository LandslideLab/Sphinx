"""Tamper-evident capture chain: SHA3-256 content hashing + Ed25519 signatures.

Every captured event (tool call / LLM inference / state change) is reduced to a
canonical byte string, hashed with SHA3-256, linked to the previous event in the
same (agent_id, session_id) chain, and signed with an Ed25519 key so the whole
decision trail can be independently verified.

Canonical form:
    JSON serialized with sort_keys=True, separators=(",", ":"), ensure_ascii=False.

Content hash:
    sha3_256(canonical({event_type, event_name, sequence, input_payload,
                        output_payload, metadata, status}))

Signature input:
    Ed25519 over the UTF-8 bytes of f"{prev_hash or ''}{content_hash}".
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError


def canonical(payload: dict) -> bytes:
    """Deterministic byte serialization of a JSON-serializable dict."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def hash_content(payload: dict) -> str:
    """SHA3-256 hex digest of the canonical form of a content payload."""
    return hashlib.sha3_256(canonical(payload)).hexdigest()


def content_of(
    *,
    event_type: str,
    event_name: str,
    sequence: int,
    input_payload: dict,
    output_payload: dict,
    metadata: dict,
    status: str,
) -> dict:
    """The subset of event fields protected by the content hash."""
    return {
        "event_type": event_type,
        "event_name": event_name,
        "sequence": sequence,
        "input_payload": input_payload,
        "output_payload": output_payload,
        "metadata": metadata,
        "status": status,
    }


def sign_message(signing_key: SigningKey, prev_hash: str | None, content_hash: str) -> str:
    """Ed25519 signature over prev_hash + content_hash, base64-encoded."""
    message = f"{prev_hash or ''}{content_hash}".encode("utf-8")
    return base64.b64encode(signing_key.sign(message).signature).decode("ascii")


def verify_signature(
    verify_key: VerifyKey, prev_hash: str | None, content_hash: str, signature_b64: str
) -> bool:
    """Return True when the signature is valid for prev_hash + content_hash."""
    try:
        message = f"{prev_hash or ''}{content_hash}".encode("utf-8")
        sig = base64.b64decode(signature_b64.encode("ascii"))
        verify_key.verify(message, sig)
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False


def load_signing_key(seed_b64: str | None = None) -> SigningKey:
    """Create a SigningKey from a base64 32-byte seed, or generate a new one."""
    if seed_b64:
        seed = base64.b64decode(seed_b64.encode("ascii"))
        if len(seed) != 32:
            raise ValueError("signing seed must be exactly 32 bytes when base64-decoded")
        return SigningKey(seed)
    return SigningKey.generate()


def seed_to_b64(signing_key: SigningKey) -> str:
    """Serialize the 32-byte seed so a key can be persisted / reused."""
    return base64.b64encode(bytes(signing_key)).decode("ascii")


def verify_chain(
    events: list[dict], verify_key: VerifyKey
) -> dict:
    """Verify a chain of event dicts (as returned by CaptureEvent.to_dict()).

    Events must be ordered by (agent_id, session_id, sequence). Recomputes each
    content hash, checks prev_hash linkage and Ed25519 signatures.

    Returns {"valid": bool, "checked": int, "errors": [str, ...]}.
    """
    errors: list[str] = []
    by_chain: dict[tuple[str, str], list[dict]] = {}
    for ev in events:
        by_chain.setdefault((ev["agent_id"], ev["session_id"]), []).append(ev)

    checked = 0
    for (agent_id, session_id), chain in by_chain.items():
        chain.sort(key=lambda e: (e["sequence"], e["created_at"]))
        prev_hash: str | None = None
        for ev in chain:
            content = content_of(
                event_type=ev["event_type"],
                event_name=ev["event_name"],
                sequence=ev["sequence"],
                input_payload=ev["input_payload"],
                output_payload=ev["output_payload"],
                metadata=ev["metadata"],
                status=ev["status"],
            )
            expected = hash_content(content)
            if expected != ev["content_hash"]:
                errors.append(
                    f"[{agent_id}/{session_id} #{ev['sequence']}] content hash mismatch: "
                    f"stored {ev['content_hash']} != recomputed {expected}"
                )
            if ev["prev_hash"] != prev_hash:
                errors.append(
                    f"[{agent_id}/{session_id} #{ev['sequence']}] chain broken: "
                    f"prev_hash {ev['prev_hash']} != expected {prev_hash}"
                )
            if not verify_signature(
                verify_key, ev["prev_hash"], ev["content_hash"], ev["signature"]
            ):
                errors.append(
                    f"[{agent_id}/{session_id} #{ev['sequence']}] invalid Ed25519 signature"
                )
            prev_hash = ev["content_hash"]
            checked += 1

    return {"valid": not errors, "checked": checked, "errors": errors}


def ensure_jsonable(value: Any) -> Any:
    """Best-effort coercion of a value into something JSON-serializable."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): ensure_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [ensure_jsonable(v) for v in value]
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    try:
        return str(value)
    except Exception:
        return "<unserializable>"
