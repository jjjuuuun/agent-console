"""probe 실행: stdin 전달, 출력·종료 코드 바이트 동일, 기록 형식·실패 격리(4R.7 완료 기준)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agent_console_hook_probe import RECORD_FORMAT, USAGE_EXIT_CODE

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX 셸 명령으로 비교한다")

HOOK_INPUT = {
    "session_id": "sess-1",
    "transcript_path": "/x/t.jsonl",
    "cwd": "/proj",
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_use_id": "toolu_01",
    "tool_input": {"command": "rm -rf build", "api_key": "sk-ant-abcdefghijklmnop123456"},
}
STDIN = json.dumps(HOOK_INPUT).encode()

# (이름, 명령, 기대 결정)
CASES = [
    (
        "allow",
        """cat >/dev/null; printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse",'\
'"permissionDecision":"allow"}}'""",
        "allow",
    ),
    (
        "deny",
        """cat >/dev/null; printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse",'\
'"permissionDecision":"deny","permissionDecisionReason":"rm 금지"}}'; echo 경고 >&2""",
        "deny",
    ),
    (
        "modify",
        """cat >/dev/null; printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse",'\
'"updatedInput":{"command":"rm -rf ./build"}}}\\n'""",
        "modify",
    ),
    ("block", "cat >/dev/null; echo 'blocked: rm' >&2; exit 2", "block"),
    ("non-json", "cat; printf 'plain \\001\\377 text'; printf 'e1\\r\\n' >&2", "none"),
    ("error", "head -c 5; echo oops >&2; exit 3", "error"),
]


