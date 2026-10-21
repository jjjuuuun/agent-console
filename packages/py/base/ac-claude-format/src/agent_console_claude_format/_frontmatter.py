"""`---`로 감싼 YAML frontmatter 읽기·쓰기와 JSON 호환 변환."""

from __future__ import annotations

import io
import json
import re
from collections.abc import Mapping
from typing import Any

from ruamel.yaml import YAML

__all__ = ["dump_json", "json_safe", "parse_frontmatter", "render_frontmatter", "str_list"]

_FENCE = "---"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """`---`로 감싼 YAML frontmatter와 본문. 없거나 잘못되면 `({}, 원문)`.

    본문은 닫는 `---` 다음 줄부터 그대로다(앞뒤 공백을 다듬지 않는다).
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FENCE:
        return {}, text
    for index in range(1, len(lines)):
        if lines[index].strip() == _FENCE:
            head = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            try:
                data = YAML(typ="safe", pure=True).load(head)
            except Exception:
                return {}, text
            if data is None:
                return {}, body
            return (dict(data) if isinstance(data, Mapping) else {}), body
    return {}, text


def _yaml() -> YAML:
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096
    yaml.sort_base_mapping_type_on_output = False  # type: ignore[assignment]  # 키 순서 유지
    return yaml


def render_frontmatter(meta: Mapping[str, Any], body: str) -> str:
    """frontmatter(키 순서 유지, 비어 있으면 생략) + 빈 줄 + 본문(끝 줄바꿈 하나)."""
    text = body.strip("\n")
    tail = f"{text}\n" if text else ""
    if not meta:
        return tail
    buffer = io.StringIO()
    _yaml().dump(json_safe(dict(meta)), buffer)
    head = f"{_FENCE}\n{buffer.getvalue()}{_FENCE}\n"
    return f"{head}\n{tail}" if tail else head


def json_safe(value: Any) -> Any:
    """YAML 값(날짜 등)을 JSON 호환 값으로."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def dump_json(data: Any) -> str:
    """사람이 읽는 JSON(들여쓰기 2, 유니코드 그대로, 끝 줄바꿈)."""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


_COMMA = re.compile(r"\s*,\s*")


def str_list(value: Any) -> list[str] | None:
    """쉼표로 이은 문자열 또는 목록 → 빈 값을 뺀 문자열 목록. 둘 다 아니면 None."""
    if isinstance(value, str):
        items = _COMMA.split(value.strip())
    elif isinstance(value, list):
        items = [str(v).strip() for v in value]
    else:
        return None
    return [v for v in items if v]
