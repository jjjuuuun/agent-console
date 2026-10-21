"""모듈 하나 끄기 매트릭스(modularity §3.8-2, 3R.16).

설치된 선택 모듈 전부(entry point — 기능·연동 모듈) M에 대해 `modules.disabled: [M]`로
서버를 띄우면:

(a) 시작에 성공한다(`/health` 200),
(b) `/modules`에 M = `disabled`, M이 주던 포트가 없어 필수 포트가 빠지는 모듈(연쇄 포함) =
    `unsatisfied`(빠진 포트 이름이 이유에 있다), 나머지는 `active`,
(c) 나머지 켜진 모듈의 API가 돈다(매개변수 없는 GET 경로 전부가 404·5xx가 아니다),
(d) M의 경로는 404다(M만 가진 경로 — 같은 경로를 켜진 모듈이 가지면 건너뛴다).

모듈 목록·포트·경로는 설치된 모듈과 조립 결과에서 읽는다(테스트에 고정 목록 없음).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute

from agent_console_modkit import Module
from agent_console_server import create_app, installed_modules
from agent_console_server.testing import API, TEST_TOKEN, make_settings, server

MODULES: list[Module] = installed_modules()
MODULE_IDS: list[str] = sorted(m.descriptor.id for m in MODULES)
PARAM = re.compile(r"\{[^}]+\}")


@dataclass(frozen=True)
class Route:
    method: str
    path: str  # API 접두 뒤

    @property
    def has_params(self) -> bool:
        return bool(PARAM.search(self.path))

    def concrete(self) -> str:
        return PARAM.sub("matrix-missing", self.path)

    def matches(self, path: str) -> bool:
        """이 경로 패턴이 ``path``에 맞는가(매개변수는 한 구간)."""
        parts = PARAM.split(self.path)
        pattern = "[^/]+".join(re.escape(p) for p in parts)
        return re.fullmatch(pattern, path) is not None


def _routes_of(parts: Any) -> set[Route]:
    found: set[Route] = set()
    for router in parts.routers:
        for route in router.routes:
            if isinstance(route, APIRoute):
                for method in route.methods or ():
                    found.add(Route(method, route.path))
    return found


@pytest.fixture(scope="module")
def reference(tmp_path_factory: pytest.TempPathFactory) -> dict[str, set[Route]]:
    """모든 모듈을 켠 조립에서 모듈 id → 경로."""
    settings = make_settings(tmp_path_factory.mktemp("reference"))
    app = create_app(settings, environ={}, token=TEST_TOKEN)
    assembly = app.state.assembly
    assert {r.id for r in assembly.report if r.active} == set(MODULE_IDS)
    return {mid: _routes_of(parts) for mid, parts in assembly.parts.items()}


def _expected_unsatisfied(disabled: str) -> dict[str, set[str]]:
    """M을 끈 뒤 필수 포트가 빠지는 모듈(연쇄) → 빠진 포트 이름."""
    by_id = {m.descriptor.id: m.descriptor for m in MODULES}
    on = set(by_id) - {disabled}
    missing: dict[str, set[str]] = {}
    while True:
        provided = {p.name for mid in on for p in by_id[mid].provides}
        newly = {mid: {p.name for p in by_id[mid].requires if p.name not in provided} for mid in on}
        newly = {mid: ports for mid, ports in newly.items() if ports}
        if not newly:
            return missing
        missing.update(newly)
        on -= set(newly)


def _get_routes(routes: Iterable[Route]) -> list[Route]:
    return sorted((r for r in routes if r.method == "GET" and not r.has_params), key=str)


def test_matrix_covers_feature_and_link_modules() -> None:
    kinds = {m.descriptor.kind for m in MODULES}
    assert {"feature", "link"} <= kinds
    assert len(MODULE_IDS) == len(set(MODULE_IDS))


@pytest.mark.parametrize("module_id", MODULE_IDS)
def test_disable_one_module(
    tmp_path: Path, module_id: str, reference: dict[str, set[Route]]
) -> None:
    expected_off = _expected_unsatisfied(module_id)
    settings = make_settings(tmp_path, modules={"disabled": [module_id]})
    with server(settings) as client:
        # (a) 시작 성공
        assert client.get(f"{API}/health").status_code == 200
        assert client.get(f"{API}/server-info").status_code == 200
        # (b) 상태
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert set(infos) == set(MODULE_IDS)
        assert infos[module_id]["status"] == "disabled"
        for mid, info in infos.items():
            if mid == module_id:
                continue
            if mid in expected_off:
                assert info["status"] == "unsatisfied", info
                for port in expected_off[mid]:
                    assert port in (info["reason"] or ""), info
            else:
                assert info["status"] == "active", info
        active = {mid for mid, info in infos.items() if info["status"] == "active"}
        active_routes = {r for mid in active for r in reference[mid]}
        # (c) 나머지 API
        for route in _get_routes(active_routes):
            res = client.get(f"{API}{route.path}")
            assert res.status_code != 404, (route, res.text[:200])
            assert res.status_code < 500, (route, res.text[:200])
        # (d) 꺼진 모듈만 가진 경로는 404
        active_patterns = {(r.method, r.path) for r in active_routes}
        for route in sorted(reference[module_id], key=str):
            if (route.method, route.path) in active_patterns:
                continue
            res = client.request(route.method, f"{API}{route.concrete()}")
            assert res.status_code in (404, 405), (route, res.status_code, res.text[:200])
            if res.status_code == 405:  # 켜진 모듈의 경로 패턴이 맞지만 메서드가 다르다
                assert any(r.matches(route.concrete()) for r in active_routes), route


def test_all_modules_on_every_get_route_responds(
    tmp_path: Path, reference: dict[str, set[Route]]
) -> None:
    """기본 설정(전부 켬)에서 매개변수 없는 GET 경로가 모두 돈다(개인 모드 동작 불변의 바닥)."""
    with server(make_settings(tmp_path)) as client:
        for route in _get_routes(r for routes in reference.values() for r in routes):
            res = client.get(f"{API}{route.path}")
            assert res.status_code < 400 or res.status_code in (409, 422), (route, res.text[:200])
