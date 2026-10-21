"""노드 구현 공통 도우미: 포트 이름, 값 → 텍스트, 실패 결과, 오류 코드."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from pydantic import BaseModel, ValidationError

from agent_console_contracts import ErrorInfo, Issue, LogWarningPayload
from agent_console_runtime import NodeContext, NodeResult
from agent_console_teams import TeamIssueCodes

IN_PORT: Final = "in"
"""에이전트 노드 입력(넘겨받는 값) 포트."""
OUT_PORT: Final = "out"
"""에이전트 노드 출력(응답) 포트."""
DELEGATES_PORT: Final = "delegates"
"""에이전트 노드 위임 출력 포트(위임 연결의 출발)."""
DELEGATED_PORT: Final = "delegated"
"""에이전트 노드 위임 입력 포트(위임 연결의 도착)."""
RESOURCES_PORT: Final = "resources"
"""에이전트 노드 리소스 입력 포트(리소스 연결의 도착)."""
PROVIDES_PORT: Final = "provides"
"""리소스 노드 출력 포트."""
SAYS_PORT: Final = "says"
"""사용자 노드 출력: 사용자 메시지(입구 연결의 출발)."""
HEARS_PORT: Final = "hears"
"""사용자 노드 입력: 답변(답변 연결의 도착)."""
ASKS_PORT: Final = "asks"
"""사용자 노드 입력: 되묻기·승인 받는 쪽(상호작용 허용 연결의 도착, design §R14.2)."""
REVIEW_PORT: Final = "review"
"""사용자 노드 입력: 검토할 값(흐름 연결의 도착, design §R14.6)."""

AGENT_ROLE: Final = "agent"
"""에이전트 노드 타입의 `role`(연결 규칙 `connects` 근거)."""
USER_ROLE: Final = "user"
"""사용자 노드 타입의 `role`."""
RESOURCE_ROLE: Final = "resource"
"""리소스 노드 타입의 `role`."""
TEAM_ROLE: Final = "team"
"""중첩 팀 노드 타입의 `role`(흐름·입구·답변·반복·조건 연결의 `connects`에 들어 있다)."""


class NodesCoreErrorCodes:
    """이 플러그인이 쓰는 `ErrorInfo.code`·`Issue.code` 값."""

    INVALID_CONFIG: Final = "nodes_core.invalid_config"
    AGENT_LOOKUP_UNAVAILABLE: Final = "agent.lookup_unavailable"
    AGENT_NOT_FOUND: Final = "agent.not_found"
    AGENT_INVALID_DEFINITION: Final = "agent.invalid_definition"
    AGENT_NO_BACKEND: Final = "agent.no_backend"
    AGENT_UNKNOWN_BACKEND: Final = "agent.unknown_backend"
    AGENT_SECRET_NOT_FOUND: Final = "agent.secret_not_found"
    AGENT_BACKEND_FAILED: Final = "agent.backend_failed"
    AGENT_CANCELLED: Final = "agent.cancelled"
    AGENT_RESOURCES_UNAVAILABLE: Final = "agent.resources_unavailable"
    AGENT_MIXED_STRATEGIES: Final = "agent.mixed_strategies"
    AGENT_UNKNOWN_STRATEGY: Final = "agent.unknown_strategy"
    AGENT_DELEGATION_INVALID: Final = "agent.delegation_invalid"
    FILES_UNAVAILABLE: Final = "files.unavailable"
    FILES_UNSAFE_PATH: Final = "files.unsafe_path"
    FILES_INVALID_ITEM: Final = "files.invalid_item"
    FILES_WRITE_FAILED: Final = "files.write_failed"
    RESOURCE_NOT_FOUND: Final = "resource.not_found"
    RESOURCE_NOT_EXECUTABLE: Final = "resource.not_executable"
    USER_NOT_REVIEWABLE: Final = "user.not_reviewable"
    REVIEW_EXPIRED: Final = "review.expired"
    REVIEW_CANCELLED: Final = "review.cancelled"
    REVIEW_UNKNOWN_DECISION: Final = "review.unknown_decision"
    REVIEW_RESERVED_PORT: Final = "review.reserved_port"
    REVIEW_UNKNOWN_KIND: Final = "review.unknown_kind"
    DELEGATION_NO_MEMBERS: Final = "delegation.no_members"
    DELEGATION_DUPLICATE_MEMBER: Final = "delegation.duplicate_member"
    DELEGATION_BACKEND_UNSUPPORTED: Final = "delegation.backend_unsupported"
    DELEGATION_UNKNOWN_BACKEND: Final = "delegation.unknown_backend"
    TEAM_LOOKUP_UNAVAILABLE: Final = TeamIssueCodes.TEAM_LOOKUP_UNAVAILABLE
    TEAM_NOT_FOUND: Final = TeamIssueCodes.TEAM_NOT_FOUND
    TEAM_INVALID_SETTINGS: Final = "team.invalid_settings"
    TEAM_CHILD_FAILED: Final = "team.child_failed"


AGENT_LOOKUP_UNAVAILABLE_MESSAGE: Final = (
    "에이전트 정의 조회 서비스가 주입되지 않았습니다. 통합 서버라면 실행에 노드 서비스를 주는 "
    "에이전트 연동 모듈(link-runs-teams)이 꺼져 있을 수 있습니다(GET /api/v1/modules로 확인)"
)
"""`agent.lookup_unavailable` 메시지(원인 힌트 포함, 3R.16). 데이터로 두어 바꾸기 쉽게 한다."""

TEAM_LOOKUP_UNAVAILABLE_MESSAGE: Final = (
    "팀 구성 조회 서비스가 주입되지 않아 중첩 팀을 실행할 수 없습니다. 통합 서버라면 실행·팀 "
    "연동 모듈(link-runs-teams)이 꺼져 있을 수 있습니다(GET /api/v1/modules로 확인)"
)
"""`team.lookup_unavailable` 메시지(원인 힌트 포함). 데이터로 두어 바꾸기 쉽게 한다."""


def as_text(value: Any) -> str:
    """노드 입력 값을 텍스트로: 문자열은 그대로, None은 빈 문자열, 그 밖은 JSON."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def failed(code: str, message: str, **details: Any) -> NodeResult:
    """`status="failed"` 결과."""
    return NodeResult(status="failed", error=ErrorInfo(code=code, message=message, details=details))


