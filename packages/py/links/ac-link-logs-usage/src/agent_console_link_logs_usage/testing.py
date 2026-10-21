"""단독 실행·테스트용 부품(공개).

- ``SampleQuery``: 주어진 토큰 표본으로 ``logs.query``의 ``token_samples``를 흉내 낸다(출처·시각
  필터만 적용). 호출 횟수를 센다.
- ``local_logs_query_module``: ``logs.query``를 ``SampleQuery``로 주는 작은 모듈.
- ``local_usage_module``: ``usage.service``를 자리만 채우는 작은 모듈(``usage.sources`` 목록을
  ``sources()``로 돌려준다).

단독 실행(``python -m agent_console_link_logs_usage``)이 ``--with`` 없이 실행되면 둘을 붙인다(통합
서버에서는 ``mod-logs``·``mod-usage``가 대신한다).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agent_console_contracts.logs import TokenSample
from agent_console_logs import LogFilter
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module

from .ports import LOGS_QUERY, USAGE_SERVICE, USAGE_SOURCES

LOCAL_LOGS_ID = "local-logs-query"
LOCAL_USAGE_ID = "local-usage"


class SampleQuery:
    """표본 목록 기반 ``token_samples``(``source``는 표본 출처 대신 ``sources`` 인자로 정한다).

    Args:
        samples: 표본(시각순이 아니어도 된다).
        source: 이 표본들의 로그 출처 id(필터 ``source``와 맞춘다).
    """

    def __init__(self, samples: Iterable[TokenSample] = (), *, source: str = "test-source") -> None:
        self.samples = list(samples)
        self.source = source
        self.calls: list[LogFilter] = []

    def token_samples(self, flt: LogFilter) -> list[TokenSample]:
        self.calls.append(flt)
        if flt.source and self.source not in flt.source:
            return []
        out = [
            s
            for s in self.samples
            if s.time is not None
            and (flt.since is None or s.time >= flt.since)
            and (flt.until is None or s.time < flt.until)
        ]
        return sorted(out, key=lambda s: s.time or 0.0)


def local_logs_query_module(module_id: str = LOCAL_LOGS_ID, *, query: Any = None) -> Module:
    """``logs.query`` 제공 모듈(주어진 조회, 없으면 빈 ``SampleQuery``)."""
    impl = query if query is not None else SampleQuery()

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(LOGS_QUERY, impl)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[LOGS_QUERY], on_build=build)


class _UsagePlaceholder:
    def __init__(self, ctx: ModuleContext) -> None:
        self._ctx = ctx

    def sources(self) -> list[Any]:
        return list(self._ctx.ports(USAGE_SOURCES))


def local_usage_module(module_id: str = LOCAL_USAGE_ID) -> Module:
    """``usage.service`` 자리 채움 모듈(받은 ``usage.sources``를 ``sources()``로 보인다)."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(USAGE_SERVICE, _UsagePlaceholder(ctx))
        return ModuleParts()

    return fake_module(
        module_id,
        kind="testing",
        provides=[USAGE_SERVICE],
        optional=[USAGE_SOURCES],
        on_build=build,
    )


__all__ = [
    "LOCAL_LOGS_ID",
    "LOCAL_USAGE_ID",
    "SampleQuery",
    "local_logs_query_module",
    "local_usage_module",
]
