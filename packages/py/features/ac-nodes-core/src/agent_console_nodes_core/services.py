"""앱이 주입하는 서비스 키와 확장 레지스트리 이름(이 플러그인이 정의·공개한다).

runtime은 정의 저장소·설정·파일 시스템 위치를 모른다. 이 플러그인이 필요한 값을 `ServiceKey`로
공개하고, 앱(apps/server)이 같은 키로 값을 넣어 `GraphRuntime(services=...)`(또는 Run마다
`start(services=...)`)에 주입한다::

    from agent_console_runtime import Services
    from agent_console_nodes_core import AGENT_LOOKUP, WORKSPACE_SETTINGS

    services = Services({AGENT_LOOKUP: find_agent, WORKSPACE_SETTINGS: workspace})

리소스 종류(X14)는 `registries.extension(RESOURCE_TYPES_EXTENSION)`에 앱이 로드한다::

    from agent_console_resources import load_resource_types
    load_resource_types(registries.extension(RESOURCE_TYPES_EXTENSION))
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import PurePath, PureWindowsPath
from typing import Final

from agent_console_contracts import Agent, Fix, Graph, WorkspaceSettings
from agent_console_resources import ResourceLookup
from agent_console_runtime import ServiceKey, SessionRef
from agent_console_teams import Layer, TeamLookup

from .tools import ToolProvider

type AgentLookup = Callable[[str], Agent | None]
"""에이전트 id → 정의. 없으면 None을 돌려준다(`LookupError`를 던져도 "없음"으로 본다)."""

type ErrorFixer = Callable[[str, Graph, str | None], Fix | None]
"""(오류 코드, 팀 구성, 노드 id | None) → 해결 버튼(없으면 None).