def parse_config[M: BaseModel](model: type[M], config: Mapping[str, Any]) -> M | NodeResult:
    """config를 모델로 검증한다. 실패하면 실패 결과(엔진 검증을 끈 실행 대비)."""
    try:
        return model.model_validate(dict(config))
    except ValidationError as exc:
        return failed(
            NodesCoreErrorCodes.INVALID_CONFIG,
            f"config가 유효하지 않습니다: {exc.error_count()}개 오류",
            errors=validation_errors(exc),
        )


def validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    """pydantic 오류를 `ErrorInfo.details`용 `[{loc, msg}]`로(입력 값은 넣지 않는다)."""
    return [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()]


def issue(code: str, message: str, path: str, *, severity: str = "error") -> Issue:
    """config 기준 `path`의 검증 이슈."""
    return Issue.model_validate(
        {"severity": severity, "code": code, "message": message, "path": path}
    )


async def warn(ctx: NodeContext, issues: list[Issue], **extra: Any) -> None:
    """이슈들을 `log.warning` 이벤트로 낸다.

    `details` = 코드·이슈 details·`extra`(설정 값·본문은 넣지 않는다).
    """
    for item in issues:
        await ctx.emit(
            "log.warning",
            LogWarningPayload(
                message=item.message,
                details={"code": item.code, **dict(item.details), **extra},
            ),
        )
