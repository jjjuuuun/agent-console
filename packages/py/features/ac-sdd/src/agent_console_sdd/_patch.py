"""작업 상태 바꾸기 = 그 작업 머리 줄 하나 고치기(design §6R.1.4 K6R-5).

체크 칸 글자와 `[키: 값]` 필드 값만 바꾸고, 나머지 바이트(줄바꿈 종류·들여쓰기·뒤 공백·다른 줄)는
그대로 둔다. 충돌은 머리 줄 해시로 판단한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_contracts.constants import ErrorCodes, KnownIssueCodes
from agent_console_contracts.sdd import EffectiveSyntax, ParsedTask, SddTaskChangedDetails

from ._compiled import (
    CompiledSyntax,
    HeadLine,
    analyze_head,
    compile_syntax,
    line_hash,
    split_lines,
)

__all__ = ["DEFAULT_FIELD_FORMAT", "TaskChangedError", "TaskPatchError", "patch_task"]

DEFAULT_FIELD_FORMAT = "[{key}: {value}]"
"""없는 필드를 머리 줄 끝에 덧붙일 때의 모양(기본 문법의 필드 모양과 짝)."""

_SPACE = " \t"


class TaskPatchError(ValueError):
    """작업 줄을 고칠 수 없다(요청 값이 문법에 맞지 않음 등).

    Attributes:
        code: 오류 코드(`ErrorCodes`·`KnownIssueCodes` 값).
        details: 화면에 줄 세부(값 원문은 넣지 않는다).
    """

    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details: dict[str, Any] = dict(details or {})


class TaskChangedError(TaskPatchError):
    """작업 머리 줄이 읽은 뒤에 바뀌었다(`sdd.task_changed`, 서버는 409).

    Attributes:
        current: 최신 줄 정보(`SddTaskChangedDetails`).
    """

    def __init__(self, current: SddTaskChangedDetails) -> None:
        super().__init__(
            ErrorCodes.SDD_TASK_CHANGED,
            "작업 줄이 바뀌었습니다. 새로 읽은 뒤 다시 시도하세요.",
            current.model_dump(mode="json", exclude_none=True),
        )
        self.current = current


def _check_value(key: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise TaskPatchError(
            ErrorCodes.VALIDATION_FAILED,
            f"필드 '{key}' 값에 줄바꿈을 넣을 수 없습니다.",
            {"field": key},
        )


def patch_task(
    text: str,
    task: ParsedTask,
    *,
    syntax: EffectiveSyntax | CompiledSyntax,
    status: str | None = None,
    fields: Mapping[str, str | None] | None = None,
    field_format: str = DEFAULT_FIELD_FORMAT,
) -> str:
    """작업 머리 줄의 상태 표시 문자와 필드만 바꾼 새 원문을 돌려준다.

    Args:
        text: 작업 문서 최신 원문.
        task: 그 원문(또는 같은 머리 줄의 이전 원문)을 파싱한 작업. `line`·`line_hash`로 줄을
            찾는다.
        syntax: 파싱에 쓴 유효 문법(또는 컴파일한 것).
        status: 바꿀 작업 상태 id(None = 그대로). 그 상태의 첫 표시 문자를 쓴다. 체크 칸이 없는
            목록 항목이면 목록 표시 뒤에 `[글자] `를 넣는다.
        fields: 필드 이름 → 새 값(None = 필드 지우기). 없는 필드는 머리 줄 끝(뒤 공백 앞)에
            `field_format`으로 덧붙인다. 같은 이름이 여럿이면 처음 것만 바꾼다.
        field_format: 덧붙일 필드 모양(`{key}`·`{value}`). 결과가 문법의 필드 정규식으로 다시
            읽히지 않으면 거부한다.

    Returns:
        고친 원문. 바뀐 것이 없으면 `text` 그대로.

    Raises:
        TaskChangedError: 그 줄의 해시가 `task.line_hash`와 다르거나 작업 줄이 아님.
        TaskPatchError: 모르는 상태, 줄바꿈이 든 값, 다시 읽었을 때 값이 다름(`validation_failed`·
            `sdd.unknown_state`).
    """
    compiled = syntax if isinstance(syntax, CompiledSyntax) else compile_syntax(syntax)
    lines = split_lines(text)
    idx = task.line - 1
    current = lines[idx] if 0 <= idx < len(lines) else None
    if current is None or line_hash(current) != task.line_hash:
        raise TaskChangedError(
            SddTaskChangedDetails(
                task_key=task.key,
                line_hash=line_hash(current) if current is not None else None,
                line=task.line if current is not None else None,
                text=current.rstrip("\r\n") if current is not None else None,
            )
        )
    head = analyze_head(current, compiled)
    if head.kind is None:
        raise TaskChangedError(
            SddTaskChangedDetails(
                task_key=task.key,
                line_hash=line_hash(current),
                line=task.line,
                text=head.text,
            )
        )

    edits: list[tuple[int, int, str]] = []
    marker: str | None = None
    if status is not None:
        info = next((s for s in compiled.statuses if s.id == status), None)
        if info is None or not info.markers:
            raise TaskPatchError(
                KnownIssueCodes.SDD_UNKNOWN_STATE,
                f"작업 상태 '{status}'가 문법에 없습니다.",
                {"ref": status},
            )
        marker = info.markers[0]
        if head.checkbox is not None:
            if head.marker != marker and compiled.marker_to_status.get(head.marker or "") != status:
                edits.append((head.checkbox[0], head.checkbox[1], marker))
        else:
            edits.append((head.marker_end, head.marker_end, f"[{marker}] "))

    appended: list[str] = []
    for key, value in (fields or {}).items():
        existing = next((f for f in head.fields if f.key == key), None)
        if value is not None:
            _check_value(key, value)
        if existing is None:
            if value is not None:
                appended.append(field_format.format(key=key, value=value))
            continue
        if value is None:
            start = existing.start
            while start > 0 and head.text[start - 1] in _SPACE:
                start -= 1
            edits.append((start, existing.end, ""))
        elif value != existing.value:
            edits.append((existing.value_start, existing.value_end, value))
    if appended:
        body_end = len(head.text.rstrip(_SPACE))
        edits.append((body_end, body_end, "".join(" " + a for a in appended)))

    if not edits:
        return text
    new_line = head.text
    for start, end, repl in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        new_line = new_line[:start] + repl + new_line[end:]
    _verify(new_line, compiled, status=status, fields=fields or {})
    lines[idx] = new_line + head.eol
    return "".join(lines)


def _verify(
    new_line: str,
    syntax: CompiledSyntax,
    *,
    status: str | None,
    fields: Mapping[str, str | None],
) -> None:
    head: HeadLine = analyze_head(new_line, syntax)
    if status is not None:
        got = syntax.marker_to_status.get(head.marker or "") if head.marker is not None else None
        if got != status:
            raise TaskPatchError(
                ErrorCodes.VALIDATION_FAILED,
                f"작업 상태 '{status}'를 이 줄에 적을 수 없습니다.",
                {"ref": status},
            )
    values: dict[str, str] = {}
    for f in head.fields:
        values.setdefault(f.key, f.value)
    for key, value in fields.items():
        if value is None:
            continue
        if values.get(key) != value.strip():
            raise TaskPatchError(
                ErrorCodes.VALIDATION_FAILED,
                f"필드 '{key}' 값을 작업 문법으로 다시 읽을 수 없습니다.",
                {"field": key},
            )
