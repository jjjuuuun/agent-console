"""5.5R.34: `api-request-blob` 행(요청 본문)은 기본 규칙에서 원문 없이 크기·해시만 색인한다.

행 규칙 `store_raw: false`·`keep`(데이터). 사용자가 규칙으로 다시 켜면 원문이 저장된다.
행 모양은 합성이다(실제 기록 아님).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent_console_contracts.logs import LogSettings
from agent_console_logs import (
    ClassifyContext,
    LogFilter,
    LogIngestor,
    LogRegistries,
    RawRecord,
    SourceRef,
    effective_config,
    query_context,
)
from agent_console_logs.testing import MemoryLogIndex
from agent_console_logs_claude import (
    OMITTED_KEY,
    ClaudeCodeClassifier,
    classifier_config_schema,
    omitted_row,
)

MARKER = "BLOB-BODY-MARKER-55r34"
BLOB: dict[str, Any] = {
    "type": "api-request-blob",
    "id": "blob-1",
    "sessionId": "S",
    "timestamp": "2026-10-27T00:00:00Z",
    "message": {"role": "user", "content": [{"type": "text", "text": f"본문 {MARKER}"}]},
}
REENABLE: dict[str, Any] = {
    "extra_row_rules": [
        {"match": {"/type": "api-request-blob"}, "category": "meta", "title": "요청 본문"}
    ]
}


def _classify(row: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> Any:
    cfg = effective_config(classifier_config_schema(), config)
    ctx = ClassifyContext(source_id="claude-code-jsonl", ref=SourceRef(ref="p/s.jsonl"), config=cfg)
    meta = {"kind": "session", "session": "S", "thread": "S", "project": "p"}
    [event] = ClaudeCodeClassifier().classify(
        RawRecord(origin="p/s.jsonl", offset=0, data=dict(row), meta=meta), ctx
    )
    return event


def _canonical_hash(row: Mapping[str, Any]) -> tuple[int, str]:
    data = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return len(data), hashlib.sha256(data).hexdigest()


def test_default_rule_keeps_size_and_hash_not_body() -> None:
    event = _classify(BLOB)
    assert (event.category, event.title) == ("meta", "API 요청 기록 · api-request-blob")
    assert event.raw == event.detail
    dumped = json.dumps([event.raw, event.detail, event.summary], ensure_ascii=False)
    assert MARKER not in dumped
    assert "content" not in dumped
    size, digest = _canonical_hash(BLOB)
    assert event.raw[OMITTED_KEY] == {"bytes": size, "sha256": digest}
    # keep: 행 종류·id·시각·세션·역할만(같은 위치)
    assert event.raw["type"] == "api-request-blob"
    assert event.raw["id"] == "blob-1"
    assert event.raw["message"] == {"role": "user"}
    assert event.summary == f"요청 본문 저장 안 함 · {size}바이트"
    # 다른 api-request* 행은 그대로
    other = _classify({"type": "api-request-other", "sessionId": "S", "x": MARKER})
    assert MARKER in json.dumps(other.raw, ensure_ascii=False)


def test_user_rule_turns_raw_storage_back_on() -> None:
    event = _classify(BLOB, REENABLE)
    assert event.title == "요청 본문"
    assert event.raw == BLOB
    assert MARKER in json.dumps(event.detail, ensure_ascii=False)


def test_store_raw_false_is_generic_rule_data() -> None:
    """어느 행이든 사용자 규칙으로 원문을 끌 수 있다(코드에 행 종류 이름 없음)."""
    config = {
        "extra_row_rules": [
            {
                "match": {"/type": "summary"},
                "category": "context",
                "title": "요약",
                "store_raw": False,
                "keep": ["/type", "/a~1b"],
            }
        ]
    }
    event = _classify({"type": "summary", "summary": MARKER, "a/b": 1}, config)
    assert MARKER not in json.dumps(event.raw, ensure_ascii=False)
    assert event.raw["a/b"] == 1
    assert set(event.raw) == {"type", "a/b", OMITTED_KEY}


def test_omitted_row_ignores_missing_and_empty_pointers() -> None:
    row = {"a": {"b": 1}, "c": [1, 2]}
    out = omitted_row(row, ["", "/zz", "/a/b", "/c/1", "nope"])
    assert out["a"] == {"b": 1}
    assert out["c"] == {"1": 2}
    assert set(out) == {"a", "c", OMITTED_KEY}
    assert row == {"a": {"b": 1}, "c": [1, 2]}  # 원본은 그대로


def _search(tmp_path: Path, classifier: Mapping[str, Any] | None) -> tuple[int, int, str]:
    """세션 파일 하나를 색인하고 (검색 결과 수, 전체 이벤트 수, 상세 덤프)를 돌려준다."""
    path = tmp_path / "projects" / "-w" / "S.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(BLOB, ensure_ascii=False) + "\n", "utf-8")
    registries = LogRegistries()
    registries.load()
    index = MemoryLogIndex()
    ingestor = LogIngestor(index, registries, environ={"CLAUDE_CONFIG_DIR": str(tmp_path)})
    source: dict[str, Any] = {"id": "claude-code-jsonl", "enabled": True}
    if classifier is not None:
        source["config"] = {"classifier": {"config": dict(classifier)}}
    settings = LogSettings.model_validate({"sources": [source]})
    ingestor.scan(settings)
    ctx = query_context(settings)
    found = index.query_events(LogFilter(q=MARKER), ctx).items
    every = index.query_events(LogFilter(), ctx).items
    details = [index.get_event(e.uid, ctx) for e in every]
    dumped = json.dumps([d.model_dump(mode="json") for d in details if d is not None])
    return len(found), len(every), dumped


def test_index_and_search_have_no_blob_body_by_default(tmp_path: Path) -> None:
    found, total, dumped = _search(tmp_path / "default", None)
    assert (found, total) == (0, 1)
    assert MARKER not in dumped
    found, total, dumped = _search(tmp_path / "on", REENABLE)
    assert (found, total) == (1, 1)
    assert MARKER in dumped
