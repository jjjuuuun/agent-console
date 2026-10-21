"""3R.33 통합 검증: 모듈 하나만 켜기(modularity §3.8-3).

설치된 기능 모듈 M마다 `modules.enabled`를 {M + M의 필수 포트 제공자(연쇄)}로 좁혀 서버를 띄운다.
(a) 시작 성공, (b) M = active이고 나머지는 모두 disabled(필수 포트 제공자만 active),
(c) 켜진 모듈의 매개변수 없는 GET 경로가 404·5xx가 아니다.
모듈 목록·포트는 설치된 것에서 읽는다(고정 목록 없음).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from agent_console_modkit import Module
from agent_console_server import create_app, installed_modules
from agent_console_server.testing import API, TEST_TOKEN, make_settings, server

MODULES: list[Module] = installed_modules()
BY_ID = {m.descriptor.id: m.descriptor for m in MODULES}
FEATURE_IDS = sorted(i for i, d in BY_ID.items() if d.kind == "feature")


def _closure(module_id: str) -> set[str]:
    """M과, M(과 그 제공자들)의 필수 포트를 주는 모든 모듈."""
    keep = {module_id}
    todo = [module_id]
    while todo:
        need = {p.name for p in BY_ID[todo.pop()].requires}
        for mid, d in BY_ID.items():
            if mid not in keep and need & {p.name for p in d.provides}:
                keep.add(mid)
                todo.append(mid)
    return keep


def test_there_are_feature_modules_to_try() -> None:
    assert len(FEATURE_IDS) >= 2


@pytest.mark.parametrize("module_id", FEATURE_IDS)
def test_only_one_feature_module_on(tmp_path: Path, module_id: str) -> None:
    keep = _closure(module_id)
    settings = make_settings(tmp_path, modules={"enabled": sorted(keep)})
    app = create_app(settings, environ={}, token=TEST_TOKEN)
    routes: dict[str, set[str]] = {}
    for mid, parts in app.state.assembly.parts.items():
        routes[mid] = {
            r.path
            for router in parts.routers
            for r in router.routes
            if isinstance(r, APIRoute) and "GET" in (r.methods or ()) and "{" not in r.path
        }
    with server(settings) as client:
        assert client.get(f"{API}/health").status_code == 200
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert infos[module_id]["status"] == "active", infos[module_id]
        for mid, info in infos.items():
            if mid in keep:
                assert info["status"] == "active", info
            else:
                assert info["status"] == "disabled", info
        for mid in keep:
            for path in sorted(routes.get(mid, ())):
                res = client.get(f"{API}{path}")
                assert res.status_code != 404, (mid, path)
                assert res.status_code < 500, (mid, path, res.text[:200])
        # 꺼진 모듈의 경로는 404다(켜진 모듈과 겹치는 경로 제외)
        on_paths = {p for mid in keep for p in routes.get(mid, ())}
        for mid in set(routes) - keep:
            for path in sorted(routes[mid] - on_paths):
                assert client.get(f"{API}{path}").status_code == 404, (mid, path)
