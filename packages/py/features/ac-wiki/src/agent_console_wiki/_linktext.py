"""링크 넣기 글 만들기(design §7R.18 Q3): 링크 규칙의 `insert` 틀(`ac-text-template`)을 서버가
채운다.

변수(`WIKI_LINK_INSERT_VARIABLES`): `target`(대상 페이지 경로), `label`(링크 글자),
`relative_path`(링크를 넣을 페이지 폴더에서 대상 파일까지 — 첫 페이지 확장자를 붙임).
"""

from __future__ import annotations

import urllib.parse

from agent_console_contracts.wiki import EffectiveWikiSyntax, WikiLinkText
from agent_console_text_template import render_template

from ._compiled import CompiledWikiSyntax, compile_syntax
from ._errors import WikiLinkInsertUnavailableError
from ._paths import check_page_path, relative_file

__all__ = ["render_link_text"]


def render_link_text(
    syntax: CompiledWikiSyntax | EffectiveWikiSyntax,
    *,
    from_page: str,
    target: str,
    label: str | None = None,
    rule_id: str | None = None,
) -> WikiLinkText:
    """링크 넣기 글을 만든다.

    Args:
        syntax: 컴파일 문법 또는 유효 문법.
        from_page: 링크를 넣을 페이지 경로(상대 경로 기준).
        target: 대상 페이지 경로(확장자 없음).
        label: 링크 글자. None·빈 값이면 `target`(대상 제목을 쓰려면 호출자가 색인에서 찾아 준다).
        rule_id: 쓸 링크 규칙. None이면 `insert`가 있는 첫 링크 규칙.

    Returns:
        `WikiLinkText{rule_id, text}`.

    Raises:
        WikiLinkInsertUnavailableError: 그 규칙(또는 어느 규칙에도) `insert`가 없다.
        WikiPathError: `from_page`·`target`이 경로 규칙에 어긋난다.
    """
    compiled = syntax if isinstance(syntax, CompiledWikiSyntax) else compile_syntax(syntax)
    if rule_id is not None:
        rule = compiled.rule(rule_id)
        if rule is None or not rule.insert:
            raise WikiLinkInsertUnavailableError(rule_id)
    else:
        rule = next((r for r in compiled.links if r.insert), None)
        if rule is None:
            raise WikiLinkInsertUnavailableError()
    assert rule.insert is not None
    source = check_page_path(from_page)
    dest = check_page_path(target)
    rel = relative_file(source, dest + compiled.new_page_extension)
    if any(c in rel for c in " \t()<>"):
        rel = urllib.parse.quote(rel, safe="/.-_~!$&'*+,;=:@")
    values = {"target": dest, "label": label or dest, "relative_path": rel}
    return WikiLinkText(rule_id=rule.id, text=render_template(rule.insert, values))
