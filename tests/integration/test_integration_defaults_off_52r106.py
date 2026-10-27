"""5.2R.106: 패키지 기본 데이터는 바꾸고 끌 수 있고, 꺼도 나머지는 동작한다(R0.1 수용 기준 3).

항목마다 세 가지를 본다: 바꾸는 길 / 끄는 길 / 끈 상태에서 나머지가 동작.
끄는 길이 없던 두 항목(분류 체계·해결 버튼 표)은 설치자 옵션으로 길을 냈다(5.2R.106 후속).
테스트용 데이터는 전부 임시 폴더 안에서 만든다(저장소에 데이터 파일을 새로 두지 않는다).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_backend_claude_sdk import DEFAULT_LOGIN_RULES
from agent_console_backend_claude_sdk._login import ClaudeSdkLoginOptions, ClaudeSdkLoginRules
from agent_console_backend_claude_sdk._login_driver import build_expect_rules
from agent_console_contracts import Issue
from agent_console_link_logs_runs import load_default_event_map, load_event_map
from agent_console_link_logs_usage import load_auto_log_sources
from agent_console_link_logs_usage.estimate import load_default_config, parse_config
from agent_console_link_runs_teams import (
    DEFAULT_ISSUE_FIXES,
    IssueFixes,
    RunsTeamsLink,
    RunsTeamsLinkSettings,
    issue_fixes_of,
    load_issue_fixes,
)
from agent_console_logs import (
    DEFAULT_SESSION_TITLE_RULES,
    load_default_session_title_rules,
    load_default_taxonomy,
    load_taxonomy,
    merge_taxonomy,
    query_context,
)
from agent_console_mod_logs import LogsModuleSettings, load_dashboard_templates
from agent_console_server.testing import API, make_settings, server

_BASE = {"schema_version": 1, "thread": "main"}
_A = {**_BASE, "session": "sess-a", "cwd": "/work/proj-a"}
_B = {**_BASE, "session": "sess-b", "cwd": "/elsewhere/tool"}
_T = 1760000000
SESSION_A: list[dict[str, Any]] = [
    {**_A, "category": "input", "title": "첫 요청", "time": _T, "tags": ["session_title"]},
    {
        **_A,
        "category": "llm",
        "title": "답변",
        "model": "model-x",
        "message_id": "m1",
        "time": _T + 1,
        "usage": {"input_tokens": 10, "output_tokens": 3},
    },
    {
        **_A,
        "category": "llm",
        "title": "답변(이어짐)",
        "model": "model-x",
        "message_id": "m1",
        "time": _T + 2,
        "usage": {"input_tokens": 10, "output_tokens": 8},
    },
    {
        **_A,
        "category": "tool_call",
        "title": "검색 호출",
        "tool": "search",
        "call_id": "c1",
        "stage": "start",
        "time": _T + 3,
        "tags": ["tool"],
    },
    {
        **_A,
        "category": "tool_result",
        "title": "검색 결과",
        "tool": "search",
        "call_id": "c1",
        "stage": "complete",
        "time": _T + 5,
        "tags": ["tool"],
    },
    {
        **_A,
        "category": "handoff",
        "title": "위임",
        "from": ["main"],
        "to": ["helper"],
        "via": "delegate",
        "time": _T + 6,
    },
    {
        **_A,
        "category": "error",
        "title": "실패",
        "thread": "helper",
        "time": _T + 7,
        "agent": {"label": "도우미", "parent_id": "main"},
    },
]
SESSION_B: list[dict[str, Any]] = [
    {**_B, "category": "input", "title": "다른 곳 요청", "time": _T + 100000},
    {
        **_B,
        "category": "llm",
        "title": "답변",
        "model": "model-y",
        "message_id": "m9",
        "time": _T + 100001,
        "usage": {"input_tokens": 1, "output_tokens": 2},
    },
]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


QUIET = {"startup_scan": False, "scan_interval_seconds": 0}


def _logs_server(tmp_path: Path, *, logs: dict[str, Any] | None = None, **mod_logs: Any) -> Any:
    root = tmp_path / "logs-src"
    root.mkdir(parents=True)
    _write_jsonl(root / "session-a.jsonl", SESSION_A)
    _write_jsonl(root / "session-b.jsonl", SESSION_B)
    s = make_settings(tmp_path / "base", options={"mod-logs": {**QUIET, **mod_logs}})
    return server(s, environ={"CLAUDE_CONFIG_DIR": str(tmp_path / "empty-claude")}), root, logs


def _scan(client: Any, root: Path, logs: dict[str, Any] | None) -> None:
    body = {
        "logs": {
            "sources": [{"id": "normalized-v1", "enabled": True, "config": {"roots": [str(root)]}}],
            **(logs or {}),
        }
    }
    assert client.put(f"{API}/settings", json=body).status_code == 200
    scan = client.post(f"{API}/logs/scan")
    assert scan.status_code in (200, 202), scan.text


# ---------- 1. 로그 기본 분류 체계


def test_taxonomy_default_change_and_off_in_package() -> None:
    default = load_default_taxonomy()
    assert default.categories  # 기본 데이터가 있다
    # 바꾸기: 설정 덮어쓰기가 범주 단위로 이긴다
    changed = merge_taxonomy(default, load_taxonomy("categories: {error: {label: 바꿈}}"))
    assert changed.categories["error"].label == "바꿈"
    # 끄기: 파일 경로 교체(없는 파일) / 빈 문서 / 빈 기본값 주입
    assert load_default_taxonomy(Path("/nonexistent/none.yaml")).categories == {}
    assert load_taxonomy("").categories == {}
    off = merge_taxonomy(None, None)
    assert off.categories == {}
    ctx = query_context(None, base_taxonomy=off, session_title_rules=())
    assert ctx.hidden_categories == frozenset()


def test_taxonomy_user_can_hide_every_default_category_through_settings(tmp_path: Path) -> None:
    """설정 `logs.taxonomy`만으로 기본 범주를 전부 숨길 수 있고, 로그 질의는 계속 동작한다."""
    ctx, root, _ = _logs_server(tmp_path)
    ids = list(load_default_taxonomy().categories)
    hide = {"taxonomy": {"categories": {cid: {"visible": False} for cid in ids}}}
    with ctx as client:
        _scan(client, root, hide)
        cats = client.get(f"{API}/logs/taxonomy").json()["categories"]
        assert all(cats[cid]["visible"] is False for cid in ids)
        assert client.get(f"{API}/logs/sessions").status_code == 200
        assert client.get(f"{API}/logs/events").status_code == 200
        assert client.get(f"{API}/health").status_code == 200


def test_taxonomy_installer_option_to_drop_defaults(tmp_path: Path) -> None:
    """설치자 옵션 `base_taxonomy_file`: 비우면 기본, 파일이면 교체, false·빈 문자열이면 끔."""
    assert LogsModuleSettings().base_taxonomy_file is None
    assert LogsModuleSettings(base_taxonomy_file=False).base_taxonomy_file is False
    assert LogsModuleSettings.model_validate({"base_taxonomy_file": ""}).base_taxonomy_file is False
    default_ids = set(load_default_taxonomy().categories)
    mine = tmp_path / "mine.yaml"
    mine.write_text("categories: {mine: {label: 내것}}", encoding="utf-8")
    cases: list[tuple[Any, set[str]]] = [(None, default_ids), (str(mine), {"mine"}), (False, set())]
    for i, (option, expect) in enumerate(cases):
        ctx, root, _ = _logs_server(tmp_path / f"t{i}", base_taxonomy_file=option)
        with ctx as client:
            _scan(client, root, None)
            r = client.get(f"{API}/logs/taxonomy")
            assert r.status_code == 200, r.text
            assert set(r.json()["categories"]) == expect
            assert client.get(f"{API}/logs/sessions").status_code == 200
            assert client.get(f"{API}/logs/events").status_code == 200


# ---------- 2. 세션 제목 규칙


def test_session_title_rules_change_off_and_server_runs(tmp_path: Path) -> None:
    # 바꾸기·끄기(모듈 설정)
    assert LogsModuleSettings().title_rules() is None  # null = 기본 데이터
    assert LogsModuleSettings(session_title_rules=[]).title_rules() == ()
    mine = LogsModuleSettings(session_title_rules=[{"tag": "x", "pick": "last"}])  # type: ignore[list-item]
    [rule] = mine.title_rules() or ()
    assert (rule.tag, rule.pick) == ("x", "last")
    assert load_default_session_title_rules()  # 기본 데이터가 있다
    assert DEFAULT_SESSION_TITLE_RULES  # 데이터 파일이 비어도 쓰는 대체 규칙

    ctx, root, _ = _logs_server(tmp_path, session_title_rules=[])
    with ctx as client:
        _scan(client, root, None)
        r = client.get(f"{API}/logs/sessions")
        assert r.status_code == 200, r.text
        sessions = r.json()
        items = sessions["items"] if isinstance(sessions, dict) else sessions
        assert items  # 제목 규칙이 없어도 세션 목록은 나온다
        assert all(not s.get("title") for s in items)


# ---------- 3. 이슈 수정 제안(issue_fixes.json)


def test_issue_fixes_change_and_off_in_package() -> None:
    assert DEFAULT_ISSUE_FIXES.codes  # 기본 데이터
    code = DEFAULT_ISSUE_FIXES.codes[0]
    issue = Issue(severity="error", code=code, message="m")
    # 끄기: 빈 표
    off = load_issue_fixes('{"rules": []}')
    assert off.codes == ()
    assert off.fix_for(code, team_kind="team", graph_id="g") is None
    assert off.attach([issue], team_kind="team", graph_id="g") == [issue]
    assert IssueFixes().codes == ()
    # 바꾸기: 다른 표
    mine = load_issue_fixes(
        json.dumps(
            {
                "rules": [
                    {
                        "codes": ["my.code"],
                        "actions": [
                            {
                                "label": "열기 {graph_id}",
                                "target": {"role": "graph", "id": "{graph_id}"},
                            }
                        ],
                    }
                ]
            }
        )
    )
    fix = mine.fix_for("my.code", team_kind="team", graph_id="g1")
    assert fix is not None
    assert fix.actions[0].label == "열기 g1"
    assert mine.fix_for(code, team_kind="team", graph_id="g") is None


def test_issue_fixes_installer_option(tmp_path: Path) -> None:
    """설치자 옵션 `issue_fixes_file`: 비우면 기본 표, 빈 표 파일이면 끔, 서버는 그대로 뜬다."""
    schema = RunsTeamsLink.descriptor.settings_schema
    assert schema is RunsTeamsLinkSettings
    assert issue_fixes_of(RunsTeamsLinkSettings().issue_fixes_file) is DEFAULT_ISSUE_FIXES
    empty = tmp_path / "fixes.json"
    empty.write_text('{"rules": []}', encoding="utf-8")
    assert issue_fixes_of(empty).codes == ()
    assert issue_fixes_of(Path("fixes.json"), tmp_path).codes == ()  # 상대 경로 = 설정 폴더 기준
    opts = {"link-runs-teams": {"issue_fixes_file": str(empty)}}
    with server(make_settings(tmp_path / "s", options=opts)) as client:
        assert client.get(f"{API}/health").status_code == 200


def test_server_runs_with_link_runs_teams_present(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        assert client.get(f"{API}/health").status_code == 200


# ---------- 4. 대시보드 템플릿(mod-logs)


def test_dashboard_templates_change_and_off(tmp_path: Path) -> None:
    assert load_dashboard_templates()  # 기본 데이터
    empty = tmp_path / "none"
    empty.mkdir()
    assert load_dashboard_templates(empty) == []  # 폴더 교체 = 끄기
    ctx, _root, _ = _logs_server(tmp_path / "s", dashboard_templates_dir=str(empty))
    with ctx as client:
        assert client.get(f"{API}/logs/dashboard-templates").json() == []
        assert client.get(f"{API}/logs/sources").status_code == 200


# ---------- 5. Claude 로그인 화면 규칙


def test_login_rules_change_and_off() -> None:
    default = ClaudeSdkLoginRules()
    assert default.open_url == list(DEFAULT_LOGIN_RULES["open_url"])
    mine = ClaudeSdkLoginRules(open_url=[r"https://x\.test/\S+"])
    assert mine.open_url == [r"https://x\.test/\S+"]
    off = ClaudeSdkLoginRules(open_url=[], needs_code=[], success=[], failure=[])
    assert off.named() == []
    opts = ClaudeSdkLoginOptions.model_validate(
        {"rules": {"open_url": [], "needs_code": [], "success": [], "failure": []}}
    )
    rules = build_expect_rules(opts)  # 규칙이 0개여도 드라이버 재료가 만들어진다
    assert rules is not None
    with pytest.raises(ValidationError):  # 안전하지 않은 규칙은 거부(바꾸는 길도 안전 검사)
        ClaudeSdkLoginRules(open_url=["(a+)+$"])


# ---------- 6. 로그 출처 자동 켜기·로컬 로그 창


def test_auto_log_sources_off_and_change(tmp_path: Path) -> None:
    assert load_auto_log_sources()  # 기본 데이터
    mine = tmp_path / "auto.json"
    mine.write_text('{"log_sources": []}', encoding="utf-8")
    assert not load_auto_log_sources(mine)  # 파일 교체 = 끄기
    # 서버: 가짜 CLAUDE_CONFIG_DIR/projects가 있으면 켜짐, 옵션을 끄면 꺼짐. 둘 다 서버는 뜬다
    claude = tmp_path / "claude"
    (claude / "projects").mkdir(parents=True)
    env = {"CLAUDE_CONFIG_DIR": str(claude)}
    for on in (True, False):
        opts = {"link-logs-usage": {"auto_enable_log_sources": on}}
        with server(make_settings(tmp_path / f"b{on}", options=opts), environ=env) as client:
            assert client.get(f"{API}/health").status_code == 200
            srcs = {x["descriptor"]["id"]: x for x in client.get(f"{API}/logs/sources").json()}
            assert srcs["claude-code-jsonl"]["enabled"] is on


def test_local_logs_defaults_change_and_off(tmp_path: Path) -> None:
    defaults = load_default_config()
    assert defaults["windows"]
    other = tmp_path / "d.json"
    other.write_text(json.dumps({**defaults, "windows": []}), encoding="utf-8")
    assert load_default_config(other)["windows"] == []  # 파일 교체
    parsed = parse_config({"windows": []}, defaults)  # 사용자 설정이 키 단위로 이김
    assert parsed.windows == ()


# ---------- 7. 실행 로그 대응표(run_event_map.yaml)


def test_run_event_map_change_and_off(tmp_path: Path) -> None:
    assert load_default_event_map(tmp_path / "none.yaml") is not None  # 없는 파일 = 빈 대응표
    empty = load_event_map("")
    mine = load_event_map("types: {x.y: {category: custom}}")
    assert empty.rule_for("x.y") != mine.rule_for("x.y")
