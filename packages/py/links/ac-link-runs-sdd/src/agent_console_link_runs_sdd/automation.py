"""자동 진행(design §6R.1.5 ``automation``, §6R.18 Q7 — 선택, 기본 꺼짐).

스펙 규칙 ``rules.automation{enabled, profile, max_parallel, max_failures, scope}``가 켜져 있을 때만
움직인다. 꺼져 있으면(기본) 아무 실행도 시작하지 않는다.

- **차례**(``tick``): 그 스펙을 다시 읽고 ``ready`` 작업(문서 순서)을 ``max_parallel``까지 시작한다
  (``RunsTaskIntegration.start`` — 관문·입력·비밀·라벨·시작). 같은 스펙 차례는 한 번에 하나만 돈다.
  진행 중 실행 = 이 앱이 따라가는 그 스펙 Run(``StatusReflector.active`` — 사람이 시작한 것 포함).
  실행 중인 작업, 건너뛴 작업, 결과가 "정착"한 작업(실패도 다시 시작도 아닌 결과로 끝나고 그 뒤로
  작업 줄이 그대로)은 시작하지 않는다.
- **언제 도나**: 따라가는 실행이 끝날 때마다(``add_listener``), [다시 시작], 스펙 보기
  (``automation_state`` — 자리가 있고 시작할 작업이 보이면 한 번), 앱 시작(단독 루트 스펙).
- **실패**: 결과 이름이 설치자 옵션 ``automation_failure_outcomes``이면 그 작업의 연속 실패 +1,
  시작 자체가 실패(관문이 아닌 오류)해도 +1. ``max_failures``에 닿으면 건너뛰고 정보 이슈
  ``sdd.automation_skipped``를 남긴다. ``automation_retry_outcomes``(기본 끊김)는 세지 않고 다시
  시작한다. 관문에 막힌 작업은 실패로 세지 않고 기다린다(문서가 바뀌면 다음 차례에 다시 본다).
- **멈춤**(``stopped_reason``, 문서 상수 ``KnownAutomationStopReasons``): ``user``([멈춤]),
  ``spec_done``(모든 작업 끝), ``stage_done``(``scope: stage``에서 그 단계 끝), ``failures``(진행 중
  실행이 없고 건너뛴 작업 때문에 더 시작할 작업이 없음). 멈춤은 새 실행만 막고 진행 중 실행은
  끊지 않는다. [다시 시작]은 멈춤·실패 수·건너뜀을 지우고 단계를 다시 고른다.
- **재시작 뒤**: 상태는 메모리에만 있다(스펙에 저장하지 않는다 — §6R.18 Q7). 앱을 다시 시작하면
  켜진 스펙은 설정대로 이어 간다: 스펙을 처음 볼 때 실행 기록(스펙 라벨)에서 **자기 앱**
  (``host_id``) Run만 골라 연속 실패 수와 정착한 작업을 되살린다. 다른 앱의 Run은 세지 않는다.
  이 프로세스가 따라가지 않는 끝나지 않은 자기 Run은 이전 프로세스에서 끊긴 것으로 본다(다시 시작
  결과). [멈춤]은 재시작 뒤에 이어지지 않는다.

상태가 바뀔 때마다 ``sdd.changed``(``automation=True``)를 낸다. 이벤트 처리기(동기, 어느
스레드든)는 차례를 이벤트 루프에 맡긴다(``bind``로 준 루프 또는 지금 도는 루프).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Callable, Coroutine, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts.sdd import (
    AutomationConfig,
    AutomationState,
    KnownAutomationStopReasons,
    KnownTaskActionStatuses,
    ParsedTask,
    RunProfile,
    SpecIssue,
)
from agent_console_sdd import SpecContext, gate_context

from .integration import RunsTaskIntegration
from .ports import LABEL_PROFILE, LABEL_TASK, SddServicePort
from .reflect import StatusReflector, TrackedRun

_log = logging.getLogger(__name__)

AUTOMATION_SKIPPED = "sdd.automation_skipped"
"""정보 이슈 코드: 자동 진행이 연속 실패 상한에 닿은 작업을 건너뛰었다(``details{failures,
run_id?}``). 계약 ``KnownIssueCodes``에 아직 없다(열린 문자열)."""

OP_STOP = "stop"
OP_RESUME = "resume"

SCOPE_STAGE = "stage"

_INTERRUPTED = "interrupted"
"""재시작 뒤 끝나지 않은 자기 Run을 볼 실행 상태(계약 ``RunStatus`` 어휘 — 결과 이름은
``run_outcomes``가 바꾼다)."""

type SpecKey = tuple[str | None, str]
type HostIdOf = Callable[[str | None], str | None]


@dataclass
class _State:
    enabled: bool = False
    stopped_reason: str | None = None
    failures: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    settled: dict[str, str] = field(default_factory=dict)
    """작업 키 → 정착했을 때의 작업 머리 줄 해시."""
    stage: str | None = None
    restored: bool = False
    last_failed: dict[str, str] = field(default_factory=dict)
    """작업 키 → 마지막으로 실패한 Run id(건너뜀 이슈 ``details.run_id``)."""
    seen: set[str] = field(default_factory=set)
    """이미 센 Run id(기록에서 되살릴 때 두 번 세지 않는다)."""


class SpecAutomation:
    """스펙 자동 진행(메모리 상태). ``RunsTaskIntegration``이 ``automation_state``·``control``로
    낸다(``AutomationControl``).

    Args:
        sdd: 스펙 서비스(``sdd.service``).
        integration: 작업 실행(``start``·``profile``·``applies``·``spec_runs``).
        reflector: 따라가는 Run(``active``·``add_listener``·``outcome_of``).
        finished_statuses: 끝난 실행 상태.
        failure_outcomes: 실패로 셀 결과 이름. retry_outcomes: 세지 않고 다시 시작할 결과 이름.
        host_id: 공간 이름 → 이 앱의 ``host_id``(실행 기록에서 자기 Run만 고른다). None이면 고르지
            않는다(모두 자기 것으로 본다).
        loop: 차례를 돌릴 이벤트 루프(None = 처리기를 부른 스레드의 도는 루프, ``bind``로 바꾼다).
    """

    def __init__(
        self,
        *,
        sdd: SddServicePort,
        integration: RunsTaskIntegration,
        reflector: StatusReflector,
        finished_statuses: Iterable[str],
        failure_outcomes: Iterable[str],
        retry_outcomes: Iterable[str],
        host_id: HostIdOf | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._sdd = sdd
        self._integration = integration
        self._reflector = reflector
        self._finished = frozenset(finished_statuses)
        self._failure = frozenset(failure_outcomes)
        self._retry = frozenset(retry_outcomes)
        self._host_id = host_id
        self._loop = loop
        self._states: dict[SpecKey, _State] = {}
        self._locks: dict[SpecKey, asyncio.Lock] = {}
        self._queued: set[SpecKey] = set()
        self._futures: set[concurrent.futures.Future[None]] = set()
        self._guard = threading.Lock()
        self._remove_listener = reflector.add_listener(self.on_run)

    # ------------------------------------------------------------ 루프
    def bind(self, loop: asyncio.AbstractEventLoop | None) -> None:
        """차례를 돌릴 이벤트 루프(모듈 시작 때 넣고 종료 때 뺀다)."""
        self._loop = loop

    def close(self) -> None:
        """실행 알림 구독을 푼다."""
        self._remove_listener()

    # ------------------------------------------------------------ AutomationControl
    def automation_state(self, ctx: SpecContext) -> AutomationState:
        """지금 상태(스펙 보기 ``automation_state``). 켜져 있고 시작할 작업이 보이면 차례를 한 번
        맡긴다(재시작 뒤·규칙을 켠 뒤 이어 가기)."""
        key = (ctx.space, ctx.spec.id)
        auto = ctx.spec.rules.automation
        st = self._states.setdefault(key, _State())
        st.enabled = bool(auto is not None and auto.enabled)
        if auto is not None and auto.enabled and self._wants_tick(ctx, st, auto):
            self.kick(ctx.space, ctx.spec.id)
        return self._snapshot(key)

    async def control(self, ctx: SpecContext, op: str) -> AutomationState | None:
        """``stop``: 새 실행만 막는다(진행 중 실행은 그대로). ``resume``: 멈춤·실패 수·건너뜀을
        지우고 차례를 돈다(규칙이 꺼져 있으면 아무것도 시작하지 않는다). 모르는 ``op`` = None."""
        key = (ctx.space, ctx.spec.id)
        if op == OP_STOP:
            before = self._snapshot(key)
            st = self._states.setdefault(key, _State())
            st.stopped_reason = KnownAutomationStopReasons.USER
            self._changed(key, before)
            return self._snapshot(key)
        if op == OP_RESUME:
            async with self._lock(key):
                before = self._snapshot(key)
                st = self._states.setdefault(key, _State())
                st.stopped_reason = None
                st.failures.clear()
                st.skipped.clear()
                st.last_failed.clear()
                st.stage = None
                st.restored = True  # 사용자가 지웠다 — 기록에서 실패 수를 되살리지 않는다
                await self._tick_locked(ctx.space, ctx.spec.id)
                self._changed(key, before)
            return self._snapshot(key)
        return None

    def task_issues(self, space: str | None, spec_id: str, keys: Iterable[str]) -> list[SpecIssue]:
        """건너뛴 작업의 정보 이슈(``sdd.automation_skipped``)."""
        st = self._states.get((space, spec_id))
        if st is None or not st.skipped:
            return []
        wanted = set(keys)
        return [
            _skip_issue(k, st.failures.get(k, 0), st.last_failed.get(k))
            for k in st.skipped
            if k in wanted
        ]

    # ------------------------------------------------------------ 상태
    def state(self, space: str | None, spec_id: str) -> AutomationState:
        """메모리 상태(스펙을 읽지 않는다 — ``enabled``는 마지막으로 본 규칙 값)."""
        return self._snapshot((space, spec_id))

    def _snapshot(self, key: SpecKey) -> AutomationState:
        st = self._states.get(key) or _State()
        active = [r.run_id for r in self._reflector.active(*key)]
        running = st.enabled and st.stopped_reason is None
        return AutomationState(
            enabled=st.enabled,
            running=running,
            active_runs=active,
            skipped_keys=list(st.skipped),
            failures={k: n for k, n in st.failures.items() if n > 0},
            stopped_reason=st.stopped_reason if st.enabled else None,
        )

    def _changed(self, key: SpecKey, before: AutomationState) -> None:
        if self._snapshot(key) == before:
            return
        try:
            self._sdd.notify(key[0], key[1], automation=True)
        except Exception:  # pragma: no cover - 알림 실패가 자동 진행을 깨지 않게
            _log.exception("sdd.changed 알림 실패")

    # ------------------------------------------------------------ 차례 맡기기
    def kick(self, space: str | None, spec_id: str) -> None:
        """그 스펙 차례를 이벤트 루프에 맡긴다(이미 맡겼으면 한 번만). 루프가 없으면 하지 않는다."""
        key = (space, spec_id)
        with self._guard:
            if key in self._queued:
                return
            self._queued.add(key)
        if not self._schedule(lambda: self._queued_tick(key)):
            with self._guard:
                self._queued.discard(key)

    async def _queued_tick(self, key: SpecKey) -> None:
        with self._guard:
            self._queued.discard(key)
        await self.tick(*key)

    def _schedule(self, make: Callable[[], Coroutine[Any, Any, None]]) -> bool:
        loop = self._loop
        try:
            current: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if loop is None:
            loop = current
        if loop is None or loop.is_closed():
            return False
        future = asyncio.run_coroutine_threadsafe(self._guarded(make), loop)
        with self._guard:
            self._futures.add(future)
        future.add_done_callback(self._done)
        return True

    async def _guarded(self, make: Callable[[], Coroutine[Any, Any, None]]) -> None:
        try:
            await make()
        except Exception:
            _log.exception("자동 진행 차례 실패")

    def _done(self, future: concurrent.futures.Future[None]) -> None:
        with self._guard:
            self._futures.discard(future)

    async def idle(self) -> None:
        """맡긴 차례가 모두 끝날 때까지 기다린다(같은 루프 안에서 — 테스트·종료용)."""
        while True:
            with self._guard:
                pending = list(self._futures)
            if not pending:
                return
            await asyncio.gather(*(asyncio.wrap_future(f) for f in pending))

    def join(self, timeout: float = 10.0) -> None:
        """맡긴 차례가 모두 끝날 때까지 기다린다(루프 밖 스레드에서 — 테스트용).

        Raises:
            TimeoutError: ``timeout``초 안에 끝나지 않았다.
        """
        while True:
            with self._guard:
                pending = list(self._futures)
            if not pending:
                return
            _, not_done = concurrent.futures.wait(pending, timeout=timeout)
            if not_done:
                raise TimeoutError("자동 진행 차례가 끝나지 않았습니다")

    # ------------------------------------------------------------ 실행 알림
    def on_run(self, run: TrackedRun, outcome: str, finished: bool) -> None:
        """``StatusReflector`` 알림: 끝난 실행의 결과를 세고 그 스펙 차례를 맡긴다."""
        if not finished:
            return
        done = _Finished(
            space=run.space,
            spec_id=run.spec_id,
            task_key=run.task_key,
            profile_id=run.profile_id,
            run_id=run.run_id,
            line_hash=run.line_hash,
            outcome=outcome,
        )
        key = (run.space, run.spec_id)
        if not self._schedule(lambda: self._after_run(key, done)):
            self._count(key, done)

    async def _after_run(self, key: SpecKey, done: _Finished) -> None:
        async with self._lock(key):
            before = self._snapshot(key)
            self._count(key, done)
            await self._tick_locked(*key)
            self._changed(key, before)

    def _count(self, key: SpecKey, done: _Finished) -> None:
        st = self._states.setdefault(key, _State())
        self._record(st, done.task_key, done.outcome, done.line_hash, done.run_id)

    def _record(
        self, st: _State, task_key: str, outcome: str, line_hash: str | None, run_id: str
    ) -> None:
        """끝난 Run 하나를 센다(같은 Run은 한 번만)."""
        if run_id in st.seen:
            return
        st.seen.add(run_id)
        if outcome in self._failure:
            self._fail(st, task_key, run_id)
        elif outcome in self._retry:
            st.settled.pop(task_key, None)
        else:
            st.failures.pop(task_key, None)
            st.last_failed.pop(task_key, None)
            if line_hash is not None:
                st.settled[task_key] = line_hash

    @staticmethod
    def _fail(st: _State, task_key: str, run_id: str | None) -> None:
        st.failures[task_key] = st.failures.get(task_key, 0) + 1
        st.settled.pop(task_key, None)
        if run_id is not None:
            st.last_failed[task_key] = run_id

    @staticmethod
    def _skip_over(st: _State, max_failures: int) -> None:
        for task_key, n in st.failures.items():
            if n >= max_failures and task_key not in st.skipped:
                st.skipped.append(task_key)

    # ------------------------------------------------------------ 차례
    def _lock(self, key: SpecKey) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        return lock

    async def tick(self, space: str | None, spec_id: str) -> None:
        """그 스펙 차례 한 번(스펙을 다시 읽는다)."""
        key = (space, spec_id)
        async with self._lock(key):
            before = self._snapshot(key)
            await self._tick_locked(space, spec_id)
            self._changed(key, before)

    async def _tick_locked(self, space: str | None, spec_id: str) -> None:
        key = (space, spec_id)
        st = self._states.setdefault(key, _State())
        try:
            scope = self._sdd.scope(space)
            loaded = scope.repository.load(spec_id)
            ctx = self._sdd.context(scope, loaded)
        except Exception:
            _log.info("자동 진행: 스펙을 읽지 못했습니다(%s, %s)", space, spec_id)
            return
        auto = ctx.spec.rules.automation
        st.enabled = bool(auto is not None and auto.enabled)
        if auto is None or not auto.enabled or st.stopped_reason is not None:
            return
        if not st.restored:
            self._restore(ctx, st, auto)
        self._skip_over(st, auto.max_failures)
        done_ids = loaded.compiled.done_ids
        tasks = list(ctx.index.tasks)
        if tasks and all(t.status in done_ids for t in tasks):
            st.stopped_reason = KnownAutomationStopReasons.SPEC_DONE
            return
        pool = tasks
        if auto.scope == SCOPE_STAGE and ctx.index.stages:
            stage = next((s for s in ctx.index.stages if s.id == st.stage), None)
            if stage is None:
                stage = next((s for s in ctx.index.stages if s.done < s.total), None)
                st.stage = stage.id if stage is not None else None
            if stage is None or stage.done >= stage.total:
                if not self._reflector.active(space, spec_id):
                    st.stopped_reason = KnownAutomationStopReasons.STAGE_DONE
                return
            pool = [t for t in tasks if t.stage is not None and t.stage.id == stage.id]
        started_any = await self._start_ready(ctx, st, auto, pool)
        if started_any or self._reflector.active(space, spec_id):
            return
        if st.skipped and not self._candidates(ctx, st, auto, pool):
            st.stopped_reason = KnownAutomationStopReasons.FAILURES

    async def _start_ready(
        self, ctx: SpecContext, st: _State, auto: AutomationConfig, pool: Sequence[ParsedTask]
    ) -> bool:
        started_any = False
        waiting: set[str] = set()  # 관문에 막힌 작업(이번 차례만)
        while True:
            active = self._reflector.active(ctx.space, ctx.spec.id)
            slots = auto.max_parallel - len(active)
            if slots <= 0:
                return started_any
            picks = [c for c in self._candidates(ctx, st, auto, pool) if c[0].key not in waiting]
            if not picks:
                return started_any
            progressed = False
            for task, profile in picks[:slots]:
                if st.stopped_reason is not None:  # 시작 중에 [멈춤]
                    return started_any
                result = await self._integration.start(ctx, task, profile)
                if result.status == KnownTaskActionStatuses.STARTED:
                    started_any = progressed = True
                    st.settled.pop(task.key, None)
                elif result.status == KnownTaskActionStatuses.BLOCKED:
                    waiting.add(task.key)
                else:
                    self._fail(st, task.key, None)  # 시작 자체가 실패(관문이 아닌 오류)
                    self._skip_over(st, auto.max_failures)
                    progressed = True
            if not progressed:
                return started_any

    def _candidates(
        self, ctx: SpecContext, st: _State, auto: AutomationConfig, pool: Sequence[ParsedTask]
    ) -> list[tuple[ParsedTask, RunProfile]]:
        busy = {r.task_key for r in self._reflector.active(ctx.space, ctx.spec.id)}
        out: list[tuple[ParsedTask, RunProfile]] = []
        for task in pool:
            if not task.ready or task.key in busy or task.key in st.skipped:
                continue
            if st.settled.get(task.key) == task.line_hash:
                continue
            profile = self._profile_for(ctx, auto, task)
            if profile is not None:
                out.append((task, profile))
        return out

    def _profile_for(
        self, ctx: SpecContext, auto: AutomationConfig, task: ParsedTask
    ) -> RunProfile | None:
        """``automation.profile``(없으면 이 작업에 맞는 첫 프로필). ``when``이 맞아야 한다."""
        subject = gate_context(ctx.spec, ctx.index, task=task)
        if auto.profile is not None:
            profile = self._integration.profile(ctx, auto.profile)
            if profile is None or not self._integration.applies(ctx, task, profile, subject):
                return None
            return profile
        for profile in ctx.spec.rules.run_profiles or ():
            if self._integration.applies(ctx, task, profile, subject):
                return profile
        return None

    def _wants_tick(self, ctx: SpecContext, st: _State, auto: AutomationConfig) -> bool:
        if st.stopped_reason is not None:
            return False
        if not st.restored:
            return True
        if len(self._reflector.active(ctx.space, ctx.spec.id)) >= auto.max_parallel:
            return False
        return bool(self._candidates(ctx, st, auto, ctx.index.tasks))

    # ------------------------------------------------------------ 재시작 뒤
    def _restore(self, ctx: SpecContext, st: _State, auto: AutomationConfig) -> None:
        """실행 기록에서 자기 앱 Run의 연속 실패 수·정착한 작업을 되살린다(처음 볼 때 한 번)."""
        st.restored = True
        tracked = {r.run_id for r in self._reflector.active(ctx.space, ctx.spec.id)}
        own = self._host_id(ctx.space) if self._host_id is not None else None
        try:
            runs = self._integration.spec_runs(ctx)
        except Exception:
            _log.info("자동 진행: 실행 기록을 읽지 못했습니다(%s, %s)", ctx.space, ctx.spec.id)
            return
        task_label = self._sdd.label_key(LABEL_TASK)
        profile_label = self._sdd.label_key(LABEL_PROFILE)
        lines = {t.key: t.line_hash for t in ctx.index.tasks}
        for run in reversed(runs):  # 오래된 것부터
            if self._host_id is not None and run.host_id != own:
                continue  # 다른 앱(host_id)의 Run은 세지 않는다
            task_key = run.labels.get(task_label)
            if not task_key or run.id in tracked:
                continue
            if auto.profile is not None and run.labels.get(profile_label) != auto.profile:
                continue
            # 이 프로세스가 따라가지 않는 끝나지 않은 자기 Run = 이전 프로세스에서 끊김
            status = run.status if run.status in self._finished else _INTERRUPTED
            outcome = self._reflector.outcome_of(status)
            self._record(st, task_key, outcome, lines.get(task_key), run.id)


@dataclass(frozen=True)
class _Finished:
    space: str | None
    spec_id: str
    task_key: str
    profile_id: str
    run_id: str
    line_hash: str
    outcome: str


def _skip_issue(task_key: str, failures: int, run_id: str | None) -> SpecIssue:
    details: dict[str, Any] = {"failures": failures}
    if run_id is not None:
        details["run_id"] = run_id
    return SpecIssue(
        severity="info",
        code=AUTOMATION_SKIPPED,
        message=f"자동 진행이 연달아 {failures}번 실패한 작업을 건너뛰었습니다.",
        task_key=task_key,
        details=details,
    )


__all__ = ["AUTOMATION_SKIPPED", "OP_RESUME", "OP_STOP", "SpecAutomation"]
