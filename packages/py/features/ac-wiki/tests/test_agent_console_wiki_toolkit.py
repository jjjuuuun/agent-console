"""`WikiToolkit`(7R.10, design §7R.1.4): 도구 7개·접근·사유 코드·이벤트·지침·R0."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.wiki import (
    WIKI_ACCESS_OPS,
    WikiAccessConfig,
    WikiAuthor,
    WikiEventPayload,
    WikiHeading,
    WikiRulesDefinition,
    wiki_access_defaults,
)
from agent_console_wiki import (
    InMemoryWikiHistory,
    RulesDocument,
    ScanSearchIndex,
    WikiRepository,
    WikiRepositoryLimits,
    WikiToolkit,
    WikiToolTarget,
    WikiToolText,
    WriteBudget,
    compile_syntax,
    default_wiki,
    effective_syntax,
    load_tool_text,
    merge_rules,
    replace_section,
    section_span,
    wiki_allowed,
    wiki_instructions,
    wikis_for,
)
from agent_console_wiki.testing import FakeClock, MemoryWikiPages

SRC = Path(__file__).resolve().parents[1] / "src" / "agent_console_wiki"
SYNTAX = compile_syntax(effective_syntax())
AGENT = WikiAuthor(kind="agent", agent_id="keeper", run_id="r1", label="위키 관리")
ALL = list(WIKI_ACCESS_OPS)


def _rules() -> Any:
    rules = WikiRulesDefinition.model_validate(
        {
            "kind": "wiki-rules",
            "id": "house",
            "name": "집 규칙",
            "instructions": {"file": "guide.md"},
            "write_rules": [
                {"id": "no-temp", "deny_patterns": [r"\bTODO\b"], "message": "임시 메모 금지"},
                {
                    "id": "needs-tag",
                    "applies_to": ["notes/**"],
                    "require": {"all": [{"path": "/page/front_matter/source", "op": "exists"}]},
                    "action": "warn",
                    "message": "근거를 다세요",
                },
            ],
            "page_templates": [{"id": "decision", "file": "d.md"}],
        }
    )
    files = {"guide.md": "결정은 decisions/ 아래에 쓴다.", "d.md": "# {title}\n날짜: {date}\n"}
    return merge_rules(["house"], [RulesDocument("house", rules, files)])


def _repo(wiki: str = "notes", **kw: Any) -> WikiRepository:
    return WikiRepository(
        MemoryWikiPages(),
        wiki_id=wiki,
        syntax=SYNTAX,
        rules=kw.pop("rules", _rules()),
        history=InMemoryWikiHistory(),
        search=kw.pop("search", ScanSearchIndex()),
        clock=FakeClock(),
        **kw,
    )


def _access(*entries: tuple[str, list[str]], **extra: Any) -> WikiAccessConfig:
    return WikiAccessConfig.model_validate(
        {"wikis": [{"wiki": w, "access": ops} for w, ops in entries], **extra}
    )


def _kit(
    repo: WikiRepository | None = None, *, access: WikiAccessConfig | None = None, **kw: Any
) -> tuple[WikiToolkit, WikiRepository]:
    repo = repo or _repo()
    kit = WikiToolkit({"notes": repo}, access=access or _access(("notes", ALL)), author=AGENT, **kw)
    return kit, repo


# ---------------------------------------------------------------- 스펙


def test_default_access_gives_read_only_tools_with_data_names() -> None:
    kit, _ = _kit(access=WikiAccessConfig.model_validate({"wikis": [{"wiki": "notes"}]}))
    specs = kit.specs()
    defaults = wiki_access_defaults()["tools"]
    assert [s.op for s in specs] == ["read", "search", "list", "links"]
    assert [s.name for s in specs] == [defaults[s.op]["name"] for s in specs]
    assert all(s.description == defaults[s.op]["description"] for s in specs)
    search = next(s for s in specs if s.op == "search")
    assert search.input_schema["required"] == ["query"]
    assert search.input_schema["properties"]["wiki"]["enum"] == ["notes"]
    assert "notes" in search.input_schema["properties"]["wiki"]["description"]


def test_all_ops_and_input_schema_names() -> None:
    kit, _ = _kit()
    specs = {s.op: s for s in kit.specs()}
    assert list(specs) == ALL
    write = specs["write"].input_schema
    assert write["required"] == ["path"]
    assert write["properties"]["mode"]["enum"] == ["replace", "append", "section"]
    assert {"content", "section", "template", "title", "if_hash", "message"} <= set(
        write["properties"]
    )
    assert specs["move"].input_schema["required"] == ["path", "to"]
    assert all(p.get("description") for p in write["properties"].values())


async def test_renamed_tools_in_access_data_behave_the_same() -> None:
    renamed = {op: {"name": f"kb_{op}", "description": f"설명 {op}"} for op in ALL}
    access = _access(("notes", ALL), tools=renamed)
    kit, _ = _kit(access=access)
    specs = {s.name: s for s in kit.specs()}
    assert set(specs) == {f"kb_{op}" for op in ALL}
    wrote = await specs["kb_write"].call({"path": "a", "content": "# A\n본문\n"}, "c1")
    assert not wrote.is_error
    assert wrote.event.tool == "kb_write"
    read = await specs["kb_read"].call({"path": "a"}, None)
    assert "본문" in read.text


# ---------------------------------------------------------------- 읽기·쓰기


async def test_write_then_read_with_header_and_hash() -> None:
    kit, repo = _kit()
    out = await kit.call("write", {"path": "guide", "content": "# 안내\n[[other]]\n"})
    assert not out.is_error, out.text
    assert out.event.status == "ok"
    assert repo.read("guide").text == "# 안내\n[[other]]\n"
    latest = repo.history.latest("notes", "guide") if repo.history else None
    assert latest is not None
    assert latest.author.label == "위키 관리"
    read = await kit.call("read", {"path": "guide"})
    first, second, *_ = read.text.splitlines()
    assert first.startswith("[위키 notes:guide · ")
    assert "agent:위키 관리" in first
    assert repo.read("guide").content_hash in second
    assert read.text.endswith("[[other]]\n")


async def test_read_section_only() -> None:
    kit, repo = _kit()
    repo.write("p", "# 제목\n머리\n## 설치\n설치 본문\n### 세부\n세부\n## 사용\n사용 본문\n")
    out = await kit.call("read", {"path": "p", "section": "설치"})
    body = out.text.split("\n", 3)[3]
    assert body == "## 설치\n설치 본문\n### 세부\n세부\n"
    missing = await kit.call("read", {"path": "p", "section": "없음"})
    assert missing.is_error
    assert missing.code == "wiki.not_found"
    assert missing.event.status == "not_found"


async def test_append_section_and_template_modes() -> None:
    kit, repo = _kit()
    first = await kit.call("write", {"path": "log", "content": "첫 줄", "mode": "append"})
    assert "새로 만들었습니다" in first.text
    await kit.call("write", {"path": "log", "content": "둘째 줄\n", "mode": "append"})
    assert repo.read("log").text == "첫 줄\n둘째 줄\n"

    repo.write("doc", "# 문서\r\n## A\r\n옛 A\r\n## B\r\nB 그대로\r\n")
    out = await kit.call(
        "write", {"path": "doc", "mode": "section", "section": "## A", "content": "새 A"}
    )
    assert not out.is_error, out.text
    assert repo.read("doc").text == "# 문서\r\n## A\r\n새 A\r\n## B\r\nB 그대로\r\n"
    no_section = await kit.call(
        "write", {"path": "doc", "mode": "section", "section": "Z", "content": "x"}
    )
    assert no_section.code == "wiki.not_found"

    made = await kit.call(
        "write",
        {"path": "decisions/api", "template": "decision", "title": "API", "content": "근거"},
    )
    assert not made.is_error, made.text
    text = repo.read("decisions/api").text
    assert text.startswith("# API\n날짜: ")
    assert text.endswith("근거")
    again = await kit.call("write", {"path": "decisions/api", "template": "decision"})
    assert again.code == "wiki.page_exists"
    assert again.event.status == "conflict"
    unknown = await kit.call("write", {"path": "x", "template": "none"})
    assert unknown.code == "wiki.template_missing"


async def test_append_uses_current_hash_so_concurrent_change_conflicts() -> None:
    kit, repo = _kit()
    repo.write("p", "하나\n")
    stale = repo.read("p").content_hash
    repo.write("p", "둘\n")
    out = await kit.call(
        "write", {"path": "p", "content": "셋", "mode": "append", "if_hash": stale}
    )
    assert out.code == "wiki.conflict"
    assert out.event.status == "conflict"
    assert repo.read("p").content_hash in out.text


async def test_list_search_links() -> None:
    kit, repo = _kit()
    repo.write("index", "# 처음\n[[guide]] [[없는곳]]\n")
    repo.write("guide", "---\ntags: [안내]\n---\n# 안내서\n위키는 서로 잇는다\n[[index]]\n")
    listed = await kit.call("list", {"limit": 1})
    assert listed.text.splitlines()[0] == "- guide · 안내서"
    assert "1/2" in listed.text
    assert listed.event.results == 1
    found = await kit.call("search", {"query": "위키", "tags": ["안내"]})
    assert "notes:guide" in found.text
    assert found.event.results == 1
    assert found.event.query_chars == 2
    links = await kit.call("links", {"path": "index"})
    assert "[[guide]] → guide" in links.text
    assert "[[없는곳]]" in links.text.split("끊긴 링크:")[1]
    assert "- guide · 안내서 (1개)" in links.text


async def test_move_and_delete() -> None:
    kit, repo = _kit()
    repo.write("a", "# A\n")
    repo.write("b", "[[a]]\n")
    moved = await kit.call("move", {"path": "a", "to": "docs/a"})
    assert not moved.is_error, moved.text
    assert moved.event.to == "docs/a"
    assert "1개" in moved.text
    assert repo.read("b").text == "[[docs/a]]\n"
    gone = await kit.call("delete", {"path": "docs/a"})
    assert not gone.is_error
    assert repo.current("docs/a") is None
    missing = await kit.call("delete", {"path": "docs/a"})
    assert missing.code == "wiki.page_not_found"
    assert missing.event.status == "not_found"


# ---------------------------------------------------------------- 사유 코드


async def test_denied_and_unavailable() -> None:
    access = _access(("notes", ["read"]), ("other", ALL), ("gone", ALL))
    repo = _repo()
    kit = WikiToolkit({"notes": repo, "other": _repo("other")}, access=access, author=AGENT)
    denied = await kit.call("write", {"path": "a", "content": "x"})
    assert (denied.code, denied.event.status) == ("wiki.denied", "denied")
    outsider = await kit.call("read", {"path": "a", "wiki": "secret"})
    assert outsider.code == "wiki.denied"
    unavailable = await kit.call("read", {"path": "a", "wiki": "gone"})
    assert (unavailable.code, unavailable.event.status) == (
        "wiki.wiki_unavailable",
        "wiki_unavailable",
    )
    assert kit.unavailable() == ["gone"]
    ok = await kit.call("write", {"path": "a", "content": "x", "wiki": "other"})
    assert not ok.is_error
    assert {s.op for s in kit.specs()} == set(ALL)


def test_access_helpers() -> None:
    access = _access(("a", ["read"]), ("b", ["write"]), ("a", ["search"]))
    assert wiki_allowed(access, "a", "search")
    assert not wiki_allowed(access, "a", "write")
    assert wikis_for(access, "write") == ["b"]
    assert default_wiki(access) == "a"
    assert default_wiki(access.model_copy(update={"default_wiki": "b"})) == "b"


async def test_rule_rejected_carries_rule_id_message_and_lines() -> None:
    events: list[tuple[str, WikiEventPayload]] = []
    kit, repo = _kit(on_event=lambda t, p: events.append((t, p)))
    out = await kit.call("write", {"path": "a", "content": "줄\nTODO 나중에\n"})
    assert out.is_error
    assert out.code == "wiki.rule_rejected"
    assert "no-temp" in out.text
    assert "임시 메모 금지" in out.text
    assert "줄 2" in out.text
    assert repo.current("a") is None
    kind, payload = events[-1]
    assert kind == "wiki.write"
    assert payload.status == "rule_rejected"
    assert payload.rule_ids == ["no-temp"]


async def test_rule_warning_is_reported_with_ok() -> None:
    kit, _ = _kit()
    out = await kit.call("write", {"path": "notes/x", "content": "# X\n"})
    assert not out.is_error
    assert "근거를 다세요" in out.text
    assert out.event.rule_ids == ["needs-tag"]
    assert [i.rule_id for i in out.issues] == ["needs-tag"]


async def test_secret_rejected_and_redacted_results() -> None:
    kit, repo = _kit()
    secret = "API_KEY=sk-abcdefghijklmnop1234\n"
    out = await kit.call("write", {"path": "s", "content": "메모\n" + secret})
    assert out.code == "wiki.secret_rejected"
    assert "sk-abcdefghijklmnop1234" not in out.text
    repo.write("s", "메모\n" + secret)  # 사람 쓰기는 경고만(기본 설정)
    read = await kit.call("read", {"path": "s"})
    assert "sk-abcdefghijklmnop1234" not in read.text


async def test_too_large_and_invalid_path_and_input() -> None:
    repo = _repo(limits=WikiRepositoryLimits(max_page_bytes=8))
    kit, _ = _kit(repo)
    big = await kit.call("write", {"path": "a", "content": "123456789"})
    assert (big.code, big.event.status) == ("wiki.too_large", "too_large")
    bad = await kit.call("write", {"path": "../x", "content": "x"})
    assert (bad.code, bad.event.status) == ("wiki.invalid_path", "invalid_path")
    wrong = await kit.call("write", {"path": "a"})
    assert (wrong.code, wrong.event.status) == ("validation_failed", "error")
    with pytest.raises(ValueError, match="모르는 동작"):
        await kit.call("rename", {})


async def test_write_budget_shared_by_mutating_ops() -> None:
    budget = WriteBudget(2)
    kit, repo = _kit(write_budget=budget)
    assert not (await kit.call("write", {"path": "a", "content": "x"})).is_error
    assert not (await kit.call("move", {"path": "a", "to": "b"})).is_error
    limited = await kit.call("delete", {"path": "b"})
    assert (limited.code, limited.event.status) == ("wiki.rate_limited", "rate_limited")
    assert repo.current("b") is not None
    other = WikiToolkit({"notes": repo}, access=_access(("notes", ALL)), write_budget=budget)
    assert (await other.call("write", {"path": "c", "content": "x"})).code == "wiki.rate_limited"
    assert not (await kit.call("read", {"path": "b"})).is_error


# ---------------------------------------------------------------- 이벤트·결과 길이


async def test_events_have_no_content_or_query_text() -> None:
    seen: list[WikiEventPayload] = []

    async def sink(_type: str, payload: WikiEventPayload) -> None:
        seen.append(payload)

    kit, _ = _kit(on_event=sink)
    body = "# 비밀스럽지않은본문\n고유한내용문자열\n"
    await kit.call("write", {"path": "p", "content": body}, "tool-1")
    await kit.call("read", {"path": "p"})
    await kit.call("search", {"query": "고유한내용"})
    dumped = json.dumps([p.model_dump(mode="json") for p in seen], ensure_ascii=False)
    assert "고유한내용" not in dumped
    assert "비밀스럽지않은본문" not in dumped
    assert seen[0].tool_use_id == "tool-1"
    assert seen[0].bytes == len(body.encode())
    assert seen[0].sha256
    assert seen[0].version == 1
    assert seen[2].query_sha256
    assert seen[2].query_chars == 5


async def test_result_is_clipped_to_max_chars() -> None:
    access = _access(("notes", ALL), max_result_chars=60)
    kit, repo = _kit(access=access)
    repo.write("long", "# L\n" + "가" * 500)
    out = await kit.call("read", {"path": "long"})
    assert len(out.text) == 60
    assert out.text.endswith("…(잘림: 60자)")


async def test_text_data_can_be_replaced() -> None:
    data = {
        "inputs": {"path": "경로"},
        "errors": {"error": "실패", "wiki.denied": "안 됨 {wiki}"},
        "created": "만듦 {path}",
    }
    kit, _ = _kit(text=WikiToolText.from_mapping(data), access=_access(("notes", ["write"])))
    out = await kit.call("write", {"path": "a", "content": "x"})
    assert out.text == "만듦 a"
    denied = await kit.call("read", {"path": "a"})
    assert denied.text == "[wiki.denied] 안 됨 notes"
    assert set(load_tool_text().inputs) >= {"query", "wiki", "path", "content", "mode", "to"}


# ---------------------------------------------------------------- 지침(7R.14 → X30)


def test_instructions_rules_and_path_hint() -> None:
    repo = _repo()
    access = _access(("notes", ["read"]), ("other", ["read"]), ("gone", ["read"]))
    kit = WikiToolkit(
        {
            "notes": WikiToolTarget(repo, name="노트", pages_dir="wiki-pages/notes"),
            "other": WikiToolTarget(_repo("other"), name="기타"),
        },
        access=access,
    )
    lines = kit.instructions()
    assert lines[0].endswith("결정은 decisions/ 아래에 쓴다.")
    assert lines[1].startswith("위키 페이지 파일은 wiki-pages/notes/ 아래")
    assert len(lines) == 2  # other: 같은 규칙 지침은 한 번, pages_dir 없어 안내 없음, gone 없음
    off = access.model_copy(update={"include_rules_instructions": False, "path_hint": ""})
    assert wiki_instructions(off, [("notes", WikiToolTarget(repo, pages_dir="p"))]) == []
    named = access.model_copy(update={"path_hint": "{wiki_name}({wiki})는 도구로"})
    assert "노트(notes)는 도구로" in wiki_instructions(
        named, [("notes", WikiToolTarget(repo, name="노트"))]
    )


# ---------------------------------------------------------------- 절 함수


def test_section_span_setext_and_last_line() -> None:
    text = "A\n===\nbody\nB\n---\nb\n"
    hs = [WikiHeading(level=1, text="A", line=1), WikiHeading(level=2, text="B", line=4)]
    span = section_span(text, hs, "a")
    assert span is not None
    assert text[span[1] : span[2]] == "body\nB\n---\nb\n"
    b = section_span(text, hs, "B")
    assert b is not None
    assert replace_section(text, b, "새") == "A\n===\nbody\nB\n---\n새"
    tail = "# T"
    t = section_span(tail, [WikiHeading(level=1, text="T", line=1)], "T")
    assert t is not None
    assert replace_section(tail, t, "본문") == "# T\n본문"
    assert section_span(text, hs, "  ") is None


# ---------------------------------------------------------------- R0


def _literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_no_hardcoded_tool_names_or_texts_in_code() -> None:
    defaults = wiki_access_defaults()
    forbidden = {t["name"] for t in defaults["tools"].values()}
    forbidden |= {t["description"] for t in defaults["tools"].values()}
    forbidden |= {defaults["result_header"], defaults["path_hint"]}
    sources = [p for p in SRC.rglob("*.py") if "testing" not in p.parts]
    assert sources
    found = {str(p.relative_to(SRC)): _literals(p) & forbidden for p in sources}
    assert {k: v for k, v in found.items() if v} == {}


def test_toolkit_does_not_import_runtime_side() -> None:
    banned = ("agent_console_runtime", "agent_console_nodes_core", "agent_console_runs")
    tree = ast.parse((SRC / "_toolkit.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(banned)
