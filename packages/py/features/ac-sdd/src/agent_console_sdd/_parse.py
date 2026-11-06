"""스펙 문서 파싱: 마크다운 원문 → `SpecIndex`(작업·필드·역할·범위 의존·요구 id·단계).

블록 구조(목록·제목·코드 블록·인용·줄 범위)는 markdown-it-py가 정하고, 작업 머리 줄 안의 체크 칸·
id·필드는 `analyze_head`가 줄 단위로 읽는다(줄 고치기와 같은 분석). 코드 블록·인용 안의 목록은
작업이 아니다. 작업 목록은 저장하지 않는 보기다(design §6R.1.3 K6R-3).
"""

from __future__ import annotations

import hashlib
import textwrap
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from markdown_it import MarkdownIt

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.sdd import (
    EffectiveSyntax,
    KnownDocumentRoles,
    ParsedDocument,
    ParsedRequirement,
    ParsedStage,
    ParsedTask,
    SpecDefinition,
    SpecDocument,
    SpecIndex,
    SpecIssue,
    SpecTemplate,
    StageRef,
)
from agent_console_safe_regex import RegexTimeoutError

from ._compiled import (
    CompiledSyntax,
    HeadLine,
    analyze_head,
    compile_syntax,
    line_hash,
    split_lines,
)
from ._graphs import dependency_cycles

__all__ = ["SpecFileContent", "find_task", "parse_spec", "task_key"]

type SpecFileContent = str | bytes | None
"""문서 본문 하나: 글(str), 원문 바이트(UTF-8), 없음(None = 파일 없음)."""

_CHECK_EVERY = 64


@cache
def _markdown() -> MarkdownIt:
    # 블록 구조만 필요하다: 인라인 파싱을 끄면 큰 문서에서 몇 배 빠르다(줄 범위 `map`은 그대로).
    md = MarkdownIt("commonmark")
    md.disable(["inline", "text_join"], ignoreInvalid=True)
    return md


def task_key(document_id: str, ordinal: int) -> str:
    """id가 없는 작업의 위치 키 `@<문서 id>:<순번>`(순번은 그 문서 안 1부터)."""
    return f"@{document_id}:{ordinal}"


def find_task(index: SpecIndex, key: str) -> ParsedTask | None:
    """작업 키로 작업을 찾는다(없으면 None)."""
    for task in index.tasks:
        if task.key == key:
            return task
    return None


class _TimeoutError(Exception):
    pass


@dataclass(slots=True)
class _RawTask:
    document: str
    line: int  # 1부터
    head: HeadLine
    line_hash: str
    status: str
    body: str
    stage: StageRef | None
    key: str = ""
    issues: list[SpecIssue] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _DocResult:
    tasks: list[_RawTask] = field(default_factory=list)
    requirements: list[ParsedRequirement] = field(default_factory=list)
    stages: list[ParsedStage] = field(default_factory=list)
    issues: list[SpecIssue] = field(default_factory=list)


def _issue(code: str, message: str, severity: str = "warning", **kw: Any) -> SpecIssue:
    return SpecIssue.model_validate({"severity": severity, "code": code, "message": message, **kw})


def _decode(content: str | bytes) -> tuple[str, str]:
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace"), hashlib.sha256(content).hexdigest()
    return content, hashlib.sha256(content.encode("utf-8")).hexdigest()


class _Clock:
    def __init__(self, clock: Callable[[], float], budget_ms: float | None) -> None:
        self._clock = clock
        self._deadline = None if budget_ms is None else clock() + budget_ms / 1000.0
        self._n = 0

    def check(self, *, force: bool = False) -> None:
        if self._deadline is None:
            return
        self._n += 1
        if (force or self._n % _CHECK_EVERY == 0) and self._clock() > self._deadline:
            raise _TimeoutError


