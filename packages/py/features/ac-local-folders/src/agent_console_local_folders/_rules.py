"""규칙 데이터(패키지 데이터 `data/browse_defaults.json`, 바꿀 수 있음): 숨김 이름·시작 위치."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any, cast

from ._types import PathFlavor

__all__ = [
    "BrowseDefaults",
    "RootRule",
    "load_browse_defaults",
]

_FLAVORS: tuple[PathFlavor, ...] = ("posix", "windows")


def _package_json(name: str) -> Any:
    text = resources.files(__package__).joinpath("data", name).read_text(encoding="utf-8")
    return json.loads(text)


def _flavor(value: Any, where: str) -> PathFlavor:
    if value not in _FLAVORS:
        raise ValueError(f"{where}: 경로 방식은 posix 또는 windows여야 합니다: {value!r}")
    return cast(PathFlavor, value)


def _names(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{where}: 문자열 목록이어야 합니다")
    return tuple(value)


def _text(data: Mapping[str, Any], key: str, where: str, *, required: bool = True) -> str | None:
    value = data.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: {key}는 빈 값이 아닌 문자열이어야 합니다")
    return value


@dataclass(frozen=True)
class RootRule:
    """기본 시작 위치 규칙 하나.

    `path` 틀(`~` = 홈, `each`가 있으면 글자마다 `{item}`) 또는 `parent` + `name_pattern`
    (그 아래 폴더 중 이름이 맞는 것). `label`은 `{path}`·`{name}`·`{NAME}`·`{item}` 틀.
    """

    kind: str
    label: str
    path: str | None = None
    each: str = ""
    parent: str | None = None
    name_pattern: re.Pattern[str] | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str) -> RootRule:
        """dict → 규칙. `path`와 `parent` 중 하나가 있어야 한다."""
        kind = _text(data, "kind", where) or ""
        path = _text(data, "path", where, required=False)
        parent = _text(data, "parent", where, required=False)
        if (path is None) == (parent is None):
            raise ValueError(f"{where}: path와 parent 중 하나만 있어야 합니다")
        pattern_text = _text(data, "name_pattern", where, required=False)
        try:
            pattern = re.compile(pattern_text) if pattern_text else None
        except re.error as exc:
            raise ValueError(f"{where}: name_pattern 정규식 오류: {exc}") from exc
        each = data.get("each", "")
        if not isinstance(each, str):
            raise ValueError(f"{where}: each는 문자열이어야 합니다")
        return cls(
            kind=kind,
            label=_text(data, "label", where, required=False) or "{path}",
            path=path,
            each=each,
            parent=parent,
            name_pattern=pattern,
        )


@dataclass(frozen=True)
class BrowseDefaults:
    """탐색 기본값.

    Attributes:
        hidden_names: 점·숨김 속성이 없어도 숨김으로 볼 폴더 이름(대소문자 무시, 기본은 빈 목록).
        roots: 경로 방식별 시작 위치 규칙.
    """

    hidden_names: frozenset[str]
    roots: Mapping[PathFlavor, tuple[RootRule, ...]]

    def is_hidden_name(self, name: str) -> bool:
        """이름 목록에 있는가(대소문자 무시)."""
        return name.casefold() in self.hidden_names


def load_browse_defaults(data: Mapping[str, Any] | None = None) -> BrowseDefaults:
    """탐색 기본값. `data`가 없으면 패키지 기본 데이터(`data/browse_defaults.json`).

    Raises:
        ValueError: 형식이 틀림.

    >>> d = load_browse_defaults({"hidden_names": ["Build-Cache"], "roots": {}})
    >>> d.is_hidden_name("build-cache"), d.roots
    (True, {})
    """
    raw = _package_json("browse_defaults.json") if data is None else data
    names = _names(raw.get("hidden_names"), "browse_defaults.hidden_names")
    roots_raw = raw.get("roots", {})
    if not isinstance(roots_raw, Mapping):
        raise ValueError("browse_defaults.roots는 객체여야 합니다")
    roots: dict[PathFlavor, tuple[RootRule, ...]] = {}
    for flavor, items in roots_raw.items():
        fl = _flavor(flavor, "browse_defaults.roots")
        if not isinstance(items, Sequence):
            raise ValueError(f"browse_defaults.roots.{fl}는 목록이어야 합니다")
        roots[fl] = tuple(
            RootRule.from_dict(item, f"browse_defaults.roots.{fl}[{i}]")
            for i, item in enumerate(items)
        )
    return BrowseDefaults(hidden_names=frozenset(n.casefold() for n in names), roots=roots)
