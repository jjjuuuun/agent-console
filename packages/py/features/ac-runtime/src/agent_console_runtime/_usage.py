"""사용량 합산·미리보기 같은 작은 순수 함수."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from agent_console_contracts import Usage

DEFAULT_PREVIEW_CHARS = 200
"""이벤트 미리보기(`outputs_preview`, `value_preview`) 기본 최대 길이."""


def sum_usage(usages: Iterable[Usage | None]) -> Usage | None:
    """사용량을 키별로 더한다. 어느 쪽도 값이 없는 키는 None, 입력이 모두 None이면 None.

    알려진 키 외 추가 숫자 키도 더한다(숫자가 아닌 추가 값은 무시).
    """
    totals: dict[str, int | float] = {}
    seen = False
    for usage in usages:
        if usage is None:
            continue
        seen = True
        for key, value in usage.model_dump().items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            totals[key] = totals.get(key, 0) + value
    if not seen:
        return None
    return Usage.model_validate(totals)


def preview(value: Any, limit: int = DEFAULT_PREVIEW_CHARS) -> str | None:
    """값의 짧은 표시 문자열(JSON, 넘치면 `…`로 자른다). 값이 None이면 None."""
    if value is None:
        return None
    text = value if isinstance(value, str) else _dumps(value)
    if len(text) > limit:
        return text[: max(limit - 1, 0)] + "…"
    return text


def _dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return repr(value)
