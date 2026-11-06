"""link-example-notes-runs가 주고받는 포트(이름 = 포트).

다른 모듈 패키지는 import하지 않는다. 받는 포트의 이름과 **이 연동이 쓰는 부분의 모양**을
여기에 다시 선언한다(노트 모듈의 ``NotesReader``와 같은 이름·같은 모양이면 연결된다).

받음(둘 다 필수 — 하나라도 없으면 이 연동만 ``unsatisfied``, 나머지 모듈은 그대로):

- ``example_notes.reader``: 노트 읽기(``NotesReaderLike``). 노트 모듈(``mod-example-notes``)이 준다.
- ``runs.reader``: 실행 조회. 실행 모듈(``mod-runs``)이 준다. 이 연동은 이 포트를 부르지
  않는다. 실행 모듈이 없으면 ``runs.scopes``를 읽을 쪽이 없으므로, 그 사실을 상태
  (``unsatisfied``)로 드러내려고 필수로 둔다.

제공:

- ``runs.scopes``(여러 제공자, X26): Run마다 노드 서비스 ``TOOL_PROVIDERS``(X30)에 노트 읽기 도구
  공급자를 더한다(``NotesRunScope.scope_run``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from agent_console_modkit import PortKey


class NoteLike(Protocol):
    """노트 하나 중 이 연동이 읽는 부분."""

    @property
    def id(self) -> str:
        """노트 id."""
        ...

    @property
    def text(self) -> str:
        """본문."""
        ...

    @property
    def tags(self) -> Sequence[str]:
        """태그."""
        ...


class NotesReaderLike(Protocol):
    """``example_notes.reader`` 모양 중 이 연동이 쓰는 부분."""

    def list_notes(
        self, project: str | None = None, *, limit: int | None = None
    ) -> Sequence[NoteLike]:
        """노트 목록. ``project``가 None이면 앱 공간. 공간을 열 수 없으면 예외(``code`` 속성)."""
        ...


NOTES_READER: PortKey[NotesReaderLike] = PortKey("example_notes.reader", "노트 읽기")
RUNS_READER: PortKey[Any] = PortKey("runs.reader", "Run·NodeRun 조회")
RUN_SCOPES: PortKey[Any] = PortKey("runs.scopes", "실행 범위(Run마다 노트 도구 공급자)", multi=True)

__all__ = ["NOTES_READER", "RUNS_READER", "RUN_SCOPES", "NoteLike", "NotesReaderLike"]
