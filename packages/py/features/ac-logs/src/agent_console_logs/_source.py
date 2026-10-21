"""로그 출처(X5)와 분류기(X6) 인터페이스(design §4R.3).

출처는 원본을 읽기만 한다. 파일은 `LogSourceContext.open_read`(주입)로만 연다. 분류기는 행 단위
무상태다(F-7): 원본 행 하나와 맥락만 보고 초안 목록을 돌려준다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable

from agent_console_contracts.logs import LogClassifierDescriptor, LogSourceDescriptor

from ._draft import LogEventDraft
from ._values import JsonValue

__all__ = [
    "DIAGNOSTIC_META_KEY",
    "ClassifyContext",
    "Cursor",
    "LogClassifier",
    "LogSource",
    "LogSourceContext",
    "RawRecord",
    "ReadResult",
    "SourceRef",
    "read_only_open",
]

DIAGNOSTIC_META_KEY = "diagnostic"
"""`RawRecord.meta`의 이 키에 문자열이 있으면 해석 실패 줄이다. 코어는 분류기를 부르지 않고
진단 이벤트(`source = "diagnostic"`, 범주 `error`)를 만든다."""


def read_only_open(path: Path) -> BinaryIO:
    """기본 `open_read`: 읽기 전용 바이너리 열기."""
    return path.open("rb")


@dataclass(frozen=True, slots=True)
class SourceRef:
    """출처 안의 단위(파일 하나, Run 하나).

    Attributes:
        ref: 출처 안에서 안정적인 이름(루트 기준 상대 경로, run id). 응답에는 이것만 싣는다.
        size: 현재 크기(바이트). 모르면 None.
        mtime: 수정 시각(epoch 초). 모르면 None.
        meta: 분류기에 넘길 맥락(thread, parent, role, session, cwd 등). JSON 값만.
    """

    ref: str
    size: int | None = None
    mtime: float | None = None
    meta: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Cursor:
    """이어 읽을 위치. `state`는 출처가 책임지는 작은 JSON 객체."""

    offset: int = 0
    state: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawRecord:
    """원본 행 하나.

    Attributes:
        origin: 나온 단위(`SourceRef.ref`).
        offset: 단위 안 위치(파일이면 줄 시작 바이트). 기본 identity에 들어간다.
        data: 해석한 값(보통 JSON 객체).
        meta: `SourceRef.meta` + 행 맥락. `DIAGNOSTIC_META_KEY`가 있으면 해석 실패 줄.
        generation: 같은 단위의 내용 세대. 단위가 다른 내용으로 바뀌었을 때(회전) 출처가 올린다.
            0이 아니면 기본 identity에 들어가 같은 위치의 새 내용이 옛 행과 겹치지 않는다.
    """

    origin: str
    offset: int
    data: JsonValue
    meta: Mapping[str, JsonValue] = field(default_factory=dict)
    generation: int = 0


@dataclass(frozen=True, slots=True)
class ReadResult:
    """`LogSource.read` 결과.

    Attributes:
        records: 읽은 행(순서대로).
        cursor: 다음에 이어 읽을 위치(이 결과의 행을 모두 색인한 뒤 저장한다).
        read_bytes: 이번에 소비한 크기(예산 계산용).
        exhausted: 지금 읽을 것이 더 없다(끝이거나 미완성 마지막 줄을 보류함).
    """

    records: list[RawRecord]
    cursor: Cursor
    read_bytes: int
    exhausted: bool


@dataclass(frozen=True, slots=True)
class LogSourceContext:
    """출처에 넘기는 맥락(모두 주입, 전역 없음).

    Attributes:
        source_id: 출처 id(레지스트리 key).
        config: 스키마 기본값을 채우고 검증한 출처 설정(`classifier` 키는 뺀다).
        environ: 환경 변수(홈·설정 폴더 해석용, 테스트에서 가짜로).
        paths: 호스트가 주는 기본 경로(`workspace`·`state` 등, 없을 수 있음).
        open_read: 읽기 전용 열기. 출처는 파일을 이것으로만 연다(테스트에서 쓰기 감시).
        now: 현재 시각(epoch 초).
    """

    source_id: str
    config: Mapping[str, JsonValue] = field(default_factory=dict)
    environ: Mapping[str, str] = field(default_factory=dict)
    paths: Mapping[str, Path] = field(default_factory=dict)
    open_read: Callable[[Path], BinaryIO] = read_only_open
    now: Callable[[], float] = field(default=lambda: 0.0)


@runtime_checkable
class LogSource(Protocol):
    """로그 출처(X5). 원본을 읽기만 한다."""

    @property
    def descriptor(self) -> LogSourceDescriptor:
        """출처 디스크립터(클래스 속성이어도 된다)."""
        ...

    def discover(self, ctx: LogSourceContext) -> Iterable[SourceRef]:
        """읽을 단위 목록(지금 상태). 예외를 내면 그 출처만 실패로 남는다."""
        ...

    def read(
        self, ref: SourceRef, cursor: Cursor, ctx: LogSourceContext, *, budget: int, final: bool
    ) -> ReadResult:
        """`cursor`부터 최대 `budget` 바이트 정도를 읽는다.

        Args:
            final: 참이면 끝나지 않은 마지막 줄도 읽는다(쓰기가 끝난 원본).
        """
        ...


@dataclass(frozen=True, slots=True)
class ClassifyContext:
    """분류기에 넘기는 맥락.

    Attributes:
        source_id: 출처 id.
        ref: 단위(`SourceRef`).
        config: 스키마 기본값을 채운 분류기 설정(`logs.sources[].config.classifier.config`).
    """

    source_id: str
    ref: SourceRef
    config: Mapping[str, JsonValue] = field(default_factory=dict)


@runtime_checkable
class LogClassifier(Protocol):
    """로그 분류기(X6). 행 단위 무상태(F-7)."""

    @property
    def descriptor(self) -> LogClassifierDescriptor:
        """분류기 디스크립터(클래스 속성이어도 된다)."""
        ...

    def classify(self, record: RawRecord, ctx: ClassifyContext) -> list[LogEventDraft]:
        """원본 행 하나 → 초안 목록(빈 목록 = 버림). 예외는 진단 이벤트가 된다."""
        ...
