"""페이지 머리말 읽기: 첫 줄이 구분 줄(데이터)이면 다음 구분 줄까지를 YAML(safe)로 읽는다.

깨진 머리말(닫는 줄 없음·YAML 오류·객체가 아님)은 `wiki.front_matter_invalid`를 내고 본문으로 읽는다
(design §7R.1.2).
"""

from __future__ import annotations

import io
import re
import threading
from dataclasses import dataclass, field
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from ._text import jsonable

__all__ = ["FrontMatter", "read_front_matter"]

_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n|\Z)")


@dataclass(slots=True)
class FrontMatter:
    """머리말 읽은 결과.

    Attributes:
        data: 머리말 값(JSON으로 옮길 수 있는 값). 없거나 깨졌으면 빈 객체.
        body_start: 본문 시작 위치(코드 포인트). 머리말이 없거나 깨졌으면 0.
        body_line: 본문 첫 줄 번호(1부터).
        error: 깨졌을 때 사람이 읽는 이유(값 원문 없음). 정상이면 None.
        error_line: 깨진 곳의 줄 번호(알면).
    """

    data: dict[str, Any] = field(default_factory=dict)
    body_start: int = 0
    body_line: int = 1
    error: str | None = None
    error_line: int | None = None


_LOCAL = threading.local()


def _safe_yaml() -> YAML:
    # YAML 객체를 만드는 비용이 읽기보다 커서 스레드마다 하나를 다시 쓴다(객체는 스레드 안전하지
    # 않다).
    yaml: YAML | None = getattr(_LOCAL, "yaml", None)
    if yaml is None:
        yaml = YAML(typ="safe")
        yaml.allow_duplicate_keys = False
        _LOCAL.yaml = yaml
    return yaml


_PLAIN = re.compile(r"[^\x00-\x1f\x7f\x85\u2028\u2029\ufeff#:{}\[\],&*!|>'\"%@`\\]+")
_AMBIGUOUS = frozenset({"null", "true", "false", "yes", "no", "on", "off", "y", "n"})
_AMBIGUOUS_START = frozenset("-+.0123456789~?<=")
_NEWLINES = re.compile(r"\r\n|\r|\n")
_SIMPLE_LINE = re.compile(r"([^ ][^:]*?): (.+)")


def _plain(value: str) -> bool:
    """YAML(1.1·1.2 모두)에서 틀림없이 글자로 읽히는 평이한 값인지(아니면 일반 YAML로 읽는다)."""
    return (
        bool(value)
        and value == value.strip(" ")
        and value[0] not in _AMBIGUOUS_START
        and value.casefold() not in _AMBIGUOUS
        and _PLAIN.fullmatch(value) is not None
    )


def _simple_yaml(source: str) -> dict[str, Any] | None:
    """흔한 머리말(`키: 값`, `키: [값, 값]`)만 빠르게 읽는다. 그 밖의 모양이면 None(일반 YAML로).

    받아들이는 모양의 값은 모두 YAML 평이한 글자라 일반 YAML 읽기와 결과가 같다(테스트가 견준다).
    페이지 수천 개를 읽을 때 머리말 읽기가 블록 파싱만큼 걸려서 둔 빠른 길이다(design §7R.14).
    """
    out: dict[str, Any] = {}
    for raw in _NEWLINES.split(source):
        if not raw.strip():
            continue
        m = _SIMPLE_LINE.fullmatch(raw)
        if m is None:
            return None
        key, value = m.group(1), m.group(2)
        if not _plain(key) or key in out:
            return None
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip(" ")
            items = [item.strip(" ") for item in inner.split(",")] if inner else []
            if not all(_plain(item) for item in items):
                return None
            out[key] = items
        elif _plain(value):
            out[key] = value
        else:
            return None
    return out


def read_front_matter(text: str, delimiter: str | None) -> FrontMatter:
    """`text` 맨 앞의 머리말을 읽는다.

    Args:
        text: 페이지 본문 원문.
        delimiter: 구분 줄(예 `---`). None·빈 값이면 머리말을 읽지 않는다.

    Returns:
        `FrontMatter`. 첫 줄이 구분 줄이 아니면 머리말 없음(오류 아님).
    """
    if not delimiter or not text.startswith(delimiter):
        return FrontMatter()
    lines = iter(_LINE.finditer(text))
    first = next(lines)
    if first.group(0).rstrip("\r\n").rstrip() != delimiter:
        return FrontMatter()
    start = first.end()
    line_no = 1
    for m in lines:
        line_no += 1
        raw = m.group(0)
        if raw.rstrip("\r\n").rstrip() == delimiter:
            source = text[start : m.start()]
            simple = _simple_yaml(source)
            if simple is not None:
                return FrontMatter(data=simple, body_start=m.end(), body_line=line_no + 1)
            try:
                loaded = _safe_yaml().load(io.StringIO(source))
            except YAMLError as exc:
                mark = getattr(exc, "problem_mark", None)
                err_line = 2 + mark.line if mark is not None else None
                return FrontMatter(error="머리말 YAML을 읽을 수 없습니다.", error_line=err_line)
            if loaded is None:
                loaded = {}
            if not isinstance(loaded, dict):
                return FrontMatter(error="머리말이 키: 값 모양이 아닙니다.", error_line=2)
            return FrontMatter(data=jsonable(loaded), body_start=m.end(), body_line=line_no + 1)
        if m.end() >= len(text):
            break
    return FrontMatter(error="머리말을 닫는 구분 줄이 없습니다.", error_line=1)
