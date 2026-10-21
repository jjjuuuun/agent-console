"""테스트·E2E용 출처: 설정에 적은 창만 그대로 돌려준다(아무것도 지어내지 않는다)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_contracts import UsageSourceDescriptor, UsageWindowSnapshot, x_ui
from agent_console_usage._interfaces import UsageSourceContext
from agent_console_usage._setup import descriptor_fields

__all__ = ["FAKE_TRUST", "FakeUsageSource"]

FAKE_TRUST = "fake"
"""알려진 등급 밖의 값. 신뢰 등급이 열린 문자열임을 보여 주는 예이기도 하다."""

_WINDOW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["window"],
    "properties": {
        "window": {
            "type": "string",
            "minLength": 1,
            "title": "창",
            "description": "보일 사용량 창 이름입니다.",
            **x_ui(
                tier="basic",
                when="다른 창 이름으로 확인하고 싶을 때 바꾸세요.",
                example="five_hour",
            ),
        },
        "used_ratio": {
            "type": ["number", "null"],
            "minimum": 0,
            "title": "사용률",
            "description": "쓴 비율입니다(0~1).",
            **x_ui(
                tier="basic", when="표시기 색·게이지를 확인하고 싶을 때 바꾸세요.", example=0.42
            ),
        },
        "used_tokens": {
            "type": ["integer", "null"],
            "minimum": 0,
            "title": "쓴 토큰",
            "description": "쓴 토큰 수입니다.",
            **x_ui(tier="advanced", example=12000, unit="개"),
        },
        "status": {
            "type": ["string", "null"],
            "title": "상태",
            "description": "창 상태 문자열입니다(예: allowed).",
            **x_ui(tier="advanced", example="allowed"),
        },
        "resets_at": {
            "type": ["number", "null"],
            "title": "초기화 시각",
            "description": "창이 다시 차는 시각(유닉스 초)입니다.",
            **x_ui(tier="advanced", example=1760000000),
        },
        "observed_at": {
            "type": "number",
            "title": "관측 시각",
            "description": "값을 본 시각(유닉스 초)입니다. 비우면 지금입니다.",
            **x_ui(tier="advanced", example=1760000000),
        },
        "resets_in_seconds": {
            "type": "number",
            "title": "초기화까지",
            "description": "지금부터 창이 다시 차기까지 남은 시간입니다.",
            **x_ui(tier="advanced", example=3600, unit="초"),
        },
        "observed_seconds_ago": {
            "type": "number",
            "minimum": 0,
            "title": "관측 경과",
            "description": "값을 본 뒤 지난 시간입니다.",
            **x_ui(tier="advanced", example=60, unit="초"),
        },
    },
    "additionalProperties": False,
}


class FakeUsageSource:
    """config `windows`에 적은 창을 그대로 낸다. 비어 있으면 빈 목록.

    시각은 절대값(`resets_at`, `observed_at`) 또는 지금 기준 상대값(`resets_in_seconds`,
    `observed_seconds_ago`)으로 적는다. 적지 않은 값은 `None`(관측 시각만 기본 = 지금).
    """

    descriptor = UsageSourceDescriptor(
        id="fake",
        title="가짜 사용량(테스트)",
        description="설정에 적은 창을 그대로 보여 준다. E2E·화면 확인용.",
        trust=FAKE_TRUST,
        config_schema={
            "type": "object",
            "properties": {
                "windows": {
                    "type": "array",
                    "items": _WINDOW_SCHEMA,
                    "title": "창 목록",
                    "description": "화면 확인용으로 그대로 보일 사용량 창입니다.",
                    **x_ui(tier="basic", when="화면 확인용 사용량 값을 바꾸고 싶을 때 바꾸세요."),
                }
            },
            "additionalProperties": False,
        },
        **descriptor_fields("fake"),
    )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        out: list[UsageWindowSnapshot] = []
        for item in ctx.config.get("windows", []):
            if not isinstance(item, Mapping):
                continue
            resets_at = item.get("resets_at")
            if resets_at is None and "resets_in_seconds" in item:
                resets_at = ctx.now + float(item["resets_in_seconds"])
            observed_at = item.get("observed_at")
            if observed_at is None:
                observed_at = ctx.now - float(item.get("observed_seconds_ago", 0))
            out.append(
                UsageWindowSnapshot(
                    source=ctx.source_id,
                    window=str(item["window"]),
                    used_ratio=item.get("used_ratio"),
                    used_tokens=item.get("used_tokens"),
                    status=item.get("status"),
                    resets_at=resets_at,
                    observed_at=observed_at,
                )
            )
        return out
