"""예제 메모리 범위 종류 플러그인(X29): entry point 선언·범위 계산·설치/제거에 따른 목록 변화.

설치 없이 실행한다(pytest 설정 ``pythonpath = ["src"]``). "설치"는 임시 폴더에 이 패키지의
``*.dist-info``(METADATA·entry_points.txt)를 만드는 것으로 흉내 낸다.
"제거"는 그 dist-info를 지우는 것이다.

X29 그룹(``agent_console.memory_scope_kinds``)의 메타데이터 발견은 그 임시 폴더로만 격리한다
(``importlib.metadata.entry_points``를 그 그룹에 한해 바꾼다). 그래서 이 예제를 venv에 실제로 설치한
상태에서도, 설치하지 않은 상태에서도 결과가 같다. 다른 그룹(조건 연산자 등)은 설치된 대로 찾는다.
호스트 플러그인 로더(``mod-memory``의 ``load_plugins``)는 설치된 패키지와 똑같이 entry point와
배포 이름(``plugin:<배포 이름>``)을 얻는다.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import shutil
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_contracts.memory import MemoryAccessContext
from agent_console_example_memory_scope import (
    KIND_ID,
    iso_week_id,
    iso_week_scope_kind,
    scope_kinds,
)
from agent_console_memory import MEMORY_SCOPE_KINDS_GROUP, as_scope_kinds, merge_scope_kinds
from agent_console_mod_memory import MEMORY_SERVICE, module
from agent_console_mod_memory.plugins import load_plugins, scope_kind_registry
from agent_console_modkit import BaseServices, ExtensionRegistries, PluginLoadContext, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_store import SqliteDatabase

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
DIST_NAME = "agent-console-example-memory-scope"
EP_NAME = "example.memory_scope"
EP_VALUE = "agent_console_example_memory_scope:scope_kinds"
ORIGIN = f"plugin:{DIST_NAME}"
TOKEN = "t" * 32
API = "/api/v1"


@pytest.fixture(autouse=True)
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """빈 설치 위치. X29 그룹의 entry point는 이 폴더에서만 찾는다(실제 venv 설치와 무관)."""
    root = tmp_path / "site"
    root.mkdir()
    original = importlib.metadata.entry_points

    def isolated(**params: Any) -> importlib.metadata.EntryPoints:
        if params.get("group") != MEMORY_SCOPE_KINDS_GROUP:
            return original(**params)
        found = [
            ep
            for dist in importlib.metadata.distributions(path=[str(root)])
            for ep in dist.entry_points.select(**params)
        ]
        return importlib.metadata.EntryPoints(found)

    monkeypatch.setattr(importlib.metadata, "entry_points", isolated)
    return root


@pytest.fixture
def database(tmp_path: Path) -> Iterator[SqliteDatabase]:
    """재시작 사이에 남는 DB(제거 뒤 이미 쓴 항목 확인용)."""
    db = SqliteDatabase.open(tmp_path / "console.sqlite3")
    yield db
    db.close()


def _install(site: Path) -> Path:
    dist_info = site / "agent_console_example_memory_scope-0.1.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {DIST_NAME}\nVersion: 0.1.0\n", encoding="utf-8"
    )
    (dist_info / "entry_points.txt").write_text(
        f"[{MEMORY_SCOPE_KINDS_GROUP}]\n{EP_NAME} = {EP_VALUE}\n", encoding="utf-8"
    )
    importlib.invalidate_caches()
    return dist_info


def _uninstall(dist_info: Path) -> None:
    shutil.rmtree(dist_info)
    importlib.invalidate_caches()


@contextmanager
def _server(
    database: SqliteDatabase, *, enabled: frozenset[str] | None = None
) -> Iterator[tuple[TestClient, Any]]:
    """서버 시작과 같은 순서: 호스트 플러그인 로더 → 모듈 조립 → 앱. (클라이언트, 메모리 서비스)."""
    registries = ExtensionRegistries()
    load_plugins(PluginLoadContext(registries=registries, enabled=enabled))
    assembly = assemble([module], None, base=BaseServices(database=database, registries=registries))
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly.port(MEMORY_SERVICE)


def _listed(client: TestClient) -> dict[str, Any]:
    response = client.get(f"{API}/memory/scope-kinds")
    assert response.status_code == 200
    return {row["kind"]: row for row in response.json()["kinds"]}


def _this_week() -> set[str]:
    """지금 주차(경계에서 테스트가 흔들리지 않게 앞뒤 1분의 주차를 모두 허용)."""
    now = datetime.now(UTC)
    return {iso_week_id(now - timedelta(minutes=1)), iso_week_id(now + timedelta(minutes=1))}


def test_entry_point_declared() -> None:
    eps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["entry-points"]
    assert eps[MEMORY_SCOPE_KINDS_GROUP] == {EP_NAME: EP_VALUE}


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 28), "2026-W44"),
        (date(2026, 1, 1), "2026-W01"),  # 목요일: 그해 첫 주
        (date(2025, 12, 29), "2026-W01"),  # 월요일이지만 ISO 주차 연도는 2026
        (date(2027, 1, 1), "2026-W53"),  # 금요일: 앞 해의 마지막 주
        (date(2021, 1, 3), "2020-W53"),
    ],
)
def test_iso_week_id(day: date, expected: str) -> None:
    assert iso_week_id(day) == expected


def test_resolver_uses_injected_clock_and_ignores_context() -> None:
    kind = iso_week_scope_kind(lambda: datetime(2026, 10, 28, 12, tzinfo=UTC))
    assert kind.template is None
    assert kind.resolve(MemoryAccessContext()) == "2026-W44"
    assert kind.resolve(MemoryAccessContext(project_id="p", graph_id="g")) == "2026-W44"
    # 지역 시간대 주차: 시계가 그 시간대 시각을 주면 그 날짜로 계산한다.
    seoul = timezone(timedelta(hours=9))
    sunday_night_utc = datetime(2026, 11, 1, 20, tzinfo=UTC)  # 서울은 월요일 05시
    assert iso_week_scope_kind(lambda: sunday_night_utc).resolve(MemoryAccessContext()) == (
        "2026-W44"
    )
    assert iso_week_scope_kind(lambda: sunday_night_utc.astimezone(seoul)).resolve(
        MemoryAccessContext()
    ) == ("2026-W45")


def test_plugin_shape_passes_loader_check() -> None:
    loaded = as_scope_kinds(scope_kinds, origin=ORIGIN)
    assert [(k.id, k.origin) for k in loaded] == [(KIND_ID, ORIGIN)]
    catalog = merge_scope_kinds(include_defaults=False, plugins=loaded)
    info = catalog.listing().kinds[0]
    assert (info.kind, info.id, info.context_fields) == (KIND_ID, None, [])


def test_install_lists_plugin_kind_resolves_it_and_uninstall_removes_it(
    site: Path, database: SqliteDatabase
) -> None:
    with _server(database) as (client, _service):
        assert KIND_ID not in _listed(client)  # 설치 전

    dist_info = _install(site)
    with _server(database) as (client, service):
        row = _listed(client)[KIND_ID]
        assert row["origin"] == ORIGIN
        assert row.get("disabled") is not True
        assert row.get("id") is None  # 계산 범위 종류: 틀 없음
        # 범위 id가 실제로 계산된다(서버가 병합한 목록에서, 맥락과 무관하게 지금 주차).
        scope = service.catalog().resolve(KIND_ID, MemoryAccessContext(project_id="p1"))
        assert scope is not None
        assert scope.kind == KIND_ID
        assert scope.id in _this_week()
        created = client.post(
            f"{API}/memory/entries",
            json={"scope": scope.model_dump(), "key": "k", "content": "본문"},
        )
        assert created.status_code == 201, created.text
        scopes = client.get(f"{API}/memory/scopes").json()
        assert [(s["scope"]["kind"], s["kind_known"]) for s in scopes] == [(KIND_ID, True)]

    _uninstall(dist_info)
    with _server(database) as (client, service):
        assert KIND_ID not in _listed(client)  # 제거 후(재시작)
        assert service.catalog().resolve(KIND_ID, MemoryAccessContext()) is None
        scopes = client.get(f"{API}/memory/scopes").json()
        assert [(s["scope"]["kind"], s["kind_known"]) for s in scopes] == [(KIND_ID, False)]


def test_turn_off_while_installed(site: Path, database: SqliteDatabase) -> None:
    _install(site)
    with _server(database, enabled=frozenset({"something-else"})) as (client, _service):
        assert KIND_ID not in _listed(client)
    registries = ExtensionRegistries()
    reports = load_plugins(PluginLoadContext(registries=registries, enabled=frozenset({EP_NAME})))
    assert [r.status for _group, r in reports if r.key == EP_NAME] == ["loaded"]
    assert [k.origin for k in scope_kind_registry(registries).get(EP_NAME)] == [ORIGIN]
