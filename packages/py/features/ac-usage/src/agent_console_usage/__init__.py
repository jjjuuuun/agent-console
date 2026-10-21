"""agent-console-usage: 사용량 출처(X13)·수집 서비스·statusLine 브리지·토큰 집계(design §R4.3).

- `UsageSource`(프로토콜) + `load_usage_sources`(entry point `agent_console.usage_sources`).
- `UsageService(sources, clock=…, extra_sources=…)` — 켜진 출처를 돌려 창 스냅샷을 모으고 관측값을
  기록한다. 레지스트리 밖 출처(런타임 출처)는 `extra_sources`로 받는다(id가 겹치면 레지스트리 우선).
- `source_config_issues`·`config_error`·`UsageService.config_issues` — 출처 설정을 그 출처
  `config_schema`로 검증(위치·규칙 이름만, 값 없음). 저장 전 검사·서버 경고가 쓴다.
- 기본 출처: `RunEventUsageSource`(run-events), `StatuslineFileSource`(statusline-file),
  `FakeUsageSource`(fake). 모두 entry point로만 등록되며 특별 취급하지 않는다. 자동 켜기·창 이름·
  연결 안내 조각은 패키지 데이터 `data/sources.json`(`descriptor_fields`·`fill_setup_snippets`).
- `statusline` 모듈: statusLine stdin JSON 파싱·파일 원자적 쓰기·상태 줄 만들기.
- `usage_records`·`token_rollup` — 에이전트·팀 구성·모델·일 단위 토큰 집계. `counts_toward_usage`
  — 루트 Run만 센다(자식 Run은 부모 노드 usage에 이미 들어 있음, 이중 집계 방지).

`statusline` 모듈은 표준 라이브러리만 쓴다. 이 `__init__`은 이름을 처음 쓸 때 import하므로
(PEP 562) `agent_console_usage.statusline`만 쓰는 쪽(CLI `statusline`)은 계약·레지스트리를
읽지 않는다.

값을 지어내지 않는다: 출처가 주지 않은 값은 `None`이다.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._config_check import (
        SOURCE_CONFIG_INVALID,
        SOURCE_SCHEMA_INVALID,
        config_error,
        source_config_issues,
    )
    from ._interfaces import UsageEventQuery, UsageObservationSink, UsageSource, UsageSourceContext
    from ._loading import (
        USAGE_SOURCES_EXTENSION,
        USAGE_SOURCES_GROUP,
        as_usage_source,
        list_descriptors,
        load_usage_sources,
        new_usage_sources,
    )
    from ._rollup import (
        DEFAULT_PRECISION_TEXT,
        ROLLUP_DIMENSIONS,
        RollupDimension,
        RollupEventSource,
        RollupRunSource,
        UsageRecord,
        counts_toward_usage,
        load_usage_records,
        sum_usage,
        token_rollup,
        usage_records,
    )
    from ._service import (
        SOURCE_FAILED,
        SOURCE_TIMEOUT,
        ExtraUsageSources,
        SetupValues,
        UsageService,
        auto_enabled,
    )
    from ._setup import (
        SETUP_AGENT_CONSOLE_CMD,
        SETUP_OUTPUT_PATH,
        builtin_source_data,
        descriptor_fields,
        fill_setup_snippets,
        fill_setup_text,
    )
    from .sources import FakeUsageSource, RunEventUsageSource, StatuslineFileSource
    from .statusline import (
        DEFAULT_STATUSLINE_FILE,
        StatuslineReading,
        StatuslineWindow,
        default_window_labels,
        format_status_line,
        load_statusline_windows,
        parse_statusline,
        update_statusline_file,
    )

_LAZY: dict[str, str] = {
    "DEFAULT_PRECISION_TEXT": "._rollup",
    "DEFAULT_STATUSLINE_FILE": ".statusline",
    "ExtraUsageSources": "._service",
    "FakeUsageSource": ".sources",
    "ROLLUP_DIMENSIONS": "._rollup",
    "RollupDimension": "._rollup",
    "RollupEventSource": "._rollup",
    "RollupRunSource": "._rollup",
    "RunEventUsageSource": ".sources",
    "SETUP_AGENT_CONSOLE_CMD": "._setup",
    "SETUP_OUTPUT_PATH": "._setup",
    "SOURCE_CONFIG_INVALID": "._config_check",
    "SOURCE_FAILED": "._service",
    "SOURCE_SCHEMA_INVALID": "._config_check",
    "SOURCE_TIMEOUT": "._service",
    "SetupValues": "._service",
    "StatuslineFileSource": ".sources",
    "StatuslineReading": ".statusline",
    "StatuslineWindow": ".statusline",
    "USAGE_SOURCES_EXTENSION": "._loading",
    "USAGE_SOURCES_GROUP": "._loading",
    "UsageEventQuery": "._interfaces",
    "UsageObservationSink": "._interfaces",
    "UsageRecord": "._rollup",
    "UsageService": "._service",
    "UsageSource": "._interfaces",
    "UsageSourceContext": "._interfaces",
    "as_usage_source": "._loading",
    "auto_enabled": "._service",
    "builtin_source_data": "._setup",
    "config_error": "._config_check",
    "counts_toward_usage": "._rollup",
    "default_window_labels": ".statusline",
    "descriptor_fields": "._setup",
    "fill_setup_snippets": "._setup",
    "fill_setup_text": "._setup",
    "format_status_line": ".statusline",
    "list_descriptors": "._loading",
    "load_statusline_windows": ".statusline",
    "load_usage_records": "._rollup",
    "load_usage_sources": "._loading",
    "new_usage_sources": "._loading",
    "parse_statusline": ".statusline",
    "source_config_issues": "._config_check",
    "sum_usage": "._rollup",
    "token_rollup": "._rollup",
    "update_statusline_file": ".statusline",
    "usage_records": "._rollup",
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY})


__all__ = [
    "DEFAULT_PRECISION_TEXT",
    "DEFAULT_STATUSLINE_FILE",
    "ROLLUP_DIMENSIONS",
    "SETUP_AGENT_CONSOLE_CMD",
    "SETUP_OUTPUT_PATH",
    "SOURCE_CONFIG_INVALID",
    "SOURCE_FAILED",
    "SOURCE_SCHEMA_INVALID",
    "SOURCE_TIMEOUT",
    "USAGE_SOURCES_EXTENSION",
    "USAGE_SOURCES_GROUP",
    "ExtraUsageSources",
    "FakeUsageSource",
    "RollupDimension",
    "RollupEventSource",
    "RollupRunSource",
    "RunEventUsageSource",
    "SetupValues",
    "StatuslineFileSource",
    "StatuslineReading",
    "StatuslineWindow",
    "UsageEventQuery",
    "UsageObservationSink",
    "UsageRecord",
    "UsageService",
    "UsageSource",
    "UsageSourceContext",
    "as_usage_source",
    "auto_enabled",
    "builtin_source_data",
    "config_error",
    "counts_toward_usage",
    "default_window_labels",
    "descriptor_fields",
    "fill_setup_snippets",
    "fill_setup_text",
    "format_status_line",
    "list_descriptors",
    "load_statusline_windows",
    "load_usage_records",
    "load_usage_sources",
    "new_usage_sources",
    "parse_statusline",
    "source_config_issues",
    "sum_usage",
    "token_rollup",
    "update_statusline_file",
    "usage_records",
]
