"""JUnit XML 검증 결과 출처(X42 `VerificationSource`).

`collect(ctx)`는 옵션(`ctx.options`)을 검사하고, 그 스펙 공간의 파일 접근(`ctx.spec.files`)으로만
JUnit 파일을 찾아 읽는다. 테스트 케이스 속성(`match_fields`)에서 요구 id·작업 키를 찾아, 요구(또는
작업)마다 결과 하나로 모은다 — 우선순위(`status_priority`)가 가장 높은 결과, 시각은 가장 늦은 것.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts.sdd import SpecIndex, VerificationRef, VerificationResult
from agent_console_safe_regex import RegexTimeoutError, SafePattern
from agent_console_sdd import SddError, SpecFiles, VerificationContext

from ._glob import find_files
from ._junit import JUnitError, TestCase, parse_junit
from ._options import JUnitOptions, parse_options

__all__ = [
    "SOURCE_ID",
    "CollectReport",
    "JUnitVerificationSource",
    "collect_results",
    "find_requirement_ids",
]

SOURCE_ID = "example.junit"
"""기본 출처 id(= entry point 이름 = 사용자 설정 `sdd.verification_sources[].id`)."""


@dataclass
class CollectReport:
    """`collect_results` 결과.

    `skipped` = (경로, 이유) — 읽지 못한 파일, `truncated` = 상한에 걸려 그만 읽음.
    """

    results: list[VerificationResult] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    truncated: bool = False


@dataclass
class _Bucket:
    counts: dict[str, int] = field(default_factory=dict)
    paths: dict[str, str] = field(default_factory=dict)  # 결과 값 → 처음 본 파일
    at: float | None = None

    def add(self, status: str, path: str, at: float | None) -> None:
        self.counts[status] = self.counts.get(status, 0) + 1
        self.paths.setdefault(status, path)
        if at is not None and (self.at is None or at > self.at):
            self.at = at


def _is_word(ch: str) -> bool:
    return ch.isalnum()  # `_`·`-`·공백은 구분자(`test_R1_login`에서 R1을 찾는다)


def _has_token(text: str, token: str) -> bool:
    start = text.find(token)
    while start >= 0:
        end = start + len(token)
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        nxt = text[end + 1] if end + 1 < len(text) else ""
        if not (before and _is_word(before)) and not (
            after and (_is_word(after) or (after == "." and nxt and _is_word(nxt)))
        ):
            return True
        start = text.find(token, start + 1)
    return False


def _pattern_values(pattern: SafePattern, text: str, group: str) -> list[str]:
    out: list[str] = []
    for m in pattern.finditer(text):
        value = m.group(group) if group in pattern.group_names else m.text
        if value:
            out.append(value)
    return out


def find_requirement_ids(
    text: str, *, pattern: SafePattern | None, known: Sequence[str]
) -> list[str]:
    """테스트 이름에서 요구 id(순서대로, 중복 없음).

    `pattern`이 있으면 그 매치(이름 그룹 `id` 또는 매치 전체), 없으면 `known` 중 단어로 든 것
    (`R1`은 `R10`·`R1.2`·`XR1` 안에서 찾지 않고, `_`·`-`·공백은 구분자다).

    Raises:
        RegexTimeoutError: 정규식 매치가 시간 제한을 넘음.
    """
    found = (
        _pattern_values(pattern, text, "id")
        if pattern is not None
        else [rid for rid in known if _has_token(text, rid)]
    )
    return list(dict.fromkeys(found))


def _subject(case: TestCase, fields: Iterable[str]) -> str:
    return " ".join(case.attributes.get(f, "") for f in fields).strip()


def _rank(priority: Sequence[str]) -> Mapping[str, int]:
    return {status: i for i, status in enumerate(priority)}


def _result(
    source: str,
    bucket: _Bucket,
    opts: JUnitOptions,
    *,
    requirement_ids: list[str],
    task_key: str | None,
) -> VerificationResult:
    rank = _rank(opts.status_priority)
    worst = min(bucket.counts, key=lambda s: (rank.get(s, len(rank)), s))
    total = sum(bucket.counts.values())
    detail = ", ".join(f"{s} {n}" for s, n in sorted(bucket.counts.items(), key=lambda kv: kv[0]))
    label = f"{opts.label} ({total})" if opts.label else str(total)
    return VerificationResult(
        source=source,
        status=worst,
        task_key=task_key,
        requirement_ids=requirement_ids,
        label=label,
        at=bucket.at,
        ref=VerificationRef(path=bucket.paths[worst]),
        detail=detail,
    )


def collect_results(
    files: SpecFiles,
    index: SpecIndex,
    options: Mapping[str, Any] | JUnitOptions | None = None,
    *,
    source_id: str = SOURCE_ID,
) -> CollectReport:
    """JUnit 파일을 찾아 요구·작업별 검증 결과로 모은다(서버 없이 쓰는 핵심 함수).

    Args:
        files: 프로젝트 폴더 파일 접근(폴더 안만).
        index: 스펙 파싱 결과(요구 id·작업 키를 여기서 안다).
        options: 출처 옵션(매핑이면 기본값 위에 덮어 검사).
        source_id: 결과의 `source`.

    Raises:
        JUnitOptionsError: 옵션이 틀림(폴더 밖 파일 패턴·쓸 수 없는 정규식 포함).
    """
    opts = options if isinstance(options, JUnitOptions) else parse_options(options)
    report = CollectReport()
    if not opts.paths:
        return report
    found = find_files(files, opts.paths, max_files=opts.max_files, max_dirs=opts.max_dirs)
    report.files, report.truncated = found.paths, found.truncated
    known = [r.id for r in index.requirements]
    task_keys: Collection[str] = {t.key for t in index.tasks}
    req_pattern, task_pattern = opts.requirement_regex(), opts.task_regex()
    by_req: dict[str, _Bucket] = {}
    by_task: dict[str, _Bucket] = {}
    remaining = opts.max_testcases
    for path in found.paths:
        if remaining <= 0:
            report.truncated = True
            break
        try:
            data = files.read(path)
        except (OSError, SddError):
            report.skipped.append((path, "unreadable"))
            continue
        if data is None:
            report.skipped.append((path, "not_file"))
            continue
        if len(data) > opts.max_file_bytes:
            report.skipped.append((path, "too_large"))
            continue
        try:
            cases = parse_junit(data, limit=remaining)
        except JUnitError:
            report.skipped.append((path, "invalid_junit"))
            continue
        remaining -= len(cases)
        for case in cases:
            status = opts.result_map.get(case.outcome, case.outcome)
            subject = _subject(case, opts.match_fields)
            try:
                reqs = find_requirement_ids(subject, pattern=req_pattern, known=known)
                tasks = (
                    [k for k in _pattern_values(task_pattern, subject, "task") if k in task_keys]
                    if task_pattern is not None
                    else []
                )
            except RegexTimeoutError:
                report.skipped.append((path, "regex_timeout"))
                continue
            for rid in reqs:
                by_req.setdefault(rid, _Bucket()).add(status, path, case.at)
            for key in dict.fromkeys(tasks):
                by_task.setdefault(key, _Bucket()).add(status, path, case.at)
    for rid, bucket in by_req.items():
        report.results.append(
            _result(source_id, bucket, opts, requirement_ids=[rid], task_key=None)
        )
    for key, bucket in by_task.items():
        report.results.append(_result(source_id, bucket, opts, requirement_ids=[], task_key=key))
    return report


class JUnitVerificationSource:
    """JUnit XML 검증 결과 출처(X42). 인자 없이 만들 수 있다(entry point 로더가 그렇게 부른다).

    Args:
        source_id: 출처 id(기본 `example.junit`). 같은 클래스를 다른 id로 여러 번 등록할 수 있다.
    """

    def __init__(self, source_id: str = SOURCE_ID) -> None:
        self._id = source_id

    @property
    def id(self) -> str:
        return self._id

    async def collect(self, ctx: VerificationContext) -> list[VerificationResult]:
        """그 스펙의 JUnit 결과. 파일 접근이 없는 공간이면 빈 목록.

        Raises:
            JUnitOptionsError: 옵션이 틀림(호출하는 mod-sdd는 이 출처만 건너뛴다).
        """
        opts = parse_options(ctx.options)
        files = ctx.spec.files
        if files is None:
            return []
        return collect_results(files, ctx.spec.index, opts, source_id=self._id).results
