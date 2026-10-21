"""모듈 라우터 순서(3R.13): 연동 모듈 라우터를 먼저 붙여 고정 하위 경로가 가려지지 않는다."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.testclient import TestClient

from agent_console_modkit import ModuleContext, ModuleParts, PortKey, assemble
from agent_console_modkit.host import ROUTE_FIRST_KINDS, SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module

ITEMS: PortKey[str] = PortKey("items.port")


def _feature() -> Any:
    router = APIRouter()

    @router.get("/items/{item_id}")
    async def get_item(item_id: str) -> dict[str, str]:
        return {"by": "feature", "id": item_id}

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(ITEMS, "items")
        return ModuleParts(routers=[router])

    return fake_module("mod-items", provides=[ITEMS], on_build=build)


def _link() -> Any:
    router = APIRouter()

    @router.get("/items/summary")
    async def summary() -> dict[str, str]:
        return {"by": "link"}

    def build(_: ModuleContext) -> ModuleParts:
        return ModuleParts(routers=[router])

    return fake_module("link-items", kind="link", requires=[ITEMS], on_build=build)


def test_routers_put_first_kinds_first() -> None:
    assembly = assemble([_feature(), _link()])
    assert assembly.order == ["mod-items", "link-items"]
    plain = assembly.routers()
    linked_first = assembly.routers(first_kinds=ROUTE_FIRST_KINDS)
    assert plain == list(reversed(linked_first))


def test_host_matches_link_static_path_before_feature_param_path() -> None:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
    app = create_host_app(assemble([_feature(), _link()]), policy=policy)
    with TestClient(app) as client:
        assert client.get("/api/v1/items/summary").json() == {"by": "link"}
        assert client.get("/api/v1/items/x").json() == {"by": "feature", "id": "x"}
