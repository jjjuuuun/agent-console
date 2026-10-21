"""`team`(중첩 팀) 노드 타입(design §5R.7).

팀 구성 안에 다른 팀 구성을 노드 하나로 넣는다. 실행하면 그 팀 구성을 **자식 Run**
(`ctx.run_child`)으로 돌리고, 자식 답변 중 config `reply` 규칙으로 고른 것을 `out`으로 낸다.

- 디스크립터: `binds{kind: "graph", field: "team_ref"}`(팀 구성 정의 종류 — `ac-teams`는 이 값으로
  중첩 팀 노드를 알아본다, `TeamConventions.team_kind`), `role = "team"`, 포트 `in` → `out`,
  `ui_hints.shape = "stacked"`.
- 팀 구성 조회는 서비스 `TEAM_LOOKUP`(없으면 `team.lookup_unavailable`로 실패).
- 대화 이어 쓰기: 자식 Run 노드 세션은 부모 대화 세션의 경로 키 `"<이 노드>/<자식 노드>"`
  (`session_path_key`)에서 꺼내 자식 Run 서비스 `SESSIONS`로 넘긴다(손자도 같은 규칙으로 이어짐).
- 사용량: 자식 Run `totals`를 노드 `usage`로 돌려준다(엔진은 자동으로 더하지 않음).
- 자식 상태: `completed` → 성공, `waiting`(parked wait — 노드가 기다림으로 끝남) → 이 노드도
  `waiting`(`wait.reason = TEAM_CHILD_WAITING`, `data.child_run_id`), 그 밖(`failed`·`cancelled`·
  `interrupted`, 중첩 한도·순환·검증 거절) → 실패(자식 오류 그대로, 없으면 `team.child_failed`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    DefinitionBinding,
    ErrorInfo,
    Graph,
    GraphSettings,
    Issue,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
    RunReplyPayload,
    UiHints,
    WaitInfo,
    x_ui,
)
from agent_console_runtime import (
    ChildRunResult,
    NodeContext,
    NodeResult,
    SessionRef,
    ValidationContext,
)
from agent_console_teams import find_team, with_team_settings

from ._common import (
    IN_PORT,
    OUT_PORT,
    TEAM_LOOKUP_UNAVAILABLE_MESSAGE,
    TEAM_ROLE,
    NodesCoreErrorCodes,
    failed,
    parse_config,
    validation_errors,
)
from .edges import DEFAULT_MESSAGE_KEY
from .services import SESSIONS, TEAM_LOOKUP

__all__ = [
    "SESSION_PATH_SEPARATOR",
    "TEAM_CHILD_WAITING",
    "TeamNode",
    "TeamNodeConfig",
    "child_sessions",
    "pick_replies",
    "session_path_key",
]

SESSION_PATH_SEPARATOR: Final = "/"
"""대화 세션 경로 키의 구분자: `"<팀 노드>/<자식 노드>"`(design §5R.7)."""

TEAM_CHILD_WAITING: Final = "team.child_waiting"
"""자식 Run이 parked wait로 끝나 이 노드도 기다림일 때 `WaitInfo.reason`."""


class TeamNodeConfig(BaseModel):
    """다른 팀 구성을 이 자리에 넣어 한 단계처럼 실행하는 설정입니다."""

    # 키 이름은 `ac-teams` `TeamConventions` 기본값과 같다.
    # (docstring은 설정 폼 머리말로 보이므로 개발자 메모는 이 주석에 둔다.)

    model_config = ConfigDict(extra="forbid", title="중첩 팀 설정")

    team_ref: str = Field(
        min_length=1,
        title="팀 구성",
        description="이 자리에 넣을 팀 구성입니다.",
        json_schema_extra=x_ui(tier="basic", when="이 자리에 다른 팀을 넣고 싶을 때 고르세요."),
    )
    version: str | None = Field(
        default=None,
        min_length=1,
        title="버전 고정",
        description="쓸 팀 구성 버전입니다. 비우면 실행할 때의 최신 버전을 씁니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="안쪽 팀을 고쳐도 이 팀의 동작이 바뀌지 않게 하고 싶을 때 고정하세요.",
            example=None,
        ),
    )
    input_key: str | None = Field(
        default=None,
        min_length=1,
        title="넘길 입력 키",
        description=(
            "받은 값이 객체일 때 안쪽 팀에 넘길 키입니다. 비우면 받은 값을 그대로 넘깁니다."
        ),
        json_schema_extra=x_ui(tier="advanced", example="question"),
    )
    reply: list[str] | None = Field(
        default=None,
        title="결과로 쓸 답변",
        description=(
            "안쪽 팀 답변 중 결과로 쓸 이름 목록입니다. 비우면 최종 답변 전부를 순서대로 합칩니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="안쪽 팀의 답변 중 일부만 결과로 쓰고 싶을 때 고르세요.",
            example=["요약"],
        ),
    )
    reply_separator: str = Field(
        default="\n\n",
        title="답변 구분자",
        description="답변 여러 개를 합칠 때 사이에 넣는 문자열입니다. 기본은 빈 줄 하나입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    settings: GraphSettings | None = Field(
        default=None,
        title="자식 팀 구성 설정 덮어쓰기",
        description=(
            "이 자리에서만 안쪽 팀의 설정을 덮어씁니다. 비우면 안쪽 팀 설정을 그대로 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="안쪽 팀을 이 자리에서만 다른 모델·설정으로 돌리고 싶을 때 바꾸세요.",
        ),
    )


_PORTS = PortSpec(
    inputs=[PortDef(name=IN_PORT, label="입력")],
    outputs=[PortDef(name=OUT_PORT, label="결과")],
)


def session_path_key(team_node: str, child_key: str) -> str:
    """부모 대화 세션에 자식 Run 노드 세션을 저장할 경로 키(`"<팀 노드>/<자식 노드>"`)."""
    return f"{team_node}{SESSION_PATH_SEPARATOR}{child_key}"


def child_sessions(
    sessions: Mapping[str, SessionRef] | None, team_node: str
) -> dict[str, SessionRef]:
    """부모 세션 중 이 팀 노드 아래 경로 키만 골라 접두를 뗀 것(자식 Run의 `SESSIONS`)."""
    prefix = session_path_key(team_node, "")
    return {
        key[len(prefix) :]: ref
        for key, ref in (sessions or {}).items()
        if key.startswith(prefix) and len(key) > len(prefix)
    }


def pick_replies(
    replies: Sequence[RunReplyPayload], labels: Sequence[str] | None
) -> list[RunReplyPayload]:
    """결과로 쓸 자식 답변.

    `labels`가 있으면 그 이름(label)의 답변을 목록 순서대로(같은 이름은 낸 순서), 없으면 최종 답변
    (`final`) 전부를 `order`(없는 것은 뒤) → 낸 순서로.
    """
    if labels:
        return [r for label in labels for r in replies if r.label == label]
    finals = [r for r in replies if r.final]
    return sorted(finals, key=lambda r: (r.order is None, r.order or 0))


def _child_input(value: Any, key: str | None) -> dict[str, Any]:
    if key is not None and isinstance(value, Mapping):
        value = value.get(key)
    return {DEFAULT_MESSAGE_KEY: value}


class TeamNode:
    """노드 타입 `team`: 다른 팀 구성을 자식 Run으로 실행한다."""

    descriptor = NodeTypeDescriptor(
        id="team",
        version=1,
        title="팀 구성",
        description="다른 팀 구성을 노드 하나로 넣는다. 실행하면 그 팀 구성이 자식 실행으로 돈다.",
        category="팀",
        role=TEAM_ROLE,
        executable=True,
        binds=DefinitionBinding(kind="graph", field="team_ref"),
        config_schema=TeamNodeConfig.model_json_schema(),
        ui_schema={
            "ui:order": [
                "team_ref",
                "version",
                "input_key",
                "reply",
                "reply_separator",
                "settings",
            ]
        },
        static_ports=_PORTS,
        ui_hints=UiHints(shape="stacked"),
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        """고정 포트(`in` → `out`)."""
        return _PORTS

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        """의미 검증은 팀 규칙(`ac-teams` 중첩 팀 규칙)이 한다. 여기서는 없음."""
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        """팀 구성을 찾아 자식 Run으로 실행하고 답변을 골라 `out`으로 낸다."""
        cfg = parse_config(TeamNodeConfig, ctx.config)
        if isinstance(cfg, NodeResult):
            return cfg
        lookup = ctx.services.get(TEAM_LOOKUP)
        if lookup is None:
            return failed(
                NodesCoreErrorCodes.TEAM_LOOKUP_UNAVAILABLE, TEAM_LOOKUP_UNAVAILABLE_MESSAGE
            )
        graph = find_team(lookup, cfg.team_ref, cfg.version)
        if graph is None:
            shown = f"{cfg.team_ref}@{cfg.version}" if cfg.version else cfg.team_ref
            return failed(
                NodesCoreErrorCodes.TEAM_NOT_FOUND,
                f"팀 구성 {shown!r}을(를) 찾을 수 없습니다",
                team=cfg.team_ref,
                version=cfg.version,
            )
        child = self._with_settings(graph, cfg)
        if isinstance(child, NodeResult):
            return child
        own = ctx.node.id
        result = await ctx.run_child(
            child,
            _child_input(inputs.get(IN_PORT), cfg.input_key),
            services={SESSIONS: child_sessions(ctx.services.get(SESSIONS), own)},
        )
        return self._result(result, cfg)

    @staticmethod
    def _with_settings(graph: Graph, cfg: TeamNodeConfig) -> Graph | NodeResult:
        if cfg.settings is None:
            return graph
        try:
            return with_team_settings(graph, cfg.settings.model_dump(exclude_unset=True))
        except ValidationError as exc:
            return failed(
                NodesCoreErrorCodes.TEAM_INVALID_SETTINGS,
                "자식 팀 구성 설정 덮어쓰기가 유효하지 않습니다",
                errors=validation_errors(exc),
            )

    @staticmethod
    def _result(result: ChildRunResult, cfg: TeamNodeConfig) -> NodeResult:
        picked = pick_replies(result.replies, cfg.reply)
        text = cfg.reply_separator.join(r.text for r in picked)
        outputs = {OUT_PORT: text} if result.status == "completed" else {}
        if result.status == "completed":
            return NodeResult(status="succeeded", outputs=outputs, usage=result.totals)
        if result.status == "waiting":
            return NodeResult(
                status="waiting",
                usage=result.totals,
                wait=WaitInfo(
                    reason=TEAM_CHILD_WAITING,
                    message="자식 팀 구성 실행이 기다림으로 끝났습니다",
                    data={"child_run_id": result.run_id},
                ),
            )
        error = result.error or ErrorInfo(
            code=NodesCoreErrorCodes.TEAM_CHILD_FAILED,
            message=f"자식 팀 구성 실행이 {result.status} 상태로 끝났습니다",
        )
        if result.run_id is not None:
            error = error.model_copy(
                update={"details": {**(error.details or {}), "child_run_id": result.run_id}}
            )
        return NodeResult(status="failed", error=error, usage=result.totals)
