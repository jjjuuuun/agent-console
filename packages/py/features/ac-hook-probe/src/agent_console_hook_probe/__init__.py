"""agent-console-hook-probe: hook 명령 감싸기 실행 파일과 그 기록을 읽는 로그 출처·분류기.

- 실행 파일(`agent-console-hook-probe`, `python -m agent_console_hook_probe`): 원래 hook
  명령을 그대로 실행하고(stdin·stdout·stderr·종료 코드 바이트 동일) 기록 형식 `hook-probe/1`
  한 줄을 남긴다.
- 감싸기 인자: `wrap_command`·`wrap_command_line`·`default_probe_command`.
- 셸 인자 규칙(데이터): `DEFAULT_SHELLS`·`ShellRule`·`shell_invocation`.
- 결정 파생: `derive_decision`·`parse_hook_output`.
- 로그 출처(X5 `hook-probe-jsonl`)·분류기(X6 `hook-probe`)는 하위 모듈
  `agent_console_hook_probe.plugins`(entry point로 등록, `agent-console-logs`를 쓴다).

이 패키지 루트와 실행 경로는 표준 라이브러리만 가져온다(hook마다 뜨는 프로세스라 시작이
가벼워야 한다).
"""

from __future__ import annotations

from ._cli import USAGE_EXIT_CODE, ProbeUsageError, main, parse_args
from ._decision import BLOCKING_EXIT_CODE, derive_decision, parse_hook_output
from ._probe import DEFAULT_GRACE_SECONDS, SPAWN_FAILED_EXIT_CODE, ProbeIO, run_probe
from ._record import (
    DEFAULT_CAPTURE_BYTES,
    RECORD_FORMAT,
    Capture,
    ProbeOutcome,
    append_line,
    build_record,
    command_digest,
    default_redactor,
    record_file_name,
)
from ._shell import (
    DEFAULT_SHELLS,
    ShellRule,
    default_shell_name,
    exec_invocation,
    shell_invocation,
)
from ._wrap import default_probe_command, wrap_command, wrap_command_line

__all__ = [
    "BLOCKING_EXIT_CODE",
    "DEFAULT_CAPTURE_BYTES",
    "DEFAULT_GRACE_SECONDS",
    "DEFAULT_SHELLS",
    "RECORD_FORMAT",
    "SPAWN_FAILED_EXIT_CODE",
    "USAGE_EXIT_CODE",
    "Capture",
    "ProbeIO",
    "ProbeOutcome",
    "ProbeUsageError",
    "ShellRule",
    "append_line",
    "build_record",
    "command_digest",
    "default_probe_command",
    "default_redactor",
    "default_shell_name",
    "derive_decision",
    "exec_invocation",
    "main",
    "parse_args",
    "parse_hook_output",
    "record_file_name",
    "run_probe",
    "shell_invocation",
    "wrap_command",
    "wrap_command_line",
]
