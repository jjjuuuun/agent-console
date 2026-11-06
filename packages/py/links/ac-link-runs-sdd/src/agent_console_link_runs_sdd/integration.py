"""작업 연동 ``runs``(X43 ``TaskIntegration`` + 선택 능력 ``ProfileChecker``, design §6R.1.5).

- **동작**(``actions``): 스펙 규칙의 실행 프로필마다 하나. 프로필 ``when``이 이 작업에 맞지 않으면
  내지 않는다(한꺼번에 시작에서 그 작업은 ``sdd.action_unavailable``). ``run`` 관문이 막으면
  ``disabled``에 ``sdd.gate_blocked`` 이슈.
- **실행**(``invoke``·``start``): ``when`` → ``run`` 관문 → 입력 틀 치환(``render_run_input``) →
  비밀 검사(사용자 설정 ``secret_scan``: ``reject``면 시작 거부, ``warn``이면 시작 + 정보 이슈) →
  라벨 상한 → ``runs.starter.start_graph(graph, input, origin, project_id=공간 이름, labels)``.
  결과는 ``TaskActionResult``(started·blocked·failed)이고 예외로 던지지 않는다 — 한꺼번에 시작이
  작업마다 결과를 모은다. 단건 경로의 HTTP 오류 변환은 ``mod-sdd`` 라우트 몫이다.
- **연결**(``links``): 스펙 라벨 질의 한 번(페이지를 상한까지) → ``TaskLink{kind=run}``.
- **프로필 검사**(``check_profile``): 그 공간에 팀 구성이 없으면 ``sdd.profile_graph_missing``
  (warning, ``details.in_library`` = 공용 구성에만 있음).
- **결과 반영 이슈**(선택 메서드 ``task_issues``): ``sdd.status_not_applied``(``StatusReflector``),
  자동 진행이 건너뛴 작업 ``sdd.automation_skipped``.
- **자동 진행**(선택 능력 ``AutomationControl`` — ``automation_state``·``control``): 붙은
  ``SpecAutomation``에 맡긴다(6R.16).

실행 모듈·프로젝트 모듈을 import하지 않는다. 공간 이름 = 실행 ``project_id``(프로젝트 연동이 공간
이름을 프로젝트 등록 id로 준다 — 단독 루트는 None).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from agent_console_conditions import ConditionOperator, builtin_operators, evaluate_conditions
from agent_console_contracts import Issue, Run, run_label_problems
from agent_console_contracts.constants import ErrorCodes, KnownIssueCodes
from agent_console_contracts.sdd import (
    AutomationState,
    KnownGateTargets,
    KnownTaskActionStatuses,
    KnownTaskLinkKinds,
    ParsedTask,
    RunProfile,
    SpecIssue,
    TaskAction,
    TaskActionResult,
    TaskLink,
)
from agent_console_sdd import SddError, SpecContext, evaluate_gates, gate_context, render_run_input

from .ports import (
    LABEL_PROFILE,
    LABEL_PURPOSE,
    LABEL_SPEC,
    LABEL_TASK,
    RunReader,
    RunStarter,
    SddServicePort,
)
from .records import labeled_runs, run_time
from .reflect import StatusReflector, TrackedRun
from .settings import RunsSddSettings

if TYPE_CHECKING:
    from .automation import SpecAutomation

SECRET_REJECT = "reject"
"""사용자 설정 ``secret_scan`` 값: 비밀 의심이 있으면 실행을 시작하지 않는다."""


class RunsTaskIntegration:
    """실행 프로필 = 작업 동작(``sdd.integrations`` 항목).

    Args:
        sdd: 스펙 서비스(``sdd.service``).
        starter: ``runs.starter``.
        reader: ``runs.reader``.
        reflector: 결과 반영(시작한 Run을 등록한다).
        settings: 설치자 설정.
        operators: 조건 연산자(None = 공간 저장소의 연산자, 없으면 ``ac-conditions`` 기본).
    """

    link_kinds: tuple[str, ...] = (KnownTaskLinkKinds.RUN,)
    """``mod-sdd``가 ``capabilities.runs``를 켜는 선택 속성(실행 연결을 낸다)."""

    def __init__(
        self,
        *,
        sdd: SddServicePort,
        starter: RunStarter,
        reader: RunReader,
        reflector: StatusReflector,
        settings: RunsSddSettings | None = None,
        operators: Mapping[str, ConditionOperator] | None = None,
    ) -> None:
        self.sdd = sdd
        self.starter = starter
        self.reader = reader
        self.reflector = reflector
        self.settings = settings or RunsSddSettings()
        self._operators = operators
        self.automation: SpecAutomation | None = None
        """자동 진행(6R.16, 모듈이 붙인다). None이면 ``automation_state``·``control``이 None."""

    @property
    def id(self) -> str:
        return self.settings.integration_id

    # ------------------------------------------------------------ 공용
    def operators(self, ctx: SpecContext) -> Mapping[str, ConditionOperator]:
        """관문·``when`` 연산자(공간 저장소와 같은 것 — 플러그인 연산자 포함)."""
        if self._operators is not None:
            return self._operators
        try:
            found = getattr(self.sdd.scope(ctx.space).repository, "operators", None)
        except Exception:
            found = None
        if isinstance(found, Mapping):
            return found
        return {op.descriptor.id: op for op in builtin_operators()}

    def profile(self, ctx: SpecContext, profile_id: str) -> RunProfile | None:
        return next((p for p in ctx.spec.rules.run_profiles or () if p.id == profile_id), None)

    def applies(
        self, ctx: SpecContext, task: ParsedTask, profile: RunProfile, subject: Mapping[str, Any]
    ) -> bool:
        """프로필 ``when``이 이 작업에 맞나(없으면 늘 참)."""
        if profile.when is None:
            return True
        return evaluate_conditions(profile.when, dict(subject), self.operators(ctx)).result

    def labels(self, ctx: SpecContext, task: ParsedTask, profile: RunProfile) -> dict[str, str]:
        """실행 라벨(키 = 설치자 접두 + 이름)."""
        labels = {
            self.sdd.label_key(LABEL_SPEC): ctx.spec.id,
            self.sdd.label_key(LABEL_TASK): task.key,
            self.sdd.label_key(LABEL_PROFILE): profile.id,
        }
        if profile.purpose:
            labels[self.sdd.label_key(LABEL_PURPOSE)] = profile.purpose
        return labels

    # ------------------------------------------------------------ X43
    async def actions(self, ctx: SpecContext, task: ParsedTask) -> list[TaskAction]:
        profiles = list(ctx.spec.rules.run_profiles or ())
        if not profiles:
            return []
        subject = gate_context(ctx.spec, ctx.index, task=task)
        blocks = evaluate_gates(
            ctx.spec.rules, KnownGateTargets.RUN, subject, operators=self.operators(ctx)
        )
        disabled = blocks[0].issue() if blocks else None
        return [
            TaskAction(
                integration=self.id,
                id=p.id,
                label=p.title,
                purpose=p.purpose,
                disabled=disabled,
            )
            for p in profiles
            if self.applies(ctx, task, p, subject)
        ]

    async def invoke(
        self, ctx: SpecContext, task: ParsedTask, action: str, args: Mapping[str, Any]
    ) -> TaskActionResult:
        profile = self.profile(ctx, action)
        subject = gate_context(ctx.spec, ctx.index, task=task)
        if profile is None or not self.applies(ctx, task, profile, subject):
            return _failed(
                task,
                ErrorCodes.SDD_ACTION_UNAVAILABLE,
                "이 작업에서 쓸 수 없는 동작입니다.",
                {"integration": self.id, "action": action},
            )
        return await self.start(ctx, task, profile)

    async def start(
        self, ctx: SpecContext, task: ParsedTask, profile: RunProfile
    ) -> TaskActionResult:
        """프로필 하나로 작업을 실행한다(관문 → 입력 → 비밀 → 라벨 → 시작). 자동 진행(6R.16)도
        이 메서드를 쓴다. ``when``은 부르는 쪽이 본다."""
        subject = gate_context(ctx.spec, ctx.index, task=task)
        blocks = evaluate_gates(
            ctx.spec.rules, KnownGateTargets.RUN, subject, operators=self.operators(ctx)
        )
        if blocks:
            return TaskActionResult(
                task_key=task.key, status=KnownTaskActionStatuses.BLOCKED, issue=blocks[0].issue()
            )
        try:
            run_input = render_run_input(profile, task, ctx.spec, spec_dir=ctx.directory)
        except SddError as exc:
            return _failed(task, exc.code, str(exc), dict(exc.details))
        findings = [
            issue for text in _strings(run_input) for issue in self.sdd.secret_findings(text)
        ]
        notice: Issue | None = None
        if findings:
            details = {"issues": [_plain(i) for i in findings]}
            if self.sdd.secret_mode() == SECRET_REJECT:
                return _failed(
                    task,
                    ErrorCodes.SDD_SECRET_REJECTED,
                    "실행 입력에 비밀로 보이는 값이 있어 실행하지 않았습니다.",
                    details,
                )
            notice = Issue(
                severity="info",
                code=KnownIssueCodes.SDD_SECRET_SUSPECT,
                message="실행 입력에 비밀로 보이는 값이 있습니다(값은 보이지 않습니다).",
                details=details,
            )
        labels = self.labels(ctx, task, profile)
        problems = run_label_problems(labels)
        if problems:
            return _failed(
                task,
                ErrorCodes.VALIDATION_FAILED,
                "실행 라벨이 상한을 넘습니다.",
                {"problems": problems},
            )
        self.reflector.begin_start()
        try:
            handle = await self.starter.start_graph(
                profile.graph,
                run_input,
                origin=self.settings.origin,
                project_id=ctx.space,
                labels=labels,
            )
        except Exception as exc:
            self.reflector.end_start()
            return TaskActionResult(
                task_key=task.key, status=KnownTaskActionStatuses.FAILED, issue=start_issue(exc)
            )
        try:
            self.reflector.track(
                TrackedRun(
                    run_id=handle.run_id,
                    space=ctx.space,
                    spec_id=ctx.spec.id,
                    task_key=task.key,
                    profile_id=profile.id,
                    line_hash=task.line_hash,
                )
            )
        finally:
            self.reflector.end_start()
        return TaskActionResult(
            task_key=task.key,
            status=KnownTaskActionStatuses.STARTED,
            run_id=handle.run_id,
            issue=notice,
        )

    async def links(self, ctx: SpecContext, tasks: Sequence[ParsedTask]) -> list[TaskLink]:
        """그 스펙의 작업 실행(최근 순). 지금 문서에 없는 작업 키의 실행도 낸다(추적 표 "모르는
        작업"). 문서에 있지만 ``tasks``에 없는 작업의 실행은 뺀다."""
        wanted = {t.key for t in tasks}
        known = {t.key for t in ctx.index.tasks}
        task_label = self.sdd.label_key(LABEL_TASK)
        profile_label = self.sdd.label_key(LABEL_PROFILE)
        purpose_label = self.sdd.label_key(LABEL_PURPOSE)
        out: list[TaskLink] = []
        for run in self.spec_runs(ctx):
            key = run.labels.get(task_label)
            if not key or (key in known and key not in wanted):
                continue
            out.append(
                TaskLink(
                    integration=self.id,
                    kind=KnownTaskLinkKinds.RUN,
                    ref=run.id,
                    task_key=key,
                    status=run.status,
                    at=run_time(run),
                    purpose=run.labels.get(purpose_label),
                    profile=run.labels.get(profile_label),
                    totals=run.totals,
                )
            )
        return out

    def spec_runs(self, ctx: SpecContext, extra: Mapping[str, str] | None = None) -> list[Run]:
        """그 스펙 라벨이 있는 루트 Run(최근 순, 상한 ``max_link_runs``)."""
        labels = {self.sdd.label_key(LABEL_SPEC): ctx.spec.id, **dict(extra or {})}
        return labeled_runs(
            self.reader,
            project_id=ctx.space,
            labels=labels,
            limit=self.settings.max_link_runs,
            page_size=self.settings.page_size,
        )

    # ------------------------------------------------------------ 선택 능력
    async def check_profile(self, ctx: SpecContext, profile: RunProfile) -> list[SpecIssue]:
        """실행 프로필의 팀 구성이 그 공간에 있나(없으면 ``sdd.profile_graph_missing``).

        ``runs.starter``의 선택 메서드 ``definitions_for``(공간 출처, 막히면
        ``project.not_imported``
        ``in_library``)와 ``find_graph``(지금 팀 구성)로 본다. 둘 다 없으면 검사하지 않는다.
        공간 자체를 열 수 없는 문제(폴더 없음 등)는 프로필 이슈가 아니라서 내지 않는다.
        """
        definitions_for = getattr(self.starter, "definitions_for", None)
        find_graph = getattr(self.starter, "find_graph", None)
        if definitions_for is None and find_graph is None:
            return []
        if definitions_for is not None:
            try:
                definitions_for(ctx.space, profile.graph)
            except Exception as exc:
                error = getattr(exc, "error", None)
                if getattr(error, "code", None) != ErrorCodes.PROJECT_NOT_IMPORTED:
                    return []
                in_library = bool((getattr(error, "details", None) or {}).get("in_library"))
                return [_graph_missing(ctx, profile, in_library=in_library)]
        if find_graph is not None and find_graph(profile.graph, project_id=ctx.space) is None:
            return [_graph_missing(ctx, profile, in_library=False)]
        return []

    def task_issues(self, ctx: SpecContext, tasks: Sequence[ParsedTask]) -> list[SpecIssue]:
        """결과 반영 실패 정보 이슈(``sdd.status_not_applied``).

        ``mod-sdd``가 작업 보기에 싣는다."""
        keys = [t.key for t in tasks]
        found = self.reflector.issues(ctx.space, ctx.spec.id, keys)
        if self.automation is not None:
            found.extend(self.automation.task_issues(ctx.space, ctx.spec.id, keys))
        return found

    # ------------------------------------------------------------ 자동 진행(AutomationControl)
    def automation_state(self, ctx: SpecContext) -> AutomationState | None:
        """자동 진행 상태(§6R.18 Q7, 선택 능력 ``AutomationControl``). 자동 진행이 없으면 None."""
        if self.automation is None:
            return None
        return self.automation.automation_state(ctx)

    async def control(self, ctx: SpecContext, op: str) -> AutomationState | None:
        """자동 진행 멈춤(``stop``)·다시 시작(``resume``). 자동 진행이 없거나 모르는 ``op``면
        None."""
        if self.automation is None:
            return None
        return await self.automation.control(ctx, op)


def _graph_missing(ctx: SpecContext, profile: RunProfile, *, in_library: bool) -> SpecIssue:
    message = (
        f"실행 프로필 '{profile.id}'의 팀 구성 '{profile.graph}'이(가) 이 프로젝트에 없습니다."
        + (" 공용 구성에서 가져오면 실행할 수 있습니다." if in_library else "")
    )
    return SpecIssue(
        severity="warning",
        code=KnownIssueCodes.SDD_PROFILE_GRAPH_MISSING,
        message=message,
        path=_profile_path(ctx, profile) + "/graph",
        details={"profile": profile.id, "graph": profile.graph, "in_library": in_library},
    )


def _profile_path(ctx: SpecContext, profile: RunProfile) -> str:
    """규칙 검사(``check_rules``)와 같은 위치(``/run_profiles/<순번>``)."""
    for i, item in enumerate(ctx.spec.rules.run_profiles or ()):
        if item.id == profile.id:
            return f"/run_profiles/{i}"
    return "/run_profiles"


def start_issue(exc: BaseException) -> Issue:
    """실행 시작 예외 → 오류 이슈(코드·사용자 문구·세부, 입력 값 없음).

    - ``error`` 속성(``ErrorInfo``: 사전 점검·정의 출처 — 예: 422 ``project.not_imported``) → 그
      본문.
    - ``code`` 속성(정의 읽기 등) → 그 코드 + ``issues``.
    - ``issues``만(그래프 검증) → ``validation_failed`` + ``issues``.
    - 그 밖 → ``internal``(예외 문장은 싣지 않는다).
    """
    error = getattr(exc, "error", None)
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return Issue(
            severity="error",
            code=code,
            message=str(getattr(error, "message", "") or ""),
            details=dict(getattr(error, "details", None) or {}),
        )
    issues = [_plain(i) for i in getattr(exc, "issues", None) or () if isinstance(i, Issue)]
    details: dict[str, Any] = {"issues": issues} if issues else {}
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return Issue(severity="error", code=code, message=str(exc), details=details)
    if issues:
        return Issue(
            severity="error",
            code=ErrorCodes.VALIDATION_FAILED,
            message="팀 구성에 실행을 막는 문제가 있습니다.",
            details=details,
        )
    return Issue(severity="error", code=ErrorCodes.INTERNAL, message="실행을 시작하지 못했습니다.")


def _failed(
    task: ParsedTask, code: str, message: str, details: Mapping[str, Any] | None = None
) -> TaskActionResult:
    return TaskActionResult(
        task_key=task.key,
        status=KnownTaskActionStatuses.FAILED,
        issue=Issue(severity="error", code=code, message=message, details=dict(details or {})),
    )


def _plain(issue: Issue) -> dict[str, Any]:
    dumped: dict[str, Any] = issue.model_dump(mode="json", exclude_none=True)
    return dumped


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strings(item)


__all__ = ["SECRET_REJECT", "RunsTaskIntegration", "start_issue"]
