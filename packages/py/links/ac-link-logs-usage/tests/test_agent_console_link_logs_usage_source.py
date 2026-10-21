"""``LocalLogsUsageSource``: 설정 데이터·캐시·무효화·사용량 서비스와의 연결(서버 없이)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agent_console_contracts import UsageSettings
from agent_console_contracts.logs import TokenSample
from agent_console_link_logs_usage import (
    DEFAULT_SOURCE_ID,
    LocalLogsUsageSource,
    LogTokenQuery,
    load_default_config,
)
from agent_console_link_logs_usage.testing import SampleQuery
from agent_console_usage import UsageService, UsageSourceContext, as_usage_source, new_usage_sources

H0 = 1_800_000_000.0
NOW = H0 + 3600.0
SRC = Path(__file__).resolve().parents[1] / "src"


def samples(*tokens: int) -> list[TokenSample]:
    return [
        TokenSample(message_id=f"m{i}", time=H0 + 60 * (i + 1), input_tokens=t)
        for i, t in enumerate(tokens)
    ]


def ctx(config: dict[str, Any] | None = None) -> UsageSourceContext:
    return UsageSourceContext(source_id="local-logs", config=config or {}, now=NOW)


MY = {"filter": {"source": "my-logs"}}


def test_is_usage_source_and_query_protocol() -> None:
    source = LocalLogsUsageSource(SampleQuery())
    assert as_usage_source(source) is source
    assert source.descriptor.id == DEFAULT_SOURCE_ID
    assert source.descriptor.trust == "estimated"
    assert isinstance(SampleQuery(), LogTokenQuery)


def test_log_source_id_lives_in_data_not_code() -> None:
    default_source = load_default_config()["filter"]["source"]
    assert default_source  # 기본값 데이터에 있다
    for path in SRC.rglob("*.py"):
        for name in default_source:
            assert name not in path.read_text(encoding="utf-8"), path


async def test_filter_from_settings_selects_log_source() -> None:
    query = SampleQuery(samples(5, 6), source="my-logs")
    source = LocalLogsUsageSource(query)
    snaps = await source.snapshot(ctx(MY))
    assert {s.window: s.used_tokens for s in snaps} == {
        "local_five_hour": 11,
        "local_seven_day": 11,
    }
    assert query.calls[-1].source == ("my-logs",)
    assert query.calls[-1].since == NOW - 7 * 86400
    # 기본 필터(데이터의 출처 id)는 이 표본 출처와 다르므로 아무것도 없다
    assert await source.snapshot(ctx()) == []


async def test_samples_are_cached_until_matching_ingest() -> None:
    query = SampleQuery(samples(5), source="my-logs")
    source = LocalLogsUsageSource(query)
    await source.snapshot(ctx(MY))
    await source.snapshot(ctx(MY))
    assert len(query.calls) == 1
    # 다른 로그 출처의 수집은 이 캐시를 건드리지 않는다
    source.on_ingested(SimpleNamespace(source_ids=["other"], count=1, max_seq=3))
    await source.snapshot(ctx(MY))
    assert len(query.calls) == 1
    # 같은 출처가 수집되면 다시 읽는다
    query.samples.extend(samples(0, 4)[1:])
    source.on_ingested(SimpleNamespace(source_ids=["my-logs"], count=1, max_seq=4))
    snaps = await source.snapshot(ctx(MY))
    assert len(query.calls) == 2
    assert snaps[0].used_tokens == 9
    assert source.invalidate() == 1


async def test_filter_without_source_is_invalidated_by_any_ingest() -> None:
    query = SampleQuery(samples(1))
    source = LocalLogsUsageSource(query, defaults={**load_default_config(), "filter": {}})
    await source.snapshot(ctx())
    source.on_ingested(SimpleNamespace(source_ids=["anything"]))
    await source.snapshot(ctx())
    assert len(query.calls) == 2


async def test_ingest_during_query_does_not_store_stale_samples() -> None:
    holder: dict[str, LocalLogsUsageSource] = {}

    class Racing(SampleQuery):
        def token_samples(self, flt: Any) -> list[TokenSample]:
            rows = super().token_samples(flt)
            holder["s"].invalidate()  # 조회 중에 새 로그가 들어왔다
            return rows

    query = Racing(samples(1), source="my-logs")
    holder["s"] = LocalLogsUsageSource(query)
    await holder["s"].snapshot(ctx(MY))
    await holder["s"].snapshot(ctx(MY))
    assert len(query.calls) == 2


async def test_missing_query_and_empty_windows_give_nothing() -> None:
    assert await LocalLogsUsageSource(lambda: None).snapshot(ctx()) == []
    source = LocalLogsUsageSource(SampleQuery(samples(1), source="my-logs"))
    assert await source.snapshot(ctx({**MY, "windows": []})) == []


async def test_through_usage_service_errors_and_settings() -> None:
    query = SampleQuery(samples(5), source="my-logs")
    service = UsageService(
        new_usage_sources(),
        clock=lambda: NOW,
        extra_sources={"local-logs": LocalLogsUsageSource(query)},
    )
    good = UsageSettings.model_validate({"sources": [{"id": "local-logs", "config": MY}]})
    windows = await service.collect(good)
    assert [(w.source, w.window, w.used_tokens, w.used_ratio) for w in windows] == [
        ("local-logs", "local_five_hour", 5, None),
        ("local-logs", "local_seven_day", 5, None),
    ]
    budget = UsageSettings.model_validate(
        {"sources": [{"id": "local-logs", "config": {**MY, "budgets": {"local_seven_day": 10}}}]}
    )
    ratios = {w.window: w.used_ratio for w in await service.collect(budget)}
    assert ratios == {"local_five_hour": None, "local_seven_day": 0.5}

    unknown_filter = UsageSettings.model_validate(
        {"sources": [{"id": "local-logs", "config": {"filter": {"nope": "x"}}}]}
    )
    assert await service.collect(unknown_filter) == []
    info = service.sources(unknown_filter)[0]
    assert info.error is not None
    assert info.error.code == "usage_source_failed"

    schema_error = UsageSettings.model_validate(
        {"sources": [{"id": "local-logs", "config": {"filter": {"until": "1"}}}]}
    )
    assert await service.collect(schema_error) == []
    info = service.sources(schema_error)[0]
    assert info.error is not None
    assert info.error.code == "validation_failed"

    off = UsageSettings.model_validate({"sources": [{"id": "local-logs", "enabled": False}]})
    assert await service.collect(off) == []


# ---------------------------------------------------------------- 5.2R.27 첫 조회 대기·창 이름


class _SlowIngest:
    """``scan``이 끝나야 표본이 생기는 수집(서버 시작 직후 첫 수집을 흉내)."""

    def __init__(self, query: SampleQuery, rows: list[TokenSample], delay: float) -> None:
        self.query, self.rows, self.delay = query, rows, delay
        self.calls: list[Any] = []

    async def scan(self, source_ids: Any = None) -> None:
        import asyncio

        self.calls.append(source_ids)
        await asyncio.sleep(self.delay)
        self.query.samples.extend(self.rows)


async def test_first_snapshot_waits_for_scan_once() -> None:
    query = SampleQuery(source="my-logs")
    ingest = _SlowIngest(query, samples(5, 6), delay=0.05)
    source = LocalLogsUsageSource(query, ingest=ingest, first_scan_wait_seconds=2)
    snaps = await source.snapshot(ctx(MY))
    assert {s.window: s.used_tokens for s in snaps}["local_five_hour"] == 11
    assert ingest.calls == [["my-logs"]]  # 읽을 로그 출처만
    await source.snapshot(ctx(MY))
    assert len(ingest.calls) == 1  # 첫 조회 한 번만 기다린다


async def test_first_snapshot_wait_is_bounded() -> None:
    query = SampleQuery(source="my-logs")
    ingest = _SlowIngest(query, samples(5), delay=5)
    source = LocalLogsUsageSource(query, ingest=lambda: ingest, first_scan_wait_seconds=0.01)
    assert await source.snapshot(ctx(MY)) == []  # 기다리다 넘치면 지금 색인으로 답한다


def test_descriptor_auto_enable_and_window_titles_from_data() -> None:
    d = LocalLogsUsageSource(SampleQuery()).descriptor
    assert d.auto_enable is True
    assert d.test_only is False
    assert d.needs_setup is False
    assert [(w.id, w.short_title) for w in d.windows] == [
        ("local_five_hour", "5h"),
        ("local_seven_day", "7d"),
    ]
    # 창 title은 설정에도 적을 수 있다(스키마 허용, 계산에는 쓰지 않음)
    service = UsageService(
        new_usage_sources(),
        clock=lambda: NOW,
        extra_sources={
            "local-logs": LocalLogsUsageSource(SampleQuery(samples(1), source="my-logs"))
        },
    )
    settings = UsageSettings.model_validate(
        {
            "sources": [
                {
                    "id": "local-logs",
                    "config": {
                        **MY,
                        "windows": [{"id": "w", "kind": "block", "hours": 5, "title": "내 창"}],
                    },
                }
            ]
        }
    )
    assert service.config_issues(settings) == []
