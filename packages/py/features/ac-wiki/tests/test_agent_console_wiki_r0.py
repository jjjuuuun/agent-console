"""R0: 링크 문법·머리말 키·제목 출처·확장자는 데이터다.

모두 바꾼 문법 데이터로 같은 위키를 읽으면 같은 결과가 나오고, 코드에는 기본 문법 데이터의 값이
없다. 판단 대상 모양은 계약 상수와 맞는다.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any

from agent_console_contracts.wiki import (
    WIKI_LINT_SUBJECT_PATHS,
    WIKI_WRITE_SUBJECT_PATHS,
    WikiAuthor,
    WikiSettings,
)
from agent_console_wiki import (
    CompiledWikiSyntax,
    WikiIndex,
    build_index,
    compile_syntax,
    effective_syntax,
    lint_subject,
    load_default_syntax,
    neighborhood,
    parse_page,
    render_link_text,
    rewrite_links,
    write_subject,
)

SRC = Path(str(files("agent_console_wiki")))

DEFAULT = compile_syntax(effective_syntax(rules=[("r", {"lint": {"orphan_ignore": ["보관/**"]}})]))
CHANGED = compile_syntax(
    effective_syntax(
        WikiSettings(include_default_syntax=False),
        rules=[
            (
                "house-style",
                {
                    "links": [
                        {
                            "id": "double-paren",
                            "kind": "pattern",
                            "pattern": r"\(\((?P<target>[^)|\n]+)(?:\|(?P<label>[^)\n]+))?\)\)",
                            "resolve": ["path", "title", "alias"],
                            "insert": "(({target}|{label}))",
                        },
                        {"id": "rel-files", "kind": "markdown", "resolve": ["relative_path"]},
                    ],
                    "front_matter": {
                        "delimiter": "+++",
                        "roles": {"title": "제목", "tags": "분류", "aliases": "별칭"},
                    },
                    "title_sources": ["front_matter", "first_heading", "file_name"],
                    "page_extensions": [".markdown"],
                    "case_insensitive": True,
                    "lint": {"orphan_ignore": ["보관/**"]},
                },
            )
        ],
    )
)


def _default_page(title: str | None, tags: list[str], links: list[str], md: list[str]) -> str:
    head = f"---\ntitle: {title}\ntags: [{', '.join(tags)}]\n---\n" if title else ""
    body = " ".join(f"[[{t}]]" for t in links) + " " + " ".join(f"[m]({m}.md)" for m in md)
    return f"{head}# 무시\n\n{body}\n\n```\n[[코드]]\n```\n"


def _changed_page(title: str | None, tags: list[str], links: list[str], md: list[str]) -> str:
    head = f"+++\n제목: {title}\n분류: [{', '.join(tags)}]\n+++\n" if title else ""
    body = " ".join(f"(({t}))" for t in links) + " " + " ".join(f"[m]({m}.markdown)" for m in md)
    return f"{head}# 무시\n\n{body}\n\n```\n((코드))\n```\n"


WIKI: dict[str, tuple[str | None, list[str], list[str], list[str]]] = {
    "home": ("첫 페이지", ["시작"], ["guide", "가이드 제목", "없는 곳"], ["notes/one"]),
    "guide": ("가이드 제목", ["안내", "기본"], ["home"], []),
    "notes/one": (None, [], ["NOTES/two"], ["../guide"]),
    "notes/two": (None, [], [], ["../../밖"]),
    "보관/old": ("옛것", [], [], []),
    "lonely": ("외톨이", [], [], []),
}


def _build(syntax: CompiledWikiSyntax, make: Callable[..., str]) -> WikiIndex:
    pages = [parse_page(path, make(*spec), syntax) for path, spec in WIKI.items()]
    return build_index(pages, syntax, home="home")


def _shape(index: WikiIndex) -> dict[str, Any]:
    out: dict[str, Any] = {
        "orphans": sorted(index.orphans),
        "duplicates": index.duplicate_titles,
        "graph": [(e.from_, e.to, e.count) for e in neighborhood(index).edges],
        "near": sorted((n.path, n.depth, n.broken) for n in neighborhood(index, "home", 2).nodes),
    }
    for path in index.pages:
        s = index.summary(path)
        out[path] = {
            "title": s.title,
            "tags": s.tags,
            "counts": (s.links_out, s.backlinks, s.broken_links, s.orphan, s.home),
            "links": [
                (lk.status, lk.resolved, lk.suggested_path, lk.label)
                for lk in index.page_links(path)
            ],
            "backlinks": [(b.path, b.count) for b in index.backlinks(path)],
        }
    return out


def test_changed_syntax_data_gives_same_wiki() -> None:
    default, changed = _build(DEFAULT, _default_page), _build(CHANGED, _changed_page)
    assert _shape(default) == _shape(changed)
    shape = _shape(default)
    assert shape["home"]["links"][2][0] == "broken"
    assert shape["notes/two"]["links"][0][0] == "outside"
    assert shape["orphans"] == ["lonely"]
    # 이름 바꾸기·링크 넣기도 같은 동작
    text_d = _default_page(*WIKI["home"])
    text_c = _changed_page(*WIKI["home"])
    rd = rewrite_links(
        text_d, default.links["home"], page="home", old="guide", new="docs/guide", syntax=DEFAULT
    )
    rc = rewrite_links(
        text_c, changed.links["home"], page="home", old="guide", new="docs/guide", syntax=CHANGED
    )
    assert (rd.count, rc.count) == (1, 1)
    assert "[[docs/guide]]" in rd.text
    assert "((docs/guide))" in rc.text
    assert (
        render_link_text(CHANGED, from_page="home", target="guide", label="안내").text
        == "((guide|안내))"
    )


def test_default_syntax_off_means_no_links_but_pages_read() -> None:
    off = compile_syntax(effective_syntax(WikiSettings(include_default_syntax=False)))
    index = _build(off, _default_page)
    assert all(index.links[p] == [] for p in index.pages)
    # 머리말 구분 줄·제목 출처도 데이터라 함께 꺼진다 → 제목 없음, 머리말 안 읽음
    assert index.summary("home").title == ""
    assert index.pages["home"].front_matter == {}
    assert len(index.pages) == len(WIKI)
    assert "wiki.syntax_missing" in [i.code for i in index.issues]


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


def test_no_default_syntax_values_in_code() -> None:
    default = load_default_syntax()
    forbidden: set[str] = {"[[", "]]", "{{", "((", "index", "home"}
    for rule in default.links or ():
        forbidden |= {rule.id, rule.pattern or "", rule.insert or ""}
    assert default.front_matter is not None
    forbidden.add(default.front_matter.delimiter or "")
    forbidden |= set(default.page_extensions or ())
    forbidden.discard("")
    sources = [p for p in SRC.rglob("*.py") if "testing" not in p.parts]
    assert sources
    found = {str(p.relative_to(SRC)): _literals(p) & forbidden for p in sources}
    assert {k: v for k, v in found.items() if v} == {}


def test_no_runtime_runs_projects_memory_imports() -> None:
    banned = (
        "agent_console_runtime",
        "agent_console_nodes_core",
        "agent_console_runs",
        "agent_console_projects",
        "agent_console_memory",
        "agent_console_sdd",
        "agent_console_modkit",
        "fastapi",
    )
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not name.startswith(banned), f"{path.name}: {name}"


def _top(pointer: str) -> str:
    return pointer.split("/")[1]


def test_subjects_match_contract_paths() -> None:
    index = _build(DEFAULT, _default_page)
    facts = index.facts("guide")
    author = WikiAuthor(kind="agent", agent_id="a", graph_id="g", run_id="r", node_id="n")
    subject = write_subject(op="move", author=author, page=facts, before=facts, from_="x", to="y")
    assert {_top(p) for p in WIKI_WRITE_SUBJECT_PATHS} == set(subject)
    for pointer in WIKI_WRITE_SUBJECT_PATHS:
        node: Any = subject
        for part in pointer.split("/")[1:]:
            assert isinstance(node, dict), pointer
            assert part in node, pointer
            node = node[part]
    lint = lint_subject(facts, backlinks=1, age_days=3.0, idle_days=1.0, updated_by_kind="user")
    assert {_top(p) for p in WIKI_LINT_SUBJECT_PATHS} <= set(lint)
    assert set(lint) - {_top(p) for p in WIKI_LINT_SUBJECT_PATHS} == {"aliases"}
    created = write_subject(op="create", author=WikiAuthor(kind="user"), page=facts)
    assert created["before"] is None
    assert created["change"] == {"op": "create"}
