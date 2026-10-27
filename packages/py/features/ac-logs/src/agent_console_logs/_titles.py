"""세션 제목 순위 규칙(데이터, 5R.19).

세션 제목은 태그가 붙은 이벤트의 `title`이다. 어떤 태그를 어떤 순서로 볼지, 같은 태그가 여러
번이면 처음 것과 마지막 것 중 무엇을 쓸지는 **규칙 데이터**다(`QueryContext.session_title_rules`).
규칙을 위에서부터 보고, 제목이 빈 문자열이 아닌 후보가 있는 첫 규칙이 이긴다. 후보가 하나도
없으면 빈 제목이다.

기본 규칙은 패키지 데이터 `data/default_session_title_rules.yaml`이고, 파일이 없거나 비면
`DEFAULT_SESSION_TITLE_RULES`(태그 `session_title`의 첫 후보 — 4R 동작)를 쓴다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal, Protocol

from ruamel.yaml import YAML

from ._draft import TAG_SESSION_TITLE

__all__ = [
    "DEFAULT_SESSION_TITLE_RULES",
    "DEFAULT_SESSION_TITLE_RULES_RESOURCE",
    "SessionTitleRule",
    "load_default_session_title_rules",
    "parse_session_title_rules",
    "pick_session_title",
]

TitlePick = Literal["first", "last"]

DEFAULT_SESSION_TITLE_RULES_RESOURCE = "data/default_session_title_rules.yaml"
"""패키지 안 기본 세션 제목 규칙 파일(코드가 아닌 데이터)."""


@dataclass(frozen=True, slots=True)
class SessionTitleRule:
    """세션 제목 규칙 하나.

    Attributes:
        tag: 후보 이벤트가 가진 태그.
        pick: 후보가 여럿이면 시각순 `first`(처음) 또는 `last`(마지막).
    """

    tag: str
    pick: TitlePick = "first"


DEFAULT_SESSION_TITLE_RULES: tuple[SessionTitleRule, ...] = (
    SessionTitleRule(TAG_SESSION_TITLE, "first"),
)
"""규칙 데이터가 없을 때의 규칙: `session_title` 태그의 시각순 첫 후보."""


class _Titled(Protocol):
    @property
    def title(self) -> str: ...

    @property
    def tags(self) -> Sequence[str]: ...


def parse_session_title_rules(data: Any) -> tuple[SessionTitleRule, ...]:
    """`{rules: [{tag, pick}]}` 또는 `[{tag, pick}]` → 규칙 목록(빈 값 = 빈 목록).

    Raises:
        ValueError: 모양이 틀렸을 때(`tag`가 빈 문자열, `pick`이 first·last가 아님).
    """
    if data is None:
        return ()
    items = data.get("rules") if isinstance(data, Mapping) else data
    if items is None:
        return ()
    if not isinstance(items, list):
        raise ValueError("세션 제목 규칙은 목록이어야 합니다")
    out: list[SessionTitleRule] = []
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError(f"세션 제목 규칙 {i}: {{tag, pick}} 객체여야 합니다")
        tag = item.get("tag")
        pick = item.get("pick", "first")
        if not isinstance(tag, str) or not tag:
            raise ValueError(f"세션 제목 규칙 {i}: tag가 비었습니다")
        if pick not in ("first", "last"):
            raise ValueError(f"세션 제목 규칙 {i}: pick은 first 또는 last입니다")
        out.append(SessionTitleRule(tag, pick))
    return tuple(out)


def load_default_session_title_rules(path: Path | None = None) -> tuple[SessionTitleRule, ...]:
    """기본 세션 제목 규칙을 읽는다.

    Args:
        path: 다른 파일을 기본값으로 쓸 때. 없으면 패키지 데이터.

    Returns:
        규칙 목록. 파일이 없거나 규칙이 비면 `DEFAULT_SESSION_TITLE_RULES`(지워도 동작한다).

    Raises:
        ValueError: 파일 모양이 틀렸을 때.
    """
    try:
        if path is not None:
            text = path.read_text(encoding="utf-8")
        else:
            text = (
                resources.files("agent_console_logs")
                .joinpath(DEFAULT_SESSION_TITLE_RULES_RESOURCE)
                .read_text(encoding="utf-8")
            )
    except (FileNotFoundError, NotADirectoryError):
        return DEFAULT_SESSION_TITLE_RULES
    data = YAML(typ="safe").load(text) if text.strip() else None
    return parse_session_title_rules(data) or DEFAULT_SESSION_TITLE_RULES


def pick_session_title(ordered: Iterable[_Titled], rules: Sequence[SessionTitleRule]) -> str:
    """시각순으로 정렬된 이벤트에서 규칙대로 세션 제목을 고른다(없으면 빈 문자열)."""
    events = [e for e in ordered if e.title]
    for rule in rules:
        found = [e for e in events if rule.tag in e.tags]
        if found:
            return (found[-1] if rule.pick == "last" else found[0]).title
    return ""
