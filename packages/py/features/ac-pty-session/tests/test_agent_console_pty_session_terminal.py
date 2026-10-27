"""TerminalText: 제어 시퀀스 제거·덮어쓰기·줄 단위 화면·원문 흐름."""

from __future__ import annotations

import pytest

from agent_console_pty_session import TerminalText, strip_ansi


def feed(*chunks: str, **kwargs: int) -> TerminalText:
    term = TerminalText(**kwargs)
    for chunk in chunks:
        term.feed(chunk)
    return term


def test_carriage_return_overwrites_line() -> None:
    term = feed("abcdef\rXY\r\n")
    assert term.screen_lines() == ["XYcdef"]
    assert term.text_since(0).text == "abcdef\nXY\n"


def test_sgr_and_modes_are_dropped() -> None:
    term = feed("\x1b[?25l\x1b[1;31mred\x1b[0m \x1b[38;5;200mpink\x1b[m\x1b[?25h\n")
    assert term.screen_lines() == ["red pink"]
    assert term.text_since(0).text == "red pink\n"


def test_ink_style_redraw_erases_previous_frame() -> None:
    # Ink: 줄 지우기(2K) + 한 줄 위(1A)를 되풀이한 뒤 첫 열(G)에서 새 화면을 쓴다
    frame1 = "Choose:\n> one\n  two"
    redraw = "\x1b[2K\x1b[1A\x1b[2K\x1b[1A\x1b[2K\x1b[G"
    frame2 = "Choose:\n  one\n> two"
    term = feed(frame1, redraw, frame2)
    assert term.screen_lines() == ["Choose:", "  one", "> two"]


def test_cursor_forward_counts_as_spaces() -> None:
    term = feed("Paste\x1b[1Ccode\x1b[3Chere\n")
    assert term.screen_lines() == ["Paste code   here"]
    assert term.text_since(0).text == "Paste code   here\n"


def test_sequence_split_across_chunks() -> None:
    term = feed("a\x1b", "[3", "1mb\x1b]8;;https://ex", "ample.com/x\x07c\x1b]8;;\x07\n")
    assert term.screen_lines() == ["abc"]
    assert term.links() == ["https://example.com/x"]


def test_osc8_target_goes_into_text_flow() -> None:
    term = feed("\x1b]8;id=1;https://claude.ai/oauth/authorize?a=1\x1b\\Login\x1b]8;;\x1b\\\r\n")
    text = term.text_since(0).text
    assert "\nhttps://claude.ai/oauth/authorize?a=1\n" in text
    assert term.screen_lines() == ["Login"]
    assert term.links() == ["https://claude.ai/oauth/authorize?a=1"]


def test_osc_title_is_dropped() -> None:
    assert feed("\x1b]0;window title\x07ok").screen_lines() == ["ok"]


def test_erase_display_clears_screen() -> None:
    term = feed("old1\nold2\n\x1b[2J\x1b[Hnew")
    assert term.screen_lines() == ["new"]


def test_erase_to_end_of_line() -> None:
    term = feed("hello world\r\x1b[5C\x1b[K!")
    assert term.screen_lines() == ["hello!"]


def test_backspace_and_tab() -> None:
    term = feed("abc\bX\tY")
    assert term.screen_lines() == ["abX     Y"]


def test_long_line_is_not_wrapped() -> None:
    term = feed("x" * 500 + "\n")
    assert term.screen_lines() == ["x" * 500]


def test_scrollback_limit_keeps_last_lines() -> None:
    term = feed(*(f"line{i}\n" for i in range(10)), scrollback_lines=3)
    assert term.screen_lines() == ["line8", "line9"]


def test_screen_last_n() -> None:
    assert feed("a\nb\nc\n").screen_lines(last=2) == ["b", "c"]
    assert feed("a\n").screen_lines(last=0) == []


def test_text_flow_limit_reports_dropped() -> None:
    term = feed("0123456789", "abcdef", max_text_chars=8)
    chunk = term.text_since(0)
    assert chunk.text == "89abcdef"
    assert chunk.offset == 16
    assert chunk.dropped == 8
    later = term.text_since(chunk.offset)
    assert later.text == ""
    term.feed("Z")
    assert term.text_since(chunk.offset).text == "Z"


def test_cursor_up_at_top_is_clamped() -> None:
    term = feed("\x1b[5Atop\n")
    assert term.screen_lines() == ["top"]


def test_invalid_limits_rejected() -> None:
    with pytest.raises(ValueError, match="1 이상"):
        TerminalText(scrollback_lines=0)


def test_strip_ansi() -> None:
    assert strip_ansi("\x1b[1mbold\x1b[0m\r\nnext") == "bold\nnext"
