"""4R.3 QA: 0.5.x 데이터 하위 호환(정의 해시 불변·HandoffCount 옛/새 필드·F-25)."""

import hashlib
import json
from typing import Any

from agent_console_contracts import Graph, HandoffCount, WorkspaceSettings
from agent_console_contracts.logs import LogEvent, LogEventDetail, LogTaxonomy


def _digest(doc: dict[str, Any]) -> str:
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def test_old_definition_dump_is_byte_identical() -> None:
    """옛(0.5.x) 문서를 exclude_unset으로 쓰면 입력과 같다(저장된 정의 해시 불변)."""
    doc = {
        "id": "g",
        "name": "g",
        "settings": {"observe": {"hooks": True, "mcp": False, "hook_events": ["PreToolUse"]}},
        "nodes": [],
        "edges": [],
    }
    dumped = Graph.model_validate(doc).model_dump(mode="json", exclude_unset=True)
    assert dumped == doc
    assert _digest(dumped) == _digest(doc)
    ws = {"schema_version": 1, "agent_defaults": {"observe": {"hooks": True}}}
    assert WorkspaceSettings.model_validate(ws).model_dump(mode="json", exclude_unset=True) == ws


def test_handoff_count_old_and_new_fields_fill_each_other() -> None:
    old = HandoffCount.model_validate({"source": "a", "target": "b", "kind": "k", "count": 2})
    assert (old.from_, old.to, old.via) == ("a", "b", "k")
    new = HandoffCount.model_validate({"from": "a", "to": "b", "via": "k", "count": 2})
    assert (new.source, new.target, new.kind) == ("a", "b", "k")
    dumped = new.model_dump(mode="json", by_alias=True)
    assert dumped["from"] == "a"
    assert dumped["source"] == "a"
    bare = HandoffCount.model_validate({"source": "a", "target": "b", "count": 1})
    assert bare.via is None
    assert bare.kind is None


def test_no_error_judgement_in_contract_f25() -> None:
    """status/category는 열린 문자열이며 어떤 값도 거부하지 않는다. 범주 'error'도 특별하지 않다."""
    for status in ("", "failed", "zz-unknown"):
        ev = LogEvent.model_validate(
            {
                "uid": "u",
                "seq": 0,
                "source": "s",
                "observed_at": 1.0,
                "category": "error",
                "status": status,
            }
        )
        assert ev.status == status
    detail = LogEventDetail.model_validate({"event": ev.model_dump(by_alias=True)})
    assert detail.truncated is False
    assert detail.detail_truncated is False
    assert detail.usage is None
    tax = LogTaxonomy.model_validate({"categories": {"error": {}, "zz": {"tone": "zz-tone"}}})
    assert tax.categories["error"].tone is None
    assert tax.categories["zz"].tone == "zz-tone"
