"""쓰기·점검 규칙의 판단 대상(subject) 만들기(design §7R.1.1).

규칙 조건(`ac-conditions`, 7R.8)이 JSON 포인터로 읽는 값이다. 모양은 계약 상수
`WIKI_WRITE_SUBJECT_PATHS`·`WIKI_LINT_SUBJECT_PATHS`(조건 위젯 제안)와 맞춘다 — 테스트가 상수의 모든
최상위 키가 여기서 나오는지 단언한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_contracts.wiki import WikiAuthor

__all__ = ["lint_subject", "write_subject"]


def write_subject(
    *,
    op: str,
    author: WikiAuthor,
    page: Mapping[str, Any],
    before: Mapping[str, Any] | None = None,
    from_: str | None = None,
    to: str | None = None,
) -> dict[str, Any]:
    """쓰기 판단 대상 `{change, author, page, before}`.

    Args:
        op: 쓰기 동작(`KnownWikiChangeOps`: create·update·delete·move, 열린 문자열).
        author: 쓴 쪽.
        page: 쓴 뒤 페이지 사실(`page_facts`·`WikiIndex.facts`). 지우기는 지우기 전 사실.
        before: 쓰기 전 페이지 사실(새 페이지면 None).
        from_: 옮기기의 옛 경로.
        to: 옮기기의 새 경로.
    """
    change: dict[str, Any] = {"op": op}
    if from_ is not None:
        change["from"] = from_
    if to is not None:
        change["to"] = to
    return {
        "change": change,
        "author": author.model_dump(mode="json", exclude_none=True),
        "page": dict(page),
        "before": dict(before) if before is not None else None,
    }


def lint_subject(
    page: Mapping[str, Any],
    *,
    backlinks: int,
    age_days: float | None,
    idle_days: float | None,
    updated_by_kind: str | None,
) -> dict[str, Any]:
    """점검 판단 대상 `{path, title, tags, front_matter, bytes, age_days, idle_days, backlinks,
    links_out, broken_links, updated_by_kind}`.

    Args:
        page: 페이지 사실(`page_facts`·`WikiIndex.facts`).
        backlinks: 들어오는 링크가 있는 페이지 수.
        age_days: 첫 기록 뒤 지난 날(모르면 None).
        idle_days: 마지막 변경 뒤 지난 날(모르면 None).
        updated_by_kind: 마지막으로 쓴 쪽의 종류(모르면 None).
    """
    return {
        "path": page.get("path"),
        "title": page.get("title", ""),
        "tags": list(page.get("tags", ())),
        "aliases": list(page.get("aliases", ())),
        "front_matter": dict(page.get("front_matter", {})),
        "bytes": page.get("bytes", 0),
        "age_days": age_days,
        "idle_days": idle_days,
        "backlinks": backlinks,
        "links_out": page.get("links_out", 0),
        "broken_links": page.get("broken_links", 0),
        "updated_by_kind": updated_by_kind,
    }
