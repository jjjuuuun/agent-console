"""mod-memory 공간(5.7R.33z, design §PI.4.3): 선택 포트 memory.spaces·REST ?project=·공간 사이 복사·
맥락 바꾸기·오류 코드. 공간 제공자는 테스트 안의 가짜(프로세스 메모리 저장소)다."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import ErrorCodes
from agent_console_contracts.memory import (
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryScopeRef,
)
from agent_console_memory import InMemoryMemoryStore, MemoryStore
from agent_console_mod_memory import (
    BRANCH,
    MEMORY_DB_SCOPE,
    MEMORY_SERVICE,
    MEMORY_SPACES,
    MemoryService,
    MemorySpacesUnavailable,
)
from agent_console_modkit import Assembly, Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_store import SqliteDatabase

API = "/api/v1"
NOTES = {"kind": "notes", "id": "p1"}

SETTINGS = {
    "memory": {
        "include_default_scope_kinds": False,
        "scope_kinds": {
            "notes": {"label": "노트", "id": "{/project_id}"},
            "shared": {"label": "공용", "id": ""},
        },
    }
}


@dataclass
class _Space:
    store: MemoryStore
    context: Mapping[str, str] = field(default_factory=dict)


class _Error(Exception):
    code = ErrorCodes.PROJECT_FOLDER_MISSING


@dataclass
class _Spaces:
    spaces: dict[str, _Space]
    opened: list[str] = field(default_factory=list)

    def open(self, space: str) -> _Space:
        self.opened.append(space)
        if space == "gone":
            raise _Error("폴더 없음")
        return self.spaces[space]


def _spaces_module(spaces: _Spaces) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(MEMORY_SPACES, spaces)
        return ModuleParts()

    return fake_module("memory-spaces", provides=(MEMORY_SPACES,), on_build=build)


def _setup(
    make_assembly: Callable[..., Assembly], database: SqliteDatabase
) -> tuple[Assembly, _Spaces]:
    spaces = _Spaces({"a": _Space(InMemoryMemoryStore(), {"project_id": "folder-a"})})
    assembly = make_assembly(database=database, settings=SETTINGS, extra=[_spaces_module(spaces)])
    return assembly, spaces


def test_branch_declares_memory_db_scope() -> None:
    assert BRANCH.scopes == ("app", MEMORY_DB_SCOPE)


def test_project_query_routes_to_space_store(
    make_assembly: Callable[..., Assembly],
    client_of: Callable[[Assembly], TestClient],
    database: SqliteDatabase,
) -> None:
    assembly, spaces = _setup(make_assembly, database)
    store = spaces.spaces["a"].store
    with client_of(assembly) as client:
        body = {"scope": NOTES, "key": "k", "content": "x"}
        created = client.post(f"{API}/memory/entries?project=a", json=body)
        assert created.status_code == 201, created.text
        assert store.find(MemoryScopeRef(**NOTES), "k") is not None
        assert client.get(f"{API}/memory/entries").json()["items"] == []
        assert len(client.get(f"{API}/memory/entries?project=a").json()["items"]) == 1
        scopes = client.get(f"{API}/memory/scopes?project=a").json()
        assert [s["scope"] for s in scopes] == [NOTES]
        tags = client.get(f"{API}/memory/tags?project=a")
        assert tags.status_code == 200
        entry = created.json()
        versions = client.get(f"{API}/memory/entries/{entry['id']}/versions?project=a")
        assert versions.status_code == 200
        exported = client.get(f"{API}/memory/export?project=a")
        assert exported.status_code == 200
        imported = client.post(
            f"{API}/memory/import?policy=rename&project=a",
            content=exported.content,
            headers={"Content-Type": "application/zip"},
        )
        assert imported.json()["renamed"] == 1
        assert client.get(f"{API}/memory/entries").json()["items"] == []  # 라이브러리 그대로
        # 모르는 공간 404, 제공자 오류 코드는 그대로
        unknown = client.get(f"{API}/memory/entries?project=zzz")
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == ErrorCodes.PROJECT_NOT_FOUND
        gone = client.get(f"{API}/memory/entries?project=gone")
        assert gone.status_code == 409
        assert gone.json()["error"]["code"] == ErrorCodes.PROJECT_FOLDER_MISSING
        assert gone.json()["error"]["details"] == {"project_id": "gone"}


def test_no_provider_project_query_is_feature_unavailable(
    make_assembly: Callable[..., Assembly],
    client_of: Callable[[Assembly], TestClient],
    database: SqliteDatabase,
) -> None:
    assembly = make_assembly(database=database, settings=SETTINGS)
    with client_of(assembly) as client:
        for path in ("/memory/entries", "/memory/scope-kinds", "/memory/scopes"):
            res = client.get(f"{API}{path}?project=a")
            assert res.status_code == 409, path
            assert res.json()["error"]["code"] == ErrorCodes.FEATURE_UNAVAILABLE
        assert client.get(f"{API}/memory/entries").status_code == 200
    service = assembly.port(MEMORY_SERVICE)
    assert isinstance(service, MemoryService)
    assert service.space(None) is service
    with pytest.raises(MemorySpacesUnavailable) as caught:
        service.space("a")
    assert caught.value.code == ErrorCodes.FEATURE_UNAVAILABLE


def test_scope_kinds_same_in_space_with_context_fields(
    make_assembly: Callable[..., Assembly],
    client_of: Callable[[Assembly], TestClient],
    database: SqliteDatabase,
) -> None:
    assembly, _spaces = _setup(make_assembly, database)
    with client_of(assembly) as client:
        library = client.get(f"{API}/memory/scope-kinds").json()
        space = client.get(f"{API}/memory/scope-kinds?project=a").json()
    assert library == space
    assert {k["kind"]: k["context_fields"] for k in space["kinds"]} == {
        "notes": ["project_id"],
        "shared": [],
    }


def test_space_toolkit_overrides_context(
    make_assembly: Callable[..., Assembly], database: SqliteDatabase
) -> None:
    assembly, spaces = _setup(make_assembly, database)
    service = assembly.port(MEMORY_SERVICE)
    assert isinstance(service, MemoryService)
    space = service.space("a")
    assert service.space("a") is space  # 같은 저장소면 같은 서비스
    assert space.space(None) is service  # 공간 서비스에서도 라이브러리로 돌아간다
    access = MemoryAccessConfig.model_validate({"scopes": [{"kind": "notes", "access": ["write"]}]})
    toolkit = space.toolkit(access, MemoryAccessContext(project_id="reg-a"))
    outcome = asyncio.run(toolkit.call("write", {"key": "k", "content": "x"}))
    assert not outcome.is_error, outcome.text
    store = spaces.spaces["a"].store
    assert store.find(MemoryScopeRef(kind="notes", id="folder-a"), "k") is not None
    assert store.find(MemoryScopeRef(kind="notes", id="reg-a"), "k") is None


def test_copy_between_spaces(
    make_assembly: Callable[..., Assembly],
    client_of: Callable[[Assembly], TestClient],
    database: SqliteDatabase,
) -> None:
    assembly, spaces = _setup(make_assembly, database)
    project = spaces.spaces["a"].store
    with client_of(assembly) as client:
        for key, content, tags in (("k1", "하나", ["t"]), ("k2", "둘", [])):
            client.post(
                f"{API}/memory/entries",
                json={"scope": NOTES, "key": key, "content": content, "tags": tags},
            )
        client.post(
            f"{API}/memory/entries?project=a",
            json={"scope": NOTES, "key": "k1", "content": "프로젝트 것"},
        )
        base = {"source": {"project_id": None}, "target": {"project_id": "a"}}
        renamed = client.post(
            f"{API}/memory/copy", json={**base, "filter": {"tags": ["t"]}, "on_conflict": "rename"}
        ).json()
        assert renamed["copied"] == 1
        assert renamed["conflicts"] == [
            {"scope": NOTES, "key": "k1", "resolution": "rename", "new_key": "k1 (2)"}
        ]
        over = client.post(
            f"{API}/memory/copy",
            json={**base, "filter": {"keys": ["k1"]}, "on_conflict": "overwrite"},
        ).json()
        assert over["copied"] == 1
        found = project.find(MemoryScopeRef(**NOTES), "k1")
        assert found is not None
        assert found.content == "하나"
        assert found.version == 2
        # 프로젝트 → 라이브러리도 같은 경로
        back = client.post(
            f"{API}/memory/copy",
            json={"source": {"project_id": "a"}, "target": {"project_id": None}},
        ).json()
        assert (back["copied"], back["skipped"]) == (1, 1)  # k1 (2)만 새로, k1은 충돌 건너뜀
        bad = client.post(f"{API}/memory/copy", json={**base, "target": {"project_id": "zzz"}})
        assert bad.status_code == 404