노드 실패 문구 3단 규칙의 둘째 단이다."""

RESOURCE_TYPES_EXTENSION: Final = "resource_types"
"""리소스 종류(X14) 레지스트리 이름(`registries.extension(...)`). agent 노드가 묶음을 만들 때 쓴다.
비어 있으면 첨부는 "모르는 종류"로 경고되고 묶음에서 빠진다."""

AGENT_LOOKUP: Final = ServiceKey[AgentLookup]("nodes_core.agent_lookup")
"""agent 노드의 `agent_ref`(와 위임 대상의 정의) 해석. 없으면 agent 노드는 실패한다."""

WORKSPACE_SETTINGS: Final = ServiceKey[WorkspaceSettings]("nodes_core.workspace_settings")
"""공통 설정(설정 층의 맨 위 `agent_defaults`, 사용자 병합 규칙). 없으면 공통 층이 비어 있다."""

DEFAULT_BACKEND: Final = ServiceKey[str]("nodes_core.default_backend")
"""모든 설정 층이 백엔드를 비웠을 때 쓸 백엔드 id(마지막 기본값)."""

WORKING_DIRECTORY: Final = ServiceKey[str]("nodes_core.working_directory")
"""유효 설정 `working_directory`가 비었을 때 `AgentRequest.cwd`(예: 서버 작업 폴더, 프로젝트
실행이면 프로젝트 폴더). 설정 값이 상대 경로면 이 폴더 기준으로 잇는다
(`resolve_working_directory`). 없으면 None(상대 경로는 그대로)."""


def resolve_working_directory(value: str | None, base: str | None) -> str | None:
    """에이전트 작업 폴더: 설정 값이 비면 `base`, 상대 경로면 `base` 기준으로 이은 정규화 경로.

    절대 경로·`~`로 시작하는 값·드라이브가 있는 값은 그대로 둔다. `base`가 없으면 값 그대로다.
    실행 범위(예: 프로젝트 경로 지킴)가 상대 경로를 그 폴더 기준으로 검사하므로, 실행 때도 같은
    기준으로 풀어 백엔드가 프로세스 작업 폴더 기준으로 읽지 않게 한다.

    >>> resolve_working_directory("sub", "/w/app")
    '/w/app/sub'
    >>> resolve_working_directory(None, "/w/app"), resolve_working_directory("/x", "/w/app")
    ('/w/app', '/x')
    >>> resolve_working_directory("sub", None)
    'sub'
    """
    if not value:
        return base or None
    if not base or value.startswith("~") or PurePath(value).is_absolute():
        return value
    if PureWindowsPath(value).drive or PureWindowsPath(value).root:
        return value
    return os.path.normpath(os.path.join(base, value))


WORKSPACE_PLACEHOLDER: Final = "workspace"
"""경로 값 안 틀 `{workspace}`의 이름(계약 `Limits.directories` 설명이 약속하는 틀). 값은 기준 폴더
(`WORKING_DIRECTORY` — 프로젝트 실행이면 프로젝트 폴더)다. 틀 표는 `path_placeholders` 한 곳에서
만든다 — 실행(`resolve_paths`)과 경로 지킴(예: link-projects-runs)이 같은 표를 쓴다."""


def path_placeholders(base: str | None) -> dict[str, str]:
    """경로 값 안 `{이름}` 틀 표(이름 → 바꿀 글자). 기준 폴더가 없으면 빈 표(틀은 그대로 남는다).

    >>> path_placeholders("/w/app"), path_placeholders(None)
    ({'workspace': '/w/app'}, {})
    """
    return {WORKSPACE_PLACEHOLDER: base} if base else {}


def resolve_paths(values: Sequence[str], base: str | None) -> list[str]:
    """경로 목록(예: `limits.directories`)을 실행 때 쓸 경로로: 틀(`path_placeholders`)을 바꾸고
    상대 경로는 `base` 기준으로 잇는다(`resolve_working_directory`와 같은 규칙).

    경로 지킴이 같은 표·같은 기준으로 검사하므로 백엔드가 받는 경로는 검사한 경로와 같다. 빈 값은
    뺀다. `base`가 없으면 값 그대로(틀도 그대로)다.

    >>> resolve_paths(["{workspace}/src", "docs", "/abs", " "], "/w/app")
    ['/w/app/src', '/w/app/docs', '/abs']
    >>> resolve_paths(["{workspace}", "docs"], None)
    ['{workspace}', 'docs']
    """
    table = path_placeholders(base)
    out: list[str] = []
    for raw in values:
        text = raw.strip()
        if not text:
            continue
        filled = text
        for name, replacement in table.items():
            filled = filled.replace("{" + name + "}", replacement)
        resolved = resolve_working_directory(filled, base) or filled
        out.append(os.path.normpath(resolved) if filled != text else resolved)
    return out


SCOPE_LAYERS: Final = ServiceKey[Sequence[Layer]]("nodes_core.scope_layers")
"""설정 층의 공통 바로 아래에 끼울 층(`ac-teams` `scope_layers`, 예: 프로젝트 층의 작업 폴더·설정).
이 플러그인은 층의 뜻을 모른다. Run마다 `start(services=...)`로 넣으며(통합 서버에서는 실행 범위
공급자 — 예: link-projects-runs), 자식 Run은 부모 서비스를 물려받아 같은 층을 쓴다.
없으면 층이 없다."""

RESOURCE_LOOKUP: Final = ServiceKey[ResourceLookup]("nodes_core.resource_lookup")
"""리소스 정의·본문 조회(`ac-resources.ResourceLookup`).
없으면 붙은 리소스를 쓰지 못하고 경고한다."""

RUN_FILES_ROOT: Final = ServiceKey[str]("nodes_core.run_files_root")
"""실행 묶음의 파일 칸을 쓸 루트 폴더. 노드마다 `<루트>/<run id>/<node id>/`에 쓴다
(design §R12.4: 앱은 `<workspace>/.state/runs`를 넣는다).
없으면 파일 칸을 전달하지 않고 경고한다."""

TEAM_LOOKUP: Final = ServiceKey[TeamLookup]("nodes_core.team_lookup")
"""중첩 팀 노드(`team`)의 `team_ref`(+ 고정 버전) 해석: `(팀 구성 id, 버전 | None) -> Graph | None`
(`ac-teams.TeamLookup`, 버전 = 정의 저장소의 버전 해시). 없으면 중첩 팀 노드는
`team.lookup_unavailable`로 실패한다(통합 서버에서는 link-runs-teams가 넣는다)."""

SESSIONS: Final = ServiceKey[Mapping[str, SessionRef]]("nodes_core.sessions")
"""노드 id → 이어 쓸 백엔드 세션(대화의 `sessions`, Run마다 `start(services=...)`로 넣는다).
유효 설정 `session`이 `fresh`이거나 백엔드가 다르면 쓰지 않는다. 중첩 팀 노드의 자식 Run 노드
세션은 경로 키 `"<팀 노드>/<자식 노드>"`로 들어 있다(`session_path_key`, design §5R.7)."""

ERROR_FIXES: Final = ServiceKey[ErrorFixer]("nodes_core.error_fixes")
"""노드 실패(`ErrorInfo`)에 붙일 해결 버튼(`fix`) 계산. 버튼이 데려갈 화면(웹 라우트 역할)은 앱 쪽
데이터라 이 플러그인은 모른다(통합 서버에서는 link-runs-teams가 넣는다).
없으면 실패에 버튼이 없다."""

TOOL_PROVIDERS: Final = ServiceKey[Sequence[ToolProvider]]("nodes_core.tool_providers")
"""에이전트 도구 공급자(X30, design §5.7R.3, `tools.ToolProvider`). agent 노드가 실행마다 순서대로
불러 공급 도구를 백엔드 요청 `host_tools`에 붙이고 소비한 칸을 묶음에서 뺀다. 이 플러그인은 도구의
뜻을 모른다. Run마다 `start(services=...)`로 넣으며(통합 서버에서는 실행 범위 공급자 X26
`runs.scopes` 항목), 자식 Run은 부모 서비스를 물려받아 같은 공급자를 쓴다.
없거나 비면 도구를 더하지 않는다(기존 실행과 같다)."""
