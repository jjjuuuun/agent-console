"""mod-wiki가 주고받는 포트(이름 = 포트, design §7R.3·§7R.4·§7R.18 Q14). 연동 모듈은 이 파일(공개
포트)만 import하거나 같은 이름을 자기 ``ports``에 선언해 연결한다.

제공:

- ``wiki.service``: 위키 서비스(``WikiServicePort`` 모양, 구현 ``WikiService``). 연동 모듈(실행 연동
  ``link-wiki-runs`` 등)이 공간의 위키 저장소(``tool_targets``·``repository``)를 받고 변경을
  알린다(``notify``).
- ``definitions.kind_contributions``(여러 제공자, X44): 정의 종류 두 개(위키 규칙 = 라이브러리·옮길
  수 있음·여러 본문 파일, 위키 = ``library=False``·옮길 수 있음 + 참조 추출 ``rules``).
- ``server.warnings``(여러 제공자): 사용자 설정 ``wiki`` 섹션 형식 문제·켠 쓰기 검사가 없음.

받음(모두 선택 — 없으면 그 부분만 꺼진다):

- ``workspace.settings``: 지금 워크스페이스 설정(``wiki`` 섹션). 없으면 기본값.
- ``secrets.rules``: 지금 비밀 의심 규칙. 없으면 ``ac-secret-rules`` 기본 규칙.
- ``definitions.store``: 앱 라이브러리 정의 저장소. 위키 규칙 종류가 있으면 공간 이름 없는 규칙
  요청·단독 공간 위키의 규칙이 라이브러리를 쓴다(``capabilities.rules_library``). 없으면 단독 루트.
- ``wiki.spaces``: 공간 이름(REST ``?project=<id>``) → ``WikiSpace``. 없으면 공간 이름이 온 요청은
  409 ``wiki.spaces_unavailable``(앱 workspace에 대신 만들지 않는다).
- ``records.spaces``: 공간의 기록 DB(``agent_console_store.RecordsSpaces``). 프로젝트 공간 페이지
  기록이 그 DB의 계보 ``wiki``에 남는다. 없으면 프로젝트 공간 기록 없음(``capabilities.history``
  거짓, 호스트 DB에 대신 쓰지 않는다).
- ``wiki.write_checks``(여러 제공자, X50): 쓰기 검사(``agent_console_wiki.WikiWriteCheck``). 늘
  켜지고, 사용자 설정 ``wiki.write_checks``에 ``enabled: false``로 적으면 끈다.
- ``wiki.integrations``(여러 제공자, Q14): 연동 선언(``WikiIntegration``). ``capabilities``에
  ``runs``를 낸 것이 있으면 ``WikiCapabilities.runs``가 참이다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from agent_console_contracts import Issue
from agent_console_contracts.wiki import WikiSettings
from agent_console_modkit import DEFINITION_KIND_CONTRIBUTIONS, KindContribution, PortKey
from agent_console_store import RECORDS_SPACES_PORT, DefinitionStore, RecordsSpaces
from agent_console_wiki import WikiRepository, WikiToolTarget, WikiWriteCheck

INTEGRATION_RUNS: Final = "runs"
"""``WikiIntegration.capabilities`` 값: 에이전트 쓰기(실행 연동). ``WikiCapabilities.runs``와 같은
이름(코드 개념)."""


@runtime_checkable
class WikiSpace(Protocol):
    """``wiki.spaces``가 여는 공간 하나(design §7R.3 ``WikiSpace{store, pages_root, folder,
    config_writable, config_dir}``).

    필수 속성:

    - ``store``: 그 공간의 정의 저장소(위키·위키 규칙 종류 — 없으면 모듈이 등록한다).
    - ``config_writable``: 쓸 수 있나(거짓이면 보기·검색만, 쓰기는 409 ``project.config_readonly``).
    - ``pages_root``: 페이지 폴더의 부모(절대 경로). 위키 하나 = ``<pages_root>/<위키 id>/``. 경로
      지킴(폴더 안만)은 제공자 몫이고, 이 모듈은 그 아래를 ``LocalWikiPages``로만 읽고 쓴다.

    선택 속성(``getattr``로 읽는다):

    - ``pages_dir``: ``pages_root``의 폴더 기준 상대 경로(화면 표시, ``WikiInfo.pages_root``).
      기본은 ``config_dir`` + 설치자 옵션 ``pages_dir``.
    - ``config_dir``: 정의 저장소 폴더(폴더 기준 상대 경로). 기본 빈 문자열.
    - ``index_dir``: 검색 색인 파일을 둘 폴더(절대 경로, 다시 만들 수 있는 캐시 — 예:
      ``<구성 폴더>/.state/wiki-index``). 없으면 색인을 메모리에만 둔다.
    - ``folder``: 폴더 절대 경로. 이 모듈은 쓰지 않는다(응답·로그에 절대 경로를 싣지 않는다).
    """

    @property
    def store(self) -> DefinitionStore: ...

    @property
    def config_writable(self) -> bool: ...

    @property
    def pages_root(self) -> Path: ...


@runtime_checkable
class WikiSpaces(Protocol):
    """``wiki.spaces`` 포트 모양: 공간 이름 → ``WikiSpace``."""

    def open(self, space: str) -> WikiSpace:
        """공간을 연다(제공자가 캐시를 맡는다).

        Raises:
            LookupError: 모르는 공간(→ 404 ``project.not_found``).
            Exception: 그 밖에 열 수 없다. ``code``(계약 오류 코드) 속성이 있으면 그 코드로
                응답한다(예: ``project.folder_missing``). 없으면 서버 오류.
        """
        ...


@runtime_checkable
class WikiIntegration(Protocol):
    """``wiki.integrations`` 항목: 연동 하나가 켜 주는 능력(예: ``{"runs"}``)."""

    @property
    def id(self) -> str: ...

    @property
    def capabilities(self) -> Collection[str]: ...


@runtime_checkable
class WikiServicePort(Protocol):
    """``wiki.service`` 포트 모양(소비자는 같은 모양을 자기 쪽에 선언해 쓴다)."""

    def settings(self) -> WikiSettings:
        """지금 사용자 설정 ``wiki``(깨진 부분은 뺀 값)."""
        ...

    def wiki_ids(self, space: str | None) -> list[str]:
        """그 공간의 위키 id(정렬). 공간을 열 수 없으면 ``SpaceError``."""
        ...

    def repository(self, space: str | None, wiki_id: str) -> WikiRepository:
        """그 공간 위키 하나의 저장소(설정·규칙이 바뀌면 새로 만든다). 없으면 ``WikiNotFound``."""
        ...

    def tool_targets(self, space: str | None) -> Mapping[str, WikiToolTarget]:
        """그 공간의 모든 위키 → 도구 대상(저장소·이름·페이지 폴더 상대 경로). 열 수 없는 위키는
        뺀다."""
        ...

    def notify(
        self,
        space: str | None,
        wiki_id: str,
        paths: Sequence[str] = (),
        *,
        deleted: bool = False,
        external: bool = False,
    ) -> None:
        """WS ``wiki.changed``를 낸다(연동이 저장소로 직접 쓴 뒤). 요약 캐시도 지운다."""
        ...


type WorkspaceSettingsReader = Callable[[], Any]
"""지금 워크스페이스 설정(``workspace.settings`` 포트 모양)."""

type SecretRulesReader = Callable[[], Any]
"""지금 비밀 의심 규칙(``secrets.rules`` 포트 모양, ``SecretRules``)."""

type WarningSource = Callable[[], Sequence[Issue]]
"""``server.warnings`` 포트 모양."""

WIKI_SERVICE: PortKey[WikiServicePort] = PortKey("wiki.service", "위키 서비스")
WIKI_SPACES: PortKey[WikiSpaces] = PortKey("wiki.spaces", "공간 이름 → 위키 저장 공간")
WIKI_WRITE_CHECKS: PortKey[WikiWriteCheck] = PortKey(
    "wiki.write_checks", "위키 쓰기 검사(X50)", multi=True
)
WIKI_INTEGRATIONS: PortKey[WikiIntegration] = PortKey(
    "wiki.integrations", "위키 연동 능력 선언", multi=True
)
RECORDS_SPACES: PortKey[RecordsSpaces] = PortKey(
    RECORDS_SPACES_PORT, "공간 이름 → 프로젝트 기록 DB 핸들"
)
KIND_CONTRIBUTIONS: PortKey[KindContribution[Any]] = DEFINITION_KIND_CONTRIBUTIONS
DEFINITIONS_STORE: PortKey[DefinitionStore] = PortKey("definitions.store", "정의 저장소")
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")
SERVER_WARNINGS: PortKey[WarningSource] = PortKey("server.warnings", "서버 정보 경고", multi=True)

__all__ = [
    "DEFINITIONS_STORE",
    "INTEGRATION_RUNS",
    "KIND_CONTRIBUTIONS",
    "RECORDS_SPACES",
    "SECRET_RULES",
    "SERVER_WARNINGS",
    "WIKI_INTEGRATIONS",
    "WIKI_SERVICE",
    "WIKI_SPACES",
    "WIKI_WRITE_CHECKS",
    "WORKSPACE_SETTINGS",
    "SecretRulesReader",
    "WarningSource",
    "WikiIntegration",
    "WikiServicePort",
    "WikiSpace",
    "WikiSpaces",
    "WorkspaceSettingsReader",
]
