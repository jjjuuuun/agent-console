"""mod-architecture가 주고받는 포트(이름 = 포트, design §5.5R.3). 다른 모듈은 이 파일을 import하지
않고 같은 이름을 선언해 연결한다.

- 제공 ``architecture.catalog``: 병합된 프로필·연산자·검사·투영(``ArchitectureCatalog`` 모양,
  구현 ``ArchitectureCatalogService``). 로그 연동(``link-logs-architecture``)이 범위 이벤트를
  모아 ``project``·``pick``·``operators``를 부르고, 상한은 ``max_scope_events``를 읽는다.
- 제공 ``server.warnings``(여러 제공자): 저장된 ``architecture`` 섹션의 형식 문제
  (``architecture.settings_invalid``).
- 선택 ``workspace.settings``: 지금 워크스페이스 설정(``() -> WorkspaceSettings``). ``architecture``
  섹션을 여기서 읽는다. 없으면 사용자 설정 없이(기본 + 플러그인 프로필만) 동작한다.

이 모듈은 로그·실행 포트를 쓰지 않는다. 투영할 이벤트는 호출자가 넘긴다(단독 투영 본문 또는
``architecture.catalog``를 쓰는 연동 모듈).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_architecture import ProfileCatalog, ProfileEntry
from agent_console_conditions import ConditionOperator
from agent_console_contracts import Issue
from agent_console_contracts.architecture import (
    ArchitectureNote,
    ArchitectureProfile,
    ArchitectureView,
)
from agent_console_contracts.logs import LogEvent, TokenSample
from agent_console_modkit import PortKey


@runtime_checkable
class ArchitectureCatalog(Protocol):
    """``architecture.catalog`` 포트 모양(소비자는 같은 모양을 자기 쪽에 선언해 쓴다)."""

    max_scope_events: int
    """로그 범위 투영 상한(설치자 값). 넘으면 소비자가 ``ensure_within``으로 거절한다."""

    def catalog(self) -> ProfileCatalog:
        """병합된 프로필(기본 → 플러그인 → 사용자)."""
        ...

    def operators(self) -> Mapping[str, ConditionOperator]:
        """조건 연산자(X22)."""
        ...

    def pick(self, requested: str | None = None) -> tuple[ProfileEntry, ArchitectureNote | None]:
        """그릴 프로필(없는 id면 기본 + 대체 안내). 하나도 없으면 ``ProfileNotFoundError``."""
        ...

    def ensure_within(self, events: int, limit: int | None) -> None:
        """상한 초과면 ``ScopeTooLargeError``(호스트가 422 ``architecture.scope_too_large``로
        바꾼다)."""
        ...

    def project(
        self,
        events: Sequence[LogEvent],
        *,
        profile: str | None = None,
        inline: ArchitectureProfile | None = None,
        inline_id: str | None = None,
        tokens: Iterable[TokenSample] = (),
        source_kinds: Mapping[str, str] | None = None,
        error_categories: Collection[str] = frozenset(),
        max_seq: int | None = None,
        limit: int | None = None,
    ) -> ArchitectureView:
        """이벤트를 프로필로 투영한다."""
        ...


type WorkspaceSettingsReader = Callable[[], Any]
"""지금 워크스페이스 설정을 돌려주는 함수(``workspace.settings`` 포트 모양,
``WorkspaceSettings``)."""

type WarningSource = Callable[[], Sequence[Issue]]
"""``server.warnings`` 포트 모양."""

ARCHITECTURE_CATALOG: PortKey[ArchitectureCatalog] = PortKey(
    "architecture.catalog", "구조도 프로필 카탈로그(병합된 프로필·연산자·검사·투영)"
)
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
SERVER_WARNINGS: PortKey[WarningSource] = PortKey("server.warnings", "서버 정보 경고", multi=True)

__all__ = [
    "ARCHITECTURE_CATALOG",
    "SERVER_WARNINGS",
    "WORKSPACE_SETTINGS",
    "ArchitectureCatalog",
    "WarningSource",
    "WorkspaceSettingsReader",
]
