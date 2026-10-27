"""로컬 로그 토큰 창 추정(순수 함수, design §4R.8 ``local-logs``·§R4.3 출처 C).

창 정의·예산·필터·셀 토큰 종류는 **설정 데이터**다(``usage.sources[].config``). 생략한 키는
기본값 데이터(``data/local_logs_defaults.json``)를 쓴다. 계산은 ``ac-logs``의 ``block_windows``
(ccusage 방식 블록)·``rolling_totals``(이동 창)다.

값을 지어내지 않는다:

- 예산(``budgets[창 id]``)이 없으면 ``used_ratio``는 ``None``이다(한도 분모가 공개되지 않는다).
- 셀 토큰 종류가 어느 표본에도 없으면 ``used_tokens``는 ``None``이다(0으로 채우지 않음).
- 조회 범위에 표본이 하나도 없으면 창을 내지 않는다(로그가 없는 것과 0을 쓴 것을 구분할 수 없다).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

from agent_console_contracts import UsageWindowInfo, UsageWindowSnapshot, x_ui
from agent_console_contracts.logs import LogTokenTotals, TokenSample
from agent_console_logs import block_windows, rolling_totals

__all__ = [
    "CONFIG_SCHEMA",
    "TOKEN_KINDS",
    "TOKEN_KIND_LABELS",
    "WINDOW_KINDS",
    "WINDOW_KIND_LABELS",
    "LocalLogsConfig",
    "WindowSpec",
    "estimate_windows",
    "load_default_config",
    "parse_config",
    "window_infos",
]

WindowKind = Literal["block", "rolling"]

WINDOW_KINDS: tuple[str, ...] = ("block", "rolling")
"""계산 방식: ``block``(ccusage 블록 — 첫 메시지 시각을 시 단위로 내림, 길이 동안, 끝나면 다음
블록), ``rolling``(``now``에서 길이만큼 뒤로 이동하는 창)."""

TOKEN_KINDS: tuple[str, ...] = ("input", "output", "cache_creation", "cache_read")
"""``count``에 쓸 수 있는 토큰 종류(``LogTokenTotals`` 필드)."""

_DEFAULTS_RESOURCE = "local_logs_defaults.json"

WINDOW_KIND_LABELS: dict[str, str] = {
    "block": "블록(첫 메시지부터 정한 길이)",
    "rolling": "이동 창(지금부터 거꾸로)",
}
"""설정 폼에 보일 계산 방식 라벨(``x-ui.enum_labels``)."""

TOKEN_KIND_LABELS: dict[str, str] = {
    "input": "입력 토큰",
    "output": "출력 토큰",
    "cache_creation": "캐시 쓰기 토큰",
    "cache_read": "캐시 읽기 토큰",
}
"""설정 폼에 보일 토큰 종류 라벨(``x-ui.enum_labels``, 다중 선택이라 배열 필드에 둔다)."""

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "title": "로컬 로그 추정",
    "properties": {
        "windows": {
            "type": "array",
            "title": "창",
            "description": "생략하면 기본 창(데이터). 같은 id가 여럿이면 처음 것만 쓴다.",
            **x_ui(tier="advanced"),
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "minLength": 1,
                        "title": "창 id",
                        "description": "예산·화면이 이 창을 가리킬 때 쓰는 이름입니다.",
                        **x_ui(tier="advanced", example="my_window"),
                    },
                    "kind": {
                        "type": "string",
                        "enum": list(WINDOW_KINDS),
                        "title": "계산 방식",
                        "description": (
                            "블록은 첫 메시지부터 길이만큼, 이동 창은 지금부터 거꾸로 셉니다."
                        ),
                        **x_ui(tier="advanced", enum_labels=WINDOW_KIND_LABELS),
                    },
                    "hours": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "title": "길이(시간)",
                        "description": "창 길이(시간). 길이(일)와 함께 적으면 더한다.",
                        **x_ui(tier="advanced", example=5, unit="시간"),
                    },
                    "days": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "title": "길이(일)",
                        "description": "창 길이(일). 길이(시간)와 함께 적으면 더한다.",
                        **x_ui(tier="advanced", example=7, unit="일"),
                    },
                    "title": {
                        "type": "string",
                        "minLength": 1,
                        "title": "표시 이름",
                        "description": "사용량 화면에 보일 창 이름입니다.",
                        **x_ui(tier="advanced", example="내 창"),
                    },
                    "short_title": {
                        "type": "string",
                        "minLength": 1,
                        "title": "짧은 이름",
                        "description": "좁은 자리(상태 줄 등)에 보일 짧은 이름.",
                        **x_ui(tier="advanced", example="5h"),
                    },
                },
                "required": ["id", "kind"],
                "anyOf": [{"required": ["hours"]}, {"required": ["days"]}],
                "additionalProperties": False,
            },
        },
        "budgets": {
            "type": "object",
            "title": "예산(토큰)",
            "description": "창 id → 토큰 수. 있으면 사용률 = 사용 토큰 / 예산. 없으면 사용률 없음.",
            **x_ui(
                tier="basic",
                when="로그 추정 창에 사용률(%)을 보고 싶을 때 창마다 토큰 예산을 적습니다.",
            ),
            "additionalProperties": {"type": "integer", "exclusiveMinimum": 0},
        },
        "filter": {
            "type": "object",
            "title": "로그 필터",
            "description": (
                "로그 질의 필터(예: source, project, model). 시각·쪽수 키는 쓰지 않는다."
            ),
            **x_ui(tier="advanced"),
            "propertyNames": {"not": {"enum": ["since", "until", "limit", "cursor", "order"]}},
            "additionalProperties": {
                "anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]
            },
        },
        "count": {
            "type": "array",
            "title": "셀 토큰 종류",
            "description": "사용 토큰에 더할 종류. 비우면 네 종류를 모두 더한다.",
            **x_ui(tier="advanced", enum_labels=TOKEN_KIND_LABELS),
            "items": {"type": "string", "enum": list(TOKEN_KINDS)},
            "uniqueItems": True,
        },
        "lookback_hours": {
            "type": "number",
            "exclusiveMinimum": 0,
            "title": "조회 범위(시간)",
            "description": (
                "블록 경계를 정하려고 읽는 과거 범위. 창 길이보다 짧으면 창 길이를 쓴다."
            ),
            **x_ui(tier="advanced", example=168, unit="시간"),
        },
    },
    "additionalProperties": False,
}
"""``local-logs`` 출처 설정 스키마(사용량 서비스가 검증한다)."""


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """창 하나: ``id``(출처가 주는 창 이름), ``kind``(계산 방식), ``seconds``(길이)."""

    id: str
    kind: WindowKind
    seconds: float


@dataclass(frozen=True, slots=True)
class LocalLogsConfig:
    """해석한 설정(생략 키는 기본값 데이터로 채운 것)."""

    windows: tuple[WindowSpec, ...]
    budgets: Mapping[str, int] = field(default_factory=dict)
    filter: Mapping[str, Any] = field(default_factory=dict)
    count: tuple[str, ...] = TOKEN_KINDS
    lookback_seconds: float = 0.0

    @property
    def span_seconds(self) -> float:
        """읽어야 하는 과거 범위: 조회 범위와 창 길이 중 큰 것."""
        return max([self.lookback_seconds, *(w.seconds for w in self.windows)])

    def cache_key(self) -> str:
        """같은 표본 조회인지 가르는 키(필터 + 범위)."""
        return json.dumps({"filter": self.filter, "span": self.span_seconds}, sort_keys=True)


def load_default_config(path: Path | None = None) -> dict[str, Any]:
    """기본값 데이터(``data/local_logs_defaults.json`` 또는 주어진 JSON 파일)를 읽는다."""
    if path is not None:
        text = path.read_text(encoding="utf-8")
    else:
        text = (files(__package__) / "data" / _DEFAULTS_RESOURCE).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("local-logs 기본값은 JSON 객체여야 합니다")
    return data


def _windows(items: Iterable[Mapping[str, Any]]) -> tuple[WindowSpec, ...]:
    out: list[WindowSpec] = []
    seen: set[str] = set()
    for item in items:
        wid = str(item["id"])
        if wid in seen:
            continue
        seen.add(wid)
        kind = str(item["kind"])
        if kind not in WINDOW_KINDS:
            raise ValueError(f"모르는 창 계산 방식: {kind}")
        seconds = float(item.get("hours") or 0) * 3600.0 + float(item.get("days") or 0) * 86400.0
        if seconds <= 0:
            raise ValueError(f"창 길이는 0보다 커야 합니다: {wid}")
        out.append(WindowSpec(id=wid, kind=kind, seconds=seconds))  # type: ignore[arg-type]
    return tuple(out)


def parse_config(config: Mapping[str, Any], defaults: Mapping[str, Any]) -> LocalLogsConfig:
    """사용자 설정 + 기본값 → ``LocalLogsConfig``(최상위 키 단위로 덮어쓴다).

    Raises:
        ValueError: 창 정의가 틀렸을 때(스키마 검증을 거친 값이면 생기지 않는다).
    """
    merged = {**defaults, **config}
    return LocalLogsConfig(
        windows=_windows(merged.get("windows") or ()),
        budgets={str(k): int(v) for k, v in (merged.get("budgets") or {}).items()},
        filter=dict(merged.get("filter") or {}),
        count=tuple(merged.get("count") or TOKEN_KINDS),
        lookback_seconds=float(merged.get("lookback_hours") or 0) * 3600.0,
    )


def window_infos(config: Mapping[str, Any]) -> list[UsageWindowInfo]:
    """설정(또는 기본값 데이터)의 창 중 ``title``이 있는 것의 표시 정보(디스크립터 ``windows``).

    >>> windows = [
    ...     {"id": "w5", "kind": "block", "hours": 5, "title": "5시간", "short_title": "5h"},
    ...     {"id": "w7", "kind": "rolling", "days": 7},
    ... ]
    >>> [(w.id, w.title, w.short_title) for w in window_infos({"windows": windows})]
    [('w5', '5시간', '5h')]
    """
    out: list[UsageWindowInfo] = []
    seen: set[str] = set()
    for item in config.get("windows") or ():
        if not isinstance(item, Mapping):
            continue
        wid, title = item.get("id"), item.get("title")
        if not isinstance(wid, str) or not wid or wid in seen:
            continue
        seen.add(wid)
        if isinstance(title, str) and title:
            short = item.get("short_title")
            out.append(
                UsageWindowInfo(
                    id=wid, title=title, short_title=short if isinstance(short, str) else None
                )
            )
    return out


def _counted(totals: LogTokenTotals, kinds: Sequence[str]) -> int | None:
    values = [getattr(totals, k) for k in kinds if k in TOKEN_KINDS]
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _tokens(totals: LogTokenTotals) -> dict[str, int | None]:
    return totals.model_dump(include={"input", "output", "cache_read", "cache_creation", "total"})


def estimate_windows(
    samples: Sequence[TokenSample],
    config: LocalLogsConfig,
    *,
    now: float,
    source_id: str,
) -> list[UsageWindowSnapshot]:
    """토큰 표본 → 창별 추정 스냅샷(설정의 창 순서).

    Args:
        samples: 응답별 토큰 표본(중복 없는 것, 보통 ``logs.query.token_samples``).
        config: 해석한 설정.
        now: 기준 시각(epoch 초).
        source_id: 스냅샷의 ``source``.

    Returns:
        - ``block``: 지금 열린 블록이 있으면 그 블록 합·``resets_at`` = 블록 끝·``status`` =
          ``"active"``. 없으면 ``used_tokens`` 0·``status`` ``"idle"``·``resets_at`` 없음.
        - ``rolling``: ``now - 길이 <= t <= now`` 합. ``resets_at`` 없음(이동 창은 초기화가 없다).
        - ``observed_at``: 범위 안 마지막 표본 시각(로그 기준 시각, ``now``를 넘지 않음).
        범위 안 표본이 없으면 빈 목록.
    """
    lo = now - config.span_seconds
    timed = [s for s in samples if s.time is not None and lo <= s.time <= now]
    if not timed:
        return []
    observed = max(s.time or 0.0 for s in timed)
    out: list[UsageWindowSnapshot] = []
    for spec in config.windows:
        budget = config.budgets.get(spec.id)
        raw: dict[str, Any] = {"kind": spec.kind, "window_seconds": spec.seconds}
        resets_at: float | None = None
        status: str | None = None
        if spec.kind == "block":
            blocks = block_windows(timed, hours=spec.seconds / 3600.0, now=now)
            active = blocks[-1] if blocks and blocks[-1].active else None
            if active is not None:
                used = _counted(active.tokens, config.count)
                resets_at, status = active.end, "active"
                raw |= {
                    "block_start": active.start,
                    "first_time": active.first_time,
                    "last_time": active.last_time,
                    "samples": active.samples,
                    "tokens": _tokens(active.tokens),
                }
            else:
                used, status = 0, "idle"
                raw |= {"samples": 0}
        else:
            totals = rolling_totals(timed, seconds=spec.seconds, now=now)
            used = _counted(totals, config.count)
            raw |= {
                "samples": sum(
                    1 for s in timed if s.time is not None and s.time >= now - spec.seconds
                ),
                "tokens": _tokens(totals),
            }
        ratio = used / budget if used is not None and budget else None
        if budget:
            raw["budget"] = budget
        out.append(
            UsageWindowSnapshot(
                source=source_id,
                window=spec.id,
                used_tokens=used,
                used_ratio=ratio,
                status=status,
                resets_at=resets_at,
                observed_at=observed,
                raw=raw,
            )
        )
    return out
