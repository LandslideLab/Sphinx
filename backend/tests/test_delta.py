from sphinx.core.delta import diff_dicts, summarize_delta


def test_diff_add_replace_remove():
    base = {"a": 1, "b": "x", "keep": True}
    mod = {"a": 2, "c": "new", "keep": True}
    changes = diff_dicts(base, mod)
    ops = {c["op"] for c in changes}
    assert "add" in ops and "replace" in ops and "remove" in ops
    paths = {c["path"] for c in changes}
    assert paths == {"a", "b", "c"}
    rep = next(c for c in changes if c["path"] == "a")
    assert rep["from"] == 1 and rep["to"] == 2


def test_diff_nested():
    base = {"order": {"amount": 100, "note": "x"}, "tags": ["a"]}
    mod = {"order": {"amount": 120, "note": "x", "flag": True}, "tags": ["a"]}
    changes = diff_dicts(base, mod)
    paths = {c["path"] for c in changes}
    assert "order.amount" in paths
    assert "order.flag" in paths
    assert "tags" not in paths


def test_diff_equal_is_empty():
    assert diff_dicts({"a": 1}, {"a": 1}) == []


def test_diff_empty_base():
    assert diff_dicts({}, {"x": 1}) == [{"op": "add", "path": "x", "to": 1}]


def test_summarize_delta():
    assert summarize_delta([]) is None
    s = summarize_delta(diff_dicts({"a": 1}, {"a": 2, "b": 3}))
    assert isinstance(s, str)
    assert "~a" in s and "+b" in s
