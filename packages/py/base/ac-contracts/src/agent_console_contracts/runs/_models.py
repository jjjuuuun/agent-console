"""런타임 엔티티(design §2.3): Run, NodeRun, RunSnapshot, 커서 페이지 RunPage(1.7.0)."""

from collections.abc import Mapping
from typing import Final, Literal

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr
from agent_console_contracts.common import ErrorInfo, RecordSource, Usage

RUN_LABEL_LIMITS: Final[dict[str, int]] = {
    "max_labels": 16,
    "max_key_length": 64,
    "max_value_length": 256,
}
"""`Run.labels` 상한(1.7.0, design §6R.1.5 X45): 키 수·키 길이·값 길이(글자). 시작 요청
(`CreateRunRequest.labels`)이 넘으면 검증 오류다. 저장된 Run은 다시 검사하지 않는다."""


def run_label_problems(labels: Mapping[str, str]) -> list[str]:
    """라벨이 `RUN_LABEL_LIMITS`를 넘는 곳을 사람이 읽는 문장 목록으로 돌려준다(빈 목록 = 문제
    없음).

    키는 빈 문자열이 아니어야 한다. 값은 빈 문자열도 된다.

    >>> run_label_problems({"sdd.spec": "payments"})
    []
    >>> run_label_problems({"": "x"})
    ['라벨 키가 비었습니다']
    """
    out: list[str] = []
    if len(labels) > RUN_LABEL_LIMITS["max_labels"]:
        out.append(f"라벨이 {len(labels)}개입니다(최대 {RUN_LABEL_LIMITS['max_labels']}개)")
    for key, value in labels.items():
        if not key:
            out.append("라벨 키가 비었습니다")
        elif len(key) > RUN_LABEL_LIMITS["max_key_length"]:
            out.append(f"라벨 키가 {RUN_LABEL_LIMITS['max_key_length']}자를 넘습니다: {key[:16]}…")
        if len(value) > RUN_LABEL_LIMITS["max_value_length"]:
            out.append(
                f"라벨 {key[:16]}의 값이 {RUN_LABEL_LIMITS['max_value_length']}자를 넘습니다"
            )
    return out


type RunStatus = Literal[
    "queued", "running", "paused", "waiting", "completed", "failed", "cancelled", "interrupted"
]
"""Run 상태(고정 어휘)."""

type NodeRunStatus = Literal[
    "pending", "queued", "running", "waiting", "succeeded", "failed", "skipped", "cancelled"
]
"""NodeRun 상태(고정 어휘). `waiting` = 승인 등 외부 응답 대기."""


class Run(ContractModel):
    """그래프 1회 실행. 하위 그래프는 자식 Run(parent_run_id).

    목록 `GET /runs` 질의(0.8.0): `project`(같은 `project_id`만), `root_only`(true면 루트 Run만,
    `root_run_id`가 null인 것). 기존 질의(`graph_id`·`conversation_id`·`root` 등)는 그대로다.
    """

    id: NonEmptyStr
    graph_id: NonEmptyStr = Field(description="실행한 그래프(팀 구성) id.")
    graph_version: NonEmptyStr = Field(description="실행 당시 그래프 version_hash.")
    status: RunStatus
    input: JsonObject = Field(description="그래프 입력 포트 이름 → 값.")
    origin: NonEmptyStr = Field(description="시작 경로. 알려진 값은 RUN_ORIGINS(확장 가능).")
    conversation_id: str | None = Field(
        default=None, description="채팅 대화의 한 턴이면 그 대화 id."
    )
    parent_run_id: str | None = Field(
        default=None, description="자식 Run(중첩 팀)이면 부모 Run id."
    )
    parent_node_id: str | None = Field(
        default=None, description="자식 Run이면 그 Run을 만든 부모 그래프의 노드 id."
    )
    root_run_id: str | None = Field(
        default=None,
        description=(
            "자식 Run이면 맨 위 Run id(0.7.0). null = 이 Run이 루트다. 응답 대기·사용량은 루트 "
            "기준으로 모은다."
        ),
    )
    project_id: str | None = Field(
        default=None,
        description=(
            "프로젝트 id(0.8.0, 불투명 문자열). null = 프로젝트 없음. `GET /runs?project=`로 "
            "같음 비교해 거른다. 자식 Run은 루트 값을 물려받는다."
        ),
    )
    host_id: str | None = Field(
        default=None,
        description=(
            "이 Run을 돌린 앱의 id(0.12.1, workspace마다 한 번 만든 불투명 문자열). 같은 기록을 "
            "두 앱이 쓸 때 재시작 복구는 자기 host_id의 Run만 한다. null = 알리지 않음."
        ),
    )
    rerun_of: str | None = None
    from_node: str | None = None
    resumed_from: str | None = Field(
        default=None,
        description="끊긴 실행을 이어 간 Run이면 원래 Run id(origin = resume).",
    )
    created_at: float = Field(description="Unix epoch 초.")
    started_at: float | None = None
    ended_at: float | None = None
    error: ErrorInfo | None = None
    totals: Usage | None = None
    labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "라벨(1.7.0, 문자열 → 문자열). 실행을 다른 기능의 항목(예: 스펙 작업)과 잇는 일반 "
            "필드다. "
            "루트 Run에만 있고 자식 Run은 빈 값이다. 목록 질의 `label=<키>=<값>`(여러 번 = AND). "
            "상한 `RUN_LABEL_LIMITS`."
        ),
    )


