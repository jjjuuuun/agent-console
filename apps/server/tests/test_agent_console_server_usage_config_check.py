"""4R.13 QA 후속: 공통 설정 저장 시 사용량 출처 설정을 그 출처 ``config_schema``로 검증한다.

- 잘못된 값(예산 -5)·모르는 키는 ``PUT /settings``가 422(``validation_failed``)로 거부하고,
  ``details.issues[].path``가 문서 기준 위치다. 메시지·본문에 입력 값은 없다.
- 맞는 설정은 저장된다.
- 저장 시점에 출처가 없으면(``link-logs-usage`` 꺼짐) 검증할 수 없어 저장된다. 그 출처가
  나타나면 ``GET /server-info`` 경고와 ``GET /usage/sources``의 ``error``로 드러난다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server

SOURCE = "local-logs"
CODE = "usage.source_config_invalid"


def _settings(config: dict[str, Any]) -> dict[str, Any]:
    return {"usage": {"sources": [{"id": SOURCE, "config": config}]}}


def _issues(body: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = body["error"]["details"]["issues"]
    return [i for i in issues if i["code"] == CODE]


def test_negative_budget_rejected_with_path(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        res = client.put(f"{API}/settings", json=_settings({"budgets": {"local_five_hour": -5}}))
        assert res.status_code == 422, res.text
        body = res.json()
        assert body["error"]["code"] == "validation_failed"
        [issue] = _issues(body)
        assert issue["path"] == "/usage/sources/0/config/budgets/local_five_hour"
        assert issue["details"] == {"source": SOURCE, "validator": "exclusiveMinimum"}
        assert "-5" not in json.dumps(body)
        # 저장되지 않았다
        assert client.get(f"{API}/settings").json() == {}


def test_unknown_key_rejected(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        res = client.put(f"{API}/settings", json=_settings({"budgetz": {"x": 1}}))
        assert res.status_code == 422, res.text
        [issue] = _issues(res.json())
        assert issue["path"] == "/usage/sources/0/config"
        assert issue["details"]["validator"] == "additionalProperties"
        assert "budgetz" not in issue["message"]


def test_valid_config_saved(tmp_path: Path) -> None:
    good = _settings({"budgets": {"local_five_hour": 1000}})
    with server(make_settings(tmp_path)) as client:
        res = client.put(f"{API}/settings", json=good)
        assert res.status_code == 200, res.text
        assert client.get(f"{API}/settings").json() == good
        warnings = client.get(f"{API}/server-info").json()["warnings"]
        assert [w for w in warnings if w["code"] == CODE] == []
        [info] = [
            s for s in client.get(f"{API}/usage/sources").json() if s["descriptor"]["id"] == SOURCE
        ]
        assert info["error"] is None


def test_absent_runtime_source_saved_then_warned_when_it_appears(tmp_path: Path) -> None:
    bad = _settings({"budgets": {"local_five_hour": -5}})
    off = make_settings(tmp_path, modules={"disabled": ["link-logs-usage"]})
    with server(off) as client:
        assert client.put(f"{API}/settings", json=bad).status_code == 200
        warnings = client.get(f"{API}/server-info").json()["warnings"]
        assert [w for w in warnings if w["code"] == CODE] == []
    with server(make_settings(tmp_path)) as client:
        warnings = client.get(f"{API}/server-info").json()["warnings"]
        [warning] = [w for w in warnings if w["code"] == CODE]
        assert warning["severity"] == "warning"
        assert warning["path"] == "/usage/sources/0/config/budgets/local_five_hour"
        assert "-5" not in json.dumps(warning)
        [info] = [
            s for s in client.get(f"{API}/usage/sources").json() if s["descriptor"]["id"] == SOURCE
        ]
        assert info["error"]["code"] == "validation_failed"
        assert info["error"]["details"]["path"] == ["budgets", "local_five_hour"]
        # 고치면 저장되고 경고가 사라진다
        fixed = _settings({"budgets": {"local_five_hour": 5}})
        assert client.put(f"{API}/settings", json=fixed).status_code == 200
        warnings = client.get(f"{API}/server-info").json()["warnings"]
        assert [w for w in warnings if w["code"] == CODE] == []
