"""기록 형식 `hook-probe/1` 조립·파일 이름·덧붙이기."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_hook_probe import (
    RECORD_FORMAT,
    Capture,
    ProbeOutcome,
    append_line,
    build_record,
    command_digest,
    default_redactor,
    record_file_name,
)


def _outcome(stdin: bytes, stdout: bytes, code: int | None = 0) -> ProbeOutcome:
    caps = [Capture(), Capture(), Capture()]
    caps[0].add(stdin)
    caps[1].add(stdout)
    return ProbeOutcome(
        exit_code=code,
        started_at=10.0,
        ended_at=10.5,
        duration_ms=500.0,
        stdin=caps[0],
        stdout=caps[1],
        stderr=caps[2],
    )


def _identity(value: Any) -> Any:
    return value


def test_build_record_fields() -> None:
    stdin = json.dumps(
        {
            "session_id": "S",
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_use_id": "t1",
            "agent_id": "a1",
            "agent_type": "reviewer",
            "cwd": "/p",
        }
    ).encode()
    record = build_record(
        _outcome(stdin, b'{"decision": "block", "reason": "lint"}'),
        command="./hooks/lint.sh",
        form="shell",
        shell="sh",
        matcher="Edit|Write",
        context={"run_id": "R"},
        probe_id="P",
        redact=_identity,
    )
    assert record["format"] == RECORD_FORMAT
    assert (record["event"], record["tool"], record["tool_use_id"]) == ("PostToolUse", "Edit", "t1")
    assert (record["agent_id"], record["agent_type"], record["cwd"]) == ("a1", "reviewer", "/p")
    assert record["decision"]["value"] == "block"
    assert record["decision"]["reason"] == "lint"
    assert record["stdout_json"] == {"decision": "block", "reason": "lint"}
    assert record["command_digest"] == command_digest("./hooks/lint.sh")
    assert "./hooks/lint.sh" not in json.dumps(record)
    assert record["duration_ms"] == 500.0
    json.dumps(record)  # 직렬화 가능


def test_non_json_input_is_kept_as_text() -> None:
    record = build_record(
        _outcome(b"not json", b"plain"),
        command=["a", "b"],
        form="exec",
        shell=None,
        matcher=None,
        context={},
        probe_id="P",
        redact=_identity,
    )
    assert record["input"] == "not json"
    assert record["event"] is None
    assert record["stdout_json"] is None
    assert record["decision"]["value"] == "none"
    assert record["command_digest"] == command_digest(["a", "b"]) != command_digest("a b")


def test_default_redactor_masks_patterns_and_secret_keys() -> None:
    redact = default_redactor()
    value: dict[str, Any] = {
        "tool_input": {"command": "curl -H 'Authorization: Bearer abcdef123456789'", "token": 42},
        "env": [{"API_KEY": "plain"}],
        "note": "ok",
    }
    masked = redact(value)
    assert "abcdef123456789" not in json.dumps(masked)
    assert masked["tool_input"]["token"] == "[REDACTED]"
    assert masked["env"][0]["API_KEY"] == "[REDACTED]"
    assert masked["note"] == "ok"
    assert value["env"][0]["API_KEY"] == "plain"  # 원본은 그대로
    assert redact("password=hunter22") != "password=hunter22"
    assert redact(None) is None


def test_record_file_name_is_safe() -> None:
    assert record_file_name("abc-123_x.y") == "abc-123_x.y.jsonl"
    assert record_file_name(None) == "no-session.jsonl"
    for bad in ("../../etc", "a/b", ".hidden", "x" * 200, "공백 있음"):
        name = record_file_name(bad)
        assert name.startswith("s-")
        assert "/" not in name
        assert name.endswith(".jsonl")


def test_append_line_creates_folder_and_appends(tmp_path: Path) -> None:
    folder = tmp_path / "a" / "hook-probe"
    append_line(folder, "s.jsonl", {"n": 1})
    path = append_line(folder, "s.jsonl", {"n": 2, "한글": "값"})
    assert [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] == [
        {"n": 1},
        {"n": 2, "한글": "값"},
    ]


def test_capture_keeps_head_and_counts_total() -> None:
    cap = Capture(limit=4, margin=0)
    cap.add(b"ab")
    cap.add(b"cdef")
    assert (bytes(cap.data), cap.total, cap.truncated) == (b"abcd", 6, True)
    assert cap.complete() is None
    zero = Capture(limit=0, margin=0)
    zero.add(b"x")
    assert (bytes(zero.data), zero.truncated) == (b"", True)
    margin = Capture(limit=4, margin=2)
    margin.add(b"abcdefgh")
    assert (bytes(margin.data), margin.truncated) == (b"abcdef", True)
    whole = Capture(limit=4)
    whole.add(b"abcd")
    assert whole.complete() == b"abcd"


SECRET = "ghp_abcdefghijklmnopqrstuvwxyz0123456789ab"


def test_every_input_derived_field_is_redacted() -> None:
    stdin = json.dumps(
        {
            "session_id": "s9",
            "cwd": f"/x?token={SECRET}",
            "tool_name": f"T {SECRET}",
            "tool_use_id": SECRET,
            "agent_id": SECRET,
            "agent_type": SECRET,
            "hook_event_name": f"E {SECRET}",
        }
    ).encode()
    outcome = _outcome(stdin, f'{{"decision": "block", "reason": "{SECRET}"}}'.encode())
    outcome.error = f"spawn_failed: {SECRET}"
    record = build_record(
        outcome,
        command="x",
        form="shell",
        shell="sh",
        matcher=f"B({SECRET})",
        context={"k": SECRET, "token": "plain-value"},
        probe_id="P",
        redact=default_redactor(),
    )
    text = json.dumps(record)
    assert SECRET not in text
    assert "plain-value" not in text  # 비밀 이름 키 아래 값
    assert record["session_id"] == "s9"
    assert record["format"] == "hook-probe/1"


def test_secret_on_capture_boundary_is_masked() -> None:
    limit = 100
    cap = Capture(limit=limit)
    cap.add(b"x" * (limit - 10) + f" {SECRET} tail".encode())
    empty = Capture()
    outcome = ProbeOutcome(
        exit_code=0,
        started_at=0.0,
        ended_at=0.0,
        duration_ms=0.0,
        stdin=empty,
        stdout=cap,
        stderr=Capture(),
    )
    record = build_record(
        outcome,
        command="x",
        form="shell",
        shell="sh",
        matcher=None,
        context={},
        probe_id="P",
        redact=default_redactor(),
    )
    assert SECRET[:9] not in record["stdout"]  # 잘린 앞부분도 남지 않는다
    assert len(record["stdout"].encode()) <= limit
