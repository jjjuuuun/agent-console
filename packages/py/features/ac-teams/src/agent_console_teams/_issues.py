"""팀 검증 이슈 코드·이슈 생성 도우미·백엔드 검사 훅 프로토콜(design §R3.1b, §R14.8)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final, Protocol, runtime_checkable

from agent_console_contracts import (
    AgentSettings,
    InteractionGrant,
    Issue,
    IssueSeverity,
    IssueSuggestion,
    KnownIssueCodes,
)

__all__ = ["SettingsValidator", "TeamIssueCodes", "make_issue"]


class TeamIssueCodes:
    """`validate_team`이 내는 `Issue.code` 값(심각도는 괄호)."""

    NO_ENTRY: Final = "team.no_entry"  # error, 실행 차단
    NO_REPLY: Final = "team.no_reply"  # warning, 실행은 됨
    UNREACHABLE: Final = "team.unreachable"  # warning
    ENTRY_NOT_EXECUTABLE: Final = "team.entry_not_executable"  # warning
    CONNECTS_MISMATCH: Final = "team.connects_mismatch"  # error
    AGENT_NOT_FOUND: Final = "team.agent_not_found"  # error
    RESOURCE_NOT_FOUND: Final = "team.resource_not_found"  # warning
    MIXED_INVOCATION: Final = "team.mixed_invocation"  # error: 흐름으로도 받고 위임으로도 불림
    MIXED_STRATEGIES: Final = KnownIssueCodes.TEAM_MIXED_STRATEGIES
    """error: 한 위임자의 대상 방식이 여럿이고 그중 `composable`이 아닌(또는 모르는) 방식이 있다."""
    UNKNOWN_STRATEGY: Final = "team.unknown_strategy"  # warning
    DELEGATION_DEPTH_EXCEEDED: Final = KnownIssueCodes.DELEGATION_DEPTH_EXCEEDED
    """error: 위임 깊이가 한도를 넘는다. `details.path` = 위임 경로 노드 id(5R.12부터 이 값)."""
    DELEGATION_CYCLE: Final = "team.delegation_cycle"  # error
    FLOW_FROM_DELEGATE: Final = "team.flow_from_delegate"  # error
    BACKEND_CAPABILITY_MISSING: Final = "team.backend_capability_missing"  # error
    MEMBER_FIELD_IGNORED: Final = "team.member_field_ignored"  # warning
    VALIDATOR_FAILED: Final = "team.validator_failed"  # warning
    INTERACTION_NO_PATH: Final = "interaction.no_path"  # warning(백엔드 훅이 냄)
    INTERACTION_UNSUPPORTED_IN_DELEGATE: Final = "interaction.unsupported_in_delegate"  # warning
    INTERACTION_UNSUPPORTED_BY_BACKEND: Final = "interaction.unsupported_by_backend"  # warning
    INTERACTION_KINDS_NOT_ALLOWED: Final = "interaction.kinds_not_allowed"  # warning
    REVIEW_DEAD_END: Final = "review.dead_end"  # warning
    MAX_ITERATIONS_INVALID: Final = KnownIssueCodes.FLOW_MAX_ITERATIONS_INVALID
    """error: 사이클 연결의 유효 최대 반복이 없거나 1 미만(엣지 이슈, path `/max_iterations`)."""
    LOOP_INVOKED_ONLY: Final = "flow.loop_invoked_only"
    """error: 반복 영역 안 노드가 위임으로만 불리고 영역 밖에서 들어오는 흐름이 없다
    (스케줄되지 않음)."""
    # 중첩 팀(design §5R.7). 값은 계약 문서 상수와 같다(엔진 실행 중 거절 코드와 같은 값).
    TEAM_RECURSIVE: Final = KnownIssueCodes.TEAM_RECURSIVE
    """error: 중첩 팀 노드가 자기 팀 구성을 직접·순환으로 다시 넣는다. `details.path` = 팀 구성 id
    경로(처음과 끝이 같은 id)."""
    TEAM_NESTING_EXCEEDED: Final = KnownIssueCodes.TEAM_NESTING_EXCEEDED
    """error: 중첩 깊이가 `delegation.max_nesting`을 넘는다. `details{depth, limit, path}`."""
    TEAM_NOT_FOUND: Final = KnownIssueCodes.TEAM_TEAM_NOT_FOUND
    """error: 중첩 팀 노드가 가리키는 팀 구성(또는 고정한 버전)이 없다. `details{team, version}`."""
    TEAM_CHILD_NO_ENTRY: Final = KnownIssueCodes.TEAM_CHILD_NO_ENTRY
    """error: 자식 팀 구성에 입구가 없다(자식 검증 요약). `details{team, version, issues}`."""
    # 저장 시점 위임 검사(design §5.2R.7, 5.2R.37). 값은 실행 시점 위임 방식 검사와 같은 코드다.
    DELEGATION_INVALID_CONFIG: Final = "delegation.invalid_config"
    """error: 위임자 노드의 방식 config(`delegation[방식 id]`)가 방식 디스크립터 `config_schema`에
    맞지 않는다. path = `/delegation/<방식 id>/…`, `details{strategy, validator}`."""
    DELEGATION_INVALID_CONFIG_SCHEMA: Final = "delegation.invalid_config_schema"
    """warning: 방식 디스크립터 `config_schema` 자체가 잘못되어 config를 검사하지 못했다."""
    DELEGATION_DUPLICATE_MEMBER: Final = "delegation.duplicate_member"
    """error: 한 위임자가 같은 대상을 같은 방식으로 두 번 넘게 잇는다(뒤 연결에 붙는다).
    `details{delegator, member, strategy, edges}`."""
    DELEGATION_DUPLICATE_NAMES: Final = "delegation.duplicate_{group}_names"
    """error 코드 형식: 한 위임자에서 합쳐 실행할 방식들이 알린 이름(`declared_names`)이 묶음
    `group` 안에서 겹친다(예: `delegation.duplicate_host_tool_names`). `details{group, names,
    strategies}`. 실행 시점 합치기 검사(`ac-runtime.merge_contributions`)와 같은 코드다."""
    TEAM_LOOKUP_UNAVAILABLE: Final = "team.lookup_unavailable"
    """실행 오류: 팀 구성 조회 수단이 주입되지 않아 중첩 팀 노드를 실행할 수 없다
    (연동이 꺼짐). 검증은 조회 수단이 없으면 정의 존재 검사를 건너뛴다."""


@runtime_checkable
class SettingsValidator(Protocol):
    """백엔드 선택 훅(X3, design §R14.8). 묻는 권한 모드 등 백엔드만 아는 규칙을 검사한다.

    `effective`는 노드(위임자 세션)의 유효 설정, `grant`는 그 세션이 열 수 있는 상호작용
    (없으면 빈 grant). 예: 묻는 권한 모드인데 `grant.kinds`에 도구 승인 종류가 없으면
    `interaction.no_path` 경고를 돌려준다(`details.kinds`에 필요한 종류를 넣으면 제안이 좁혀진다).
    """

    def validate_settings(
        self, effective: AgentSettings, grant: InteractionGrant
    ) -> list[Issue]: ...


def make_issue(
    severity: IssueSeverity,
    code: str,
    message: str,
    *,
    node_id: str | None = None,
    edge_id: str | None = None,
    details: Mapping[str, Any] | None = None,
    suggestions: Iterable[IssueSuggestion | None] = (),
    blocks_run: bool | None = None,
    path: str | None = None,
) -> Issue:
    """`Issue` 하나(제안 중 None은 뺀다)."""
    return Issue(
        severity=severity,
        code=code,
        message=message,
        node_id=node_id,
        edge_id=edge_id,
        path=path,
        details=dict(details or {}),
        suggestions=[s for s in suggestions if s is not None],
        blocks_run=blocks_run,
    )
