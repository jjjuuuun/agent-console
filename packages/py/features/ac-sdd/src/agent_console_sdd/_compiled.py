"""유효 문법을 한 번 컴파일한 형태와 작업 머리 줄 분석(파싱과 줄 고치기가 같은 분석을 쓴다).

사용자 정규식은 모두 `ac-safe-regex`로 컴파일한다(시간·길이 상한). 컴파일할 수 없는 정규식은
`sdd.invalid_pattern` 이슈를 내고 그 규칙만 없는 것으로 본다.

작업 상태는 체크 칸 글자(`- [x]`)나, 문법에 `status_pattern`이 있으면 줄 머리 낱말(`- TODO:`)로
읽는다(6R.32). 줄 머리 낱말은 체크 칸이 없는 줄에서만 찾고, 맞은 범위를 뗀 나머지에서 id·필드·제목을
읽는다.
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

from ._syntax import package_task_format

__all__ = [
    "KNOWN_LIST_ITEMS",
    "STATUS_GROUP",
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
STATUS_GROUP = "status"
"""`TaskSyntax.status_pattern`의 이름 묶음(코드 개념): 맞은 글자가 작업 상태 표시 문자다."""
_IGNORED_NO_GROUP = "no_status_group"
_IGNORED_CHECKBOX = "checkbox"


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
        marker: 체크 칸 안 글자 또는 줄 머리 상태 낱말(없으면 None).
        body_start: 본문 맨 앞 위치(목록 표시·체크 칸·뒤 공백 다음). 상태 없는 줄에 상태 낱말을
            넣는 곳이다.
        status_span: 줄 머리 상태 낱말(`status` 묶음) 위치 (시작, 끝). 없으면 None.
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
    body_start: int = 0
    status_span: tuple[int, int] | None = None


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
    status_pattern: SafePattern | None
    status_format: str | None
    field_format: str | None
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
        `CompiledSyntax`. `issues`에는 `sdd.invalid_pattern`(정규식·작업 줄 모양),
        `sdd.duplicate_status_marker`(두 상태가 같은 표시 문자),
        `sdd.status_pattern_ignored`(warning — 줄 머리 상태 정규식에 `status` 묶음이 없거나
        작업 줄 모양이 체크 칸이라 쓰지 않음, `details.reason`)가 들어간다.
        `status_format`·`field_format`은 문법 층이 모두 비우면 패키지 기본 데이터 값이다.
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
    status_pattern = _status_pattern(task.status_pattern if task else None, list_item, t, issues)
    status_format = task.status_format if task else None
    field_format = task.field_format if task else None

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
        status_pattern=status_pattern,
        status_format=status_format
        if status_format is not None
        else package_task_format("status_format"),
        field_format=field_format
        if field_format is not None
        else package_task_format("field_format"),
        empty=syntax.empty or list_item is None,
        issues=issues,
    )


def _status_pattern(
    pattern: str | None, list_item: str | None, timeout: float, issues: list[SpecIssue]
) -> SafePattern | None:
    path = "/task/status_pattern"
    compiled = _compile(pattern, path, (), timeout, issues)
    if compiled is None:
        return None
    reason: str | None = None
    message = ""
    if STATUS_GROUP not in compiled.group_names:
        reason = _IGNORED_NO_GROUP
        message = "줄 머리 상태 정규식에 status 이름의 묶음이 없어 쓰지 않습니다."
    elif list_item == "checkbox":
        reason = _IGNORED_CHECKBOX
        message = (
            "작업 줄 모양이 체크 칸이라 체크 칸으로 상태를 읽고 "
            "줄 머리 상태 정규식은 쓰지 않습니다."
        )
    if reason is None:
        return compiled
    issues.append(
        _issue(
            KnownIssueCodes.SDD_STATUS_PATTERN_IGNORED,
            message,
            severity="warning",
            path=path,
            details={"reason": reason},
        )
    )
    return None


def analyze_head(line: str, syntax: CompiledSyntax, *, require_checkbox: bool = False) -> HeadLine:
    """작업 머리 줄 하나를 나눈다(목록 표시·체크 칸·id·필드·제목). 줄바꿈은 따로 둔다.

    목록 항목 줄이 아니면 `kind`가 None이다. `require_checkbox`면 체크 칸이 없는 줄은 id·필드를
    읽지 않고 바로 돌려준다(`checkbox`가 None). 체크 칸이 없고 문법에 줄 머리 상태 정규식이
    있으면 본문에서 그 정규식을 찾아 `status` 묶음을 `marker`로 삼고, 맞은 범위 전체를 뗀
    나머지에서 id·필드·제목을 읽는다(위치는 늘 원래 줄 기준). 정규식 시간 초과는
    `RegexTimeoutError`로 올린다.
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
    body_start = pos

    # 줄 머리 상태 낱말: 정규식이 맞은 범위를 떼고 나머지(rest)에서 id·필드·제목을 읽는다.
    # rest 위치 i → 줄 위치는 떼어 낸 곳(`cut`, rest 기준) 뒤라면 떼어 낸 길이(`shift`)만큼 민다:
    # 시작 위치는 i >= cut, 끝 위치는 i > cut일 때. 떼어 낸 곳에 걸친(a < cut < b) id·필드는 원래
    # 줄에서 이어진 글자가 아니므로 읽지 않는다. 떼어 낸 곳이 없으면 cut은 rest 길이보다 커서
    # 세 조건이 모두 거짓이다(작업 줄마다 부르므로 함수 대신 식으로 쓴다).
    status_span: tuple[int, int] | None = None
    shift = 0
    rest = text[pos:]
    cut = len(rest) + 1
    if checkbox is None and syntax.status_pattern is not None and rest:
        sm = syntax.status_pattern.search(rest)
        group = sm.span(STATUS_GROUP) if sm is not None else None
        if sm is not None and group is not None and group[1] > group[0]:
            status_span = (pos + group[0], pos + group[1])
            marker = rest[group[0] : group[1]]
            cut, shift = sm.start, sm.end - sm.start
            rest = rest[: sm.start] + rest[sm.end :]

    base = len(rest) - len(rest.lstrip(_SPACE))
    task_id: str | None = None
    id_span: tuple[int, int] | None = None
    if syntax.id_pattern is not None and base < len(rest):
        im = syntax.id_pattern.search(rest[base:])
        if im is not None:
            span = im.span("id")
            if span is not None and span[1] > span[0]:
                a, b = base + span[0], base + span[1]
                if not a < cut < b:
                    task_id = im.group("id")
                    id_span = (
                        pos + a + (shift if a >= cut else 0),
                        pos + b + (shift if b > cut else 0),
                    )
                    base += im.end

    sub = rest[base:]
    fields: list[FieldSpan] = []
    title = sub
    if syntax.field_pattern is not None and sub:
        pieces: list[str] = []
        last = 0
        at = pos + base  # sub 위치 → 줄 위치(떼어 낸 곳 앞)
        sub_cut = cut - base  # sub 기준 떼어 낸 곳
        for fm in syntax.field_pattern.finditer(sub):
            ks = fm.span("key")
            vs = fm.span("value")
            fs, fe = fm.start, fm.end
            if ks is None or vs is None or fs < sub_cut < fe:
                continue
            fields.append(
                FieldSpan(
                    key=sub[ks[0] : ks[1]],
                    value=sub[vs[0] : vs[1]].strip(),
                    start=at + fs + (shift if fs >= sub_cut else 0),
                    end=at + fe + (shift if fe > sub_cut else 0),
                    value_start=at + vs[0] + (shift if vs[0] >= sub_cut else 0),
                    value_end=at + vs[1] + (shift if vs[1] > sub_cut else 0),
                )
            )
            pieces.append(sub[last:fs])
            last = fe
        pieces.append(sub[last:])
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
        body_start=body_start,
        status_span=status_span,
    )
