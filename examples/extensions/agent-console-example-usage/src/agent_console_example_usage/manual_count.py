"""사용량 출처 `example.manual_count`: 사용자가 설정에 적은 "쓴 양 / 한도"로 창을 만든다.

공식 사용량 값이 없는 도구(사내 게이트웨이, 팀 공용 할당량 등)를 손으로 기록할 때 쓴다.
UsageSource(X13)는 두 가지만 갖추면 된다.

1. ``descriptor`` — id·제목·신뢰 등급(`trust`, 열린 문자열)·설정 스키마(`config_schema`).
   서버는 설정 `usage.sources[].config`를 이 스키마로 검증한 뒤 넘긴다.
2. ``async snapshot(ctx)`` — 창별 최신 관측값 목록. **값을 지어내지 않는다**: 적지 않은 값은 None.

동작은 결정적이다(관측 시각은 주입된 `ctx.now`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from agent_console_contracts import UsageSourceDescriptor, UsageWindowSnapshot
from agent_console_usage import UsageSourceContext

SOURCE_ID: Final = "example.manual_count"
"""출처 id(entry point 이름과 같다)."""
TRUST: Final = "manual"
"""신뢰 등급. 알려진 등급(`KnownUsageTrust`) 밖의 값도 된다 — 화면은 기본 배지로 보인다."""

_WINDOW_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "required": ["window", "used", "limit"],
    "properties": {
        "window": {"type": "string", "minLength": 1, "title": "창 이름"},
        "used": {"type": "number", "minimum": 0, "title": "쓴 양"},
        "limit": {"type": "number", "exclusiveMinimum": 0, "title": "한도"},
        "status": {"type": "string", "title": "상태(선택)"},
    },
    "additionalProperties": False,
}


def windows_from_config(
    source_id: str, config: Mapping[str, Any], now: float
) -> list[UsageWindowSnapshot]:
    """설정 `windows`(쓴 양·한도) → 창 스냅샷. 사용률 = used / limit.

    Args:
        source_id: 스냅샷 `source`에 넣을 출처 id(레지스트리 key).
        config: 출처 설정(`windows` 목록). 형식이 틀린 항목은 건너뛴다.
        now: 관측 시각(Unix epoch 초).

    Returns:
        창마다 하나. `status`를 적지 않았으면 None(지어내지 않는다).
    """
    out: list[UsageWindowSnapshot] = []
    for item in config.get("windows", []):
        if not isinstance(item, Mapping):
            continue
        try:
            used, limit = float(item["used"]), float(item["limit"])
            window = str(item["window"])
        except (KeyError, TypeError, ValueError):
            continue
        if limit <= 0 or not window:
            continue
        status = item.get("status")
        out.append(
            UsageWindowSnapshot(
                source=source_id,
                window=window,
                used_ratio=used / limit,
                status=str(status) if status is not None else None,
                observed_at=now,
            )
        )
    return out


class ManualCountSource:
    """사용량 출처 `example.manual_count`(X13 예제 구현)."""

    descriptor = UsageSourceDescriptor(
        id=SOURCE_ID,
        title="직접 적은 사용량",
        description="설정에 적은 '쓴 양 / 한도'로 사용률을 보인다(예제 확장).",
        trust=TRUST,
        config_schema={
            "type": "object",
            "properties": {"windows": {"type": "array", "items": _WINDOW_SCHEMA}},
            "additionalProperties": False,
        },
    )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        """설정 창 목록을 그대로 계산해 돌려준다."""
        return windows_from_config(ctx.source_id, ctx.config, ctx.now)
