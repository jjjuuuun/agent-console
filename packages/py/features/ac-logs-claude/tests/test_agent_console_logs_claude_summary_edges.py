"""요약 틀 문법의 경계: 없는 포인터·숫자/bool·키 목록·긴 값·병적 입력(예외·ReDoS 없음)."""

from __future__ import annotations

import time

import pytest

from agent_console_logs_claude import _classifier as c

DETAIL = {
    "a": "x",
    "n": 5,
    "f": 1.5,
    "b": True,
    "z": False,
    "nul": None,
    "o": {"k1": 1, "k2": 2},
    "e": {},
    "l": [1],
    "t": "  ",
}


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("{/a}", "x"),
        ("{/n}", "5"),
        ("{/f}", "1.5"),
        ("{/b}", "true"),
        ("{/z}", "false"),
        ("{/o|keys}", "k1, k2"),
        ("{/missing}", None),
        ("{/nul}", None),
        ("{/l}", None),
        ("{/e|keys}", None),
        ("{/t}", None),
        ("x {/n} {/missing}", None),
        ("{/a}{/a}", "xx"),
        ("no slots", "no slots"),
        ("{", "{"),
        ("{/a", "{/a"),
        ("", None),
    ],
)
def test_template_edges(template: str, expected: str | None) -> None:
    assert c.summary_text(DETAIL, [template]) == expected


def test_missing_slot_falls_through_to_next_item() -> None:
    assert c.summary_text(DETAIL, ["{/missing} · {/a}", "{/a} · {/n}"]) == "x · 5"
    assert c.summary_text(DETAIL, ["{/missing}", "fallback"]) == "fallback"


def test_substituted_value_is_not_reexpanded() -> None:
    assert c.summary_text({"s": "{/a}", "a": "x"}, ["{/s}"]) == "{/a}"


def test_long_values_and_pathological_templates_are_fast() -> None:
    detail = {"long": "y" * 2_000_000, "a": "x"}
    pathological = ["{" * 100_000, "{/" * 100_000, "{/a" + "}" * 100_000, "{/a}" * 50_000]
    start = time.perf_counter()
    assert len(c.summary_text(detail, ["{/long}"]) or "") == 2_000_000
    for template in pathological:
        c.summary_text(detail, [template])
    assert time.perf_counter() - start < 5
