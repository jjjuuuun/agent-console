"""R0 C-1: 위키의 네 가지 데이터를 한꺼번에 바꾸고 한 바퀴 돈다(앱 조립, fake 백엔드).

바꾸는 것(값은 모두 이 테스트가 만든 임의 값 — 기본값을 손으로 적지 않는다):

1. 링크 패턴·머리말(구분 줄·키 역할)·페이지 확장자 = 사용자 설정 ``wiki``의 문법 데이터
   (``include_default_syntax: false`` + ``syntax``).
2. 도구 이름·설명 = 위키 접근 리소스 config ``tools``(``WikiAccessConfig``).
3. 페이지 폴더 이름 = ``modules.options.link-projects-wiki.pages_dir``.

한 바퀴: 바뀐 이름의 도구로 에이전트가 페이지를 만들고 → 바뀐 폴더에 바뀐 확장자의 파일이 생기고 →
바뀐 머리말 키로 제목·태그를 읽고 → 바뀐 링크 패턴으로 링크·역링크가 풀리고 → 바뀐 이름의 옮기기
도구가 바뀐 패턴으로 링크를 고친다. 기본 문법·기본 폴더 이름·기본 도구 이름은 결과(파일·페이지
보기·실행 이벤트·위키 정보)에 하나도 나오지 않는다. 기본 도구 이름으로 부르면 그런 도구가 없다.

비교할 기본값은 패키지 데이터에서 읽는다(``load_default_syntax``·``wiki_access_defaults``·설정
모델 기본값).
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi.testclient import TestClient

from agent_console_backend_fake_agent import UNKNOWN_HOST_TOOL_TEXT
from agent_console_contracts.wiki import wiki_access_defaults
from agent_console_link_projects_wiki import ProjectsWikiSettings
from agent_console_link_wiki_runs import load_wiki_resource_type
from agent_console_mod_wiki import package_defaults as mod_wiki_defaults
from agent_console_server.testing import (
    API,
    agent_doc,
    make_settings,
    register_project,
    server,
    wait_run,
)
from agent_console_wiki import compile_syntax, effective_syntax, load_default_syntax, parse_page

PROJECT = "p1"
OPS = ("search", "read", "list", "links", "write", "move", "delete")
TERMINAL_EVENTS = frozenset({"run.completed", "run.finished", "run.failed"})


def _token() -> str:
    """영문 소문자로만 된 임의 값(정규식·도구 이름·YAML 키에 그대로 쓸 수 있게)."""
    return "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz") for _ in range(6))


class Changed:
    """이 테스트가 만든 임의 값 묶음."""

    def __init__(self) -> None:
        t = _token()
        self.token = t
        self.open, self.close = f"%{t}(", f"){t}%"
        self.pattern = (
            re.escape(self.open)
            + r"(?P<target>[^()|\n]+)(?:\|(?P<label>[^()\n]+))?"
            + re.escape(self.close)
        )
        self.insert = self.open + "{target}|{label}" + self.close
        self.rule_id = f"r-{t}"
        self.delimiter = f"+{t}+"
        self.roles = {"title": f"t{t}", "tags": f"g{t}", "aliases": f"a{t}"}
        self.extension = f".p{t}"
        self.pages_dir = f"pg-{t}"
        self.wiki = f"w-{t}"
        self.tools = {
            op: {"name": f"k{t}_{i}", "description": f"d{t} {i}"} for i, op in enumerate(OPS)
        }

    def name(self, op: str) -> str:
        return self.tools[op]["name"]

    def link(self, target: str, label: str | None = None) -> str:
        return f"{self.open}{target}{'|' + label if label else ''}{self.close}"

    def page(self, title: str, tags: list[str], body: str) -> str:
        roles = self.roles
        head = f"{roles['title']}: {title}\n{roles['tags']}: [{', '.join(tags)}]\n"
        return f"{self.delimiter}\n{head}{self.delimiter}\n# 머리 제목 {title}\n\n{body}\n"

    def wiki_settings(self) -> dict[str, Any]:
        return {
            "include_default_syntax": False,
            "syntax": {
                "links": [
                    {
                        "id": self.rule_id,
                        "kind": "pattern",
                        "pattern": self.pattern,
                        "resolve": ["path", "title", "alias"],
                        "insert": self.insert,
                    }
                ],
                "front_matter": {"delimiter": self.delimiter, "roles": self.roles},
                "title_sources": ["front_matter", "first_heading", "file_name"],
                "page_extensions": [self.extension],
            },
        }


def _defaults() -> dict[str, set[str]]:
    """패키지 기본값(결과에 나오면 안 되는 것)."""
    syntax = load_default_syntax()
    marks: set[str] = set()
    for rule in syntax.links or ():
        if rule.insert:
            # 틀의 고정 글자 중 두 글자 이상(``[[``·``]]``·``](``): 한 글자 구두점은 본문에도 흔하다
            marks |= {p for p in re.split(r"\{[a-z_]+\}", rule.insert) if len(p) >= 2}
    assert syntax.front_matter is not None
    assert syntax.front_matter.roles
    tools = wiki_access_defaults()["tools"]
    return {
        "link_marks": marks,
        "delimiter": {syntax.front_matter.delimiter or ""} - {""},
        "role_keys": set(syntax.front_matter.roles.values()),
        "extensions": set(syntax.page_extensions or ()),
        "pages_dirs": {ProjectsWikiSettings().pages_dir, mod_wiki_defaults()["pages_dir"]},
        "tool_names": {t["name"] for t in tools.values()},
        "tool_descriptions": {t["description"] for t in tools.values()},
    }


def _edge(eid: str, src: tuple[str, str], dst: tuple[str, str], kind: str) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src[0], "port": src[1]},
        "target": {"node": dst[0], "port": dst[1]},
        "kind": kind,
        "config": {},
    }


def _seed(client: TestClient, c: Changed, probe_tool: str) -> None:
    q = f"?project={PROJECT}"
    created = client.post(f"{API}/wiki/wikis{q}", json={"id": c.wiki, "name": f"위키 {c.token}"})
    assert created.status_code == 201, created.text
    resource = {
        "id": f"acc-{c.token}",
        "type": load_wiki_resource_type().id,
        "name": "위키 접근",
        "config": {"wikis": [{"wiki": c.wiki, "access": list(OPS)}], "tools": c.tools},
    }
    res = client.post(f"{API}/resources{q}", json=resource)
    assert res.status_code == 201, res.text
    page_a = c.page(
        f"가{c.token}", [f"x{c.token}", f"y{c.token}"], f"본문 {c.link('docs/b', '비')} 끝"
    )
    page_b = c.page(f"나{c.token}", [f"z{c.token}"], f"되돌아 {c.link(f'가{c.token}')}")
    calls: list[tuple[str, dict[str, Any]]] = [
        (c.name("write"), {"path": "a", "content": page_a}),
        (c.name("write"), {"path": "docs/b", "content": page_b}),
        (c.name("links"), {"path": "a"}),
        (c.name("read"), {"path": "a"}),
        (c.name("search"), {"query": f"x{c.token}"}),
        (c.name("list"), {}),
        (c.name("move"), {"path": "docs/b", "to": "keep/c", "rewrite_links": True}),
        (probe_tool, {"path": "zz", "content": "기본 이름"}),  # 기본 이름은 주지 않았다
    ]
    keeper = agent_doc("keeper", "$host_3", resources=[{"ref": resource["id"]}])
    keeper["backend_options"]["default"]["host_tool_calls"] = [
        {"tool": tool, "input": data, "append": False} for tool, data in calls
    ]
    assert client.post(f"{API}/agents{q}", json=keeper).status_code == 201
    graph = {
        "id": "g",
        "name": "한 바퀴",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "k", "type": "agent", "label": "k", "config": {"agent_ref": "keeper"}},
        ],
        "edges": [
            _edge("m", ("you", "says"), ("k", "in"), "message"),
            _edge("r", ("k", "out"), ("you", "hears"), "reply"),
        ],
    }
    res = client.post(f"{API}/graphs{q}", json=graph)
    assert res.status_code == 201, res.text


def _run(client: TestClient) -> list[dict[str, Any]]:
    body = {"graph_id": "g", "input": {"text": "go"}, "project_id": PROJECT}
    started = client.post(f"{API}/runs", json=body)
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    snap = wait_run(client, run_id, timeout=30)
    assert snap["run"]["status"] == "completed", snap["run"]
    events: list[dict[str, Any]] = []
    for _ in range(200):
        events = client.get(f"{API}/runs/{run_id}/events?project={PROJECT}").json()
        if any(e["type"] in TERMINAL_EVENTS for e in events):
            break
        time.sleep(0.05)
    return events


def _view(client: TestClient, c: Changed, path: str) -> dict[str, Any]:
    res = client.get(f"{API}/wiki/wikis/{c.wiki}/pages/{path}?project={PROJECT}")
    assert res.status_code == 200, res.text
    view: dict[str, Any] = res.json()
    return view


def _absent(text: str, forbidden: set[str], where: str) -> None:
    found = sorted(v for v in forbidden if v and v in text)
    assert not found, f"{where}에 기본값이 나왔다: {found}"


def test_four_changes_round_trip(tmp_path: Path) -> None:
    c = Changed()
    d = _defaults()
    probe_tool = sorted(d["tool_names"])[0]
    folder = tmp_path / "proj"
    folder.mkdir()
    options: dict[str, dict[str, Any]] = {
        "link-projects-wiki": {"pages_dir": c.pages_dir},
        "mod-wiki": {"scan_interval_seconds": 0},
    }
    with server(make_settings(tmp_path, options=options)) as client:
        settings = client.get(f"{API}/settings").json()
        settings["wiki"] = c.wiki_settings()
        res = client.put(f"{API}/settings", json=settings)
        assert res.status_code == 200, res.text
        register_project(client, PROJECT, folder)
        _seed(client, c, probe_tool)
        events = _run(client)

        # 1) 바뀐 이름의 도구: 모든 위키 동작이 ok, 기본 이름은 도구가 없다
        calls = [e for e in events if e["type"] == "agent.tool_call"]
        results = {
            e["payload"].get("tool_use_id"): e for e in events if e["type"] == "agent.tool_result"
        }
        names = [e["payload"]["name"] for e in calls]
        assert names[:-1] == [
            c.name(op) for op in ("write", "write", "links", "read", "search", "list", "move")
        ], names
        assert names[-1] == probe_tool
        probe = results[calls[-1]["payload"].get("tool_use_id")]
        assert probe["payload"]["is_error"] is True, probe
        unknown = UNKNOWN_HOST_TOOL_TEXT.format(tool=probe_tool)
        assert probe["payload"].get("output_preview") == unknown, probe
        wiki_events = [e for e in events if e["type"].startswith("wiki.")]
        assert [e["payload"]["status"] for e in wiki_events] == ["ok"] * 7, wiki_events

        # 2) 바뀐 폴더 + 바뀐 확장자(구성 폴더 이름은 mod-projects 설정 — 서버가 준 값)
        info = client.get(f"{API}/wiki/info?project={PROJECT}").json()
        assert PurePosixPath(info["pages_root"]).name == c.pages_dir, info
        directory = f"{info['pages_root']}/{c.wiki}"
        wiki_view = client.get(f"{API}/wiki/wikis/{c.wiki}?project={PROJECT}").json()
        listed = client.get(f"{API}/wiki/wikis?project={PROJECT}").json()
        assert wiki_view["directory"] == directory, wiki_view
        assert [w["directory"] for w in listed] == [directory], listed
        wiki_root = folder / directory
        files = sorted(
            p.relative_to(wiki_root).as_posix() for p in wiki_root.rglob("*") if p.is_file()
        )
        assert files == [f"a{c.extension}", f"keep/c{c.extension}"], files
        parts = {part for p in folder.rglob("*") for part in p.relative_to(folder).parts}
        assert not (parts & d["pages_dirs"]), parts
        assert not [p for p in folder.rglob("*") if p.suffix in d["extensions"]]

        # 3) 바뀐 머리말 키로 제목·태그
        a, moved = _view(client, c, "a"), _view(client, c, "keep/c")
        assert a["page"]["title"] == f"가{c.token}"
        assert a["page"]["tags"] == [f"x{c.token}", f"y{c.token}"]
        assert moved["page"]["title"] == f"나{c.token}"
        assert moved["page"]["tags"] == [f"z{c.token}"]
        assert set(a["front_matter"]) == {c.roles["title"], c.roles["tags"]}

        # 4) 바뀐 링크 패턴으로 링크·역링크(경로·제목으로 풀림)
        assert [(lk["rule_id"], lk["resolved"], lk["label"]) for lk in a["links"]] == [
            (c.rule_id, "keep/c", "비")
        ]
        assert [(lk["rule_id"], lk["resolved"]) for lk in moved["links"]] == [(c.rule_id, "a")]
        assert [b["path"] for b in a["backlinks"]] == ["keep/c"]
        assert [b["path"] for b in moved["backlinks"]] == ["a"]

        # 5) 옮기기가 바뀐 패턴으로 링크를 고쳤다(파일 원문)
        text_a = (wiki_root / f"a{c.extension}").read_text(encoding="utf-8")
        assert c.link("keep/c", "비") in text_a
        assert "docs/b" not in text_a

        # 링크 넣기도 바뀐 틀
        made = client.post(
            f"{API}/wiki/wikis/{c.wiki}/link-text?project={PROJECT}",
            json={"from_page": "a", "target": "keep/c", "label": "씨"},
        )
        assert made.status_code == 200, made.text
        assert made.json() == {"rule_id": c.rule_id, "text": c.link("keep/c", "씨")}

        # 기본 문법·폴더 이름·도구 이름이 결과에 하나도 없다
        pages_text = "\n".join(
            p.read_text(encoding="utf-8") for p in wiki_root.rglob("*") if p.is_file()
        )
        views_text = json.dumps([a, moved], ensure_ascii=False)
        for where, text in (("페이지 파일", pages_text), ("페이지 보기", views_text)):
            _absent(text, d["link_marks"], where)
            _absent(text, d["pages_dirs"], where)
            _absent(text, d["tool_names"], where)
        # 기본 문법으로 같은 파일을 읽으면 링크도 머리말도 없다(바뀐 문법만 맞는다)
        default_syntax = compile_syntax(effective_syntax())
        for p in wiki_root.rglob("*"):
            if p.is_file():
                parsed = parse_page(p.stem, p.read_text(encoding="utf-8"), default_syntax)
                assert (parsed.links, parsed.front_matter, parsed.tags) == ([], {}, []), p
        for line in pages_text.splitlines():
            assert line not in d["delimiter"], line
            assert line.split(":", 1)[0] not in d["role_keys"], line
        probe_ids = {calls[-1]["event_id"], probe["event_id"]}
        events_text = json.dumps(
            [e for e in events if e["event_id"] not in probe_ids], ensure_ascii=False
        )
        _absent(events_text, d["tool_names"] | d["tool_descriptions"], "실행 이벤트")
        _absent(events_text, d["pages_dirs"], "실행 이벤트")
        _absent(events_text, d["link_marks"], "실행 이벤트")
        wiki_text = json.dumps([info, wiki_view, listed], ensure_ascii=False)
        _absent(wiki_text, d["pages_dirs"], "위키 정보")
