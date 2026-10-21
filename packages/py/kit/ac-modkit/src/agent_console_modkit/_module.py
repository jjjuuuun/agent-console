"""모듈 인터페이스: 서술자·빌드 결과·WS 토픽 처리기(modularity §3.2, design §3R.1.2).

이 파일은 FastAPI를 import하지 않는다. ``ModuleParts.routers``의 항목은 호스트(``[host]`` extra)가
``fastapi.APIRouter``로 붙인다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel

from ._compat import SettingsCompat
from ._database import MigrationBranch
from ._errors import ErrorMapping
from ._ports import PortKey

if TYPE_CHECKING:
    from ._assemble import ModuleContext

KNOWN_MODULE_KINDS: tuple[str, ...] = ("feature", "link")
"""``ModuleDescriptor.kind``의 알려진 값(문서 상수). 다른 값도 받는다."""


@dataclass(frozen=True)
class ModuleDescriptor:
    """모듈이 스스로를 설명하는 데이터. 조립 순서·켜고 끄기·보고에 쓴다.

    Args:
        id: 모듈 id(예: ``"mod-chat"``). 설정 ``modules.*``의 키.
        version: 모듈 버전(보고용).
        kind: ``"feature"``(기능 모듈) 또는 ``"link"``(연동 모듈). 열린 문자열.
        title: 사람이 읽는 이름.
        description: 설명.
        provides: 제공하는 포트. ``build``에서 ``ctx.provide``로 실제 구현을 넣는다.
        requires: 필수 포트. 하나라도 없으면 이 모듈은 ``unsatisfied``로 꺼진다(이유 보고).
        optional: 선택 포트. 없으면 ``ctx.port``가 None(또는 빈 목록)이고 그 부분만 끈다.
        settings_schema: 자기 설정(``modules.options.<id>``) 검증 모델. None이면 설정을 받지 않는다.
        contracts: 이 모듈이 쓰는 계약 하위 모듈 → 버전(보고용, 예: ``{"chat": "1.0.0"}``).
        web_roles: 웹 라우트 역할(예: ``"conversations"``).
        migrations: 이 모듈이 소유한 DB 마이그레이션 계보. 호스트가 **이 모듈이 켜질 때만**
            ``database.upgrade``로 올린다(build 직전). 호스트에 DB가 없으면 올리지 않는다.
        settings_compat: 호스트 설정 호환 선언(옛 최상위 키·환경변수·명령행 별칭 → 이 모듈 설정).
            호스트는 모듈 이름을 모르므로 모듈이 알린다(``SettingsCompat``). None이면 없음.
    """

    id: str
    version: str
    kind: str
    title: str
    description: str = ""
    provides: tuple[PortKey[Any], ...] = ()
    requires: tuple[PortKey[Any], ...] = ()
    optional: tuple[PortKey[Any], ...] = ()
    settings_schema: type[BaseModel] | None = None
    contracts: Mapping[str, str] = field(default_factory=dict, hash=False)
    web_roles: tuple[str, ...] = ()
    migrations: tuple[MigrationBranch, ...] = ()
    settings_compat: SettingsCompat | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("모듈 id가 비어 있습니다")


# ---------------------------------------------------------------- WS 토픽 처리기


@dataclass(frozen=True)
class WsSubscribeRequest:
    """WS 구독 요청 하나(호스트가 해석해 처리기에 넘긴다).

    Attributes:
        topic: 요청한 토픽 전체(예: ``"run:r1"``).
        target: 접두 키(``"run:"``) 뒤의 부분. 정확히 일치하는 키면 빈 문자열.
        since_seq: 이 seq 다음부터 재생(없으면 0).
        request_id: 요청 상관 id.
    """

    topic: str
    target: str
    since_seq: int = 0
    request_id: str | None = None


@dataclass(frozen=True)
class WsReject:
    """구독 거절(소켓에 ``error`` 메시지로 간다, 구독은 생기지 않는다)."""

    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


type WsSend = Callable[[object], Awaitable[None]]
"""메시지 하나를 소켓으로 보낸다(호스트 코덱이 문자열로 바꾼다)."""

type WsForward = Callable[[WsSend], Awaitable[None]]
"""구독이 살아 있는 동안 메시지를 보내는 코루틴 함수. 끝나면 구독도 끝난다. 해제하면 취소된다."""

type WsTopicHandler = Callable[[WsSubscribeRequest], Awaitable[WsForward | WsReject | None]]
"""토픽 처리기. ``WsForward``=구독 시작, ``WsReject``=거절, ``None``=받아 두기만(보낼 메시지 없음).

``ModuleParts.ws_topics``의 키가 ``":"``로 끝나면 접두(``"run:"`` → ``run:<id>``, 대상 필수),
아니면 정확히 일치하는 토픽(``"interactions"``)이다.
"""


# ---------------------------------------------------------------- 빌드 결과·모듈


@dataclass
class ModuleParts:
    """``Module.build``가 돌려주는 것. 호스트가 합친다.

    Attributes:
        routers: ``fastapi.APIRouter`` 목록. 호스트가 API 접두(``/api/v1``) 아래 붙인다.
        ws_topics: WS 토픽 키 → 처리기. 키가 다른 모듈과 겹치면 이 모듈은 ``failed``.
        error_map: 예외 형식 → 오류 코드 또는 ``ErrorMapper``(예외 → ``ErrorReply``: 코드·메시지·
            ``details``·헤더). 호스트가 HTTP 상태·오류 본문으로 바꾼다.
        startup: 시작 때 조립 순서대로 부를 코루틴 함수.
        shutdown: 종료 때 **역순**으로 부를 코루틴 함수.
        background: 시작 뒤 작업으로 띄울 코루틴 함수(종료 때 취소).
    """

    routers: list[Any] = field(default_factory=list)
    ws_topics: dict[str, WsTopicHandler] = field(default_factory=dict)
    error_map: dict[type[Exception], ErrorMapping] = field(default_factory=dict)
    startup: list[Callable[[], Awaitable[None]]] = field(default_factory=list)
    shutdown: list[Callable[[], Awaitable[None]]] = field(default_factory=list)
    background: list[Callable[[], Awaitable[None]]] = field(default_factory=list)


@runtime_checkable
class Module(Protocol):
    """서버 모듈. entry point 그룹 ``MODULES_GROUP``으로 설치하거나 직접 넘긴다."""

    descriptor: ModuleDescriptor

    def build(self, ctx: ModuleContext) -> ModuleParts:
        """자기 구현을 만들고 포트를 제공한 뒤 서버에 붙일 부분을 돌려준다(전역 없음)."""
        ...


__all__ = [
    "KNOWN_MODULE_KINDS",
    "Module",
    "ModuleDescriptor",
    "ModuleParts",
    "WsForward",
    "WsReject",
    "WsSend",
    "WsSubscribeRequest",
    "WsTopicHandler",
]
