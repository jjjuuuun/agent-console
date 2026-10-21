from agent_console_logs import bounded, glob_match, json_pointer, text, timestamp


def test_bounded_limits_and_drops() -> None:
    value = {
        "a": "x" * 10,
        "encrypted_content": "secret",
        "list": list(range(5)),
        "nested": {"encryptedContent": 1, "k": "y" * 3},
    }
    out = bounded(value, max_chars=4, max_items=2, note="…")
    assert out == {"a": "xxxx…", "list": [0, 1], "nested": {"k": "yyy"}}
    assert value["a"] == "x" * 10  # 원본은 그대로


def test_bounded_defaults_match_agent_bench() -> None:
    long = "z" * 80_001
    assert bounded(long).startswith("z" * 80_000)
    assert bounded(long).endswith("원시 로그에 전체 내용 보존]")
    assert len(bounded(list(range(300)))) == 200


def test_timestamp() -> None:
    assert timestamp(5) == 5.0
    assert timestamp("1970-01-01T00:00:10Z") == 10.0
    assert timestamp("nope") is None
    assert timestamp(True) is None
    assert timestamp(None) is None


def test_text() -> None:
    assert text("가") == "가"
    assert text({"k": "가"}) == '{"k": "가"}'


def test_json_pointer() -> None:
    doc = {"a": {"b/c": [10, {"d~e": 1}]}}
    assert json_pointer(doc, "/a/b~1c/0") == 10
    assert json_pointer(doc, "/a/b~1c/1/d~0e") == 1
    assert json_pointer(doc, "/a/zz", "dflt") == "dflt"
    assert json_pointer(doc, "/a/b~1c/9") is None
    assert json_pointer(doc, "") is doc
    assert json_pointer(doc, "no-slash") is None


def test_glob_match() -> None:
    assert glob_match("**/*.jsonl", "a.jsonl")
    assert glob_match("**/*.jsonl", "x/y/a.jsonl")
    assert not glob_match("*.jsonl", "x/a.jsonl")
    assert glob_match("/proj/**", "/proj")
    assert glob_match("/proj/**", "/proj/sub/deep")
    assert not glob_match("/proj/**", "/project")
    assert glob_match("C:/w/**", "C:\\w\\x")
    assert glob_match("a/**/b", "a/b")
    assert glob_match("a/?.txt", "a/1.txt")
