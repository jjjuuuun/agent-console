"""Run별 기록 직렬화기: "저장 후 발행"을 지키고 이벤트를 묶어 저장한다(내부 모듈)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from agent_console_contracts import RunEvent, parse_run_event

from ._interfaces import Clock, EventSink, IdFactory, RunRecorder

_log = logging.getLogger(__name__)


class RecorderError(RuntimeError):
    """저장소 기록이 실패했다(원인은 `__cause__`). 이후 기록은 버려진다."""


@dataclass(slots=True)
class _Op:
    fn: Callable[[], object]


@dataclass(slots=True)
class _Barrier:
    future: asyncio.Future[None]


@dataclass(slots=True)
class _Call:
    fn: Callable[[], Any]
    future: asyncio.Future[Any]


type _Item = RunEvent | _Op | _Barrier | _Call


class RunJournal:
    """한 Run의 모든 기록(Run·NodeRun·이벤트·라우팅)을 들어온 순서대로 처리한다.

    - 연속된 이벤트는 `events.append_many` 한 번(워커 스레드)으로 저장한 뒤 순서대로 발행한다.
    - 저장소 호출은 이 Run 안에서 한 번에 하나다(저장소 구현의 스레드 안전 부담을 줄인다).
    - `seq`는 `event()`를 부를 때 즉시 매긴다(같은 이벤트 루프 안에서 순서 보장).
    """

    def __init__(
        self,
        run_id: str,
        recorder: RunRecorder,
        sink: EventSink | None,
        *,
        clock: Clock,
        ids: IdFactory,
        redact: Callable[[Any], Any] | None = None,
        start_seq: int = 0,
        observe: Callable[[RunEvent], None] | None = None,
    ) -> None:
        """`observe`: `event()`가 이벤트를 만들 때마다(저장 전, 비밀을 가린 값) 부르는 함수."""
        self.run_id = run_id
        self._observe = observe
        self._recorder = recorder
        self._sink = sink
        self._clock = clock
        self._ids = ids
        self._redact = redact
        self._seq = start_seq
        self._queue: asyncio.Queue[_Item] = asyncio.Queue()
        self._error: BaseException | None = None
        self._writer = asyncio.create_task(self._run_writer(), name=f"journal:{run_id}")

    @property
    def recorder(self) -> RunRecorder:
        """기록 대상 저장 묶음."""
        return self._recorder

    @property
    def last_seq(self) -> int:
        """마지막으로 매긴 seq."""
        return self._seq

    def event(
        self,
        type: str,
        payload: Mapping[str, Any] | BaseModel | None = None,
        *,
        node_path: list[str] | None = None,
        attempt: int | None = None,
        actor: str | None = None,
        raw: Any = None,
        evidence: str = "observed",
    ) -> RunEvent:
        """이벤트를 만들어 기록 줄에 넣고 돌려준다. 알려진 type이면 payload 형식을 검증한다.

        Raises:
            pydantic.ValidationError: 알려진 type의 payload가 형식에 맞지 않을 때.
        """
        if isinstance(payload, BaseModel):
            body: Any = payload.model_dump(mode="json", by_alias=True)
        else:
            body = dict(payload or {})
        if self._redact is not None:
            body, raw = self._redact(body), self._redact(raw)
        draft = {
            "event_id": self._ids(),
            "run_id": self.run_id,
            "seq": self._seq + 1,
            "ts": self._clock(),
            "type": type,
            "node_path": list(node_path or []),
            "attempt": attempt,
            "actor": actor,
            "evidence": evidence,
            "raw": raw,
            "payload": body,
        }
        parse_run_event(draft)  # 알려진 type의 payload 형식 검사(실패 시 seq 소비 안 함)
        event = RunEvent.model_validate(draft)
        self._seq += 1
        self._queue.put_nowait(event)
        if self._observe is not None:
            self._observe(event)
        return event

    def save[M: BaseModel](self, write: Callable[[M], object], record: M) -> None:
        """기록 하나를 저장소에 쓰는 작업을 줄에 넣는다. 저장 전에 비밀 값을 가린 사본을 만든다.

        Run·NodeRun 등 저장되는 모든 모델은 이 경로를 거친다(이벤트는 `event`).
        """
        stored = self.redact_model(record)
        self.op(lambda: write(stored))

    def redact_model[M: BaseModel](self, record: M) -> M:
        """비밀 값을 가린 모델 사본(가릴 것이 없으면 그대로)."""
        if self._redact is None:
            return record
        data = record.model_dump(mode="json", by_alias=True)
        redacted = self._redact(data)
        if redacted == data:
            return record
        return type(record).model_validate(redacted)

    def redact(self, value: Any) -> Any:
        """비밀 값을 가린 사본(해석기가 없으면 그대로)."""
        return value if self._redact is None else self._redact(value)

    def call[T](self, fn: Callable[[], T]) -> asyncio.Future[T]:
        """저장소 호출 하나를 줄에 넣고 그 결과를 받을 future를 돌려준다.

        `op`와 달리 예외가 Run 기록을 멈추지 않는다. 예외는 future로 호출자에게 간다
        (조건부 갱신의 "이미 닫힘"처럼 호출자가 해석할 결과). 이미 기록이 실패한 뒤면
        `RecorderError`.
        """
        future: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        self._queue.put_nowait(_Call(fn, future))
        return future

    def op(self, fn: Callable[[], object]) -> None:
        """저장소 호출 하나를 기록 줄에 넣는다(이전 항목이 처리된 뒤 실행)."""
        self._queue.put_nowait(_Op(fn))

    async def flush(self) -> None:
        """지금까지 넣은 항목이 모두 저장·발행될 때까지 기다린다.

        Raises:
            RecorderError: 기록 중 저장소 예외가 있었을 때.
        """
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._queue.put_nowait(_Barrier(future))
        await future

    async def close(self) -> None:
        """남은 항목을 처리하고 워커를 멈춘다. 기록 오류가 있었으면 `RecorderError`."""
        try:
            await self.flush()
        finally:
            self._writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer

    async def _run_writer(self) -> None:
        while True:
            item = await self._queue.get()
            batch: list[_Item] = [item]
            while not self._queue.empty():
                batch.append(self._queue.get_nowait())
            await self._process(batch)

    async def _process(self, batch: list[_Item]) -> None:
        events: list[RunEvent] = []
        for item in batch:
            if isinstance(item, RunEvent):
                events.append(item)
                continue
            await self._write_events(events)
            events = []
            if isinstance(item, _Op):
                if self._error is None:
                    try:
                        await asyncio.to_thread(item.fn)
                    except Exception as exc:
                        self._fail(exc)
            elif isinstance(item, _Call):
                await self._call(item)
            elif not item.future.done():
                if self._error is None:
                    item.future.set_result(None)
                else:
                    err = RecorderError(f"Run {self.run_id} 기록 실패")
                    err.__cause__ = self._error
                    item.future.set_exception(err)
        await self._write_events(events)

    async def _call(self, item: _Call) -> None:
        if item.future.done():
            return
        if self._error is not None:
            err = RecorderError(f"Run {self.run_id} 기록 실패")
            err.__cause__ = self._error
            item.future.set_exception(err)
            return
        try:
            result = await asyncio.to_thread(item.fn)
        except Exception as exc:
            if not item.future.done():
                item.future.set_exception(exc)
            return
        if not item.future.done():
            item.future.set_result(result)

    async def _write_events(self, events: list[RunEvent]) -> None:
        if not events or self._error is not None:
            return
        try:
            await asyncio.to_thread(self._recorder.events.append_many, events)
        except Exception as exc:
            self._fail(exc)
            return
        if self._sink is None:
            return
        for event in events:
            try:
                self._sink.publish(event)
            except Exception:
                _log.exception("이벤트 발행 실패 (run=%s seq=%s)", event.run_id, event.seq)

    def _fail(self, exc: BaseException) -> None:
        _log.error("Run %s 기록 실패: %r", self.run_id, exc)
        self._error = exc
