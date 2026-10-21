"""선언형 종류의 안전 치환(design §5.4 `fill`과 같은 규칙).

`{이름}`·`{이름:형식}`만 치환한다. 속성·인덱스 접근을 하지 않고, 형식 지정자는 숫자 정밀도
(`.1f`, `.0%`)만 허용한다. 모르는 이름·허용하지 않는 형식은 원문 그대로 둔다. 치환된 값은 다시
치환하지 않는다(본문 안의 `{...}`는 그대로 남는다).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

__all__ = ["DEFAULT_MAX_RENDER_CHARS", "fill_value", "render_template"]

_FIELD = re.compile(r"\{(\w+)(?::([^{}]*))?\}")
_SAFE_SPEC = re.compile(r"\.\d{1,2}[f%]?")

DEFAULT_MAX_RENDER_CHARS = 1_000_000
"""치환 결과의 기본 최대 길이(지침 본문이 들어가므로 콘솔 `fill`보다 크다)."""


def render_template(
    template: str, values: Mapping[str, Any], *, max_chars: int = DEFAULT_MAX_RENDER_CHARS
) -> str:
    """`template`의 `{이름}`을 `values`로 바꾼다. 결과는 `max_chars`에서 잘라 `…`를 붙인다."""

    def sub(m: re.Match[str]) -> str:
        name, spec = m.group(1), m.group(2)
        if name not in values:
            return m.group(0)
        value = values[name]
        if spec is None:
            return str(value)
        if not _SAFE_SPEC.fullmatch(spec):
            return m.group(0)
        try:
            return format(value, spec)
        except (ValueError, TypeError):
            return str(value)

    result = _FIELD.sub(sub, template)
    if len(result) > max_chars:
        return result[: max(max_chars - 1, 0)] + "…"
    return result


def fill_value(
    value: Any, values: Mapping[str, Any], *, max_chars: int = DEFAULT_MAX_RENDER_CHARS
) -> Any:
    """객체·목록 안의 모든 문자열에 `render_template`을 적용한 사본. 키는 바꾸지 않는다."""
    if isinstance(value, str):
        return render_template(value, values, max_chars=max_chars)
    if isinstance(value, Mapping):
        return {k: fill_value(v, values, max_chars=max_chars) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [fill_value(v, values, max_chars=max_chars) for v in value]
    return value
