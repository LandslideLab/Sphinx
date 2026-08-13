from __future__ import annotations


def diff_dicts(base: dict, modified: dict, path: str = "") -> list[dict]:
    """Recursively diff two dicts into an ordered change list.

    Each entry: {"op": "add"|"remove"|"replace", "path": "a.b[2].c", "from":?, "to":?}
    """
    changes: list[dict] = []

    def p(key) -> str:
        return f"{path}.{key}" if path else str(key)

    base_keys = set(base)
    mod_keys = set(modified)

    for key in sorted(base_keys - mod_keys):
        changes.append({"op": "remove", "path": p(key), "from": base[key]})

    for key in sorted(mod_keys - base_keys):
        changes.append({"op": "add", "path": p(key), "to": modified[key]})

    for key in sorted(base_keys & mod_keys):
        bv, mv = base[key], modified[key]
        if isinstance(bv, dict) and isinstance(mv, dict):
            changes.extend(diff_dicts(bv, mv, p(key)))
        elif bv != mv:
            changes.append({"op": "replace", "path": p(key), "from": bv, "to": mv})

    return changes


def summarize_delta(changes: list[dict]) -> str | None:
    if not changes:
        return None
    parts = []
    for c in changes[:5]:
        if c["op"] == "add":
            parts.append(f"+{c['path']}")
        elif c["op"] == "remove":
            parts.append(f"-{c['path']}")
        else:
            parts.append(f"~{c['path']}")
    if len(changes) > 5:
        parts.append(f"…(+{len(changes) - 5} more)")
    return ", ".join(parts)
