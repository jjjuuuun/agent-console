"""저장소 사이 복사(5.7R.33z, design §PI.4.3): 조건·충돌·범위 id 바꾸기·보관 상태·비밀 거부·독립."""

from __future__ import annotations

import pytest

from agent_console_contracts import ErrorCodes
from agent_console_contracts.memory import (
    MemoryAccessContext,
    MemoryCopyFilter,
    MemoryScopeRef,
    MemoryScopeRemap,
)
from agent_console_memory import (
    InMemoryMemoryStore,
    MemoryPolicy,
    MemorySecretGuard,
    SecretRulesScanner,
    copy_memory,
    merge_scope_kinds,
)
from agent_console_memory.testing import user_author

SECRET = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8" * 3
A = MemoryScopeRef(kind="team", id="g1")
B = MemoryScopeRef(kind="notes", id="")


def _source() -> InMemoryMemoryStore:
    store = InMemoryMemoryStore()
    store.write(A, "k1", "하나", author=user_author(), tags=["x"])
    store.write(A, "k2", "둘", author=user_author(), tags=["y"])
    entry = store.write(B, "k3", "셋", author=user_author()).entry
    store.archive(entry.id, author=user_author(), archived=True, if_version=entry.version)
    return store


def test_filter_and_archived_state() -> None:
    target = InMemoryMemoryStore()
    result = copy_memory(_source(), target, filter=MemoryCopyFilter(tags=["x", "nope"]))
    assert (result.copied, result.skipped, result.conflicts) == (1, 0, [])
    assert target.find(A, "k1") is not None
    assert target.find(A, "k2") is None
    everything = InMemoryMemoryStore()
    copy_memory(_source(), everything, filter=MemoryCopyFilter(scope_kinds=["notes"]))
    copied = everything.find(B, "k3")
    assert copied is not None
    assert copied.archived
    assert copy_memory(_source(), InMemoryMemoryStore(), include_archived=False).copied == 2


def test_remap_and_kind_limit() -> None:
    target = InMemoryMemoryStore()
    remap = [MemoryScopeRemap.model_validate({"from": "g1", "to": "g9", "kind": "team"})]
    copy_memory(_source(), target, remap=remap)
    assert target.find(MemoryScopeRef(kind="team", id="g9"), "k1") is not None
    assert target.find(A, "k1") is None
    assert target.find(B, "k3") is not None  # 다른 범위 종류는 그대로


@pytest.mark.parametrize(
    ("policy", "content", "copied", "new_key"),
    [("skip", "대상", 0, None), ("overwrite", "하나", 1, None), ("rename", "대상", 1, "k1 (2)")],
)
def test_conflicts(policy: str, content: str, copied: int, new_key: str | None) -> None:
    target = InMemoryMemoryStore()
    target.write(A, "k1", "대상", author=user_author())
    result = copy_memory(
        _source(),
        target,
        filter=MemoryCopyFilter(keys=["k1"]),
        on_conflict=policy,  # type: ignore[arg-type]
    )
    assert result.copied == copied
    [conflict] = result.conflicts
    assert (conflict.resolution, conflict.new_key) == (policy, new_key)
    found = target.find(A, "k1")
    assert found is not None
    assert found.content == content
    if new_key:
        assert target.find(A, new_key) is not None


def test_independent_after_copy() -> None:
    source, target = _source(), InMemoryMemoryStore()
    copy_memory(source, target)
    entry = source.find(A, "k1")
    assert entry is not None
    source.update(entry.id, author=user_author(), content="고침", if_version=entry.version)
    copied = target.find(A, "k1")
    assert copied is not None
    assert (copied.content, copied.version) == ("하나", 1)


class _Blind:
    """아무것도 찾지 않는 판정기(원본에 비밀 의심 값을 넣으려고)."""

    def find(self, text: str) -> list[str]:
        return []

    def redact(self, text: str) -> str:
        return text


def test_secret_rejected_by_target_policy_without_body() -> None:
    blind = InMemoryMemoryStore(policy=MemoryPolicy(secrets=MemorySecretGuard(_Blind())))
    blind.write(B, "s", f"값 {SECRET}", author=user_author())
    strict = InMemoryMemoryStore(
        policy=MemoryPolicy(secrets=MemorySecretGuard(SecretRulesScanner(), "reject"))
    )
    result = copy_memory(blind, strict)
    assert (result.copied, result.skipped) == (0, 1)
    assert [i.code for i in result.issues] == [ErrorCodes.MEMORY_SECRET_REJECTED]
    assert SECRET not in repr(result)


def test_unknown_policy() -> None:
    with pytest.raises(ValueError, match="on_conflict"):
        copy_memory(InMemoryMemoryStore(), InMemoryMemoryStore(), on_conflict="merge")  # type: ignore[arg-type]


def test_unresolvable_catalog_keeps_listing() -> None:
    catalog = merge_scope_kinds(
        include_defaults=False, user={"team": {"label": "팀", "id": "{/graph_id}"}}
    )
    blocked = catalog.unresolvable()
    assert blocked.listing().model_dump()["kinds"][0]["kind"] == "team"
    assert catalog.resolve("team", MemoryAccessContext(graph_id="g")) is not None
    assert blocked.resolve("team", MemoryAccessContext(graph_id="g")) is None
