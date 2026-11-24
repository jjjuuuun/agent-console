import pytest

from agent_console_path_glob import glob_match, glob_regex, normalize_path


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("**/*.jsonl", "a.jsonl", True),
        ("**/*.jsonl", "x/y/a.jsonl", True),
        ("*.jsonl", "x/a.jsonl", False),
        ("/proj/**", "/proj", True),
        ("/proj/**", "/proj/sub/deep", True),
        ("/proj/**", "/project", False),
        ("a/**/b", "a/b", True),
        ("a/**/b", "a/x/y/b", True),
        ("a/?.txt", "a/1.txt", True),
        ("a/?.txt", "a/12.txt", False),
        ("a?b", "a/b", False),
        ("a**b", "a/x/b", True),
        ("a.b", "axb", False),
        ("[x]", "[x]", True),
        ("drafts/*", "drafts/a/b", False),
    ],
)
def test_rules(pattern: str, path: str, expected: bool) -> None:
    assert glob_match(pattern, path) is expected


def test_case() -> None:
    assert not glob_match("Notes/*", "notes/a")
    assert glob_match("Notes/*", "notes/a", case_insensitive=True)


def test_path_is_not_normalized() -> None:
    assert not glob_match("C:/w/**", "C:\\w\\x")
    assert glob_match("C:/w/**", normalize_path("C:\\w\\x"))
    assert glob_match(normalize_path("C:/w/"), normalize_path("C:/w"))


def test_newline_in_path_matches_star_star() -> None:
    assert glob_match("**", "a\nb")
    assert not glob_match("*", "a\nb/c")


def test_regex_is_cached() -> None:
    assert glob_regex("a/*") is glob_regex("a/*")
    assert glob_regex("a/*") is not glob_regex("a/*", case_insensitive=True)


def test_normalize_path() -> None:
    assert normalize_path("a\\b\\") == "a/b"
    assert normalize_path("/") == "/"
    assert normalize_path("") == ""
