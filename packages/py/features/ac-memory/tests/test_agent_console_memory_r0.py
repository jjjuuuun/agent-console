"""R0: 범위 종류·도구 이름은 데이터다. 이름을 모두 바꾼 데이터로도 같은 결과, 코드에 이름이 없다."""

from __future__ import annotations

import ast
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from agent_console_contracts.memory import MemoryAccessConfig, memory_access_defaults
from agent_console_memory import (
    InMemoryMemoryStore,
    MemoryToolkit,
    ScopeKindCatalog,
    load_default_scope_kinds,
    merge_scope_kinds,
)
from agent_console_memory.testing import FakeClock, sample_context, sample_scope_kinds

SRC = Path(str(files("agent_console_memory")))


def _access(everyone: str, per_project: str, per_graph: str) -> MemoryAccessConfig:
    return MemoryAccessConfig.model_validate(
        {
            "scopes": [
                {"kind": per_graph, "access": ["read", "search", "write"]},
                {"kind": per_project, "access": ["read", "search"]},
                {"kind": everyone, "access": ["read", "search", "write", "delete"]},
            ],
            "default_scope": per_graph,
        }
    )


async def _scenario(catalog: ScopeKindCatalog, names: tuple[str, str, str]) -> list[Any]:
    """두 에이전트·두 실행에 걸친 시나리오. 결과에서 범위 종류 이름·라벨을 빼고 모양만 남긴다."""
    everyone, per_project, per_graph = names
    store = InMemoryMemoryStore(clock=FakeClock(step=1.0))
    access = _access(everyone, per_project, per_graph)
    agent_a = MemoryToolkit(store, access=access, context=sample_context(), catalog=catalog)
    agent_b = MemoryToolkit(
        store,
        access=access,
        context=sample_context(agent_id="agent-b", run_id="run-2", project_id=""),
        catalog=catalog,
    )
    other_graph = MemoryToolkit(
        store, access=access, context=sample_context(graph_id="g2"), catalog=catalog
    )
    calls: list[tuple[MemoryToolkit, str, dict[str, Any]]] = [
        (agent_a, "write", {"key": "결정/api", "content": "v2"}),
        (agent_a, "write", {"key": "공지", "content": "all", "scope": everyone}),
        (agent_b, "search", {"query": "v2"}),
        (agent_b, "read", {"key": "결정/api"}),
        (agent_b, "read", {"key": "x", "scope": per_project}),  # 프로젝트 없음
        (agent_b, "write", {"key": "y", "content": "z", "scope": per_project}),  # 권한 없음
        (agent_b, "write", {"key": "결정/api", "content": "v3", "if_version": 1}),
        (agent_b, "write", {"key": "결정/api", "content": "v4", "if_version": 1}),  # 충돌
        (other_graph, "read", {"key": "결정/api"}),  # 다른 팀 구성 범위
        (other_graph, "read", {"key": "공지", "scope": everyone}),
        (agent_b, "delete", {"key": "공지", "scope": everyone}),
        (agent_b, "delete", {"key": "결정/api"}),  # 권한 없음
    ]
    shapes: list[Any] = []
    for kit, op, args in calls:
        out = await kit.call(op, args)
        ev = out.event
        shapes.append(
            (
                op,
                out.is_error,
                out.code,
                ev.status,
                ev.version,
                ev.results,
                ev.bytes,
                ev.scope.id if ev.scope else None,
                ev.key,
            )
        )
    shapes.append(sorted((s.scope.id, s.entries) for s in store.list_scopes()))
    return shapes


async def test_renamed_scope_kinds_give_same_results() -> None:
    default_names = tuple(load_default_scope_kinds())
    assert len(default_names) == 3
    everyone, per_project, per_graph = _by_template(default_names)
    baseline = await _scenario(merge_scope_kinds(), (everyone, per_project, per_graph))
    renamed = ("notes", "journal", "board")
    other = await _scenario(
        merge_scope_kinds(include_defaults=False, user=sample_scope_kinds(renamed)), renamed
    )
    assert baseline == other
    statuses = [row[3] for row in baseline[:-1]]
    assert statuses == [
        "ok",
        "ok",
        "ok",
        "ok",
        "scope_unavailable",
        "denied",
        "ok",
        "conflict",
        "not_found",
        "ok",
        "ok",
        "denied",
    ]


def _by_template(names: tuple[str, ...]) -> tuple[str, str, str]:
    """기본 데이터의 범위 종류를 틀 모양(공용·프로젝트·팀 구성)으로 고른다(이름을 쓰지 않는다)."""
    defaults = load_default_scope_kinds()
    pick = {spec.id: name for name, spec in defaults.items() if name in names}
    return pick[""], pick["{/project_id}"], pick["{/graph_id}"]


async def test_scope_kinds_turned_off_gives_no_scope() -> None:
    catalog = merge_scope_kinds(include_defaults=False)
    names = _by_template(tuple(load_default_scope_kinds()))
    kit = MemoryToolkit(
        InMemoryMemoryStore(), access=_access(*names), context=sample_context(), catalog=catalog
    )
    out = await kit.call("write", {"key": "k", "content": "x"})
    assert out.code == "memory.scope_unavailable"


def _literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_no_hardcoded_scope_kind_or_tool_names_in_code() -> None:
    defaults = load_default_scope_kinds()
    forbidden = set(defaults) | {spec.label for spec in defaults.values()}
    forbidden |= {tool["name"] for tool in memory_access_defaults()["tools"].values()}
    sources = [p for p in SRC.rglob("*.py") if "testing" not in p.parts]
    assert sources
    found = {str(p.relative_to(SRC)): _literals(p) & forbidden for p in sources}
    assert {k: v for k, v in found.items() if v} == {}


def test_no_runtime_nodes_or_logs_imports() -> None:
    banned = ("agent_console_runtime", "agent_console_nodes_core", "agent_console_logs")
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            for name in names:
                assert not name.startswith(banned), f"{path.name}: {name}"


def test_default_data_is_json_safe() -> None:
    data = {k: v.model_dump() for k, v in load_default_scope_kinds().items()}
    assert json.loads(json.dumps(data)) == data
