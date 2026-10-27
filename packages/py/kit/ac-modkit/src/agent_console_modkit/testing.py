"""테스트·예제용 모듈(공개). 다른 패키지의 테스트도 이것을 쓴다(다른 패키지 ``tests/`` import 금지).

- ``fake_module(id, provides=…, requires=…, …)``: 서술자만 정하면 되는 가짜 모듈. 기본 build는
  선언한 포트마다 ``"<모듈 id>/<포트 이름>"`` 문자열을 제공한다. ``on_build``로 바꿀 수 있다.
- ``EchoModule``: 라우터·WS 토픽·오류 맵·포트·모듈 이벤트를 모두 쓰는 최소 예제 모듈
  (``build``에서만 FastAPI를 import한다 — extra ``[host]`` 필요).
- 호스트 확장 지점 예제(3R.16): ``example_plugin_loader``(플러그인 로더 — 이름 붙은 확장
  ``EXAMPLE_EXTENSION``에 항목 하나), ``RecordingDatabase``·``open_recording_database``(DB 공장 —
  ``upgrade``·``close``를 기록), ``ECHO_SETTINGS_COMPAT``(설정 호환 선언 예).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agent_console_modkit._assemble import ModuleContext
from agent_console_modkit._compat import (
    EnvSetting,
    FlagSetting,
    RemovedSetting,
    SeedSetting,
    SettingsCompat,
)
from agent_console_modkit._database import MigrationBranch
from agent_console_modkit._hostext import PluginLoadContext
from agent_console_modkit._module import (
    ModuleDescriptor,
    ModuleParts,
    WsForward,
    WsReject,
    WsSend,
    WsSubscribeRequest,
)
from agent_console_modkit._ports import PortKey, Topic
from agent_console_registry import LoadReport


@dataclass
class FakeModule:
    """가짜 모듈. ``contexts``에 build가 받은 문맥을 모은다."""

    descriptor: ModuleDescriptor
    on_build: Callable[[ModuleContext], ModuleParts | None] | None = None
    contexts: list[ModuleContext] = field(default_factory=list)

    def build(self, ctx: ModuleContext) -> ModuleParts:
        self.contexts.append(ctx)
        if self.on_build is not None:
            parts = self.on_build(ctx)
            return parts if parts is not None else ModuleParts()
        for key in self.descriptor.provides:
            ctx.provide(key, f"{self.descriptor.id}/{key.name}")
        return ModuleParts()


def _keys(items: Iterable[PortKey[Any] | str]) -> tuple[PortKey[Any], ...]:
    return tuple(i if isinstance(i, PortKey) else PortKey(i) for i in items)


def fake_module(
    module_id: str,
    *,
    provides: Iterable[PortKey[Any] | str] = (),
    requires: Iterable[PortKey[Any] | str] = (),
    optional: Iterable[PortKey[Any] | str] = (),
    kind: str = "feature",
    version: str = "0.1.0",
    settings_schema: type[BaseModel] | None = None,
    migrations: Iterable[MigrationBranch] = (),
    on_build: Callable[[ModuleContext], ModuleParts | None] | None = None,
) -> FakeModule:
    """가짜 모듈을 만든다. 포트는 ``PortKey`` 또는 이름 문자열(단일 포트)."""
    return FakeModule(
        ModuleDescriptor(
            id=module_id,
            version=version,
            kind=kind,
            title=module_id,
            provides=_keys(provides),
            requires=_keys(requires),
            optional=_keys(optional),
            settings_schema=settings_schema,
            migrations=tuple(migrations),
        ),
        on_build,
    )


# ---------------------------------------------------------------- 예제 모듈


ECHO_TRANSFORM: PortKey[Callable[[str], str]] = PortKey(
    "echo.transform", "문자열 변환(선택). 없으면 그대로 돌려준다"
)
"""Echo가 선택적으로 받는 포트."""

ECHO_SAID: Topic[str] = Topic("echo.said")
"""Echo가 ``POST /echo``마다 발행하는 모듈 이벤트."""

ECHO_WS_PREFIX = "echo:"


class EchoSettings(BaseModel):
    """Echo 설정(``modules.options.echo``)."""

    prefix: str = ""


class EchoBody(BaseModel):
    """``POST /echo/{channel}`` 본문."""

    text: str


class EchoNotFoundError(LookupError):
    """``GET /echo/missing`` → 오류 맵으로 404."""


class EchoModule:
    """최소 예제 모듈.

    - ``GET /echo?text=`` → ``{"text": prefix + transform(text)}``
    - ``POST /echo/{channel}`` (본문 ``{"text"}``) → WS ``echo:<channel>`` 구독자에게 보내고
      이벤트 ``ECHO_SAID`` 발행
    - ``GET /echo/transformed?text=`` → 선택 포트 ``ECHO_TRANSFORM``이 없으면 409
      ``feature_unavailable{module: "echo", port}``(``ctx.unavailable``)
    - ``GET /echo/missing`` → ``EchoNotFoundError`` → 404 ``not_found``
    - WS ``echo:<channel>``: 처음에 ``{"type": "echo.ready"}``, 이후 발행된 메시지.
      대상이 ``forbidden``이면 거절한다.
    """

    descriptor = ModuleDescriptor(
        id="echo",
        version="0.1.0",
        kind="feature",
        title="Echo",
        description="modkit 예제 모듈",
        optional=(ECHO_TRANSFORM,),
        settings_schema=EchoSettings,
        web_roles=("echo",),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        from fastapi import APIRouter

        settings = ctx.settings if isinstance(ctx.settings, EchoSettings) else EchoSettings()
        given = ctx.port(ECHO_TRANSFORM)
        transform = given or (lambda text: text)
        hub = ctx.ws_hub
        router = APIRouter()

        @router.get("/echo")
        async def echo(text: str = "") -> dict[str, str]:
            return {"text": settings.prefix + transform(text)}

        @router.get("/echo/transformed")
        async def transformed(text: str = "") -> dict[str, str]:
            if given is None:  # 선택 포트가 없어 이 동작만 꺼졌다 → 409 feature_unavailable
                raise ctx.unavailable(ECHO_TRANSFORM)
            return {"text": given(text)}

        @router.get("/echo/missing")
        async def missing() -> dict[str, str]:
            raise EchoNotFoundError("없는 메아리")

        @router.post("/echo/{channel}")
        async def say(channel: str, body: EchoBody) -> dict[str, int]:
            hub.publish(f"{ECHO_WS_PREFIX}{channel}", {"type": "echo.said", "text": body.text})
            ctx.publish(ECHO_SAID, body.text)
            return {"subscribers": hub.subscriber_count(f"{ECHO_WS_PREFIX}{channel}")}

        async def ws_echo(req: WsSubscribeRequest) -> WsForward | WsReject | None:
            if req.target == "forbidden":
                return WsReject("forbidden", "이 채널은 구독할 수 없습니다")

            async def forward(send: WsSend) -> None:
                sub = hub.subscribe(req.topic)
                try:
                    await send({"type": "echo.ready", "channel": req.target})
                    async for message in sub:
                        await send(message)
                finally:
                    sub.close()

            return forward

        return ModuleParts(
            routers=[router],
            ws_topics={ECHO_WS_PREFIX: ws_echo},
            error_map={EchoNotFoundError: "not_found"},
        )


echo_module = EchoModule()
"""entry point·``standalone.run`` 예제용 인스턴스."""


# ---------------------------------------------------------------- 호스트 확장 지점 예제(3R.16)

EXAMPLE_EXTENSION = "examples"
"""``example_plugin_loader``가 쓰는 이름 붙은 확장."""

EXAMPLE_KEY = "example"
"""``example_plugin_loader``가 등록하는 항목 key(``plugins.enabled``로 고를 수 있다)."""


def example_plugin_loader(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """플러그인 로더 예(entry point ``agent_console.host_plugin_loaders``).

    ``EXAMPLE_EXTENSION`` 확장에 ``{"workspace": …, "options": …}`` 항목 하나를 등록한다.
    ``ctx.enabled``에 ``EXAMPLE_KEY``가 없으면 건너뛴다.
    """
    source = "example loader"
    if ctx.enabled is not None and EXAMPLE_KEY not in ctx.enabled:
        return [(EXAMPLE_EXTENSION, LoadReport(source=source, status="skipped", key=EXAMPLE_KEY))]
    registry = ctx.registries.extension(EXAMPLE_EXTENSION)
    item = {
        "workspace": str(ctx.paths.workspace) if ctx.paths is not None else None,
        "options": dict(ctx.options.get(EXAMPLE_KEY, {})),
    }
    registry.register(EXAMPLE_KEY, item, source=source)
    return [(EXAMPLE_EXTENSION, LoadReport(source=source, status="loaded", key=EXAMPLE_KEY))]


@dataclass
class RecordingDatabase:
    """``DatabaseHandle`` 예(DB 없음): ``upgrade``한 계보 이름과 ``close``를 기록한다."""

    path: Path
    upgraded: list[list[str]] = field(default_factory=list)
    closed: bool = False

    @property
    def engine(self) -> Any:
        return None

    def upgrade(self, branches: Iterable[MigrationBranch] = ()) -> None:
        self.upgraded.append([b.name for b in branches])

    def close(self) -> None:
        self.closed = True


def open_recording_database(path: Path) -> RecordingDatabase:
    """DB 공장 예(entry point ``agent_console.host_database``)."""
    return RecordingDatabase(path)


ECHO_SETTINGS_COMPAT = SettingsCompat(
    env=(EnvSetting("ECHO_TAGS", ("tags",), split=","),),
    flags=(FlagSetting("echo-tag", ("tags",), metavar="TAG", repeat=True),),
    seeds=(SeedSetting("host", "host"),),
    removed=(
        RemovedSetting("echo.legacy", "echo.legacy는 지웠습니다"),
        RemovedSetting("echo_old", new="modules.options.mod-echo"),
    ),
)
"""설정 호환 선언 예: 환경변수 ``<접두어>ECHO_TAGS``, 명령행 ``--echo-tag``, 호스트 ``host`` 값을
기본값으로, 지운 키 ``echo.legacy``(이유만)·``echo_old``(옛 위치 → 새 위치 안내)."""


__all__ = [
    "ECHO_SAID",
    "ECHO_SETTINGS_COMPAT",
    "ECHO_TRANSFORM",
    "ECHO_WS_PREFIX",
    "EXAMPLE_EXTENSION",
    "EXAMPLE_KEY",
    "EchoBody",
    "EchoModule",
    "EchoNotFoundError",
    "EchoSettings",
    "FakeModule",
    "RecordingDatabase",
    "echo_module",
    "example_plugin_loader",
    "fake_module",
    "open_recording_database",
]
