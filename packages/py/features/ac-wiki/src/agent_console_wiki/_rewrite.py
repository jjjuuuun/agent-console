"""이름 바꾸기 링크 고치기: 링크 원문 안의 대상 부분만 바꾸고 나머지 바이트는 그대로 둔다.

렌더러로 다시 쓰지 않는다(사용자 서식·줄바꿈 종류·탭이 바뀌지 않게, design §7R.10). 경로(`path`)나
상대 경로(`relative_path`)로 찾은 링크만 고친다 — 제목·별칭으로 찾은 링크는 옮긴 뒤에도 그대로
이어진다.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass

from agent_console_contracts.wiki import KnownWikiResolvers

from ._compiled import CompiledWikiSyntax
from ._index import IndexedLink
from ._paths import relative_file, split_extension

__all__ = ["RewriteResult", "rewrite_links"]


@dataclass(frozen=True, slots=True)
class RewriteResult:
    """링크 고치기 결과.

    Attributes:
        text: 고친 본문.
        count: 고친 링크 수.
        skipped: 원문이 색인과 달라(그사이 바뀜) 건너뛴 링크 수.
    """

    text: str
    count: int
    skipped: int = 0


def _new_target(
    item: IndexedLink,
    original: str,
    *,
    page_after: str,
    target_after: str,
    syntax: CompiledWikiSyntax,
    angle: bool,
) -> str:
    split = split_extension(original.split("#", 1)[0], syntax.page_extensions)
    if item.resolver == KnownWikiResolvers.PATH:
        ext = split[1] if split is not None else ""
        lead = "/" if original.startswith("/") else ""
        return f"{lead}{target_after}{ext}"
    # relative_path: 링크가 있는 페이지(옮긴 뒤 위치) 폴더에서 대상 파일까지.
    decoded = urllib.parse.unquote(original)
    dsplit = split_extension(decoded, syntax.page_extensions)
    ext = dsplit[1] if dsplit is not None else (split[1] if split else syntax.new_page_extension)
    rel = relative_file(page_after, target_after + ext)
    if decoded.startswith("./") and not rel.startswith("../"):
        rel = "./" + rel
    if not angle and (decoded != original or any(c in rel for c in " \t()<>")):
        rel = urllib.parse.quote(rel, safe="/.-_~!$&'*+,;=:@")
    return rel


def rewrite_links(
    text: str,
    links: Iterable[IndexedLink],
    *,
    page: str,
    old: str,
    new: str,
    syntax: CompiledWikiSyntax,
) -> RewriteResult:
    """페이지 `old`를 `new`로 옮길 때 한 페이지 본문의 링크를 고친다.

    Args:
        text: 그 페이지 본문(색인을 만든 원문 그대로 — 줄바꿈 바꾸지 않은 것).
        links: 그 페이지의 해석한 링크(`WikiIndex.links[page]`).
        page: 고칠 페이지 경로. `old`와 같으면 옮기는 페이지 자신이라, 상대 경로 링크를 새 위치
            기준으로 모두 다시 계산한다.
        old: 옮기기 전 페이지 경로.
        new: 옮긴 뒤 페이지 경로.
        syntax: 컴파일 문법(페이지 확장자).

    Returns:
        `RewriteResult`. 링크 밖 글자는 한 글자도 바뀌지 않는다.
    """
    moved_self = page == old
    page_after = new if moved_self else page
    edits: list[tuple[int, int, str]] = []
    skipped = 0
    for item in links:
        link = item.link
        if item.resolved is None or link.target_start is None or link.target_end is None:
            continue
        if item.resolver not in (KnownWikiResolvers.PATH, KnownWikiResolvers.RELATIVE_PATH):
            continue
        points_old = item.resolved == old
        if not points_old and not (
            moved_self and item.resolver == KnownWikiResolvers.RELATIVE_PATH
        ):
            continue
        if text[link.start : link.end] != link.raw:
            skipped += 1
            continue
        original = text[link.target_start : link.target_end]
        angle = link.target_start > 0 and text[link.target_start - 1] == "<"
        target_after = new if points_old else item.resolved
        replacement = _new_target(
            item,
            original,
            page_after=page_after,
            target_after=target_after,
            syntax=syntax,
            angle=angle,
        )
        if replacement != original:
            edits.append((link.target_start, link.target_end, replacement))
    if not edits:
        return RewriteResult(text=text, count=0, skipped=skipped)
    parts: list[str] = []
    cursor = 0
    for start, end, replacement in sorted(edits):
        parts.append(text[cursor:start])
        parts.append(replacement)
        cursor = end
    parts.append(text[cursor:])
    return RewriteResult(text="".join(parts), count=len(edits), skipped=skipped)
