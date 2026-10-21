"""hook probe 감싸기(design §4R.7 "감싸기 적용", F-16).

유효 관측 설정 `observe.hook_probe`가 참이면, 이 백엔드가 **전달하는** 명령형 hook(실행 묶음 `hooks`
칸)을 `agent-console-hook-probe`로 감싸 실행한다. 기록 폴더는 `AgentRequest.run_folder` 아래
`hook-probe`(설치자 옵션 `hook_probe_folder`)다. 사용자 설정 파일·`.claude` 내보내기는
건드리지 않는다.

감싸기 인자는 `agent_console_hook_probe`(`wrap_command`·`wrap_command_line`)가 만든다. 그 패키지는
선택 의존(추가 기능 `hook-probe`)이라 실행할 때 가져오고, 없으면 감싸지 않고 경고한다.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_console_contracts import Issue, LogWarningPayload

__all__ = [
    "DEFAULT_HOOK_PROBE_FOLDER",
    "HOOK_PROBE_ISSUES",
    "HOOK_PROBE_MODULE",
    "HookProbePlan",
    "hook_probe_enabled",
    "hook_probe_note",
    "plan_hook_probe",
]

DEFAULT_HOOK_PROBE_FOLDER = "hook-probe"
"""`run_folder` 아래 기록 폴더 이름(`hook-probe-jsonl` 출처의 경로 규칙과 같다)."""

HOOK_PROBE_MODULE = "agent_console_hook_probe"
"""감싸기 인자를 만드는 모듈(선택 의존)."""


class HOOK_PROBE_ISSUES:  # noqa: N801 — 문서 상수 묶음
    """hook probe 관련 이슈 코드."""

    WRAPPED = "observe.hook_probe_wrapped"
    """info: 묶음 미리보기 "hook 감싸기 켜짐" 안내."""


def hook_probe_enabled(observe: Mapping[str, Any] | None) -> bool:
    """유효 관측 설정(`AgentRequest.observe` = `ObserveSettings` 덤프)의 `hook_probe`가 참인가."""
    return observe is not None and observe.get("hook_probe") is True


@dataclass(frozen=True, slots=True)
class HookProbePlan:
    """한 실행의 감싸기 방법.

    Attributes:
        out: 기록 폴더.
        probe: probe 실행 인자(None = 패키지 기본 `default_probe_command()`).
        context: 기록에 붙일 맥락(`run_id`·`node_path`).
        wrap: `agent_console_hook_probe.wrap_command`.
        wrap_line: `agent_console_hook_probe.wrap_command_line`.
    """

    out: Path
    probe: list[str] | None
    wrap: Callable[..., list[str]]
    wrap_line: Callable[..., str]
    context: dict[str, str] = field(default_factory=dict)

    def argv(self, argv: Sequence[str], matcher: str | None) -> list[str]:
        """셸 없이 돌릴 인자 목록(callback 경로) → probe가 `--exec`로 그대로 실행하는 인자."""
        return list(
            self.wrap(
                list(argv), out=self.out, probe=self.probe, matcher=matcher, context=self.context
            )
        )

    def line(self, command: str, matcher: str | None) -> str:
        """설정 JSON의 셸 명령 문자열(settings 경로) → 감싼 명령 한 줄(셸 형식 유지)."""
        return str(
            self.wrap_line(
                command, out=self.out, probe=self.probe, matcher=matcher, context=self.context
            )
        )


def plan_hook_probe(
    observe: Mapping[str, Any] | None,
    *,
    run_folder: str | None,
    run_context: Mapping[str, str],
    probe_command: Sequence[str] | None,
    folder_name: str = DEFAULT_HOOK_PROBE_FOLDER,
    importer: Callable[[str], Any] = importlib.import_module,
) -> tuple[HookProbePlan | None, list[LogWarningPayload]]:
    """관측 설정 → 감싸기 방법(꺼져 있거나 할 수 없으면 None).

    Args:
        observe: 유효 관측 설정. `hook_probe`가 참일 때만 감싼다(기본 꺼짐).
        run_folder: 노드 실행 폴더(`AgentRequest.run_folder`). 없으면 감싸지 않고 경고.
        run_context: 기록 맥락(`AgentRequest.run_context`, 빈 값은 뺀다).
        probe_command: 설치자 옵션 `hook_probe_command`(None = 기본).
        folder_name: 기록 폴더 이름.
        importer: 모듈 가져오기(테스트 주입).

    Returns:
        (감싸기 방법 또는 None, 경고 목록).
    """
    if not hook_probe_enabled(observe):
        return None, []
    if not run_folder:
        return None, [
            LogWarningPayload(
                message="실행 폴더가 없어 hook을 hook probe로 감싸지 않습니다",
                details={"option": "observe.hook_probe"},
            )
        ]
    try:
        module = importer(HOOK_PROBE_MODULE)
        wrap = module.wrap_command
        wrap_line = module.wrap_command_line
    except (ImportError, AttributeError):
        return None, [
            LogWarningPayload(
                message="agent-console-hook-probe가 설치되지 않아 hook을 감싸지 않습니다",
                details={"option": "observe.hook_probe", "package": "agent-console-hook-probe"},
            )
        ]
    return (
        HookProbePlan(
            out=Path(run_folder) / folder_name,
            probe=list(probe_command) if probe_command is not None else None,
            context={k: v for k, v in run_context.items() if k and "=" not in k and v},
            wrap=wrap,
            wrap_line=wrap_line,
        ),
        [],
    )


def hook_probe_note(hooks: int, *, delivered: bool) -> Issue:
    """묶음 미리보기 안내(info `observe.hook_probe_wrapped`). 감싸기가 켜졌을 때 부른다.

    Args:
        hooks: 묶음의 명령형 hook 항목 수.
        delivered: 이 백엔드가 명령형 hook을 전달하는가(설치자 `allow_command_hooks`).
    """
    if delivered:
        message = (
            f"hook 감싸기 켜짐: 이 노드가 전달하는 hook 명령 {hooks}개를 hook probe로 감싸 "
            "입력·출력·결정·소요 시간을 기록합니다"
            "(.claude 내보내기와 사용자 설정은 원래 명령 그대로)"
        )
    else:
        message = (
            "hook 감싸기 켜짐: 다만 명령형 hook 전달이 꺼져 있어 감쌀 hook이 없습니다"
            "(설치자 allow_command_hooks)"
        )
    return Issue(
        severity="info",
        code=HOOK_PROBE_ISSUES.WRAPPED,
        message=message,
        details={"hooks": hooks if delivered else 0, "option": "observe.hook_probe"},
    )