def _parse_document(
    doc: SpecDocument,
    text: str,
    syntax: CompiledSyntax,
    *,
    want_tasks: bool,
    want_requirements: bool,
    clock: _Clock,
    task_room: int | None,
) -> tuple[_DocResult, bool]:
    """문서 하나. 반환 (결과, 작업 상한에 걸렸는가)."""
    out = _DocResult()
    lines = split_lines(text)
    tokens = _markdown().parse(text)
    clock.check(force=True)

    code_lines: set[int] = set()
    quote_depth = 0
    lists: list[str] = []  # 열린 목록 종류(bullet | ordered)
    item_depth = 0
    stage: StageRef | None = None
    stage_ids: set[str] = set()
    ordinal = 0
    hit_limit = False
    want_stages = want_tasks and bool(syntax.stage_levels)

    for i, tok in enumerate(tokens):
        ttype = tok.type
        if ttype == "blockquote_open":
            quote_depth += 1
        elif ttype == "blockquote_close":
            quote_depth -= 1
        elif ttype == "bullet_list_open":
            lists.append("bullet")
        elif ttype == "ordered_list_open":
            lists.append("ordered")
        elif ttype in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
        elif ttype == "list_item_close":
            item_depth -= 1
        elif ttype in ("fence", "code_block", "html_block"):
            if tok.map:
                code_lines.update(range(tok.map[0], tok.map[1]))
        elif ttype == "heading_open" and want_stages and quote_depth == 0 and item_depth == 0:
            level = int(tok.tag[1:]) if tok.tag[1:].isdigit() else 0
            if level in syntax.stage_levels and tok.map:
                inline = tokens[i + 1] if i + 1 < len(tokens) else None
                title = " ".join((inline.content if inline else "").split())
                stage_id = title
                if syntax.stage_pattern is not None:
                    sm = syntax.stage_pattern.search(title)
                    stage_id = (sm.group("id") if sm else None) or title
                if not stage_id:
                    stage_id = f"@{doc.id}:{tok.map[0] + 1}"
                if stage_id in stage_ids:
                    stage_id = f"{stage_id}@{tok.map[0] + 1}"
                stage_ids.add(stage_id)
                stage = StageRef(id=stage_id, title=title)
                out.stages.append(
                    ParsedStage(id=stage_id, title=title, document=doc.id, line=tok.map[0] + 1)
                )
        elif ttype == "list_item_open":
            item_depth += 1
            if not want_tasks or hit_limit or quote_depth or not tok.map or not lists:
                continue
            if syntax.max_depth is not None and item_depth > syntax.max_depth:
                continue
            clock.check()
            kind = lists[-1]
            if syntax.list_item in ("bullet", "ordered") and kind != syntax.list_item:
                continue
            start, end = tok.map
            head = analyze_head(
                lines[start], syntax, require_checkbox=syntax.list_item == "checkbox"
            )
            if head.kind is None:
                continue
            if syntax.list_item == "checkbox" and head.checkbox is None:
                continue
            if task_room is not None and len(out.tasks) >= task_room:
                hit_limit = True
                continue
            ordinal += 1
            issues: list[SpecIssue] = []
            status = syntax.first_status or ""
            if head.marker is not None:
                known = syntax.marker_to_status.get(head.marker)
                if known is None:
                    issues.append(
                        _issue(
                            KnownIssueCodes.SDD_UNKNOWN_STATUS_MARKER,
                            f"체크 칸 글자 '{head.marker}'는 어느 작업 상태에도 없어 첫 상태로 "
                            "봅니다.",
                            document=doc.id,
                            line=start + 1,
                            details={"marker": head.marker},
                        )
                    )
                else:
                    status = known
            body = ""
            if syntax.body and end > start + 1:
                body_lines = [ln.rstrip("\r\n") for ln in lines[start + 1 : end]]
                body = textwrap.dedent("\n".join(body_lines)).strip("\n")
            raw = _RawTask(
                document=doc.id,
                line=start + 1,
                head=head,
                line_hash=line_hash(lines[start]),
                status=status,
                body=body,
                stage=stage,
                issues=issues,
            )
            raw.key = head.id or task_key(doc.id, ordinal)
            out.tasks.append(raw)

    if want_requirements and syntax.requirement_patterns:
        seen: set[str] = set()
        for n, ln in enumerate(lines):
            if n in code_lines:
                continue
            clock.check()
            content = ln.rstrip("\r\n")
            for pattern in syntax.requirement_patterns:
                rm = pattern.search(content)
                if rm is None:
                    continue
                rid = rm.group("id")
                if rid and rid not in seen:
                    seen.add(rid)
                    title = content[rm.end :].strip().lstrip(":—\u2013-").strip()
                    out.requirements.append(
                        ParsedRequirement(id=rid, title=title, document=doc.id, line=n + 1)
                    )
                break
    return out, hit_limit


