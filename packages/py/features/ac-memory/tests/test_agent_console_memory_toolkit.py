"""도구 묶음: 스펙·이름 바꾸기·사유 코드·이벤트 payload(본문·검색어 없음)·동시 쓰기."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Any

import pytest

from agent_console_contracts.memory import (
    KNOWN_MEMORY_EVENT_TYPES,
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryEventPayload,
    MemoryScopeRef,
)
from agent_console_memory import (
    InMemoryMemoryStore,
    MemoryLimits,
    MemoryPolicy,
    MemoryToolkit,
    WriteBudget,
    load_tool_text,
    merge_scope_kinds,
)
from agent_console_memory.testing import FakeClock, sample_context, sample_scope_kinds

KINDS = ("everyone", "per-project", "per-graph")
SECRET = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8" * 3
BODY = "결정: API 버전은 v2로 고정한다. 참고 문서 링크 포함."
QUERY = "고정한다"


def _access(**ops: list[str]) -> MemoryAccessConfig:
    return MemoryAccessConfig.model_validate(
        {"scopes": [{"kind": k, "access": v} for k, v in ops.items()]}
    )


def _full_access() -> MemoryAccessConfig:
    return MemoryAccessConfig.model_validate(
        {
            "scopes": [
                {"kind": "per-graph", "access": ["read", "search", "write"]},
                {"kind": "per-project", "access": ["read", "search"]},
                {"kind": "everyone", "access": ["read", "search", "write", "delete"]},
            ],
            "default_scope": "per-graph",
        }
    )


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, MemoryEventPayload]] = []

    async def __call__(self, event_type: str, payload: MemoryEventPayload) -> None:
        self.events.append((event_type, payload))


def _kit(
    *,
    access: MemoryAccessConfig | None = None,
    context: MemoryAccessContext | None = None,
    store: InMemoryMemoryStore | None = None,
    names: tuple[str, str, str] = KINDS,
    **kwargs: Any,
) -> tuple[MemoryToolkit, InMemoryMemoryStore, Recorder]:
    store = store or InMemoryMemoryStore(clock=FakeClock())
    recorder = Recorder()
    catalog = merge_scope_kinds(defaults=sample_scope_kinds(names))
    kit = MemoryToolkit(
        store,
        access=access or _full_access(),
        context=context or sample_context(),
        catalog=catalog,
        on_event=recorder,
        **kwargs,
    )
    return kit, store, recorder


def _spec(kit: MemoryToolkit, op: str) -> Any:
    return next(s for s in kit.specs() if s.op == op)


async def test_specs_follow_access_and_default_names() -> None:
    kit, _, _ = _kit()
    specs = kit.specs()
    assert [s.op for s in specs] == ["read", "search", "write", "delete"]
    assert [s.name for s in specs] == [
        "memory_read",
        "memory_search",
        "memory_write",
        "memory_delete",
    ]
    write = _spec(kit, "write")
    assert write.input_schema["required"] == ["key", "content"]
    assert write.input_schema["properties"]["scope"]["enum"] == ["per-graph", "everyone"]
    assert "per-graph(per-graph label)" in write.input_schema["properties"]["scope"]["description"]
    read_only, _, _ = _kit(access=_access(**{"per-graph": ["read"]}))
    assert [s.op for s in read_only.specs()] == ["read"]
    nothing, _, _ = _kit(access=MemoryAccessConfig())
    assert nothing.specs() == []


async def test_tool_names_are_data() -> None:
    access = _full_access().model_copy(deep=True)
    access.tools.write.name = "notes_put"
    access.tools.read.name = "notes_get"
    kit, _, recorder = _kit(access=access)
    names = {s.op: s.name for s in kit.specs()}
    assert names["write"] == "notes_put"
    assert names["read"] == "notes_get"
    await _spec(kit, "write").call({"key": "a", "content": "x"}, "tu-1")
    assert recorder.events[0][1].tool == "notes_put"
    assert recorder.events[0][1].tool_use_id == "tu-1"


async def test_write_read_search_delete_round_trip() -> None:
    kit, store, recorder = _kit()
    out = await kit.call("write", {"key": "결정/api", "content": BODY, "tags": ["t"]}, "c1")
    assert not out.is_error
    assert out.code is None
    read = await kit.call("read", {"key": "결정/api"}, "c2")
    assert not read.is_error
    header, body = read.text.split("\n", 1)
    assert body == BODY
    assert "per-graph label:결정/api" in header
    assert "v1" in header
    assert "agent:agent-a" in header
    entry = store.find(MemoryScopeRef(kind="per-graph", id="g1"), "결정/api")
    assert entry is not None
    assert entry.last_read_at is not None
    assert entry.created_by.run_id == "run-1"
    assert entry.created_by.graph_id == "g1"
    search = await kit.call("search", {"query": QUERY}, "c3")
    assert "결정/api" in search.text
    assert recorder.events[-1][1].results == 1
    recent = await kit.call("search", {}, "c4")
    assert "결정/api" in recent.text
    denied = await kit.call("delete", {"key": "결정/api"}, "c5")
    assert denied.is_error
    assert denied.code == "memory.denied"
    await kit.call("write", {"key": "x", "content": "y", "scope": "everyone"})
    gone = await kit.call("delete", {"key": "x", "scope": "everyone"})
    assert not gone.is_error
    assert store.find(MemoryScopeRef(kind="everyone", id=""), "x") is None
    assert [t for t, _ in recorder.events] == [
        "memory.write",
        "memory.read",
        "memory.search",
        "memory.search",
        "memory.delete",
        "memory.write",
        "memory.delete",
    ]
    assert {t for t, _ in recorder.events} <= set(KNOWN_MEMORY_EVENT_TYPES)


async def test_event_payload_has_no_content_or_query() -> None:
    kit, _, recorder = _kit()
    await kit.call("write", {"key": "k", "content": BODY})
    await kit.call("read", {"key": "k"})
    await kit.call("search", {"query": QUERY})
    for _type, payload in recorder.events:
        dumped = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        assert BODY not in dumped
        assert QUERY not in dumped
        assert set(payload.model_dump(exclude_none=True)) <= set(MemoryEventPayload.model_fields)
    write, read, search = (p for _t, p in recorder.events)
    assert write.bytes == len(BODY.encode())
    assert write.sha256
    assert write.version == 1
    assert read.sha256 == write.sha256
    assert read.entry_id == write.entry_id
    assert search.query_chars == len(QUERY)
    assert search.query_sha256
    assert search.results == 1
    assert all(p.duration_ms is not None and p.status == "ok" for _t, p in recorder.events)


async def test_reason_codes() -> None:
    kit, _, recorder = _kit(context=sample_context(project_id=""))
    assert (await kit.call("read", {"key": "nope"})).code == "memory.not_found"
    unavailable = await kit.call("read", {"key": "k", "scope": "per-project"})
    assert unavailable.code == "memory.scope_unavailable"
    assert (await kit.call("write", {"key": "k", "content": "x", "scope": "per-project"})).code == (
        "memory.denied"
    )
    assert (await kit.call("write", {"key": "a/../b", "content": "x"})).code == "memory.invalid_key"
    assert (await kit.call("write", {"key": "k"})).code == "error"  # content 빠짐
    assert (await kit.call("read", {"key": "k", "scope": "unknown-kind"})).code == "memory.denied"
    await kit.call("write", {"key": "k", "content": "a"})
    conflict = await kit.call("write", {"key": "k", "content": "b", "if_version": 9})
    assert conflict.code == "memory.conflict"
    assert "v1" in conflict.text
    assert recorder.events[-1][1].version == 1
    assert recorder.events[-1][1].status == "conflict"
    statuses = [p.status for _t, p in recorder.events]
    assert statuses[:5] == ["not_found", "scope_unavailable", "denied", "error", "error"]
    assert all(out.startswith("[") for out in [conflict.text])


async def test_too_large_and_secret_rejected_do_not_leak() -> None:
    store = InMemoryMemoryStore(
        policy=MemoryPolicy(limits=replace(MemoryLimits(), max_entry_bytes=16))
    )
    kit, _, recorder = _kit(store=store)
    big = await kit.call("write", {"key": "k", "content": "x" * 17})
    assert big.code == "memory.too_large"
    assert "max_entry_bytes" in big.text
    secret = await kit.call("write", {"key": "k", "content": SECRET})
    assert secret.is_error
    assert secret.code == "memory.secret_rejected"
    assert SECRET not in secret.text
    assert SECRET not in json.dumps([p.model_dump(mode="json") for _t, p in recorder.events])
    assert recorder.events[-1][1].status == "secret_rejected"


async def test_unknown_scope_kind_in_catalog_is_unavailable() -> None:
    access = _access(**{"removed-kind": ["read"]})
    kit, _, _ = _kit(access=access)
    assert (await kit.call("read", {"key": "k"})).code == "memory.scope_unavailable"


async def test_archived_entries_are_hidden_from_tools() -> None:
    kit, store, _ = _kit()
    await kit.call("write", {"key": "k", "content": "a"})
    entry = store.find(MemoryScopeRef(kind="per-graph", id="g1"), "k")
    assert entry is not None
    store.archive(entry.id, author=entry.created_by)
    assert (await kit.call("read", {"key": "k"})).code == "memory.not_found"
    assert (await kit.call("search", {})).text == load_tool_text().search_empty


async def test_write_budget_rate_limits() -> None:
    budget = WriteBudget(2)
    kit, _, recorder = _kit(write_budget=budget)
    other, _, _ = _kit(write_budget=budget, store=kit.store)  # type: ignore[arg-type]
    assert not (await kit.call("write", {"key": "a", "content": "1"})).is_error
    assert not (await other.call("write", {"key": "b", "content": "1"})).is_error
    limited = await kit.call("write", {"key": "c", "content": "1"})
    assert limited.code == "memory.rate_limited"
    assert recorder.events[-1][1].status == "rate_limited"


async def test_result_is_truncated() -> None:
    access = _full_access().model_copy(update={"max_result_chars": 60})
    kit, _, _ = _kit(access=access)
    await kit.call("write", {"key": "k", "content": "y" * 500})
    out = await kit.call("read", {"key": "k"})
    assert len(out.text) == 60
    assert out.text.endswith("60자)")


async def test_append_mode_and_mode_validation() -> None:
    kit, store, _ = _kit()
    await kit.call("write", {"key": "log", "content": "a", "mode": "append"})
    await kit.call("write", {"key": "log", "content": "b", "mode": "append"})
    entry = store.find(MemoryScopeRef(kind="per-graph", id="g1"), "log")
    assert entry is not None
    assert entry.content == "a\nb"
    assert (await kit.call("write", {"key": "log", "content": "c", "mode": "x"})).code == "error"


async def test_parallel_tool_writes_are_serialized() -> None:
    kit, store, recorder = _kit()
    n = 30
    outs = await asyncio.gather(
        *(kit.call("write", {"key": "shared/k", "content": f"v{i}"}, f"c{i}") for i in range(n))
    )
    assert not any(o.is_error for o in outs)
    versions = sorted(p.version or 0 for _t, p in recorder.events)
    assert versions == list(range(1, n + 1))
    entry = store.find(MemoryScopeRef(kind="per-graph", id="g1"), "shared/k")
    assert entry is not None
    assert entry.version == n
    assert [v.version for v in store.history(entry.id)] == list(range(1, n + 1))


async def test_parallel_if_version_writes_one_wins() -> None:
    kit, _, _ = _kit()
    await kit.call("write", {"key": "k", "content": "base"})
    outs = await asyncio.gather(
        *(kit.call("write", {"key": "k", "content": f"v{i}", "if_version": 1}) for i in range(10))
    )
    assert sum(1 for o in outs if not o.is_error) == 1
    assert sum(1 for o in outs if o.code == "memory.conflict") == 9


async def test_sync_event_sink_and_unknown_op() -> None:
    seen: list[str] = []
    store = InMemoryMemoryStore()
    kit = MemoryToolkit(
        store,
        access=_full_access(),
        context=sample_context(),
        catalog=merge_scope_kinds(defaults=sample_scope_kinds(KINDS)),
        on_event=lambda t, _p: seen.append(t),
    )
    await kit.call("search", {})
    assert seen == ["memory.search"]
    with pytest.raises(ValueError, match="모르는 동작"):
        await kit.call("explode", {})
