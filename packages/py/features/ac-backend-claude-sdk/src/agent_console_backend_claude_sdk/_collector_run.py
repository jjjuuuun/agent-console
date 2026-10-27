"""실행 하나에서 켜진 관측 수집기(X7)를 부르는 디스패처. 백엔드 내부 부품이지만 단독으로 쓸 수 있다.

- 수집기 예외는 삼키고 실행마다 수집기별 경고 하나(`log.warning`)로 남긴다(실행에 영향 없음).
- 이벤트 내보내기 실패(sink 오류)도 삼킨다(관측은 실행을 멈추지 않는다, design §8.3).
- 수집기 이름으로 분기하지 않는다. 켜진 목록은 설정 해석 결과(`ResolvedCollector`)에서 온다.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any

from agent_console_contracts import LogWarningPayload

from ._collector_api import ClaudeSdkCollector, CollectedEvent, CollectorContext, ResolvedCollector

__all__ = ["COLLECTOR_ERROR_MESSAGE", "CollectorRun"]

COLLECTOR_ERROR_MESSAGE = "관측 수집기에서 오류가 나 그 항목을 건너뜁니다(실행은 계속합니다)"
"""수집기 예외 경고 문장. 같은 실행에서 같은 수집기의 다음 오류는 알리지 않는다."""

type EventOut = Callable[[CollectedEvent], Awaitable[object]]
type WarningOut = Callable[[LogWarningPayload], Awaitable[object]]
type HookCallback = Callable[[Any, str | None, Any], Awaitable[dict[str, Any]]]


class CollectorRun:
    """켜진 수집기 목록과 실행 하나.

    Args:
        collectors: 사용할 수 있는 수집기(id = `descriptor.id`).
        settings: 해석한 관측 설정(`resolve_collector_settings`). `enabled`인 것만 쓴다.
            모르는 id는 무시한다(설정 검증이 경고한다).
        clock: 소요 시간 측정 시각 함수.
        redact: payload 값 가리기.
        out: 수집 이벤트를 내보낼 곳(백엔드가 raw 정제·서브에이전트 귀속을 한다).
        warn: 경고를 내보낼 곳.
    """

    def __init__(
        self,
        collectors: Iterable[ClaudeSdkCollector],
        settings: Mapping[str, ResolvedCollector],
        *,
        clock: Callable[[], float],
        redact: Callable[[Any], Any],
        out: EventOut,
        warn: WarningOut,
    ) -> None:
        self._out = out
        self._warn = warn
        self._warned: set[str] = set()
        self._pending_warnings: list[LogWarningPayload] = []
        self._active: list[tuple[ClaudeSdkCollector, CollectorContext]] = []
        for collector in collectors:
            setting = settings.get(collector.descriptor.id)
            if setting is None or not setting.enabled:
                continue
            ctx = CollectorContext(
                collector_id=collector.descriptor.id,
                config=dict(setting.config),
                clock=clock,
                redact=redact,
            )
            self._active.append((collector, ctx))
        self._events: dict[str, list[tuple[ClaudeSdkCollector, CollectorContext]]] = {}
        self._include_hook_events = False
        for collector, ctx in self._active:
            try:
                events = list(collector.hook_events(ctx.config))
                include = bool(collector.include_hook_events(ctx.config))
            except Exception as exc:
                self._note_error(ctx.collector_id, "setup", exc)
                continue
            self._include_hook_events = self._include_hook_events or include
            for event in events:
                self._events.setdefault(event, []).append((collector, ctx))

    @property
    def include_hook_events(self) -> bool:
        """켜진 수집기 중 하나라도 CLI 설정 hook 실행 메시지를 원하는지."""
        return self._include_hook_events

    def hook_events(self) -> list[str]:
        """관측 콜백을 걸 SDK 훅 이벤트 이름(처음 나온 순서)."""
        return list(self._events)

    def hook_callback(self, event: str) -> HookCallback:
        """이벤트 하나의 SDK 훅 콜백(`(input, tool_use_id, context) -> {}`). 이 이벤트를 원하는
        수집기를 차례로 부른다. 항상 `{}`(실행에 개입하지 않음)."""

        async def callback(
            input_data: Any, tool_use_id: str | None, context: Any
        ) -> dict[str, Any]:
            data: Mapping[str, Any] = input_data if isinstance(input_data, Mapping) else {}
            for collector, ctx in self._events.get(event, ()):
                try:
                    await collector.on_hook(event, data, tool_use_id, ctx)
                except Exception as exc:
                    self._note_error(ctx.collector_id, "on_hook", exc)
                await self._flush(ctx)
            await self.flush_warnings()
            return {}

        return callback

    async def on_message(self, message: object) -> None:
        """SDK 메시지 하나를 켜진 수집기 모두에 넘기고 낸 이벤트를 내보낸다."""
        for collector, ctx in self._active:
            try:
                collector.on_message(message, ctx)
            except Exception as exc:
                self._note_error(ctx.collector_id, "on_message", exc)
            await self._flush(ctx)
        await self.flush_warnings()

    async def flush_warnings(self) -> None:
        """쌓인 수집기 오류 경고를 내보낸다(설정 단계 오류는 실행 시작 때 백엔드가 부른다)."""
        pending, self._pending_warnings = self._pending_warnings, []
        for warning in pending:
            with contextlib.suppress(Exception):
                await self._warn(warning)

    async def _flush(self, ctx: CollectorContext) -> None:
        for event in ctx.drain():
            with contextlib.suppress(Exception):
                await self._out(event)

    def _note_error(self, collector_id: str, stage: str, exc: Exception) -> None:
        if collector_id in self._warned:
            return
        self._warned.add(collector_id)
        # 예외 메시지는 싣지 않는다(입력 값·비밀이 섞일 수 있다).
        self._pending_warnings.append(
            LogWarningPayload(
                message=COLLECTOR_ERROR_MESSAGE,
                details={"collector": collector_id, "stage": stage, "error": type(exc).__name__},
            )
        )
