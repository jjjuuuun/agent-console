"""포인터 자리 표시 틀(`{/포인터}`·`{/포인터|count}`) → 원문 틀 + 값(계약 `TextTemplate`).

분류기 설정의 제목·요약 틀은 자리 표시가 JSON 포인터라 화면 번역의 원문 키로 쓸 수 없다.
여기서 자리 표시를 이름(`{name}`)으로 바꾼 틀과 채운 값을 만든다(`LogEvent.text_templates`).

이름 규칙(저장소 i18n 검사 `static.data`의 `pointer_slots`와 같아야 한다):

- 포인터 마지막 조각(`~1`→`/`, `~0`→`~`), 글자·숫자·`_` 밖 글자는 `_`, 숫자로 시작하면 앞에 `v`,
  빈 조각이면 `value`.
- `|keys`·`|count`가 붙으면 `_keys`·`_count`를 덧붙인다.
- 서로 다른 자리 표시가 같은 이름이 되면 틀을 만들지 않는다(칸 값은 그대로 원문이다).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from agent_console_contracts import TextTemplate, render_text_template

__all__ = ["POINTER_SLOT", "pointer_text_template", "slot_name"]

POINTER_SLOT = re.compile(r"\{(/[^{}|]*)(?:\|(\w+))?\}")
"""자리 표시 `{/포인터}`·`{/포인터|방식}`(그룹 1 = 포인터, 2 = 방식)."""


def slot_name(pointer: str, mode: str | None = None) -> str:
    """자리 표시 하나의 이름.

    >>> slot_name("/data/hookName"), slot_name("/output", "count"), slot_name("/output/0")
    ('hookName', 'output_count', 'v0')
    """
    pieces = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/") if p]
    base = re.sub(r"\W", "_", pieces[-1]) if pieces else ""
    if not base:
        base = "value"
    elif not (base[0].isalpha() or base[0] == "_"):
        base = f"v{base}"
    return f"{base}_{mode}" if mode else base


def _literal(text: str) -> str:
    return text.replace("{", "{{").replace("}", "}}")


def pointer_text_template(
    template: str, values: Mapping[tuple[str, str | None], str], shown: str
) -> TextTemplate | None:
    """포인터 틀 + 채운 자리 값 → 원문 틀 + 값. 쓸 수 없으면 None.

    Args:
        template: 설정의 틀(`{/포인터}` 자리 표시).
        values: (포인터, 방식) → 채운 글자.
        shown: 칸에 실제로 들어간 값(틀을 채운 결과와 같아야 한다).

    Returns:
        자리 표시가 없거나, 자리 밖에 글자(문자)가 없거나(값만으로 된 틀), 이름이 겹치거나, 채운
        결과가 ``shown``과 다르면 None.

    >>> pointer_text_template("요약 · {/hookCount}개", {("/hookCount", None): "2"}, "요약 · 2개")
    TextTemplate(template='요약 · {hookCount}개', params={'hookCount': '2'})
    """
    matches = list(POINTER_SLOT.finditer(template))
    if not matches:
        return None
    if not any(ch.isalpha() for ch in POINTER_SLOT.sub("", template)):
        return None
    names: dict[tuple[str, str | None], str] = {}
    for m in matches:
        key = (m.group(1), m.group(2))
        names.setdefault(key, slot_name(*key))
    if len(set(names.values())) != len(names):
        return None
    out: list[str] = []
    params: dict[str, str] = {}
    last = 0
    for m in matches:
        key = (m.group(1), m.group(2))
        out.append(_literal(template[last : m.start()]))
        out.append("{" + names[key] + "}")
        params[names[key]] = values.get(key, "")
        last = m.end()
    out.append(_literal(template[last:]))
    built = TextTemplate(template="".join(out).strip(), params=dict(params))
    return built if render_text_template(built) == shown else None
