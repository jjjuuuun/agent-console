"""서버 자동 정리 한 주기(5.7R.46, design ``[pl 결정 11/20, 5.7R.46·5.7R.47]``).

저장된 정리 규칙(앱 설정 하나)을 사용자 설정 ``memory.retention.auto``가 고른 저장소에 차례로
적용한다.

- 규칙이 없으면 아무것도 열지 않는다(기본 규칙은 빈 목록이라 켜도 지우는 것이 없다).
- 순서: 공용(``auto.library``) → 공간(``auto.projects``)마다. 공간 이름은 ``memory.spaces`` 제공자의
  선택 메서드 ``existing()``이 준다(없으면 공용만). ``auto.exclude_projects``에 든 이름은 뺀다.
- 공간마다 실패(열 수 없음·잠김·계보 불일치 등)는 기록하고 건너뛴다. 다음 주기에 다시 한다.
- 멈춤(``should_stop``): 저장소마다 시작 전에 묻고, 참이면 남은 것을 하지 않는다(서버 종료).
- 적용 결과는 ``MemoryService.apply_retention``과 같다(쓴 주체 ``system``, ``label`` = 규칙 id).

주기·끄기(``retention_interval_seconds: 0``)는 모듈이 정한다. 이 모듈은 HTTP·시각·스레드를 모른다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agent_console_contracts.memory import MemoryRetentionAuto, MemoryRetentionResult

if TYPE_CHECKING:
    from .service import MemoryService

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetentionCycleResult:
    """자동 정리 한 주기의 결과.

    Attributes:
        results: 정리한 저장소 → 결과(공용 = None, 공간 = 공간 이름). 적용한 순서.
        failed: 건너뛴 저장소 → 오류 코드(``code`` 속성, 없으면 예외 이름).
        stopped: 멈춤 요청(``should_stop``)으로 남은 저장소를 하지 않고 끝났나.
    """

    results: Mapping[str | None, MemoryRetentionResult] = field(default_factory=dict)
    failed: Mapping[str | None, str] = field(default_factory=dict)
    stopped: bool = False


def retention_targets(service: MemoryService, auto: MemoryRetentionAuto) -> list[str | None]:
    """``auto``가 고른 저장소(공용 = None, 공간 이름). 공간 목록은 ``existing_spaces()``."""
    targets: list[str | None] = []
    if auto.library:
        targets.append(None)
    if auto.projects:
        excluded = set(auto.exclude_projects)
        targets.extend(name for name in service.existing_spaces() if name not in excluded)
    return targets


def _code_of(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else type(exc).__name__


def run_retention_cycle(
    service: MemoryService, *, should_stop: Callable[[], bool] = lambda: False
) -> RetentionCycleResult:
    """저장된 정리 규칙을 자동 정리 대상에 한 번 적용한다(막히는 호출).

    Args:
        service: 라이브러리(공용) 메모리 서비스. 공간은 ``service.space(name)``으로 연다.
        should_stop: 저장소마다 시작 전에 묻는다. 참이면 남은 저장소를 하지 않고 끝낸다
            (서버 종료, ``stopped`` = 참). 하던 저장소는 끝까지 한다.

    Returns:
        저장소별 결과와 건너뛴 저장소. 규칙이 없으면 빈 결과(아무것도 열지 않음).
    """
    if not service.has_retention_rules():
        return RetentionCycleResult()
    auto = service.settings().retention.auto
    results: dict[str | None, MemoryRetentionResult] = {}
    failed: dict[str | None, str] = {}
    for name in retention_targets(service, auto):
        if should_stop():
            return RetentionCycleResult(results, failed, stopped=True)
        try:
            results[name] = service.space(name).apply_retention()
        except Exception as exc:
            failed[name] = _code_of(exc)
            _log.warning(
                "메모리 자동 정리: %s 건너뜀(%s)",
                "공용" if name is None else f"공간 {name!r}",
                failed[name],
                exc_info=True,
            )
    return RetentionCycleResult(results, failed)


__all__ = ["RetentionCycleResult", "retention_targets", "run_retention_cycle"]
