"""호스트 기본 서비스(design §3R.1.2). 포트가 아니라 항상 있다.

모듈은 이것을 ``ModuleContext``로 받는다. 값은 호스트(서버 앱·``standalone``·테스트)가 만들어
주입한다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._database import DatabaseHandle
from ._events import EventBus
from ._hub import Hub


def utc_now() -> datetime:
    """기본 시계(UTC)."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class Paths:
    """호스트 경로. ``base_dir``=상대 경로 기준, ``workspace``=정의 폴더, ``state``=상태 폴더."""

    base_dir: Path
    workspace: Path
    state: Path


@dataclass
class BaseServices:
    """모든 모듈이 받는 기본 서비스.

    Attributes:
        clock: 현재 시각 함수.
        environ: 환경(비밀·설정 조회용). 기본은 빈 매핑 — 호스트가 명시적으로 넘긴다.
        paths: 호스트 경로. 경로를 정하지 않은 호스트(테스트 등)는 None.
        database: 공용 DB 핸들(엔진 + 브랜치 실행기, ``DatabaseHandle``). 없으면 None —
            모듈은 저장소 없이 켜질 수 있어야 한다(그 부분만 꺼진다).
        registries: 플러그인 레지스트리 묶음(``plugins.*``로 호스트가 한 번 로드). 없으면 None.
        ws_hub: WS 토픽 팬아웃.
        events: 모듈 이벤트 버스.
        secret_resolver: ``이름 → 값`` 비밀 해석기. 없으면 None.
    """

    clock: Callable[[], datetime] = utc_now
    environ: Mapping[str, str] = field(default_factory=dict)
    paths: Paths | None = None
    database: DatabaseHandle | None = None
    registries: Any | None = None
    ws_hub: Hub[Any] = field(default_factory=Hub)
    events: EventBus = field(default_factory=EventBus)
    secret_resolver: Callable[[str], str | None] | None = None


__all__ = ["BaseServices", "Paths", "utc_now"]
