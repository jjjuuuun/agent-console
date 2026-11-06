"""이름 바꾸기 링크 고치기: 링크 대상 부분만 바뀌고 링크 밖 바이트(CRLF·탭·서식)는 그대로."""

from __future__ import annotations

from agent_console_wiki import (
    WikiIndex,
    build_index,
    compile_syntax,
    effective_syntax,
    parse_page,
    rewrite_links,
)

SYNTAX = compile_syntax(effective_syntax())


def _index(files: dict[str, str]) -> WikiIndex:
    return build_index([parse_page(p, t, SYNTAX) for p, t in files.items()], SYNTAX)


def _outside_links_unchanged(before: str, after: str, index: WikiIndex, page: str) -> None:
    """링크 원문 밖 부분을 차례로 견준다(링크 사이 글자가 한 글자도 바뀌지 않음)."""
    links = index.links[page]
    cursor = 0
    pieces: list[str] = []
    for item in links:
        pieces.append(before[cursor : item.link.start])
        cursor = item.link.end
    pieces.append(before[cursor:])
    pos = 0
    for piece in pieces:
        found = after.find(piece, pos)
        assert found >= pos, piece
        pos = found + len(piece)
    assert after.encode("utf-8").endswith(pieces[-1].encode("utf-8"))


def test_rewrites_only_link_targets_and_keeps_bytes() -> None:
    text = (
        "---\r\ntitle: 노트\r\n---\r\n"
        "들여쓰기\t[[old/page|라벨]] 그리고 [[OLD/Page#절]]\r\n"
        '*강조* [상대](old/page.md#sec "제목")  끝 공백  \r\n'
        "`[[old/page]]` 코드는 그대로\r\n"
        "[[제목으로]] 링크도 그대로\r\n"
    )
    index = _index({"note": text, "old/page": "---\r\ntitle: 제목으로\r\n---\r\n"})
    result = rewrite_links(
        text, index.links["note"], page="note", old="old/page", new="new/place", syntax=SYNTAX
    )
    assert result.count == 3
    # 줄 첫머리 탭은 들여쓴 코드 블록이라 링크가 아니다(CommonMark)
    assert parse_page("x", "\t[[old/page]]\n", SYNTAX).links == []
    # 링크 밖 글자 수는 그대로: 길이 차이 = 고친 대상 길이 차이의 합
    grew = sum(len("new/place") - len(t) for t in ("old/page", "OLD/Page", "old/page"))
    assert len(result.text) - len(text) == grew
    assert "[[new/place|라벨]]" in result.text
    assert "[[new/place#절]]" in result.text
    assert '[상대](new/place.md#sec "제목")' in result.text
    assert "`[[old/page]]`" in result.text
    assert "[[제목으로]]" in result.text
    assert result.text.count("\r\n") == text.count("\r\n")
    assert "들여쓰기\t" in result.text
    assert "  끝 공백  \r\n" in result.text
    _outside_links_unchanged(text, result.text, index, "note")


def test_relative_links_recomputed_for_other_and_moved_page() -> None:
    files = {
        "a/one": "[to two](../b/two.md) [self](one.md) [[b/two]]",
        "b/two": "[back](../a/one.md)",
    }
    index = _index(files)
    other = rewrite_links(
        files["b/two"],
        index.links["b/two"],
        page="b/two",
        old="a/one",
        new="c/d/one",
        syntax=SYNTAX,
    )
    assert other.text == "[back](../c/d/one.md)"
    moved = rewrite_links(
        files["a/one"],
        index.links["a/one"],
        page="a/one",
        old="a/one",
        new="c/d/one",
        syntax=SYNTAX,
    )
    # 옮기는 페이지 자신: 상대 링크는 새 위치 기준, 경로 링크는 그대로
    assert moved.text == "[to two](../../b/two.md) [self](one.md) [[b/two]]"
    assert moved.count == 1


def test_percent_encoding_and_dot_slash_and_angle() -> None:
    files = {"x": "[a](./my%20page.md) [b](<my page.md>) [c](my%20page.md)", "my page": ""}
    index = _index(files)
    result = rewrite_links(
        files["x"], index.links["x"], page="x", old="my page", new="new name", syntax=SYNTAX
    )
    assert result.text == "[a](./new%20name.md) [b](<new name.md>) [c](new%20name.md)"


def test_stale_text_is_skipped() -> None:
    files = {"x": "[[a]] [[a]]", "a": ""}
    index = _index(files)
    changed = "[[a]] [[b]]"
    result = rewrite_links(changed, index.links["x"], page="x", old="a", new="z", syntax=SYNTAX)
    assert result.text == "[[z]] [[b]]"
    assert (result.count, result.skipped) == (1, 1)


def test_nothing_to_rewrite_returns_same_text() -> None:
    files = {"x": "[[a]]", "a": "", "b": ""}
    index = _index(files)
    result = rewrite_links(files["x"], index.links["x"], page="x", old="b", new="c", syntax=SYNTAX)
    assert result.text is files["x"]
    assert result.count == 0
