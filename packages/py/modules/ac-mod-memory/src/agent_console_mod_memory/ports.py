"""mod-memory가 주고받는 포트(이름 = 포트, design §5.7R.5.2). 다른 모듈은 이 파일을 import하지
않고 같은 이름을 자기 ``ports``에 선언해 연결한다.

제공:

- ``memory.service``: 메모리 서비스(``MemoryServicePort`` 모양, 구현 ``MemoryService``).
  ``store``(변경 알림을 내는 저장소)·``catalog()``(범위 종류)·``settings()``(지금 사용자 설정)·
  ``limits``(설치자 한도)·``toolkit(access, context, on_event, ...)``(에이전트 도구 묶음). 실행
  연동(``link-memory-runs``)이 에이전트 도구를 만들 때 쓴다.
- ``server.warnings``(여러 제공자): 저장소가 메모리(``memory.storage_memory``), 전문 검색 폴백
  (``memory.search_fallback``), 저장된 ``memory`` 섹션의 형식·규칙 문제
  (``memory.settings_invalid``).

받음(선택 — 없으면 그 부분만 꺼진다):

- ``workspace.settings``: 지금 워크스페이스 설정(``memory`` 섹션). 없으면 기본값(패키지 기본 범위
  종류, 비밀 거부, 정리 규칙 없음).
- ``memory.spaces``(5.7R.33z): 공간 이름(REST ``?project=<id>``, 실행의 ``project_id``) → 그 공간의
  메모리 저장소(``MemorySpaces.open`` → ``MemorySpaceLike``: ``store`` + 맥락 바꾸기 ``context``).
  ``link-projects-memory``가 프로젝트 폴더의 ``memory.sqlite3``를 열어 준다. 없으면 공간 이름이 온
  요청은 409 ``feature_unavailable``이고, 메모리 서비스의 ``space(name)``도 같은 예외를 낸다(실행
  연동은 그 실행의 메모리 도구를 ``scope_unavailable``로 둔다). 범위 종류·설정·한도는 공간과
  무관하게 앱 설정 하나다.

실행·로그 포트는 쓰지 않는다(메모리는 실행 없이도 사람이 쓴다).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Issue
from agent_console_contracts.memory import (
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryAuthor,
    MemorySettings,
)
from agent_console_memory import (
    EventSink,
    MemoryLimits,
    MemoryStore,
    MemoryToolkit,
    ScopeKindCatalog,
    ToolText,
    WriteBudget,
)
from agent_console_modkit import PortKey


@runtime_checkable
class MemoryServicePort(Protocol):
    """``memory.service`` 포트 모양(소비자는 같은 모양을 자기 쪽에 선언해 쓴다)."""

    @property
    def store(self) -> MemoryStore:
        """메모리 저장소(쓰면 WS ``memory.changed``로 알린다)."""
        ...

    @property
    def limits(self) -> MemoryLimits:
        """설치자 한도."""
        ...

    def catalog(self) -> ScopeKindCatalog:
        """병합된 범위 종류(패키지 기본 → 플러그인 → 사용자)."""
        ...

    def settings(self) -> MemorySettings:
        """지금 사용자 설정(깨진 부분은 뺀 값)."""
        ...

    def toolkit(
        self,
        access: MemoryAccessConfig,
        context: MemoryAccessContext,
        *,
        on_event: EventSink | None = None,
        author: MemoryAuthor | None = None,
        write_budget: WriteBudget | None = None,
        text: ToolText | None = None,
    ) -> MemoryToolkit:
        """에이전트 도구 묶음(이 저장소·범위 종류·설치자 검색 상한으로)."""
        ...


@runtime_checkable
class MemorySpaceLike(Protocol):
    """``memory.spaces``가 여는 공간 하나."""

    @property
    def store(self) -> MemoryStore:
        """그 공간의 메모리 저장소(정책은 메모리 서비스가 지금 설정에 맞춰 바꿔 끼운다)."""
        ...

    @property
    def context(self) -> Mapping[str, str]:
        """그 공간의 실행 도구 접근 맥락에 덮어쓸 값(``MemoryAccessContext`` 필드 이름 → 값).

        예: 프로젝트 공간은 ``{"project_id": <폴더 id>}`` — 범위 id가 등록 id가 아니라 폴더 id로
        풀린다. 모르는 필드 이름은 무시한다.
        """
        ...


@runtime_checkable
class MemorySpaces(Protocol):
    """``memory.spaces`` 포트 모양: 공간 이름 → 메모리 공간."""

    def open(self, space: str) -> MemorySpaceLike:
        """공간을 연다(제공자가 캐시·상한을 맡는다).

        Raises:
            LookupError: 모르는 공간(→ 404 ``project.not_found``).
            Exception: 그 밖에 열 수 없다. 예외에 ``code``(계약 오류 코드) 속성이 있으면 그 코드로
                응답한다(예: ``project.folder_missing``). 없으면 서버 오류.
        """
        ...


type WorkspaceSettingsReader = Callable[[], Any]
"""지금 워크스페이스 설정을 돌려주는 함수(``workspace.settings`` 포트 모양)."""

type WarningSource = Callable[[], Sequence[Issue]]
"""``server.warnings`` 포트 모양."""

MEMORY_SERVICE: PortKey[MemoryServicePort] = PortKey(
    "memory.service", "공유 메모리(저장소·범위 종류·설정·도구 묶음)"
)
SERVER_WARNINGS: PortKey[WarningSource] = PortKey("server.warnings", "서버 정보 경고", multi=True)
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
MEMORY_SPACES_PORT = "memory.spaces"
"""포트 이름: 공간 이름 → 메모리 공간(``MemorySpaces``)."""
MEMORY_SPACES: PortKey[MemorySpaces] = PortKey(MEMORY_SPACES_PORT, "공간 이름 → 메모리 저장소")

__all__ = [
    "MEMORY_SERVICE",
    "MEMORY_SPACES",
    "MEMORY_SPACES_PORT",
    "SERVER_WARNINGS",
    "WORKSPACE_SETTINGS",
    "MemoryServicePort",
    "MemorySpaceLike",
    "MemorySpaces",
    "WarningSource",
    "WorkspaceSettingsReader",
]
