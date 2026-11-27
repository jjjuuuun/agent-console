"""값이 섞인 로그 제목의 원문 틀 + 값(I.7f, 계약 ``LogEvent.text_templates``).

대응표 틀 ``실행 {/payload/status}`` → ``실행 {status}`` + ``{status: ...}``. 채운 값 == 제목,
제목이 잘리면·값만으로 된 틀이면 틀이 없다. 설치자 대응표를 바꾸면 그 틀이 실린다(번역 키가
달라진다).
"""

from __future__ import annotations

import json
import re
from importlib.resources import files

import pytest

import agent_console_link_logs_runs
from agent_console_contracts import TextTemplate, render_text_parts
from agent_console_contracts.logs import LogEvent
from agent_console_link_logs_runs.event_map import (
    load_default_event_map,
    resolve,
    resolve_text_template,
)
from agent_console_link_logs_runs.testing import PlatformRunsRig, run_event, run_record
from agent_console_logs import LogFilter, query_context


def _events(rig: PlatformRunsRig) -> list[LogEvent]:
    return rig.index.query_events(LogFilter(limit=200), query_context(None)).items


@pytest.mark.parametrize(
    ("spec", "doc", "expected"),
    [
        ("실행 {/payload/status}", {"payload": {"status": "completed"}}, "실행 {status}"),
        (
            "사용 한도 {/payload/window} {/payload/status}",
            {"payload": {"window": "five_hour", "status": "allowed"}},
            "사용 한도 {window} {status}",
        ),
        (
            "세션 시작 {/payload/session_id}",
            {"payload": {"session_id": "s1"}},
            "세션 시작 {session_id}",
        ),
        (
            "자식 {/payload/source/node} → {/payload/target/node}",
            {"payload": {"source": {"node": "a"}, "target": {"node": "b"}}},
            "자식 {source_node} → {target_node}",
        ),
        ("{node} 실패", {}, "{node} 실패"),
        ("괄호 {/a} }{", {"a": "x"}, None),  # 자리표시자가 아닌 괄호 조각은 렌더 비교로 걸러진다
    ],
)
def test_resolve_text_template_names_and_values(
    spec: str, doc: dict[str, object], expected: str | None
) -> None:
    names = {"node": "lead"}
    found = resolve_text_template(spec, doc, names)
    if expected is None:
        assert found is None or render_text_parts([found]) == resolve(spec, doc, names)
        return
    assert found is not None
    assert found.template == expected
    assert render_text_parts([found]) == resolve(spec, doc, names)


def test_fixed_or_value_only_templates_have_none() -> None:
    doc = {"payload": {"text": "hello", "status": ""}}
    assert resolve_text_template("맥락 구성", doc, {}) is None
    assert resolve_text_template("{/payload/text}", doc, {}) is None
    assert resolve_text_template("{node} {/payload/status}", doc, {"node": "a"}) is None
    # 빈 값으로 앞뒤 공백이 잘리면 채운 값이 제목과 달라 틀을 싣지 않는다
    assert resolve_text_template("실행 {/payload/status}", doc, {}) is None


def test_conditional_title_uses_chosen_branch() -> None:
    spec = {
        "pointer": "/payload/path",
        "map": {"null": "위키 {/payload/op} {/payload/wiki}"},
        "default": "위키 {/payload/op} {/payload/wiki}/{/payload/path}",
    }
    page = resolve_text_template(spec, {"payload": {"op": "read", "wiki": "w", "path": "p"}}, {})
    assert page == TextTemplate(
        template="위키 {op} {wiki}/{path}", params={"op": "read", "wiki": "w", "path": "p"}
    )
    whole = resolve_text_template(spec, {"payload": {"op": "list", "wiki": "w", "path": None}}, {})
    assert whole is not None
    assert whole.template == "위키 {op} {wiki}"


def test_indexed_events_carry_title_templates() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record(status="running"))
    rig.records.events.append(
        run_event(1, "run.started", {"status": "running"}),
        run_event(2, "usage.rate_limit", {"window": "five_hour", "status": "allowed"}),
        run_event(3, "node.started", {"status": "running"}),
    )
    rig.scan()
    by_title = {e.title: e for e in _events(rig)}
    run = by_title["실행 running"]
    assert run.text_templates == {
        "/title": [TextTemplate(template="실행 {status}", params={"status": "running"})]
    }
    limit = by_title["사용 한도 five_hour allowed"]
    assert limit.text_templates["/title"][0].template == "사용 한도 {window} {status}"
    assert by_title["a running"].text_templates == {}  # 값만으로 된 틀
    for event in _events(rig):
        for parts in event.text_templates.values():
            assert render_text_parts(parts) == event.title


def test_installer_event_map_changes_the_template() -> None:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record(status="running"))
    rig.records.events.append(run_event(1, "run.started", {"status": "running"}))
    rig.scan({"event_map": {"run.started": {"title": "Run is {/payload/status}"}}})
    (event,) = _events(rig)
    assert event.title == "Run is running"
    assert event.text_templates["/title"][0].template == "Run is {status}"


def test_truncated_title_has_no_template() -> None:
    rig = PlatformRunsRig()
    rig.item.classifier._title_chars = 8  # 제목 상한(생성자 인자)을 작게
    rig.records.runs.save(run_record(status="running"))
    rig.records.events.append(run_event(1, "run.started", {"status": "running-long-status"}))
    rig.scan()
    (event,) = _events(rig)
    assert event.title.endswith("…")
    assert event.text_templates == {}


def test_english_catalog_has_the_default_title_templates() -> None:
    path = files(agent_console_link_logs_runs).joinpath("locales", "en.json")
    text = json.loads(path.read_text(encoding="utf-8"))["text"]
    wanted = set()
    for rule in load_default_event_map().rules.values():
        title = rule.get("title")
        if isinstance(title, str):
            doc: dict[str, object] = {}
            for pointer in re.findall(r"\{(/[^{}]*)\}", title):  # 모든 포인터에 값을 채운 문서
                node = doc
                *heads, last = pointer[1:].split("/")
                for head in heads:
                    node = node.setdefault(head, {})  # type: ignore[assignment]
                node[last] = "x"
            found = resolve_text_template(title, doc, {"node": "n", "type": "t"})
            if found is not None and any("가" <= ch <= "힣" for ch in found.template):
                wanted.add(found.template)
    assert {"실행 {status}", "사용 한도 {window} {status}", "세션 시작 {session_id}"} <= wanted
    assert sorted(wanted - set(text)) == []
