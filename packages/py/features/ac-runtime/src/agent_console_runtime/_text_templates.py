"""응답 글자 칸의 원문 틀 + 값(``text_templates``) 도우미(design §I18N.13 I-15·I-16).

서비스(상태·연결 테스트·로그인·로그아웃)와 백엔드가 같은 규칙으로 칸 값과 ``text_templates``를
맞춘다. 채우기 자체는 계약 순수 함수 ``render_text_template``·``render_text_parts``다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_console_contracts import TextTemplate, render_text_parts

__all__ = ["compact_number", "matching_text_templates"]

_MISSING = object()


def compact_number(value: float) -> float:
    """``:g`` 표기(유효 숫자 6자리)로 줄인 수. 틀 값으로 넣으면 옛 ``{x:g}`` 출력과 같다.

    >>> compact_number(100 / 60)
    1.66667
    >>> compact_number(20.0)
    20.0
    """
    return float(format(value, "g"))


def _resolve(document: Any, pointer: str) -> Any:
    """JSON Pointer(RFC 6901) 값(없으면 ``_MISSING``)."""
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        return _MISSING
    node = document
    for raw in pointer[1:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, Mapping):
            if key not in node:
                return _MISSING
            node = node[key]
        elif isinstance(node, list):
            if not key.isdigit() or int(key) >= len(node):
                return _MISSING
            node = node[int(key)]
        else:
            return _MISSING
    return node


def matching_text_templates(
    document: Mapping[str, Any], templates: Mapping[str, Sequence[TextTemplate]]
) -> dict[str, list[TextTemplate]]:
    """``templates`` 중 칸 값과 맞는 항목만(포인터가 ``document``의 글자 칸이고 채운 값이 그 칸 값).

    맞지 않는 항목(잘린 칸·다른 문장으로 바뀐 칸·없는 칸)은 뺀다 — 화면이 다른 문장의 번역을
    보이지 않게. ``document``는 가리기 전 응답 JSON이다.

    >>> t = TextTemplate(template="{n}초", params={"n": 2})
    >>> doc = {"message": "2초", "detail": "x"}
    >>> matching_text_templates(doc, {"/message": [t], "/detail": [t]})
    {'/message': [TextTemplate(template='{n}초', params={'n': 2})]}
    """
    kept: dict[str, list[TextTemplate]] = {}
    for pointer, parts in templates.items():
        value = _resolve(document, pointer)
        if not isinstance(value, str) or not parts:
            continue
        if render_text_parts(parts) == value:
            kept[pointer] = list(parts)
    return kept
