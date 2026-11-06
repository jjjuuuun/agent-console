"""Agent Console — 안전 문자열 치환 기반 패키지.

공개 API:
    - ``render_template(template, values, *, max_chars)``: `{이름}`·`{이름:형식}` 치환.
    - ``fill_value(value, values, *, max_chars)``: 매핑·목록 안 문자열 전부에 치환을 적용한 사본.
    - ``template_variables(template) -> set[str]``: 틀이 참조하는 변수 이름.
    - ``DEFAULT_MAX_RENDER_CHARS``: 결과 길이 기본 상한.
"""

from __future__ import annotations

from agent_console_text_template._template import (
    DEFAULT_MAX_RENDER_CHARS,
    fill_value,
    render_template,
    template_variables,
)

__all__ = ["DEFAULT_MAX_RENDER_CHARS", "fill_value", "render_template", "template_variables"]
