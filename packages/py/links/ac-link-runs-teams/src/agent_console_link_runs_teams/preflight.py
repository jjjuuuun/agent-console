"""실행 백엔드 사전 점검 오류 ``backend.unresolved``(design §5.2R.5, ux-overhaul §1.5-B).

해석은 ``ac-teams``(``resolve_backends``·``unresolved_backends``)가 하고, 여기서는 오류 본문
(``ErrorInfo`` + ``BackendUnresolvedDetails`` + 해결 버튼 ``Fix``)을 만든다. 문구·웹 라우트 역할·
설정 섹션·초점 위치는 ``BackendFixTexts`` **데이터**이며 바꿔 넘길 수 있다. 백엔드를 자동으로 고르지
않는다(비용이 드는 선택은 사용자가 한다).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from agent_console_contracts import (
    BackendDescriptor,
    BackendUnresolvedDetails,
    ErrorCodes,
    ErrorInfo,
    Fix,
    FixAction,
    FixTarget,
    UnresolvedBackendNode,
)
from agent_console_teams import TeamPlan, UnresolvedBackend

__all__ = ["DEFAULT_BACKEND_FIX_TEXTS", "BackendFixTexts", "backend_unresolved_error"]


@dataclass(frozen=True, slots=True)
class BackendFixTexts:
    """``backend.unresolved`` 오류의 문구·해결 버튼 데이터.

    Attributes:
        message_one: 노드 하나일 때 문구(``{label}``).
        message_many: 여럿일 때 문구(``{label}``·``{others}`` = 나머지 수).
        node_action_label / node_role_template / node_focus: [노드에서 지정] 버튼. 역할은
            ``{kind}``(팀 구성 정의 종류 = ``conventions.team_kind``)로 만든다. 대상 ``id`` = 팀
            구성 id, ``section`` = 첫 노드 id.
        default_action_label / default_role / default_section / default_focus: [기본값으로 지정]
            버튼(설정 화면의 공통 섹션).
    """

    message_one: str = "'{label}'을(를) 실행할 백엔드가 정해지지 않았습니다."
    message_many: str = "'{label}' 외 {others}개 노드를 실행할 백엔드가 정해지지 않았습니다."
    node_action_label: str = "노드에서 지정"
    node_role_template: str = "definition:{kind}"
    node_focus: str = "/backend"
    default_action_label: str = "기본값으로 지정"
    default_role: str = "settings"
    default_section: str = "common"
    default_focus: str = "/backend"


DEFAULT_BACKEND_FIX_TEXTS = BackendFixTexts()
"""기본 문구·웹 역할(웹 라우트 역할 `definition:<종류>`·`settings`, 설정 섹션 `common`)."""


def backend_unresolved_error(
    plan: TeamPlan,
    unresolved: Sequence[UnresolvedBackend],
    options: Sequence[BackendDescriptor],
    *,
    texts: BackendFixTexts = DEFAULT_BACKEND_FIX_TEXTS,
) -> ErrorInfo | None:
    """백엔드가 빈 노드가 있으면 ``backend.unresolved`` 오류 본문, 없으면 None.

    Args:
        plan: 팀 구성 해석 결과(팀 구성 id·정의 종류 이름).
        unresolved: ``unresolved_backends`` 결과(그래프 순서).
        options: 등록된 백엔드 디스크립터(등록 순서 그대로). 숨김 표시(``ui_hints.hidden``,
            개발·테스트용)는 선택지에서 뺀다.
        texts: 문구·해결 버튼 데이터.
    """
    if not unresolved:
        return None
    first = unresolved[0]
    message = (
        texts.message_one.format(label=first.label)
        if len(unresolved) == 1
        else texts.message_many.format(label=first.label, others=len(unresolved) - 1)
    )
    details = BackendUnresolvedDetails(
        nodes=[UnresolvedBackendNode(id=u.node_id, label=u.label) for u in unresolved],
        options=[o for o in options if o.ui_hints is None or o.ui_hints.hidden is not True],
    )
    fix = Fix(
        actions=[
            FixAction(
                label=texts.node_action_label,
                target=FixTarget(
                    role=texts.node_role_template.format(kind=plan.conventions.team_kind),
                    id=plan.graph.id,
                    section=first.node_id,
                ),
                focus=texts.node_focus,
            ),
            FixAction(
                label=texts.default_action_label,
                target=FixTarget(role=texts.default_role, section=texts.default_section),
                focus=texts.default_focus,
            ),
        ]
    )
    return ErrorInfo(
        code=ErrorCodes.BACKEND_UNRESOLVED,
        message=message,
        details=details.model_dump(mode="json"),
        fix=fix,
    )
