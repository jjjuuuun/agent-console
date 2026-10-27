"""agent-console-mod-runs: 실행 기능 모듈(design §3R.1.3, R4.4·R8.6·R8.7·R14).

실행 엔진(``ac-runtime``)과 실행 기록(``ac-store`` legacy 테이블)을 서버에 꽂는다. Run 시작·조회·
취소·이벤트·상호작용·이어 가기 경로와 WS ``run:<id>``·``interactions``, 재시작 복구를 맡고, 팀 규칙·
노드 서비스·대화 이어 가기는 포트로 받는다(엔진은 노드 타입·팀 의미를 모른다).

공개 API:
    - ``module``(``RunsModule``): entry point ``agent_console.server_modules``의 ``mod-runs``.
    - 포트·토픽(``ports``): 제공 ``RUNS_STARTER``·``RUNS_READER``·``RUNS_EVENTS``·
      ``INTERACTIONS_PORT``·``SECRET_REDACT``·``SERVER_WARNINGS``·``SERVER_ATTRIBUTES``, 토픽
      ``RUNS_EVENT``·``INTERACTIONS_UPDATED``. 받음 ``DEFINITIONS_LOOKUP``(필수)·``RUN_PREPARERS``·
      ``RUN_SERVICES``·``RUN_SCOPES``·``RESUME_HANDLERS``·``WORKSPACE_SETTINGS``·``SECRET_RULES``.
    - 확장 지점 프로토콜: ``RunPreparer``(+ ``RunPreparation``, 선택 사전 점검 ``RunPreflight`` →
      ``RunPreflightError``, 선택 이슈 꾸미기 ``RunIssueAnnotator``)·``RunScoper``(+ ``RunScope``,
      요청 ``project_id`` → 이 Run의 서비스·경고, 5.2R.34)·``RunServiceProvider``
      (+ ``RunEnvironment``)·``ResumeHandler``.
    - HTTP 없이 쓰는 부품: ``RunService``(검증·시작·취소·이어 가기·종료)·``InteractionService``·
      ``configure_backends``·``reveal_hidden_backends``(설정 ``show_hidden_backends``, 개발·테스트용
      백엔드 숨김 풀기)·``build_secret_resolver``·``SuspectedRedaction``·``open_recorder``.
    - ``build_router``·``topic_handlers``·``ERROR_MAP``(``error_map(child_resume=)``, 자식 Run
      이어 가기 거절 버튼 데이터 ``ChildResumeFix``), 설정 ``RunsModuleSettings``.
    - 관측 탭 이벤트 접두어 데이터(5.5R.13): ``DEFAULT_OBSERVE_EVENT_PREFIXES``·
      ``load_observe_event_prefixes``·``observe_event_prefixes_of``.
"""

from __future__ import annotations

from .backends import (
    BackendOptionsError,
    LookupSecretProvider,
    build_secret_resolver,
    configure_backends,
    reveal_hidden_backends,
)
from .errors import (
    DEFAULT_CHILD_RESUME_FIX,
    ERROR_MAP,
    BackendNotFoundError,
    ChildResumeFix,
    DefinitionReadError,
    NodeTypeNotFoundError,
    PortConfigError,
    RunNotFoundError,
    RunPreflightError,
    error_map,
)
from .interactions import INTERACTIONS_TOPIC, InteractionService
from .module import MODULE_ID, WEB_ROLES, PublishingSink, RunsModule, module
from .observe import (
    DEFAULT_OBSERVE_EVENT_PREFIXES,
    load_observe_event_prefixes,
    observe_event_prefixes_of,
)
from .ports import (
    DEFINITIONS_LOOKUP,
    INTERACTIONS_PORT,
    INTERACTIONS_UPDATED,
    RESUME_HANDLERS,
    RUN_PREPARERS,
    RUN_SCOPES,
    RUN_SERVICES,
    RUNS_EVENT,
    RUNS_EVENTS,
    RUNS_READER,
    RUNS_STARTER,
    SECRET_REDACT,
    SECRET_RULES,
    SERVER_ATTRIBUTES,
    SERVER_WARNINGS,
    WORKSPACE_SETTINGS,
    DefinitionLookup,
    ResumeHandler,
    RunEnvironment,
    RunIssueAnnotator,
    RunPreflight,
    RunPreparation,
    RunPreparer,
    RunScope,
    RunScopeLike,
    RunScoper,
    RunServiceProvider,
)
from .redaction import SuspectedRedaction
from .routes import build_router
from .service import TEAM_RULES_UNAVAILABLE, RunService, blocks_run, team_rules_warning
from .settings import RunsModuleSettings, RuntimeOptions
from .storage import STORAGE_MEMORY, open_recorder
from .ws import RUN_TOPIC, topic_handlers

__all__ = [
    "DEFAULT_CHILD_RESUME_FIX",
    "DEFAULT_OBSERVE_EVENT_PREFIXES",
    "DEFINITIONS_LOOKUP",
    "ERROR_MAP",
    "INTERACTIONS_PORT",
    "INTERACTIONS_TOPIC",
    "INTERACTIONS_UPDATED",
    "MODULE_ID",
    "RESUME_HANDLERS",
    "RUNS_EVENT",
    "RUNS_EVENTS",
    "RUNS_READER",
    "RUNS_STARTER",
    "RUN_PREPARERS",
    "RUN_SCOPES",
    "RUN_SERVICES",
    "RUN_TOPIC",
    "SECRET_REDACT",
    "SECRET_RULES",
    "SERVER_ATTRIBUTES",
    "SERVER_WARNINGS",
    "STORAGE_MEMORY",
    "TEAM_RULES_UNAVAILABLE",
    "WEB_ROLES",
    "WORKSPACE_SETTINGS",
    "BackendNotFoundError",
    "BackendOptionsError",
    "ChildResumeFix",
    "DefinitionLookup",
    "DefinitionReadError",
    "InteractionService",
    "LookupSecretProvider",
    "NodeTypeNotFoundError",
    "PortConfigError",
    "PublishingSink",
    "ResumeHandler",
    "RunEnvironment",
    "RunIssueAnnotator",
    "RunNotFoundError",
    "RunPreflight",
    "RunPreflightError",
    "RunPreparation",
    "RunPreparer",
    "RunScope",
    "RunScopeLike",
    "RunScoper",
    "RunService",
    "RunServiceProvider",
    "RunsModule",
    "RunsModuleSettings",
    "RuntimeOptions",
    "SuspectedRedaction",
    "blocks_run",
    "build_router",
    "build_secret_resolver",
    "configure_backends",
    "error_map",
    "load_observe_event_prefixes",
    "module",
    "observe_event_prefixes_of",
    "open_recorder",
    "reveal_hidden_backends",
    "team_rules_warning",
    "topic_handlers",
]
