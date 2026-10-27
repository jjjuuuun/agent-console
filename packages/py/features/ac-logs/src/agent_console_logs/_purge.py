"""색인 비우기(M-3, design §5.7R): 범위(출처·범주·시각)에 맞는 색인 행을 지운다.

색인은 `INSERT OR IGNORE`라 이미 넣은 이벤트는 분류 기본값이 바뀌어도 그대로 남는다
(예: 5.5R.34 전에 넣은 `api-request-blob` 원문). 이 함수로 그 행을 지우고 커서를 지우면
다음 수집이 원본을 처음부터 다시 읽어 지금 규칙으로 다시 색인한다. 원본 파일은 건드리지 않는다.

범위의 출처·범주 이름은 호출자가 주는 데이터다. 이 모듈은 어떤 출처·범주도 모른다.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "PurgeResult",
    "PurgeScope",
    "PurgeableLogIndex",
    "purge_index",
    "reset_index",
]


@dataclass(frozen=True, slots=True)
class PurgeScope:
    """지울 범위. 주어진 조건을 모두 만족하는(AND) 이벤트를 지운다. None = 그 조건 없음.

    Attributes:
        sources: 이벤트 출처 id(`LogEvent.source`) 목록.
        categories: 이벤트 범주 id(`LogEvent.category`) 목록.
        before: 이 시각(epoch 초)보다 이른 이벤트(시각 없으면 색인 시각, `prune`과 같은 기준).
        rescan: True면 범위 출처(`sources`가 없으면 모든 출처)의 커서도 지워 다음 수집이
            처음부터 다시 읽게 한다(남은 이벤트는 같은 uid라 다시 들어가지 않는다).
            False면 커서를 두어 지운 이벤트가 다시 색인되지 않는다.
    """

    sources: tuple[str, ...] | None = None
    categories: tuple[str, ...] | None = None
    before: float | None = None
    rescan: bool = True

    @property
    def whole_sources(self) -> bool:
        """범주·시각 조건이 없다(출처 단위 전체를 지운다 → 에이전트 표시 행도 지운다)."""
        return self.categories is None and self.before is None


@dataclass(frozen=True, slots=True)
class PurgeResult:
    """지운(dry_run이면 지울) 행 수.

    Attributes:
        dry_run: True면 아무것도 지우지 않았다.
        events: 이벤트 수(본문·검색·태그·연결·근거 행은 이벤트를 따라 지운다).
        usage: 토큰 표본 행 수.
        cursors: 커서 행 수.
        agents: 에이전트 표시 행 수.
    """

    dry_run: bool
    events: int = 0
    usage: int = 0
    cursors: int = 0
    agents: int = 0


@runtime_checkable
class PurgeableLogIndex(Protocol):
    """비우기를 지원하는 색인(`MemoryLogIndex`·`SqliteLogIndex`). `LogIndex`와 따로 둔다.

    구현 규칙(두 구현이 같다, `testing.PurgeContractTests`):
    - 이벤트: `scope`의 조건을 모두 만족하는 것.
    - 토큰 표본: 지울 이벤트와 키(출처·thread·message_id)가 같고 남는 이벤트와는 같지 않은 것.
      `categories`가 없으면 출처·시각 조건에 맞는 표본도(시각 없는 표본은 `before`가 없을 때만).
    - 커서: `rescan`이면 범위 출처(없으면 전부)의 커서.
    - 에이전트 표시 행: `whole_sources`일 때 범위 출처(없으면 전부)의 행.
    - `dry_run`이면 같은 수를 세기만 한다. 실제 지우기는 한 트랜잭션이다.
    """

    def purge(self, scope: PurgeScope, *, dry_run: bool) -> PurgeResult:
        """범위의 행을 지운다(또는 센다)."""
        ...


def _names(name: str, values: Iterable[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    if isinstance(values, str):
        raise TypeError(f"{name}는 문자열 목록이어야 합니다")
    out = tuple(dict.fromkeys(v for v in values))
    if not out or any(not v for v in out):
        # 빈 목록을 "조건 없음"으로 읽으면 전부 지워진다. 실수를 막으려고 거부한다.
        raise ValueError(f"{name}가 비었습니다(조건을 빼려면 None)")
    return out


def purge_index(
    index: object,
    *,
    sources: Iterable[str] | None = None,
    categories: Iterable[str] | None = None,
    before: float | None = None,
    rescan: bool = True,
    dry_run: bool = False,
) -> PurgeResult:
    """색인에서 범위에 맞는 행을 지운다(규칙은 `PurgeableLogIndex`).

    Args:
        index: `PurgeableLogIndex`를 구현한 색인.
        sources: 출처 id 목록(None = 모든 출처).
        categories: 범주 id 목록(None = 모든 범주).
        before: 이 시각(epoch 초)보다 이른 이벤트만(None = 시각 조건 없음).
        rescan: 커서도 지워 다음 수집에서 다시 색인되게 한다.
        dry_run: True면 지우지 않고 수만 센다.

    Returns:
        `PurgeResult`.

    Raises:
        TypeError: 색인이 비우기를 지원하지 않거나 목록 자리에 문자열을 줬다.
        ValueError: 빈 목록·빈 이름.
    """
    if not isinstance(index, PurgeableLogIndex):
        raise TypeError(f"{type(index).__name__}는 비우기(purge)를 지원하지 않습니다")
    scope = PurgeScope(
        sources=_names("sources", sources),
        categories=_names("categories", categories),
        before=float(before) if before is not None else None,
        rescan=rescan,
    )
    return index.purge(scope, dry_run=dry_run)


def reset_index(index: object, *, dry_run: bool = False) -> PurgeResult:
    """색인 전체를 비운다(이벤트·표본·커서·에이전트). 다음 수집이 모든 원본을 다시 읽는다.

    Raises:
        TypeError: 색인이 비우기를 지원하지 않는다.
    """
    return purge_index(index, dry_run=dry_run)