def _split_values(value: str, syntax: CompiledSyntax) -> list[str]:
    if value.strip() in syntax.none_values:
        return []
    parts = value.split(syntax.list_separator) if syntax.list_separator else [value]
    return [p.strip() for p in parts if p.strip() not in syntax.none_values and p.strip()]


def _lookup(item: str, table: Mapping[str, int]) -> int | None:
    pos = table.get(item)
    if pos is None:
        first = item.split(None, 1)[0] if item.split() else item
        pos = table.get(first)
    return pos


def _expand(
    item: str, order: Sequence[str], table: Mapping[str, int], range_sep: str | None
) -> list[str] | None:
    """값 하나 → 키 목록. 범위면 문서 순서상 그 사이 전부. 못 찾으면 None."""
    pos = _lookup(item, table)
    if pos is not None:
        return [order[pos]]
    if range_sep and range_sep in item:
        a, b = (s.strip() for s in item.split(range_sep, 1))
        pa, pb = _lookup(a, table), _lookup(b, table)
        if pa is not None and pb is not None and pa <= pb:
            return list(order[pa : pb + 1])
    return None


def _task_docs(
    spec: SpecDefinition | SpecTemplate | Sequence[SpecDocument],
) -> Sequence[SpecDocument]:
    if isinstance(spec, SpecDefinition | SpecTemplate):
        return spec.documents
    return spec


