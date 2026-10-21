"""출처 A: 플랫폼 실행 이벤트 `usage.rate_limit`의 창별 최신값(design §R4.3)."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from agent_console_contracts import (
    KnownUsageTrust,
    UsageRateLimitPayload,
    UsageSourceDescriptor,
    UsageWindowSnapshot,
    x_ui,
)
from agent_console_usage._interfaces import UsageSourceContext
from agent_console_usage._setup import descriptor_fields

__all__ = ["RunEventUsageSource"]

_DEFAULT_EVENT_TYPE = "usage.rate_limit"
_DEFAULT_SCAN_LIMIT = 200


class RunEventUsageSource:
    """`usage.rate_limit` 이벤트(백엔드가 SDK `RateLimitEvent`를 옮긴 것)에서 창별 최신값.

    최근 이벤트 `scan_limit`개를 훑어 창마다 가장 최근 것 하나를 낸다. `utilization`이 없으면
    `used_ratio`도 `None`이다(경고 임계 전 등). payload 형식이 틀린 이벤트는 건너뛴다.
    """

    descriptor = UsageSourceDescriptor(
        id="run-events",
        title="플랫폼 실행(SDK 사용량 이벤트)",
        description=(
            "이 플랫폼이 Agent SDK로 실행할 때 받은 사용량 한도 이벤트의 창별 최신값. "
            "구독 로그인 실행에서만 갱신되며, 경고 임계 전에는 사용률이 비어 있을 수 있다."
        ),
        trust=KnownUsageTrust.OFFICIAL,
        config_schema={
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "minLength": 1,
                    "default": _DEFAULT_EVENT_TYPE,
                    "title": "이벤트 종류",
                    "description": (
                        "사용량 한도 값을 담은 실행 기록 이벤트 이름입니다. 보통은 바꾸지 않습니다."
                    ),
                    **x_ui(tier="advanced"),
                },
                "scan_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10000,
                    "default": _DEFAULT_SCAN_LIMIT,
                    "title": "훑을 최근 이벤트 수",
                    "description": (
                        "최근 기록을 몇 개까지 거슬러 볼지입니다. 늘리면 오래된 값도 찾지만 "
                        "느려집니다."
                    ),
                    **x_ui(tier="advanced", unit="개"),
                },
            },
            "additionalProperties": False,
        },
        setup_help=(
            "설정할 것이 없습니다. 구독 로그인으로 에이전트를 실행하면 값이 생깁니다. "
            "API 키 인증 실행에는 5시간·주간 창이 없습니다."
        ),
        **descriptor_fields("run-events"),
    )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        if ctx.events is None:
            return []
        event_type = str(ctx.config.get("event_type", _DEFAULT_EVENT_TYPE))
        limit = int(ctx.config.get("scan_limit", _DEFAULT_SCAN_LIMIT))
        latest: dict[str, UsageWindowSnapshot] = {}
        for event in ctx.events.latest_by_type(event_type, limit=limit):
            try:
                payload = UsageRateLimitPayload.model_validate(event.payload)
            except ValidationError:
                continue
            if payload.window in latest:
                continue  # ts 내림차순이므로 처음 본 것이 최신
            raw: dict[str, Any] = payload.model_dump(exclude_none=True)
            raw["run_id"] = event.run_id
            if event.actor is not None:
                raw["actor"] = event.actor
            latest[payload.window] = UsageWindowSnapshot(
                source=ctx.source_id,
                window=payload.window,
                used_ratio=payload.utilization,
                status=payload.status,
                resets_at=payload.resets_at,
                observed_at=event.ts,
                raw=raw,
            )
        return [latest[k] for k in sorted(latest)]
