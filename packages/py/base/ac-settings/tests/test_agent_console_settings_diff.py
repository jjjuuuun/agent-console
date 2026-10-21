"""문서 비교(`diff_documents`·`diff_digests`, design §2R.9)."""

from __future__ import annotations

import copy
import json
import random
from typing import Any

from agent_console_settings import (
    MISSING,
    DigestChange,
    DocumentChange,
    diff_digests,
    diff_documents,
    get_at,
)


def _ops(changes: list[DocumentChange]) -> list[tuple[str, str]]:
    return [(c.op, c.path) for c in changes]


def test_same_documents_have_no_changes() -> None:
    doc = {"a": 1, "l": [1, {"b": None}]}
    assert diff_documents(doc, copy.deepcopy(doc)) == []


def test_scalar_add_remove_replace() -> None:
    changes = diff_documents({"x": 1, "y": "a"}, {"y": "b", "z": [1]})
    by_path = {c.path: c for c in changes}
    assert by_path["/x"] == DocumentChange("remove", "/x", before=1)
    assert by_path["/y"] == DocumentChange("replace", "/y", before="a", after="b")
    assert by_path["/z"] == DocumentChange("add", "/z", after=[1])
    assert by_path["/x"].after is MISSING
    assert by_path["/z"].before is MISSING


def test_type_change_is_detected() -> None:
    [change] = diff_documents({"a": 1}, {"a": True})
    assert (change.op, change.before, change.after) == ("replace", 1, True)


def test_list_paths_follow_original_documents() -> None:
    """jsonpatch는 앞 원소를 지우면 뒤 번호를 당긴 경로를 내지만, 결과는 원래 문서 기준이다."""
    nodes = [{"id": str(i), "label": f"L{i}"} for i in range(6)]
    after = [n for n in nodes if n["id"] not in ("1", "2")]
    after[2] = {**after[2], "label": "X"}  # 원래 4번
    after.append({"id": "9"})
    changes = diff_documents({"nodes": nodes}, {"nodes": after})
    assert ("remove", "/nodes/1") in _ops(changes)
    assert ("remove", "/nodes/2") in _ops(changes)
    [label] = [c for c in changes if c.path.endswith("/label")]
    assert label.path == "/nodes/4/label"  # 이전 문서 기준
    assert get_at({"nodes": nodes}, label.path) == label.before
    [added] = [c for c in changes if c.op == "add"]
    assert added.path == "/nodes/4"  # 이후 문서 기준
    assert get_at({"nodes": after}, added.path) == added.after


def test_moved_key_becomes_remove_and_add() -> None:
    changes = diff_documents({"a": {"x": 1}}, {"b": {"x": 1}})
    assert _ops(changes) == [("remove", "/a"), ("add", "/b")]


def test_secret_position_is_masked_but_change_detected() -> None:
    before = {"env": {"TOKEN": "plain-1", "MODE": "a"}}
    after = {"env": {"TOKEN": "plain-2", "MODE": "a"}}
    [change] = diff_documents(
        before, after, before_secrets=["/env/TOKEN"], after_secrets=["/env/TOKEN"]
    )
    assert change == DocumentChange("replace", "/env/TOKEN", "***", "***", secret=True)
    # 같은 비밀 값이면 변경 없음
    same = ["/env/TOKEN"]
    assert diff_documents(before, before, before_secrets=same, after_secrets=same) == []


def test_secret_masked_on_one_side_only_hides_both_values() -> None:
    [change] = diff_documents(
        {"env": {"TOKEN": "plain"}},
        {"env": {"TOKEN": "secret://T"}},
        before_secrets=["/env/TOKEN"],
        mask="<hidden>",
    )
    assert (change.before, change.after, change.secret) == ("<hidden>", "<hidden>", True)


def test_nested_secret_inside_changed_value_is_masked() -> None:
    before: dict[str, Any] = {"nodes": []}
    after = {"nodes": [{"id": "a", "env": {"TOKEN": "plain-zz"}}]}
    [change] = diff_documents(before, after, after_secrets=["/nodes/0/env/TOKEN"])
    assert change.op == "add"
    assert not change.secret
    assert change.after == {"id": "a", "env": {"TOKEN": "***"}}
    assert "plain-zz" not in json.dumps(change.after)
    assert "agent-console-secret" not in json.dumps(change.after)


def test_bad_or_missing_secret_pointers_are_ignored() -> None:
    changes = diff_documents({"a": 1}, {"a": 2}, before_secrets=["/nope", "bad", "/a/x"])
    assert changes == [DocumentChange("replace", "/a", 1, 2)]


def test_inputs_are_not_modified() -> None:
    before = {"l": [1, 2, 3], "s": {"k": "v"}}
    after = {"l": [3], "s": {}}
    snapshot = copy.deepcopy((before, after))
    diff_documents(before, after, before_secrets=["/s/k"])
    assert (before, after) == snapshot


def _random_value(rng: random.Random, depth: int) -> Any:
    if depth <= 0 or rng.random() < 0.4:
        return rng.choice([0, 1, 2, "a", "b", None, True])
    if rng.random() < 0.5:
        return [_random_value(rng, depth - 1) for _ in range(rng.randint(0, 5))]
    return {rng.choice("pqrs"): _random_value(rng, depth - 1) for _ in range(rng.randint(0, 4))}


def _mutate(rng: random.Random, value: Any, depth: int) -> Any:
    if isinstance(value, list):
        out = [_mutate(rng, v, depth - 1) for v in value if rng.random() > 0.25]
        if rng.random() < 0.4:
            out.insert(rng.randint(0, len(out)), _random_value(rng, 2))
        if rng.random() < 0.2 and len(out) > 1:
            out.reverse()
        return out
    if isinstance(value, dict):
        out_d = {k: _mutate(rng, v, depth - 1) for k, v in value.items() if rng.random() > 0.2}
        if rng.random() < 0.3:
            out_d[rng.choice("pqrsx")] = _random_value(rng, 2)
        return out_d
    return _random_value(rng, 1) if rng.random() < 0.3 else value


def test_paths_resolve_in_original_documents_randomized() -> None:
    """무작위 문서 쌍: remove·replace 경로는 이전 문서의 그 값을, add 경로는 이후 문서의 그 값을
    가리킨다."""
    rng = random.Random(20261016)
    for _ in range(400):
        before = {"root": _random_value(rng, 4)}
        after = {"root": _mutate(rng, before["root"], 4)}
        for change in diff_documents(before, after):
            if change.op in ("remove", "replace"):
                assert get_at(before, change.path) == change.before, (before, after, change)
            if change.op == "add":
                assert get_at(after, change.path) == change.after, (before, after, change)


def test_diff_digests() -> None:
    assert diff_digests({"a": "1", "b": "2", "c": "3"}, {"b": "2", "c": "4", "d": "5"}) == [
        DigestChange("a", "1", None),
        DigestChange("c", "3", "4"),
        DigestChange("d", None, "5"),
    ]
