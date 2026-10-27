"""5.5R.10: 로그·구조도 연동(link-logs-architecture)을 서버 조립 수준에서 확인한다.

- 설치된 서버에서 연동이 켜지고 웹 역할 `logs:architecture`를 낸다. 사용자 설정 `architecture`의
  프로필로 `/logs/architecture`를 그리고, 칸의 `selector` + `max_seq`로 거른 이벤트 수 = 칸 `count`.
- 모듈 켜고 끄기(design §5.5R.3 표 1~3행): `mod-architecture`만 → 프로필 API만, 로그 구조도 404.
  `mod-logs`만 → 로그 그대로, `arch`는 422. 연동을 끄면 경로 404·`arch` 422, 두 모듈은 그대로.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_server.testing import API, make_settings, server

QUIET = {"mod-logs": {"startup_scan": False, "scan_interval_seconds": 0}}
PROFILE: dict[str, Any] = {
    "title": "테스트",
    "cells": {
        "ask": {"when": {"all": [{"path": "/category", "op": "eq", "value": "input"}]}},
        "work": {
            "when": {"all": [{"path": "/category", "op": "eq", "value": "tool"}]},
            "group_by": "/tool",
        },
    },
    "edges": [
        {
            "id": "call",
            "from": "ask",
            "to": "work",
            "kind": "observed",
            "when": {"all": [{"path": "/tags", "op": "contains", "value": "tool_call"}]},
        }
    ],
    "unassigned": True,
}


def _write_logs(root: Path) -> None:
    root.mkdir(parents=True)
    base = {"schema_version": 1, "session": "S1", "thread": "main"}
    rows = [
        {**base, "category": "input", "title": "요청", "time": 1_760_000_000},
        {**base, "category": "tool", "tool": "Read", "tags": ["tool_call"], "time": 1_760_000_001},
        {**base, "category": "tool", "tool": "Grep", "time": 1_760_000_002},
        {**base, "category": "tool", "time": 1_760_000_003},
        {**base, "category": "other", "time": 1_760_000_004},
        {**base, "session": "S2", "category": "tool", "tool": "Read", "time": 1_760_000_005},
    ]
    rows = [{"title": f"e{i}", **r} for i, r in enumerate(rows)]
    text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    (root / "a.jsonl").write_text(text, encoding="utf-8")


def _configure(client: TestClient, root: Path, *, profile: bool = True) -> None:
    settings = client.get(f"{API}/settings").json()
    entry = {"id": "normalized-v1", "enabled": True, "config": {"roots": [str(root)]}}
    settings["logs"] = {"sources": [entry]}
    if profile:
        settings["architecture"] = {"profiles": {"t": PROFILE}, "default_profile": "t"}
    assert client.put(f"{API}/settings", json=settings).status_code == 200
    assert client.post(f"{API}/logs/scan").status_code == 202


def _count(client: TestClient, params: dict[str, Any]) -> int:
    total, cursor = 0, None
    while True:
        query = {**params, "limit": 2, **({"cursor": cursor} if cursor else {})}
        res = client.get(f"{API}/logs/events", params=query)
        assert res.status_code == 200, res.text
        body = res.json()
        total += len(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return total


def _selector_params(selector: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"arch": selector["arch"]}
    if selector.get("arch_group") is not None:
        out["arch_group"] = selector["arch_group"]
    if selector.get("arch_sources") is not None:
        out["arch_sources"] = ",".join(selector["arch_sources"])
    return out


def test_link_active_and_click_counts(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    _write_logs(root)
    with server(make_settings(tmp_path, options=QUIET)) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        link = infos["link-logs-architecture"]
        assert (link["status"], link["kind"], link["web_roles"]) == (
            "active",
            "link",
            ["logs:architecture"],
        )
        _configure(client, root)
        res = client.get(f"{API}/logs/architecture", params={"session": "S1"})
        assert res.status_code == 200, res.text
        view = res.json()
        assert view["profile"] == "t"
        assert view["event_total"] == 5
        cells = {c["id"]: c for c in view["cells"]}
        assert cells["work"]["metrics"]["count"]["value"] == 3
        targets = [cells["ask"]["selector"], cells["work"]["selector"]]
        targets += [g["selector"] for g in cells["work"]["groups"]]
        targets += [e["selector"] for e in view["edges"] if e["selector"]]
        targets.append(view["unassigned"]["selector"])
        expected = [cells["ask"]["metrics"]["count"]["value"], 3]
        expected += [g["metrics"]["count"]["value"] for g in cells["work"]["groups"]]
        expected += [e["metrics"]["count"]["value"] for e in view["edges"] if e["selector"]]
        expected.append(view["unassigned"]["metrics"]["count"]["value"])
        got = [
            _count(client, {"session": "S1", "max_seq": view["max_seq"], **_selector_params(s)})
            for s in targets
        ]
        assert got == expected
        assert sorted(g["key"] or "" for g in cells["work"]["groups"]) == ["", "Grep", "Read"]
        names = {f["id"] for f in client.get(f"{API}/logs/schema").json()["filters"]}
        assert {"arch", "arch_group", "arch_sources"} <= names


def test_architecture_module_alone(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, options=QUIET, modules={"disabled": ["mod-logs"]})
    with server(settings) as client:
        statuses = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
        assert statuses["link-logs-architecture"] == "unsatisfied"
        assert client.get(f"{API}/architecture/profiles").status_code == 200
        assert client.get(f"{API}/logs/architecture").status_code == 404


def test_logs_without_architecture_or_link(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    _write_logs(root)
    for off, state in (("mod-architecture", "unsatisfied"), ("link-logs-architecture", "disabled")):
        home = tmp_path / off
        settings = make_settings(home, options=QUIET, modules={"disabled": [off]})
        with server(settings) as client:
            statuses = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
            assert statuses["link-logs-architecture"] == state
            assert statuses["mod-logs"] == "active"
            _configure(client, root, profile=False)
            assert _count(client, {"session": "S1"}) == 5
            assert client.get(f"{API}/logs/architecture").status_code == 404
            res = client.get(f"{API}/logs/events", params={"arch": "t:cell:work"})
            assert res.status_code == 422