class NodeRun(ContractModel):
    """노드 1회 실행. 재실행·반복은 attempt/iteration 증가."""

    run_id: NonEmptyStr
    node_id: NonEmptyStr
    attempt: int = Field(default=1, ge=1)
    iteration: int = Field(
        default=0, ge=0, description="반복 회차(사이클 연결로 다시 열릴 때마다 1씩)."
    )
    call: int = Field(
        default=0,
        ge=0,
        description=(
            "호출 회차: 위임자가 이 노드를 실행 안에서 부른 순번(0부터). "
            "스케줄로 실행된 NodeRun은 0."
        ),
    )
    invoked_by: list[str] | None = Field(
        default=None,
        description="위임자가 불러 실행됐으면 위임자의 노드 경로. null = 스케줄로 실행됨.",
    )
    status: NodeRunStatus
    node_type: str | None = None
    inputs: JsonObject = Field(default_factory=dict)
    outputs: JsonObject = Field(default_factory=dict)
    error: ErrorInfo | None = None
    usage: Usage | None = None
    started_at: float | None = None
    ended_at: float | None = None
    duration_ms: int | None = None
    backend_session_id: str | None = None


class RunSnapshot(ContractModel):
    """`GET /runs/{id}` 응답. 이후 WS `subscribe run:<id> since_seq=last_seq`로 증분을 받는다."""

    run: Run
    node_runs: list[NodeRun]
    last_seq: int = Field(ge=0)
    children: list[Run] | None = Field(
        default=None,
        description=("이 Run이 만든 자식 Run(중첩 팀). null = 서버가 채우지 않음, [] = 자식 없음."),
    )


class RunPage(ContractModel):
    """`GET /runs/page` 응답: 실행 목록 커서 페이지(1.7.0).

    정렬은 `created_at` 내림차순 + `id`. `next_cursor`를 다음 요청 `cursor=`로 넘긴다(불투명
    문자열).
    프로젝트 목록은 폴더 기록(`source=project`)을 끝까지 읽은 뒤 앱 기록(`source=app`)을 따로
    읽는다(두 출처를 시간순으로 섞지 않는다).
    """

    items: list[Run] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, description="다음 페이지 커서. null = 끝.")
    source: RecordSource = Field(description="이 페이지의 기록 출처(project·app).")


class WaitInfo(ContractModel):
    """노드가 waiting일 때 무엇을 기다리는지(`node.waiting` payload의 `wait`).

    상호작용 대기면 `reason` = 상호작용 종류 id, `data.interaction_ids` = 대기 중 상호작용 id 목록
    .
    """

    reason: NonEmptyStr = Field(description="대기 이유 문자열(고정 목록 아님).")
    message: str = ""
    options: list[str] = Field(default_factory=list)
    data: JsonObject = Field(default_factory=dict)
