from __future__ import annotations

from typing import Any

import pytest

from agent_console_text_template import (
    DEFAULT_MAX_RENDER_CHARS,
    fill_value,
    render_template,
    template_variables,
)


def test_known_names_are_replaced() -> None:
    assert render_template("{a}-{b}", {"a": 1, "b": "x"}) == "1-x"


def test_unknown_names_keep_original_text() -> None:
    assert render_template("{missing} {a}", {"a": "v"}) == "{missing} v"


def test_no_attribute_or_index_access() -> None:
    values: dict[str, Any] = {"o": {"secret": "s"}, "l": [1]}
    assert render_template("{o.secret} {l[0]} {o}", values) == "{o.secret} {l[0]} {'secret': 's'}"


def test_replaced_values_are_not_rendered_again() -> None:
    assert render_template("{t}", {"t": "{a}", "a": "no"}) == "{a}"


@pytest.mark.parametrize(
    ("spec", "expected"),
    [(".1f", "1.2"), (".0%", "123%"), (".2", "1.2"), (".10f", "1.2345000000")],
)
def test_allowed_format_specs(spec: str, expected: str) -> None:
    assert render_template("{a:" + spec + "}", {"a": 1.2345}) == expected


@pytest.mark.parametrize("spec", [">99999", "x", "s", ".123f", ",", "0>10", "!r", ""])
def test_disallowed_format_specs_keep_original_text(spec: str) -> None:
    text = "{a:" + spec + "}"
    assert render_template(text, {"a": 1.5}) == text


def test_format_mismatch_falls_back_to_str() -> None:
    assert render_template("{a:.1f}", {"a": "text"}) == "text"


def test_length_cap() -> None:
    assert render_template("{t}{t}", {"t": "{a"}, max_chars=3) == "{a…"
    assert render_template("abc", {}, max_chars=3) == "abc"
    assert render_template("abcd", {}, max_chars=0) == "…"
    big = render_template("{t}", {"t": "x" * (DEFAULT_MAX_RENDER_CHARS + 10)})
    assert len(big) == DEFAULT_MAX_RENDER_CHARS
    assert big.endswith("…")


def test_fill_value_walks_nested_values() -> None:
    value = {"k": ["{a}", 2, ("{b}",)], "{a}": None}
    assert fill_value(value, {"a": "A", "b": "B"}) == {"k": ["A", 2, ["B"]], "{a}": None}
    assert fill_value(3, {"a": 1}) == 3


def test_fill_value_applies_length_cap_per_string() -> None:
    assert fill_value(["abcd", "ab"], {}, max_chars=3) == ["ab…", "ab"]


def test_template_variables() -> None:
    assert template_variables("{a} {b:.1f} {c:>9} {a} {o.x} {{d}} plain") == {"a", "b", "c", "d"}
    assert template_variables({"{key}": ["{x}", {"y": "{y}"}], "n": 1}) == {"x", "y"}
    assert template_variables("no fields") == set()
    assert template_variables(None) == set()


def test_template_variables_matches_render_for_unknown_check() -> None:
    template = "Task {task_id}: {title} ({unknown})"
    known = {"task_id": "T1", "title": "Do it"}
    assert template_variables(template) - known.keys() == {"unknown"}
    assert render_template(template, known) == "Task T1: Do it ({unknown})"
