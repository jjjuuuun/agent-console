"""안전 문자열 치환(design §5.4 `fill`과 같은 규칙, §6R.3 `ac-text-template`).

`{이름}`·`{이름:형식}`만 치환한다. 속성·인덱스 접근을 하지 않고, 형식 지정자는 숫자 정밀도
(`.1f`, `.0%`)만 허용한다. 모르는 이름·허용하지 않는 형식은 원문 그대로 둔다. 치환된 값은 다시
치환하지 않는다(값 안의 `{...}`는 그대로 남는다).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

__all__ = ["DEFAULT_MAX_RENDER_CHARS", "fill_value", "render_template", "template_variables"]

_FIELD = re.compile(r"\{(\w+)(?::([^{}]*))?\}")
_SAFE_SPEC = re.compile(r"\.\d{1,2}[f%]?")

DEFAULT_MAX_RENDER_CHARS = 1_000_000
"""치환 결과의 기본 최대 길이(문자 수)."""


def render_template(
    template: str, values: Mapping[str, Any], *, max_chars: int = DEFAULT_MAX_RENDER_CHARS
) -> str:
    """`template`의 `{이름}`·`{이름:형식}`을 `values`로 바꾼다.

    Args:
        template: 틀 문자열.
        values: 이름 → 값. 값은 `str()`(형식이 있으면 `format()`)로 바뀐다.
        max_chars: 결과 최대 길이. 넘으면 `max_chars - 1`자에서 잘라 `…`를 붙인다.

    Returns:
        치환한 문자열. 모르는 이름, 허용하지 않는 형식(`.1f`·`.0%`·`.2` 꼴만 허용)은 원문 그대로다.
        값에 맞지 않는 형식은 `str(value)`로 대신한다. 예외를 던지지 않는다.
    """

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
    """객체·목록 안의 모든 문자열에 `render_template`을 적용한 사본. 키는 바꾸지 않는다.

    튜플은 목록으로 바뀐다(JSON 직렬화 대상 전제). 문자열·매핑·목록이 아닌 값은 그대로 돌려준다.
    """
    if isinstance(value, str):
        return render_template(value, values, max_chars=max_chars)
    if isinstance(value, Mapping):
        return {k: fill_value(v, values, max_chars=max_chars) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [fill_value(v, values, max_chars=max_chars) for v in value]
    return value


def template_variables(template: Any) -> set[str]:
    """틀이 참조하는 변수 이름(모르는 변수 검사용).

    Args:
        template: 문자열, 또는 문자열을 담은 매핑·목록(`fill_value`와 같은 순회, 키는 보지 않는다).

    Returns:
        `{이름}`·`{이름:형식}` 자리의 이름 집합. 형식이 허용되지 않는 자리도 이름은 포함한다
        (그 자리는 치환되지 않지만 틀이 그 이름을 쓰려 한 것이므로). 문자열이 없으면 빈 집합.
    """
    found: set[str] = set()
    if isinstance(template, str):
        found.update(m.group(1) for m in _FIELD.finditer(template))
    elif isinstance(template, Mapping):
        for v in template.values():
            found |= template_variables(v)
    elif isinstance(template, list | tuple):
        for v in template:
            found |= template_variables(v)
    return found