def _records(folder: Path) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.jsonl")):
        lines += [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    return lines


@pytest.mark.parametrize(("name", "command", "decision"), CASES, ids=[c[0] for c in CASES])
def test_bytes_identical_and_decision_recorded(
    name: str,
    command: str,
    decision: str,
    tmp_path: Path,
    probe: Callable[..., Any],
    direct: Callable[..., Any],
) -> None:
    out = tmp_path / "rec"
    got = probe(["--out", str(out), "--matcher", "Bash", "--", command], STDIN)
    want = direct(command, STDIN)
    assert (got.stdout, got.stderr, got.code) == (want.stdout, want.stderr, want.code)
    [record] = _records(out)
    assert record["format"] == RECORD_FORMAT
    assert record["decision"]["value"] == decision
    assert record["exit_code"] == want.code
    assert record["event"] == "PreToolUse"
    assert record["session_id"] == "sess-1"
    assert record["tool_use_id"] == "toolu_01"
    assert record["tool"] == "Bash"
    assert record["matcher"] == "Bash"
    assert record["form"] == "shell"
    assert record["ended_at"] >= record["started_at"]
    assert record["duration_ms"] >= 0
    assert record["bytes"]["stdout"] == len(want.stdout)
    assert (out / "sess-1.jsonl").is_file()


def test_record_hides_command_and_suspected_secrets(
    tmp_path: Path, probe: Callable[..., Any]
) -> None:
    out = tmp_path / "rec"
    command = (
        "cat; echo 'Authorization: Bearer abcdef1234567890' >&2; echo TOPSECRET-MARK >/dev/null"
    )
    got = probe(["--out", str(out), "--", command], STDIN)
    assert b"Bearer abcdef1234567890" in got.stderr  # 원래 출력은 그대로
    text = (out / "sess-1.jsonl").read_text(encoding="utf-8")
    assert "TOPSECRET-MARK" not in text  # 명령 원문은 남기지 않는다
    assert "sk-ant-abcdefghijklmnop123456" not in text
    assert "abcdef1234567890" not in text
    [record] = _records(out)
    assert record["command_digest"].startswith("sha256:")
    assert record["input"]["tool_input"]["command"] == "rm -rf build"
    assert record["input"]["tool_input"]["api_key"] == "[REDACTED]"


def test_recording_failure_does_not_change_result(
    tmp_path: Path, probe: Callable[..., Any], direct: Callable[..., Any]
) -> None:
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x")
    command = "cat; echo e >&2; exit 2"
    got = probe(["--out", str(blocker / "sub"), "--", command], STDIN)
    want = direct(command, STDIN)
    assert (got.stdout, got.stderr, got.code) == (want.stdout, want.stderr, want.code)


def test_redactor_failure_does_not_change_result(
    tmp_path: Path, direct: Callable[..., Any]
) -> None:
    from agent_console_hook_probe import ProbeIO, main

    def broken() -> Callable[[Any], Any]:
        raise RuntimeError("규칙 로딩 실패")

    r, w = os.pipe()
    os.write(w, STDIN)
    os.close(w)
    with (tmp_path / "o").open("w+b") as o, (tmp_path / "e").open("w+b") as e:
        code = main(
            ["--out", str(tmp_path / "rec"), "--", "cat; exit 4"],
            io=ProbeIO(r, o.fileno(), e.fileno()),
            handle_signals=False,
            redactor=broken,
        )
    os.close(r)
    assert code == 4
    assert (tmp_path / "o").read_bytes() == STDIN
    assert (tmp_path / "e").read_bytes() == b""
    assert not (tmp_path / "rec").exists() or not list((tmp_path / "rec").iterdir())


def test_large_streams_pass_through_and_record_is_bounded(
    tmp_path: Path, probe: Callable[..., Any]
) -> None:
    big = b"".join(bytes([i % 256]) for i in range(300_000))
    out = tmp_path / "rec"
    got = probe(["--out", str(out), "--capture-bytes", "1000", "--", "cat"], big)
    assert got.stdout == big
    assert got.code == 0
    [record] = _records(out)
    assert record["truncated"] == {"stdin": True, "stdout": True, "stderr": False}
    assert record["bytes"]["stdin"] == len(big) == record["bytes"]["stdout"]
    assert len(record["stdout"]) <= 1000
    assert record["session_id"] is None  # 입력이 잘려 JSON을 읽지 않았다
    assert (out / "no-session.jsonl").is_file()


def test_exec_form_runs_without_shell(tmp_path: Path, probe: Callable[..., Any]) -> None:
    out = tmp_path / "rec"
    got = probe(["--out", str(out), "--", "printf", "%s|", "a b", "$HOME"], b"")
    assert got.stdout == b"a b|$HOME|"  # 셸 해석 없음
    [record] = _records(out)
    assert record["form"] == "exec"
    assert record["shell"] is None
    forced = probe(["--out", str(out), "--exec", "--", "true"], b"")
    assert forced.code == 0


def test_context_and_spawn_failure(tmp_path: Path, probe: Callable[..., Any]) -> None:
    out = tmp_path / "rec"
    got = probe(
        [
            *("--out", str(out), "--context", "run_id=R1", "--context", "node=a/b"),
            *("--exec", "--", "/nonexistent/hook-binary"),
        ],
        b"",
    )
    assert got.code == 127
    assert b"agent-console-hook-probe" in got.stderr
    [record] = _records(out)
    assert record["context"] == {"run_id": "R1", "node": "a/b"}
    assert record["error"].startswith("spawn_failed")
    assert record["decision"]["value"] == "error"


@pytest.mark.parametrize(
    "args",
    [
        ["--out", "x", "true"],  # `--` 없음
        ["--out", "x", "--"],  # 명령 없음
        ["--", "true"],  # --out 없음
        ["--out", "x", "--context", "novalue", "--", "true"],
        ["--out", "x", "--bogus", "--", "true"],
    ],
)
def test_usage_errors_exit_non_blocking(args: list[str], probe: Callable[..., Any]) -> None:
    got = probe(args, b"")
    assert got.code == USAGE_EXIT_CODE  # 2(차단)가 아니다
    assert got.stdout == b""
    assert got.stderr.startswith(b"agent-console-hook-probe:")


def test_concurrent_appends_keep_lines_whole(tmp_path: Path, probe: Callable[..., Any]) -> None:
    from concurrent.futures import ThreadPoolExecutor

    out = tmp_path / "rec"
    with ThreadPoolExecutor(4) as pool:
        list(
            pool.map(lambda _i: probe(["--out", str(out), "--", "cat >/dev/null"], STDIN), range(8))
        )
    records = _records(out)
    assert len(records) == 8
    assert len({r["probe_id"] for r in records}) == 8
