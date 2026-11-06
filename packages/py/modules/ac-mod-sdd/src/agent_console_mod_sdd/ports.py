"""mod-sdd가 주고받는 포트(이름 = 포트, design §6R.3·§6R.4·§6R.5). 다른 모듈은 이 파일을 import하지
않고 같은 이름을 자기 ``ports``에 선언해 연결한다.

제공:

- ``sdd.service``: 스펙 서비스(``SddServicePort`` 모양, 구현 ``SddService``). 연동 모듈(실행 연동
  ``link-runs-sdd`` 등)이 공간의 스펙을 읽고(``context``), 작업 줄을 고치고(``repository``),
  라벨 키(``label_key``)·비밀 검사(``secret_findings``)·변경 알림(``notify``)을 쓴다.
- ``definitions.kind_contributions``(여러 제공자, X44): 정의 종류 두 개(문서 틀 = 라이브러리·옮길
  수 있음 + 참조 추출(실행 프로필의 팀 구성), 스펙 = ``library=False``·옮길 수 있음).
- ``server.warnings``(여러 제공자): 사용자 설정 ``sdd`` 섹션 형식 문제(``sdd.settings_invalid``).

받음(모두 선택 — 없으면 그 부분만 꺼진다):

- ``workspace.settings``: 지금 워크스페이스 설정(``sdd`` 섹션). 없으면 기본값.
- ``secrets.rules``: 지금 비밀 의심 규칙. 없으면 ``ac-secret-rules`` 기본 규칙.
- ``definitions.store``: 앱 라이브러리 정의 저장소(공용 구성 문서 틀). 있으면 공간 이름 없는 틀
  요청·틀로 저장 기본 대상이 라이브러리다. 없으면 ``capabilities.templates=false``, 라이브러리로
  틀로 저장은 409 ``feature_unavailable``.
- ``sdd.spaces``: 공간 이름(REST ``?project=<id>``) → ``SddSpace``. 없으면 공간 이름이 온 요청은
  409 ``sdd.spaces_unavailable``(앱 workspace에 대신 만들지 않는다). 공간 이름이 없는 요청은 늘
  단독 루트(설치자 옵션 ``standalone_root``).
- ``sdd.integrations``(여러 제공자, X43): 작업 연동(``agent_console_sdd.TaskIntegration``).
- ``sdd.verification_sources``(여러 제공자, X42): 검증 결과 출처
  (``agent_console_sdd.VerificationSource``). 플러그인 출처(entry point
  ``agent_console.sdd_verification_sources``)는 사용자 설정으로 켠다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Issue
from agent_console_contracts.sdd import SddSettings
from agent_console_modkit import DEFINITION_KIND_CONTRIBUTIONS, KindContribution, PortKey
from agent_console_sdd import (
    LoadedSpec,
    SpecContext,
    SpecFiles,
    SpecRepository,
    TaskIntegration,
    VerificationSource,
)
from agent_console_store import DefinitionStore

LABEL_SPEC = "spec"
"""실행 라벨 이름(접두 없음): 스펙 id. 코드 개념(라벨 키 = 설치자 접두 + 이 이름)."""
LABEL_TASK = "task"
"""실행 라벨 이름: 작업 키."""
LABEL_PROFILE = "profile"
"""실행 라벨 이름: 실행 프로필 id."""
LABEL_PURPOSE = "purpose"
"""실행 라벨 이름: 실행 프로필 목적."""
LABEL_NAMES = (LABEL_SPEC, LABEL_TASK, LABEL_PROFILE, LABEL_PURPOSE)


@runtime_checkable
class SddSpace(Protocol):
    """``sdd.spaces``가 여는 공간 하나(design §6R.3 ``SddSpace{store, folder, config_writable,
    files}``).

    필수 속성:

    - ``store``: 그 공간의 정의 저장소(스펙·문서 틀 종류 — 없으면 모듈이 등록한다).
    - ``config_writable``: 쓸 수 있나(거짓이면 보기만, ``SddInfo.writable``).
    - ``files``: 그 폴더 안만 읽고 쓰는 ``SpecFiles``(없으면 None — 가져오기·내보내기 꺼짐).

    선택 속성(``getattr``로 읽는다):

    - ``config_dir``: 정의 저장소 폴더(폴더 기준 상대 경로, 예: 앱 구성 폴더). 기본 빈 문자열.
      ``SddInfo.spec_root``·입력 틀 ``spec_dir``의 앞부분이고, 가져오기·내보내기에서 그 첫
      구성요소는 예약(쓸 수 없음)이다.
    - ``max_content_bytes``: 문서 본문 한도(``SddLimits.max_doc_bytes``). 기본 None.
    - ``folder``: 폴더 절대 경로. 이 모듈은 쓰지 않는다(응답·로그에 절대 경로를 싣지 않는다).
    """

    @property
    def store(self) -> DefinitionStore: ...

    @property
    def config_writable(self) -> bool: ...

    @property
    def files(self) -> SpecFiles | None: ...


@runtime_checkable
class SddSpaces(Protocol):
    """``sdd.spaces`` 포트 모양: 공간 이름 → ``SddSpace``."""

    def open(self, space: str) -> SddSpace:
        """공간을 연다(제공자가 캐시를 맡는다).

        Raises:
            LookupError: 모르는 공간(→ 404 ``project.not_found``).
            Exception: 그 밖에 열 수 없다. ``code``(계약 오류 코드) 속성이 있으면 그 코드로
                응답한다(예: ``project.folder_missing``). 없으면 서버 오류.
        """
        ...


@runtime_checkable
class SddScopeLike(Protocol):
    """요청 하나가 쓰는 공간(구현 ``service.SddScope``)."""

    @property
    def name(self) -> str | None:
        """공간 이름(단독 루트면 None)."""
        ...

    @property
    def repository(self) -> SpecRepository:
        """그 공간의 스펙 저장소(작업 고치기 ``patch_task(…, by=…)``·상태 전환 등)."""
        ...

    @property
    def files(self) -> SpecFiles | None:
        """폴더 안 파일 접근(없으면 None)."""
        ...

    @property
    def spec_root(self) -> str:
        """스펙 폴더(폴더 기준 상대 경로)."""
        ...


@runtime_checkable
class SddServicePort(Protocol):
    """``sdd.service`` 포트 모양(소비자는 같은 모양을 자기 쪽에 선언해 쓴다)."""

    def scope(self, space: str | None) -> SddScopeLike:
        """공간 이름 → 공간(None = 단독 루트). 열 수 없으면 ``SpaceError``(``code``)."""
        ...

    def context(self, scope: Any, loaded: LoadedSpec) -> SpecContext:
        """읽은 스펙 → 연동·검증 출처 맥락(``SpecContext``)."""
        ...

    def settings(self) -> SddSettings:
        """지금 사용자 설정 ``sdd``(깨진 부분은 뺀 값)."""
        ...

    def label_key(self, name: str) -> str:
        """실행 라벨 키(설치자 접두 + ``name``, 예: ``LABEL_TASK``)."""
        ...

    def secret_findings(self, text: str) -> list[Issue]:
        """글(예: 치환한 실행 입력)의 비밀 의심 위치(``sdd.secret_suspect``, 값 없음). 설정
        ``secret_scan``이 ``off``면 빈 목록."""
        ...

    def secret_mode(self) -> str:
        """지금 사용자 설정 ``secret_scan`` 값(off·warn·reject)."""
        ...

    def notify(
        self,
        space: str | None,
        spec_id: str,
        *,
        version_hash: str | None = None,
        automation: bool = False,
        deleted: bool = False,
    ) -> None:
        """WS ``sdd.changed``를 낸다(연동이 스펙·자동 진행 상태를 바꾼 뒤)."""
        ...


type WorkspaceSettingsReader = Callable[[], Any]
"""지금 워크스페이스 설정(``workspace.settings`` 포트 모양)."""

type SecretRulesReader = Callable[[], Any]
"""지금 비밀 의심 규칙(``secrets.rules`` 포트 모양, ``SecretRules``)."""

type WarningSource = Callable[[], Sequence[Issue]]
"""``server.warnings`` 포트 모양."""

SDD_SERVICE: PortKey[SddServicePort] = PortKey("sdd.service", "스펙 서비스")
SDD_SPACES: PortKey[SddSpaces] = PortKey("sdd.spaces", "공간 이름 → 스펙 저장 공간")
SDD_INTEGRATIONS: PortKey[TaskIntegration] = PortKey(
    "sdd.integrations", "작업 연동(X43)", multi=True
)
SDD_VERIFICATION_SOURCES: PortKey[VerificationSource] = PortKey(
    "sdd.verification_sources", "검증 결과 출처(X42)", multi=True
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
    "KIND_CONTRIBUTIONS",
    "LABEL_NAMES",
    "LABEL_PROFILE",
    "LABEL_PURPOSE",
    "LABEL_SPEC",
    "LABEL_TASK",
    "SDD_INTEGRATIONS",
    "SDD_SERVICE",
    "SDD_SPACES",
    "SDD_VERIFICATION_SOURCES",
    "SECRET_RULES",
    "SERVER_WARNINGS",
    "WORKSPACE_SETTINGS",
    "SddScopeLike",
    "SddServicePort",
    "SddSpace",
    "SddSpaces",
    "SecretRulesReader",
    "WarningSource",
    "WorkspaceSettingsReader",
]
