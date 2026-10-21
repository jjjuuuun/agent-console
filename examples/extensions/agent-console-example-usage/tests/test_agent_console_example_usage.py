"""예제 사용량 출처 `example.manual_count`: entry point 로딩(+ enabled 필터)·설정 검증·계산.

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). entry point는 `EntryPoint` 객체를 직접
만들어 로더에 넘긴다(설치했을 때 로더가 찾는 것과 같은 값).
"""

from __future__ import annotations

import tomllib
from importlib.metadata import EntryPoint
from pathlib import Path

from agent_console_contracts import UsageSettings
from agent_console_example_usage import SOURCE_ID, TRUST, ManualCountSource, windows_from_config
from agent_console_usage import (
    USAGE_SOURCES_GROUP,
    UsageService,
    UsageSourceContext,
    load_usage_sources,
    new_usage_sources,
)

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
VALUE = "agent_console_example_usage:ManualCountSource"


def entry_point() -> EntryPoint:
    return EntryPoint(name=SOURCE_ID, value=VALUE, group=USAGE_SOURCES_GROUP)


def test_entry_point_declared() -> None:
    eps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["entry-points"]
    assert eps[USAGE_SOURCES_GROUP] == {SOURCE_ID: VALUE}


def test_loads_through_entry_point_and_respects_enabled_filter() -> None:
    reg = new_usage_sources()
    load_usage_sources(reg, entry_points=[entry_point()])
    assert reg.get(SOURCE_ID).descriptor.trust == TRUST
    off = new_usage_sources()
    load_usage_sources(off, enabled={"something-else"}, entry_points=[entry_point()])
    assert SOURCE_ID not in [e.key for e in off.list()]  # 꺼 두면 등록되지 않는다(제거와 같음)


def test_windows_from_config_computes_ratio_and_skips_bad_items() -> None:
    config = {
        "windows": [
            {"window": "weekly", "used": 30, "limit": 120, "status": "allowed"},
            {"window": "daily", "used": 5, "limit": 10},
            {"window": "broken", "used": 1, "limit": 0},
            {"window": "no-limit", "used": 1},
            "not a mapping",
        ]
    }
    snaps = windows_from_config(SOURCE_ID, config, now=100.0)
    assert [(s.window, s.used_ratio, s.status) for s in snaps] == [
        ("weekly", 0.25, "allowed"),
        ("daily", 0.5, None),  # 적지 않은 값은 지어내지 않는다
    ]
    assert all(s.observed_at == 100.0 and s.resets_at is None for s in snaps)


async def test_snapshot_uses_context() -> None:
    ctx = UsageSourceContext(
        source_id="renamed", config={"windows": [{"window": "w", "used": 1, "limit": 4}]}, now=7.0
    )
    [snap] = await ManualCountSource().snapshot(ctx)
    assert (snap.source, snap.used_ratio, snap.observed_at) == ("renamed", 0.25, 7.0)


async def test_service_validates_config_and_collects() -> None:
    reg = new_usage_sources()
    reg.register(SOURCE_ID, ManualCountSource())
    service = UsageService(reg, clock=lambda: 50.0)
    good = UsageSettings.model_validate(
        {
            "sources": [
                {"id": SOURCE_ID, "config": {"windows": [{"window": "w", "used": 3, "limit": 6}]}}
            ]
        }
    )
    [snap] = await service.collect(good)
    assert (snap.source, snap.window, snap.used_ratio) == (SOURCE_ID, "w", 0.5)

    bad = UsageSettings.model_validate(
        {"sources": [{"id": SOURCE_ID, "config": {"windows": [{"window": "w", "used": -1}]}}]}
    )
    assert await service.collect(bad) == []
    [info] = service.sources(bad)
    assert info.error is not None  # config_schema 검증 실패는 그 출처의 오류로 보인다
