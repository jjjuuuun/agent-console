"""유효 문법을 한 번 컴파일한 형태와 작업 머리 줄 분석(파싱과 줄 고치기가 같은 분석을 쓴다).

사용자 정규식은 모두 `ac-safe-regex`로 컴파일한다(시간·길이 상한). 컴파일할 수 없는 정규식은
`sdd.invalid_pattern` 이슈를 내고 그 규칙만 없는 것으로 본다.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.sdd import (
    EffectiveSyntax,
    KnownTaskFieldRoles,
    SpecIssue,
    TaskStatusInfo,
)
from agent_console_safe_regex import (
    DEFAULT_TIMEOUT_SECONDS,
    SafePattern,
    UnsafeRegexError,
    compile_user_regex,
)

__all__ = [
    "KNOWN_LIST_ITEMS",
    "CompiledSyntax",
    "FieldSpan",
    "HeadLine",
    "analyze_head",
    "compile_syntax",
    "line_hash",
    "split_lines",
]

KNOWN_LIST_ITEMS = ("checkbox", "bullet", "ordered")
"""`TaskSyntax.list_item`에 파서가 다루는 값(코드 개념): checkbox = 체크 칸이 있는 목록 항목,
bullet = 글머리 목록 항목, ordered = 번호 목록 항목(뒤 둘은 체크 칸이 없어도 작업)."""

_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+\Z")
_EOL = "\r\n"
_LIST_MARKER = re.compile(r"[ \t]*(?:([-+*])|(\d{1,9})[.)])(?:[ \t]+|\Z)")
_SPACE = " \t"


def split_lines(text: str) -> list[str]:
    """줄바꿈(`\\r\\n`·`\\r`·`\\n`)을 붙인 채 줄로 나눈다. CommonMark 줄 번호와 같다."""
    return _LINE.findall(text)


def line_hash(line: str) -> str:
    """작업 머리 줄의 해시(줄바꿈 문자 제외, sha256 16진수 앞 16자).

    상태 바꾸기 요청의 `expected_line_hash`가 이 값이다(design §6R.1.4 K6R-5).
    """
    return hashlib.sha256(line.rstrip(_EOL).encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class FieldSpan:
    """머리 줄의 `[키: 값]` 필드 하나(위치는 줄바꿈 뺀 줄 기준 문자 위치)."""

    key: str
    value: str
    start: int
    end: int
    value_start: int
    value_end: int


@dataclass(slots=True)
class HeadLine:
    """작업 머리 줄 분석 결과.

    Attributes:
        text: 줄바꿈을 뺀 줄.
        eol: 줄바꿈 문자(없으면 빈 문자열).
        kind: `bullet` 또는 `ordered`(목록 항목이 아니면 None).
        marker_end: 목록 표시(`- `·`1. `) 끝 위치.
        checkbox: 체크 칸 안 글자 위치 (시작, 끝). 없으면 None.
        marker: 체크 칸 안 글자(없으면 None).
        id: 작업 id(없으면 None), id_span: 그 위치.
        title: 체크 칸·id·필드를 뺀 제목.
        fields: 필드 목록(줄 순서).
    """

    text: str
    eol: str
    kind: str | None
    marker_end: int = 0
    checkbox: tuple[int, int] | None = None
    marker: str | None = None
    id: str | None = None
    id_span: tuple[int, int] | None = None
    title: str = ""
    fields: tuple[FieldSpan, ...] = ()


@dataclass(slots=True)
class CompiledSyntax:
    """컴파일한 유효 문법. `compile_syntax`로 만든다."""

    statuses: list[TaskStatusInfo]
    list_item: str | None
    marker_to_status: dict[str, str]
    done_ids: frozenset[str]
    first_status: str | None
    max_marker_len: int
    id_pattern: SafePattern | None
    field_pattern: SafePattern | None
    list_separator: str | None
    range_separator: str | None
    none_values: frozenset[str]
    roles: dict[str, str]
    body: bool
    max_depth: int | None
    requirement_patterns: list[SafePattern]
    stage_levels: frozenset[int]
    stage_pattern: SafePattern | None
    empty: bool
    issues: list[SpecIssue] = field(default_factory=list)

    def fields_with_role(self, role: str) -> list[str]:
        """그 역할(`KnownTaskFieldRoles`)인 필드 이름들."""
        return [name for name, r in self.roles.items() if r == role]

    @property
    def dependency_fields(self) -> list[str]:
        return self.fields_with_role(KnownTaskFieldRoles.DEPENDENCIES)

    @property
    def requirement_fields(self) -> list[str]:
        return self.fields_with_role(KnownTaskFieldRoles.REQUIREMENTS)


def _issue(code: str, message: str, *, severity: str = "error", **kw: object) -> SpecIssue:
    return SpecIssue.model_validate({"severity": severity, "code": code, "message": message, **kw})


def _compile(
    pattern: str | None,
    path: str,
    groups: tuple[str, ...],
    timeout: float,
    issues: list[SpecIssue],
) -> SafePattern | None:
    if not pattern:
        return None
    try:
        return compile_user_regex(pattern, required_groups=groups, timeout=timeout)
    except UnsafeRegexError as exc:
        issues.append(
            _issue(
                KnownIssueCodes.SDD_INVALID_PATTERN,
                f"작업 문법의 정규식을 쓸 수 없습니다: {exc}",
                path=path,
            )
        )
        return None


def compile_syntax(
    syntax: EffectiveSyntax, *, regex_timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> CompiledSyntax:
    """유효 문법을 컴파일한다. 잘못된 부분은 `issues`에 넣고 그 규칙만 없는 것으로 본다.

    Args:
        syntax: `merge_syntax`·`effective_syntax` 결과.
        regex_timeout: 정규식 매치 1회 시간 상한(초).

    Returns:
        `CompiledSyntax`. `issues`에는 `sdd.invalid_pattern`(정규식·작업 줄 모양)과
        `sdd.duplicate_status_marker`(두 상태가 같은 표시 문자)가 들어간다.
    """
    issues: list[SpecIssue] = []
    task = syntax.syntax.task
    req = syntax.syntax.requirement
    stage = syntax.syntax.stage
    statuses = list(syntax.statuses)

    marker_to_status: dict[str, str] = {}
    for info in statuses:
        for m in info.markers:
            if m in marker_to_status and marker_to_status[m] != info.id:
                issues.append(
                    _issue(
                        KnownIssueCodes.SDD_DUPLICATE_STATUS_MARKER,
                        f"작업 상태 '{marker_to_status[m]}'와 '{info.id}'가 같은 체크 칸 글자를 "
                        "씁니다. 앞의 상태로 읽습니다.",
                        path="/task/statuses",
                        details={"marker": m},
                    )
                )
                continue
            marker_to_status.setdefault(m, info.id)

    list_item = task.list_item if task else None
    if list_item is not None and list_item not in KNOWN_LIST_ITEMS:
        issues.append(
            _issue(
                KnownIssueCodes.SDD_INVALID_PATTERN,
                f"작업 줄 모양 '{list_item}'은 읽을 수 없습니다"
                f"({', '.join(KNOWN_LIST_ITEMS)} 중 하나).",
                path="/task/list_item",
            )
        )
        list_item = None

    t = regex_timeout
    id_pattern = _compile(task.id_pattern if task else None, "/task/id_pattern", ("id",), t, issues)
    field_pattern = _compile(
        task.field_pattern if task else None, "/task/field_pattern", ("key", "value"), t, issues
    )
    req_patterns: list[SafePattern] = []
    for i, p in enumerate((req.patterns if req else None) or ()):
        compiled = _compile(p, f"/requirement/patterns/{i}", ("id",), t, issues)
        if compiled is not None:
            req_patterns.append(compiled)
    stage_pattern = _compile(stage.pattern if stage else None, "/stage/pattern", ("id",), t, issues)

    roles = dict((task.roles if task else None) or {})
    return CompiledSyntax(
        statuses=statuses,
        list_item=list_item,
        marker_to_status=marker_to_status,
        done_ids=frozenset(s.id for s in statuses if s.done),
        first_status=statuses[0].id if statuses else None,
        max_marker_len=max((len(m) for m in marker_to_status), default=1) or 1,
        id_pattern=id_pattern,
        field_pattern=field_pattern,
        list_separator=(task.list_separator if task else None) or None,
        range_separator=(task.range_separator if task else None) or None,
        none_values=frozenset(v.strip() for v in ((task.none_values if task else None) or ())),
        roles=roles,
        body=(task.body if task else None) == "nested",
        max_depth=task.max_depth if task else None,
        requirement_patterns=req_patterns,
        stage_levels=frozenset((stage.heading_levels if stage else None) or ()),
        stage_pattern=stage_pattern,
        empty=syntax.empty or list_item is None,
        issues=issues,
    )


def analyze_head(line: str, syntax: CompiledSyntax, *, require_checkbox: bool = False) -> HeadLine:
    """작업 머리 줄 하나를 나눈다(목록 표시·체크 칸·id·필드·제목). 줄바꿈은 따로 둔다.

    목록 항목 줄이 아니면 `kind`가 None이다. `require_checkbox`면 체크 칸이 없는 줄은 id·필드를
    읽지 않고 바로 돌려준다(`checkbox`가 None). 정규식 시간 초과는 `RegexTimeoutError`로 올린다.
    """
    text = line.rstrip(_EOL)
    eol = line[len(text) :]
    m = _LIST_MARKER.match(text)
    if m is None:
        return HeadLine(text=text, eol=eol, kind=None)
    kind = "bullet" if m.group(1) else "ordered"
    pos = m.end()
    checkbox: tuple[int, int] | None = None
    marker: str | None = None
    if pos < len(text) and text[pos] == "[":
        close = text.find("]", pos + 1, pos + 2 + syntax.max_marker_len)
        if close > pos + 1 and (close + 1 == len(text) or text[close + 1] in _SPACE):
            checkbox = (pos + 1, close)
            marker = text[pos + 1 : close]
            pos = close + 1
    if require_checkbox and checkbox is None:
        return HeadLine(text=text, eol=eol, kind=kind, marker_end=m.end())
    while pos < len(text) and text[pos] in _SPACE:
        pos += 1
    rest_start = pos
    rest = text[pos:]

    task_id: str | None = None
    id_span: tuple[int, int] | None = None
    if syntax.id_pattern is not None and rest:
        im = syntax.id_pattern.search(rest)
        if im is not None:
            span = im.span("id")
            if span is not None and span[1] > span[0]:
                task_id = im.group("id")
                id_span = (rest_start + span[0], rest_start + span[1])
                rest_start += im.end
                rest = text[rest_start:]

    fields: list[FieldSpan] = []
    title = rest
    if syntax.field_pattern is not None and rest:
        pieces: list[str] = []
        last = 0
        for fm in syntax.field_pattern.finditer(rest):
            ks = fm.span("key")
            vs = fm.span("value")
            if ks is None or vs is None:
                continue
            fields.append(
                FieldSpan(
                    key=rest[ks[0] : ks[1]],
                    value=rest[vs[0] : vs[1]].strip(),
                    start=rest_start + fm.start,
                    end=rest_start + fm.end,
                    value_start=rest_start + vs[0],
                    value_end=rest_start + vs[1],
                )
            )
            pieces.append(rest[last : fm.start])
            last = fm.end
        pieces.append(rest[last:])
        title = "".join(pieces)
    return HeadLine(
        text=text,
        eol=eol,
        kind=kind,
        marker_end=m.end(),
        checkbox=checkbox,
        marker=marker,
        id=task_id,
        id_span=id_span,
        title=" ".join(title.split()),
        fields=tuple(fields),
    )
