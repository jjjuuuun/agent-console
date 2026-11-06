"""실행 결과 → 작업 상태 반영(design §6R.1.5 "결과 반영", §6R.18 Q12, K6R-5·K6R-6).

이 연동이 시작한 루트 Run만 따라간다(``track``). 상태 반영 이벤트(설치자 옵션 ``status_events``)가
오면 그 Run 상태를 결과 이름(``run_outcomes``)으로 바꾸고, **그때의 스펙 규칙**에서 실행 프로필을
찾아 ``status_on[결과]``(없으면 ``status_on[실행 상태]``)가 있을 때만 작업 머리 줄 하나를 고친다
(``patch_task(by="run")``). 줄 해시는 실행을 시작할 때 읽은 값이다 — 실행 중에 사람·에이전트가 그
작업 줄을 고쳤으면 고치지 않는다. 이 연동이 바꾼 뒤에는 새 줄 해시로 이어 간다.

고치지 못하면(줄 바뀜·작업 없음·관문 ``task_status``·폴더를 쓸 수 없음 등) 실패로 끝내지 않고 정보
이슈 ``sdd.status_not_applied``(``details.reason``, 관문이면 ``details.gate_id``)를 그 작업에
남긴다.
같은 작업이 나중에 반영되면 지운다. 이슈는 메모리에만 있다(실행 결과는 라벨로 늘 보인다).

이벤트 처리는 동기다(파일 쓰기 한 번 — 상태 이벤트는 실행마다 몇 개뿐). 시작 요청이 끝나기 전에 온
이벤트는 잠깐 모았다가 ``track`` 때 다시 적용한다.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import RunEvent
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.sdd import KnownTransitionActors, SpecIssue
from agent_console_sdd import GateBlockedError, TaskChangedError, find_task

from .ports import SddServicePort

_log = logging.getLogger(__name__)

REASON_TASK_CHANGED = "task_changed"
"""``details.reason``: 실행 중에 작업 줄이 바뀌었거나 작업이 없어졌다."""
REASON_GATE_BLOCKED = "gate_blocked"
"""``details.reason``: ``task_status`` 관문이 막았다(``details.gate_id``)."""
REASON_ERROR = "error"
"""``details.reason``: 그 밖에 고치지 못했다(``details.code`` = 예외 코드)."""

_MAX_EARLY_EVENTS = 256


@dataclass
class TrackedRun:
    """이 연동이 시작한 루트 Run 하나(메모리).

    Attributes:
        run_id: 루트 Run id. space: 공간 이름(단독 루트면 None). spec_id·task_key·profile_id:
            라벨과 같은 값. line_hash: 다음 반영에 쓸 작업 머리 줄 해시. outcome: 마지막으로 처리한
            결과 이름. status: 마지막 실행 상태.
    """

    run_id: str
    space: str | None
    spec_id: str
    task_key: str
    profile_id: str
    line_hash: str
    outcome: str | None = None
    status: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


type RunListener = Callable[[TrackedRun, str, bool], None]
"""``(실행, 결과 이름, 끝났나)`` — 반영 뒤에 부른다(자동 진행 6R.16 자리)."""


class StatusReflector:
    """실행 상태 이벤트 → 작업 상태 반영.

    Args:
        sdd: 스펙 서비스(``sdd.service``).
        run_outcomes: 실행 상태 → 결과 이름(설치자 옵션).
        status_events: 반영할 이벤트 종류(설치자 옵션, 빈 목록 = 반영 안 함).
        finished_statuses: 끝난 실행 상태(끝나면 따라가기를 멈춘다).
        max_issues: 기억할 이슈 수 상한(오래된 것부터 뺀다).
    """

    def __init__(
        self,
        sdd: SddServicePort,
        *,
        run_outcomes: Mapping[str, str],
        status_events: Iterable[str],
        finished_statuses: Iterable[str],
        max_issues: int,
    ) -> None:
        self._sdd = sdd
        self._outcomes = dict(run_outcomes)
        self._events = frozenset(status_events)
        self._finished = frozenset(finished_statuses)
        self._max_issues = max(1, max_issues)
        self._runs: dict[str, TrackedRun] = {}
        self._issues: OrderedDict[tuple[str | None, str, str], SpecIssue] = OrderedDict()
        self._starting = 0
        self._early: OrderedDict[str, list[RunEvent]] = OrderedDict()
        self._early_count = 0
        self._listeners: list[RunListener] = []

    # ------------------------------------------------------------ 결과 이름
    def outcome_of(self, status: str) -> str:
        """실행 상태 → 결과 이름(표에 없으면 상태 그대로)."""
        return self._outcomes.get(status, status)

    # ------------------------------------------------------------ 따라가기
    def begin_start(self) -> None:
        """실행 시작 요청 앞(이 사이에 온 모르는 Run의 상태 이벤트를 모은다)."""
        self._starting += 1

    def end_start(self) -> None:
        """실행 시작 요청 뒤(시작 중인 요청이 없으면 모은 이벤트를 버린다)."""
        self._starting = max(0, self._starting - 1)
        if self._starting == 0:
            self._early.clear()
            self._early_count = 0

    def track(self, run: TrackedRun) -> None:
        """따라갈 Run을 등록하고, 시작 요청 중에 먼저 온 그 Run의 이벤트를 적용한다."""
        self._runs[run.run_id] = run
        early = self._early.pop(run.run_id, [])
        self._early_count -= len(early)
        for event in early:
            self.on_event(event)

    def active(self, space: str | None, spec_id: str) -> list[TrackedRun]:
        """그 스펙에서 따라가는(끝나지 않은) Run."""
        return [r for r in self._runs.values() if r.space == space and r.spec_id == spec_id]

    def add_listener(self, listener: RunListener) -> Callable[[], None]:
        """반영 뒤 알림을 받는다(돌려준 함수로 해제). 처리기 예외는 기록만 한다."""
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    # ------------------------------------------------------------ 이슈
    def issues(self, space: str | None, spec_id: str, keys: Iterable[str]) -> list[SpecIssue]:
        """그 작업들에 남은 ``sdd.status_not_applied`` 이슈."""
        out: list[SpecIssue] = []
        for key in keys:
            found = self._issues.get((space, spec_id, key))
            if found is not None:
                out.append(found)
        return out

    def _remember(self, run: TrackedRun, issue: SpecIssue) -> None:
        key = (run.space, run.spec_id, run.task_key)
        self._issues.pop(key, None)
        self._issues[key] = issue
        while len(self._issues) > self._max_issues:
            self._issues.popitem(last=False)

    def _forget(self, run: TrackedRun) -> None:
        self._issues.pop((run.space, run.spec_id, run.task_key), None)

    # ------------------------------------------------------------ 이벤트
    def on_event(self, event: RunEvent) -> None:
        """``runs.event`` 구독 처리기(동기). 따라가는 루트 Run의 상태 이벤트만 본다."""
        if event.node_path or event.type not in self._events:
            return
        status = event.payload.get("status")
        if not isinstance(status, str) or not status:
            return
        run = self._runs.get(event.run_id)
        if run is None:
            if self._starting > 0:
                self._keep_early(event)
            return
        self.apply(run, status)

    def _keep_early(self, event: RunEvent) -> None:
        self._early.setdefault(event.run_id, []).append(event)
        self._early.move_to_end(event.run_id)
        self._early_count += 1
        while self._early_count > _MAX_EARLY_EVENTS and self._early:
            _, dropped = self._early.popitem(last=False)
            self._early_count -= len(dropped)

    def apply(self, run: TrackedRun, status: str) -> None:
        """실행 상태 하나를 반영한다(같은 결과가 이어지면 한 번만)."""
        outcome = self.outcome_of(status)
        finished = status in self._finished
        if finished:
            self._runs.pop(run.run_id, None)
        if outcome == run.outcome:
            return
        run.outcome, run.status = outcome, status
        try:
            self._reflect(run, outcome, status)
        except Exception:  # pragma: no cover - 방어: 반영 실패가 실행 이벤트 흐름을 깨지 않게
            _log.exception("작업 상태 반영 실패: %s", run.run_id)
        for listener in list(self._listeners):
            try:
                listener(run, outcome, finished)
            except Exception:
                _log.exception("실행 결과 알림 처리기 실패")

    def _reflect(self, run: TrackedRun, outcome: str, status: str) -> None:
        try:
            scope = self._sdd.scope(run.space)
            repo = scope.repository
            loaded = repo.load(run.spec_id)
        except Exception as exc:
            self._not_applied(run, outcome, None, REASON_ERROR, code=_code(exc))
            return
        profile = next(
            (p for p in loaded.spec.rules.run_profiles or () if p.id == run.profile_id), None
        )
        if profile is None:
            return
        target = profile.status_on.get(outcome)
        if target is None and outcome != status:
            target = profile.status_on.get(status)
        if not target:
            return  # status_on 비움 = 상태를 바꾸지 않는다(K6R-6)
        task = find_task(loaded.index, run.task_key)
        if task is not None and task.line_hash == run.line_hash and task.status == target:
            self._forget(run)
            return
        try:
            result = repo.patch_task(
                run.spec_id,
                run.task_key,
                expected_line_hash=run.line_hash,
                status=target,
                by=KnownTransitionActors.RUN,
                message=f"작업 {run.task_key} 상태 ← 실행 {run.run_id} ({outcome})",
            )
        except GateBlockedError as exc:
            self._not_applied(
                run, outcome, target, REASON_GATE_BLOCKED, gate_id=exc.blocked.gate_id
            )
        except TaskChangedError:
            self._not_applied(run, outcome, target, REASON_TASK_CHANGED)
        except Exception as exc:
            self._not_applied(run, outcome, target, REASON_ERROR, code=_code(exc))
        else:
            run.line_hash = result.task.line_hash
            self._forget(run)
            self._sdd.notify(run.space, run.spec_id, version_hash=result.version_hash)

    def _not_applied(
        self,
        run: TrackedRun,
        outcome: str,
        target: str | None,
        reason: str,
        *,
        gate_id: str | None = None,
        code: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"run_id": run.run_id, "outcome": outcome, "reason": reason}
        if target is not None:
            details["status"] = target
        if gate_id is not None:
            details["gate_id"] = gate_id
        if code is not None:
            details["code"] = code
        self._remember(
            run,
            SpecIssue(
                severity="info",
                code=KnownIssueCodes.SDD_STATUS_NOT_APPLIED,
                message=_MESSAGES.get(reason, _MESSAGES[REASON_ERROR]),
                task_key=run.task_key,
                details=details,
            ),
        )
        try:
            self._sdd.notify(run.space, run.spec_id)
        except Exception:  # pragma: no cover - 알림 실패는 무시
            _log.exception("sdd.changed 알림 실패")


_MESSAGES: dict[str, str] = {
    REASON_TASK_CHANGED: "실행 중에 작업 줄이 바뀌어 실행 결과로 상태를 바꾸지 않았습니다.",
    REASON_GATE_BLOCKED: "관문이 막아 실행 결과로 상태를 바꾸지 않았습니다.",
    REASON_ERROR: "작업 문서를 고칠 수 없어 실행 결과로 상태를 바꾸지 않았습니다.",
}


def _code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else "internal"


__all__ = [
    "REASON_ERROR",
    "REASON_GATE_BLOCKED",
    "REASON_TASK_CHANGED",
    "RunListener",
    "StatusReflector",
    "TrackedRun",
]
