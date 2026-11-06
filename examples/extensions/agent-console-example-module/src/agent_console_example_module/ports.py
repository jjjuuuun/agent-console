"""mod-example-notes가 주고받는 포트(이름 = 포트).

다른 모듈은 이 파일을 import하지 않고 같은 이름의 ``PortKey``를 자기 ``ports``에 선언해 연결한다
(모듈끼리 서로의 패키지에 기대지 않는다). 포트 모양(``NotesReader``)도 소비자가 자기 쪽에 같은
모양으로 선언하면 된다.

제공:

- ``example_notes.reader``: 노트 읽기(``NotesReader``). 연동 모듈(예: 실행마다 노트 읽기 도구를
  주는 연동)이 받는다.
- ``definitions.kind_contributions``(여러 제공자, X44): 정의 종류 하나(노트 틀). 정의 모듈이 받아
  라이브러리 저장소에 등록한다. 없으면(정의 모듈 꺼짐) 틀 기능만 쓸 수 없다.
- ``server.warnings``(여러 제공자): 사용자 설정 섹션 형식 문제.

받음(모두 선택 — 없으면 그 부분만 꺼진다):

- ``workspace.settings``: 지금 워크스페이스 설정(사용자 설정 섹션). 없으면 기본값.
- ``definitions.lookup``: 정의 읽기(노트 틀). 없으면 ``template``을 준 요청만 409
  ``feature_unavailable``.
- ``records.spaces``: 공간 이름 → 프로젝트 기록 DB 핸들. 없으면 ``?project=``를 준 요청만 409
  ``feature_unavailable``(앱 DB에 대신 쓰지 않는다).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Issue
from agent_console_modkit import DEFINITION_KIND_CONTRIBUTIONS, KindContribution, PortKey
from agent_console_store import RECORDS_SPACES_PORT, DefinitionStore, RecordsSpaces

from .models import Note


@runtime_checkable
class NotesReader(Protocol):
    """``example_notes.reader`` 포트 모양."""

    def list_notes(self, project: str | None = None, *, limit: int | None = None) -> list[Note]:
        """노트 목록(사용자 설정 순서). ``project``가 None이면 앱 공간.

        Raises:
            FeatureUnavailableError: ``project``를 줬는데 프로젝트 기록 연동이 없다.
        """
        ...


type WorkspaceSettingsReader = Callable[[], Any]
"""``workspace.settings`` 포트 모양(지금 워크스페이스 설정)."""

type WarningSource = Callable[[], Sequence[Issue]]
"""``server.warnings`` 포트 모양."""

NOTES_READER: PortKey[NotesReader] = PortKey("example_notes.reader", "노트 읽기(예제)")
KIND_CONTRIBUTIONS: PortKey[KindContribution[Any]] = DEFINITION_KIND_CONTRIBUTIONS
SERVER_WARNINGS: PortKey[WarningSource] = PortKey("server.warnings", "서버 정보 경고", multi=True)
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
DEFINITIONS_LOOKUP: PortKey[DefinitionStore] = PortKey("definitions.lookup", "정의 읽기")
RECORDS_SPACES: PortKey[RecordsSpaces] = PortKey(
    RECORDS_SPACES_PORT, "공간 이름 → 프로젝트 기록 DB 핸들"
)

__all__ = [
    "DEFINITIONS_LOOKUP",
    "KIND_CONTRIBUTIONS",
    "NOTES_READER",
    "RECORDS_SPACES",
    "SERVER_WARNINGS",
    "WORKSPACE_SETTINGS",
    "NotesReader",
    "WarningSource",
    "WorkspaceSettingsReader",
]