def parse_spec(
    spec: SpecDefinition | SpecTemplate | Sequence[SpecDocument],
    files: Mapping[str, SpecFileContent],
    syntax: EffectiveSyntax | CompiledSyntax,
    *,
    max_tasks: int | None = None,
    timeout_ms: float | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> SpecIndex:
    """스펙 문서들을 파싱해 작업·요구·단계 목록을 만든다(서버 없이 쓸 수 있는 순수 함수).

    작업은 `tasks` 역할 문서에서, 요구는 `requirements` 역할 문서에서 읽는다. 역할이 없는 문서는
    `documents`에 있는지·해시만 싣는다.

    Args:
        spec: 스펙(또는 문서 틀) 정의, 아니면 문서 목록.
        files: 문서 `file` → 본문(str 또는 UTF-8 바이트). 키가 없거나 None이면 파일 없음
            (`sdd.document_missing`).
        syntax: 유효 문법(`effective_syntax`) 또는 미리 컴파일한 것(`compile_syntax`).
        max_tasks: 작업 수 상한(스펙 전체). 넘으면 뒤를 읽지 않고 `sdd.too_many_tasks`.
        timeout_ms: 문서 하나 파싱 시간 상한. 넘으면 그 문서의 작업·요구를 버리고
            `sdd.parse_timeout`.
        clock: 시간 상한에 쓰는 시계(초, 테스트 주입용).

    Returns:
        `SpecIndex`. `issues`는 문법 이슈와 문서·작업 이슈 전부이고, 작업 하나에 걸린 이슈는 그
        작업의 `issues`에도 들어간다. 작업 순서 = 문서 순서 → 줄 순서.
    """
    compiled = syntax if isinstance(syntax, CompiledSyntax) else compile_syntax(syntax)
    issues: list[SpecIssue] = list(compiled.issues)
    documents: list[ParsedDocument] = []
    raw_tasks: list[_RawTask] = []
    requirements: list[ParsedRequirement] = []
    stages: list[ParsedStage] = []
    hit_limit = False
    has_task_doc = False
    req_docs_read = False

    for doc in _task_docs(spec):
        roles = set(doc.roles)
        want_tasks = KnownDocumentRoles.TASKS in roles
        want_reqs = KnownDocumentRoles.REQUIREMENTS in roles
        has_task_doc = has_task_doc or want_tasks
        content = files.get(doc.file)
        if content is None:
            documents.append(
                ParsedDocument(id=doc.id, file=doc.file, roles=doc.roles, exists=False)
            )
            issues.append(
                _issue(
                    KnownIssueCodes.SDD_DOCUMENT_MISSING,
                    f"문서 '{doc.title}'의 파일 '{doc.file}'이 없습니다.",
                    document=doc.id,
                    details={"document_id": doc.id, "file": doc.file},
                )
            )
            continue
        text, digest = _decode(content)
        result = _DocResult()
        if want_reqs or (want_tasks and not compiled.empty):
            room = None if max_tasks is None else max(0, max_tasks - len(raw_tasks))
            try:
                result, limited = _parse_document(
                    doc,
                    text,
                    compiled,
                    want_tasks=want_tasks and not compiled.empty,
                    want_requirements=want_reqs,
                    clock=_Clock(clock, timeout_ms),
                    task_room=room,
                )
                hit_limit = hit_limit or limited
            except (_TimeoutError, RegexTimeoutError):
                result = _DocResult()
                issues.append(
                    _issue(
                        KnownIssueCodes.SDD_PARSE_TIMEOUT,
                        f"문서 '{doc.title}'을 읽는 시간이 상한을 넘어 건너뛰었습니다.",
                        document=doc.id,
                        details={"timeout_ms": timeout_ms},
                    )
                )
            req_docs_read = req_docs_read or want_reqs
        raw_tasks.extend(result.tasks)
        requirements.extend(result.requirements)
        stages.extend(result.stages)
        issues.extend(result.issues)
        documents.append(
            ParsedDocument(
                id=doc.id,
                file=doc.file,
                roles=doc.roles,
                exists=True,
                content_hash=digest,
                tasks=len(result.tasks),
                requirements=len(result.requirements),
            )
        )

    if compiled.empty and has_task_doc:
        issues.append(
            _issue(
                KnownIssueCodes.SDD_SYNTAX_MISSING,
                "작업 문법이 없어 작업을 읽지 않았습니다. 규칙에서 작업 문법을 정하세요.",
                severity="info",
            )
        )
    if hit_limit:
        issues.append(
            _issue(
                KnownIssueCodes.SDD_TOO_MANY_TASKS,
                f"작업이 상한({max_tasks}개)을 넘어 뒤의 작업은 읽지 않았습니다.",
                details={"limit": max_tasks},
            )
        )

    tasks = _resolve(raw_tasks, requirements, compiled, check_requirements=req_docs_read)
    _count_stages(stages, tasks, compiled)
    for task in tasks:
        issues.extend(task.issues)
    return SpecIndex(
        documents=documents,
        requirements=requirements,
        stages=stages,
        tasks=tasks,
        issues=issues,
    )


def _resolve(
    raw: list[_RawTask],
    requirements: Sequence[ParsedRequirement],
    syntax: CompiledSyntax,
    *,
    check_requirements: bool,
) -> list[ParsedTask]:
    # 같은 id 둘 이상: 뒤의 것은 위치 키로(K6R-4).
    seen: set[str] = set()
    per_doc: dict[str, int] = {}
    for t in raw:
        per_doc[t.document] = per_doc.get(t.document, 0) + 1
        if t.key in seen:
            pos_key = task_key(t.document, per_doc[t.document])
            t.issues.append(
                _issue(
                    KnownIssueCodes.SDD_DUPLICATE_TASK_ID,
                    f"작업 id '{t.key}'가 이미 있어 이 작업은 위치 키 '{pos_key}'로 봅니다.",
                    document=t.document,
                    line=t.line,
                    task_key=pos_key,
                    details={"id": t.key},
                )
            )
            t.key = pos_key
        seen.add(t.key)

    order = [t.key for t in raw]
    table: dict[str, int] = {}
    for n, t in enumerate(raw):
        table.setdefault(t.key, n)
        if t.head.id is not None:
            table.setdefault(t.head.id, n)
    req_order = [r.id for r in requirements]
    req_table = {rid: n for n, rid in enumerate(req_order)}
    dep_fields = syntax.dependency_fields
    req_fields = syntax.requirement_fields

    for t in raw:
        values = {f.key: f.value for f in reversed(t.head.fields)}
        deps: list[str] = []
        for name in dep_fields:
            if name not in values:
                continue
            for item in _split_values(values[name], syntax):
                keys = _expand(item, order, table, syntax.range_separator)
                if keys is None:
                    is_range = bool(syntax.range_separator and syntax.range_separator in item)
                    code = (
                        KnownIssueCodes.SDD_RANGE_UNRESOLVED
                        if is_range
                        else KnownIssueCodes.SDD_UNKNOWN_DEPENDENCY
                    )
                    t.issues.append(
                        _issue(
                            code,
                            f"의존 '{item}'에 해당하는 작업을 찾지 못했습니다.",
                            document=t.document,
                            line=t.line,
                            task_key=t.key,
                            details={"ref": item},
                        )
                    )
                    continue
                for k in keys:
                    if k not in deps:
                        deps.append(k)
        t.dependencies = deps
        reqs: list[str] = []
        for name in req_fields:
            if name not in values:
                continue
            for item in _split_values(values[name], syntax):
                found = _expand(item, req_order, req_table, syntax.range_separator)
                if found is None:
                    found = [item]
                    if check_requirements:
                        t.issues.append(
                            _issue(
                                KnownIssueCodes.SDD_UNKNOWN_REQUIREMENT,
                                f"요구 '{item}'가 요구 문서에 없습니다.",
                                severity="info",
                                document=t.document,
                                line=t.line,
                                task_key=t.key,
                                details={"ref": item},
                            )
                        )
                for rid in found:
                    if rid not in reqs:
                        reqs.append(rid)
        t.requirements = reqs

    deps_map = {t.key: t.dependencies for t in raw}
    by_key = {t.key: t for t in raw}
    for cycle in dependency_cycles(order, deps_map):
        for k in cycle:
            node = by_key[k]
            node.issues.append(
                _issue(
                    KnownIssueCodes.SDD_DEPENDENCY_CYCLE,
                    "작업 의존이 순환합니다: " + " → ".join([*cycle, cycle[0]]),
                    document=node.document,
                    line=node.line,
                    task_key=k,
                    details={"cycle": cycle},
                )
            )

    done = syntax.done_ids
    status_of = {t.key: t.status for t in raw}
    out: list[ParsedTask] = []
    for t in raw:
        is_done = t.status in done
        ready = not is_done and all(status_of.get(d) in done for d in t.dependencies)
        values = {}
        for f in t.head.fields:
            values.setdefault(f.key, f.value)
        out.append(
            ParsedTask(
                key=t.key,
                id=t.head.id,
                title=t.head.title,
                status=t.status or "unknown",
                fields=values,
                requirements=t.requirements,
                dependencies=t.dependencies,
                stage=t.stage,
                document=t.document,
                line=t.line,
                line_hash=t.line_hash,
                ready=ready,
                body=t.body,
                issues=t.issues,
            )
        )
    return out


def _count_stages(
    stages: Sequence[ParsedStage], tasks: Sequence[ParsedTask], syntax: CompiledSyntax
) -> None:
    by_id = {s.id: s for s in stages}
    for t in tasks:
        if t.stage is None:
            continue
        s = by_id.get(t.stage.id)
        if s is None:
            continue
        s.total += 1
        if t.status in syntax.done_ids:
            s.done += 1
