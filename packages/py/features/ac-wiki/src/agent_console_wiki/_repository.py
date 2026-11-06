"""위키 하나의 저장소 `WikiRepository`(design §7R.1.2·§7R.6·§7R.18 Q1·Q9·Q13·Q19).

원본은 페이지 파일(`WikiPages`)이다. 이 클래스는 그 위에 쓰기 판단(쓰기 규칙·비밀 검사·X50),
기록(X49), 검색 색인 갱신(X48, 선택), 링크 고치기를 묶는다. 서버·공간·실행을 모른다(공간 고르기·WS
알림·설정 읽기는 서버 모듈 몫). 동기 API이고 쓰기는 잠금 하나로 줄을 선다.

- 쓰기 `write`: 경로 규칙 → 크기 한도 → `if_hash`·새 페이지만 → 쓰기 판단 → 앱 밖 변경이 있으면 먼저
  `external` 기록 → 원자적 쓰기 → 기록(`create`·`update`) → 보관 수 정리 → 색인 갱신. 본문이 같으면
  아무 것도 하지 않는다.
- 미리보기 `preview`: 쓰기와 같은 판단, 파일·기록·색인을 건드리지 않는다.
- 옮기기 `move`: 백링크 페이지의 링크 문자열만 고친다. 색인을 만든 뒤 그사이 바뀐 페이지·원문이
  색인과 다른 링크가 있는 페이지는 고치지 않고 `conflicts`에 둔다.
- 되돌리기 `restore`: 그 버전 본문으로 같은 쓰기 판단을 거쳐(없는 경로면 `create`) 새 버전
  `restore`.
- 외부 변경 `scan`: 파일 해시를 마지막 기록과 비교 — 다르면 `external`, 기록이 없거나 마지막이
  지우기·옮겨 감이면 `import`, 파일이 사라졌으면 쓴 주체 `external`의 `delete`. 같은 해시는 다시
  남기지 않는다.
- 기록 저장소가 쓰기 중 실패하면 파일 쓰기는 그대로 두고 결과 이슈 `wiki.history_unavailable`
  (정보)를 더한다(기록 DB를 못 써도 페이지는 쓴다, design §7R.6).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import threading
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_conditions import ConditionOperator
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import (
    KnownWikiAuthorKinds,
    KnownWikiChangeOps,
    KnownWikiVersionOps,
    WikiAuthor,
    WikiChangePage,
    WikiGraph,
    WikiHistoryPage,
    WikiIssue,
    WikiLinkText,
    WikiLintReport,
    WikiMoveResult,
    WikiPageList,
    WikiPagePreview,
    WikiPageSummary,
    WikiPageVersion,
    WikiPageView,
    WikiRewrittenPage,
    WikiScanResult,
    WikiSearchResult,
    WikiTemplateRender,
)

from ._compiled import CompiledWikiSyntax
from ._errors import (
    WikiConflictError,
    WikiHistoryUnavailableError,
    WikiPageExistsError,
    WikiPageNotFoundError,
    WikiPathError,
    WikiRuleRejectedError,
    WikiSecretRejectedError,
    WikiTemplateNotFoundError,
    WikiTooLargeError,
    WikiVersionNotFoundError,
)
from ._history import HistoryEntry, HistorySummary, WikiHistory
from ._index import WikiIndex, build_index, neighborhood, page_facts
from ._linktext import render_link_text
from ._lint import PageTimes, lint
from ._pages import PageFile, ParseCache, WikiPages, read_pages
from ._parse import ParsedPage, decode_page, parse_page
from ._paths import check_page_path, page_path_for_file
from ._rewrite import rewrite_links as _rewrite_links
from ._ruleset import EffectiveWikiRules, default_operator_map
from ._search import WikiSearchIndex, search_document, sync_search_index
from ._subjects import write_subject
from ._template import render_page_template
from ._writecheck import (
    CompiledWriteRules,
    WikiSecretPolicy,
    WikiWriteCheck,
    WriteDecision,
    check_write,
    compile_write_rules,
    run_write_checks,
)

__all__ = ["PageContent", "WikiRepository", "WikiRepositoryLimits", "WriteOutcome"]

_GONE_OPS = frozenset({KnownWikiVersionOps.DELETE, KnownWikiVersionOps.MOVE_OUT})


@dataclass(frozen=True, slots=True)
class WikiRepositoryLimits:
    """위키 한도(서버 모듈은 설치자 옵션으로 채운다).

    Attributes:
        max_page_bytes: 페이지 하나 본문 크기 상한(바이트).
        max_pages: 페이지 수 상한(넘는 새 페이지는 거부, 색인은 경로 순 앞만).
        parse_timeout_ms: 페이지 하나 링크 찾기 시간 상한(None = 없음).
        graph_max_nodes: 그래프 칸 수 상한.
        max_versions_per_page: 페이지당 기록 보관 수(첫 버전은 남김, 사용자 설정
            `wiki.max_versions_per_page`).
    """

    max_page_bytes: int = 512 * 1024
    max_pages: int = 10_000
    parse_timeout_ms: float | None = 2000.0
    graph_max_nodes: int = 500
    max_versions_per_page: int = 50


@dataclass(frozen=True, slots=True)
class PageContent:
    """페이지 하나의 지금 본문.

    Attributes:
        path: 페이지 경로.
        file: 위키 폴더 기준 파일 경로(확장자 포함).
        data: 원문 바이트.
        content_hash: sha256(16진수).
        mtime: 파일 수정 시각.
    """

    path: str
    file: str
    data: bytes
    content_hash: str
    mtime: float | None = None

    @property
    def text(self) -> str:
        return decode_page(self.data)[0]


@dataclass(slots=True)
class WriteOutcome:
    """쓰기·지우기·되돌리기 결과.

    Attributes:
        path: 페이지 경로.
        content_hash: 쓴 뒤 본문 해시(지우기는 지운 본문 해시).
        version: 남긴 버전(기록 저장소가 없거나 실패, 본문이 같아 쓰지 않았으면 None).
        created: 새 페이지를 만들었다. changed: 파일을 실제로 바꿨다(본문이 같으면 거짓).
        issues: 경고(쓰기 규칙 warn·비밀 의심·X50 경고·기록 실패).
    """

    path: str
    content_hash: str
    version: WikiPageVersion | None = None
    created: bool = False
    changed: bool = True
    issues: list[WikiIssue] = field(default_factory=list)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _user() -> WikiAuthor:
    return WikiAuthor(kind=KnownWikiAuthorKinds.USER)


def _external() -> WikiAuthor:
    return WikiAuthor(kind=KnownWikiAuthorKinds.EXTERNAL)


def _history_issue(exc: Exception) -> WikiIssue:
    return WikiIssue(
        severity="info",
        code=KnownIssueCodes.WIKI_HISTORY_UNAVAILABLE,
        message=f"이번 변경은 기록하지 못했습니다({type(exc).__name__}).",
    )


class WikiRepository:
    """위키 하나(페이지 폴더 하나)의 읽기·쓰기·옮기기·기록·점검.

    Args:
        pages: 페이지 파일 접근(위키 폴더).
        wiki_id: 위키 id(기록의 열쇠).
        syntax: 컴파일한 유효 문법.
        rules: 합친 위키 규칙(None = 규칙 없음).
        home: 위키 첫 페이지(고아 점검 제외).
        history: 기록 저장소(X49, None = 기록 없음 — 기록·되돌리기는 `WikiHistoryUnavailableError`).
        search: 검색 색인(X48, None = 갱신 안 함).
        checks: 쓰기 검사 보탬(X50).
        secrets: 비밀 검사(기본 = 계약 `WikiSettings` 기본 방식 + `ac-secret-rules` 기본 규칙).
        limits: 한도. operators: 조건 연산자(기본 `default_operator_map()`).
        clock: 시계(유닉스 초) — 기록 시각·점검·틀 `date`(그 시각의 로컬 날짜).
        parse_cache_entries: 파싱 캐시 크기(0 = 캐시 없음). 서버 모듈은 공간 캐시를 따로 둘 수 있다.
    """

    def __init__(
        self,
        pages: WikiPages,
        *,
        wiki_id: str,
        syntax: CompiledWikiSyntax,
        rules: EffectiveWikiRules | None = None,
        home: str | None = None,
        history: WikiHistory | None = None,
        search: WikiSearchIndex | None = None,
        checks: Sequence[WikiWriteCheck] = (),
        secrets: WikiSecretPolicy | None = None,
        limits: WikiRepositoryLimits | None = None,
        operators: Mapping[str, ConditionOperator] | None = None,
        clock: Callable[[], float] = time.time,
        parse_cache_entries: int = 20_000,
    ) -> None:
        self.pages = pages
        self.wiki_id = wiki_id
        self.syntax = syntax
        self.rules = rules or EffectiveWikiRules()
        self.home = home or None
        self.history = history
        self.search_index = search
        self.checks = tuple(checks)
        self.secrets = secrets or WikiSecretPolicy()
        self.limits = limits or WikiRepositoryLimits()
        self.operators = operators if operators is not None else default_operator_map()
        self.clock = clock
        self._lock = threading.RLock()
        self._cache: ParseCache | None = {} if parse_cache_entries > 0 else None
        self._cache_cap = parse_cache_entries
        self._write_rules: CompiledWriteRules = compile_write_rules(
            self.rules,
            operators=self.operators,
            case_insensitive=syntax.case_insensitive,
        )
        self._list_issues: list[WikiIssue] = []

    # ------------------------------------------------------------ 읽기

    @property
    def issues(self) -> list[WikiIssue]:
        """설정 수준 이슈(문법·규칙 합치기·쓰기 규칙 컴파일)."""
        return [*self.syntax.issues, *self.rules.issues, *self._write_rules.issues]

    def _files(self) -> list[PageFile]:
        return self.pages.list(self.syntax.page_extensions)

    def _find_file(self, path: str) -> str | None:
        for ext in self.syntax.page_extensions:
            file = path + ext
            try:
                if self.pages.stat(file) is not None:
                    return file
            except WikiPathError:
                return None
        return None

    def _new_file(self, path: str) -> str:
        ext = self.syntax.new_page_extension
        if not ext:
            raise WikiPathError(path, "extension")
        return check_page_path(path + ext)

    def current(self, path: str) -> PageContent | None:
        """페이지의 지금 본문(없으면 None).

        Raises:
            WikiPathError: 경로 규칙에 어긋남.
        """
        path = check_page_path(path)
        file = self._find_file(path)
        if file is None:
            return None
        data = self.pages.read(file)
        if data is None:
            return None
        info = self.pages.stat(file)
        return PageContent(path, file, data, _sha(data), info.mtime if info else None)

    def read(self, path: str) -> PageContent:
        """페이지 본문.

        Raises:
            WikiPageNotFoundError: 없음(`has_history` 포함).
        """
        found = self.current(path)
        if found is None:
            raise WikiPageNotFoundError(path, has_history=self.has_history(path))
        return found

    def index(self) -> WikiIndex:
        """지금 파일로 링크 색인을 만든다(파싱 캐시)."""
        cache = self._cache
        if cache is not None and len(cache) > self._cache_cap:
            cache.clear()
        parsed, issues = read_pages(
            self.pages,
            self.syntax,
            max_pages=self.limits.max_pages,
            max_page_bytes=self.limits.max_page_bytes,
            timeout_ms=self.limits.parse_timeout_ms,
            cache=cache,
        )
        self._list_issues = issues
        index = build_index(parsed, self.syntax, home=self.home)
        index.issues.extend(issues)
        return index

    def _summaries(self) -> dict[str, HistorySummary]:
        if self.history is None:
            return {}
        try:
            return self.history.summaries(self.wiki_id)
        except Exception:  # 기록 DB를 못 읽어도 페이지는 보인다
            return {}

    def _times(self, index: WikiIndex) -> dict[str, PageTimes]:
        summaries = self._summaries()
        out: dict[str, PageTimes] = {}
        mtimes: dict[str, float] = {}
        if len(summaries) < len(index.pages):
            for info in self._files():
                page = page_path_for_file(info.file, self.syntax.page_extensions)
                if page is not None:
                    mtimes.setdefault(page, info.mtime)
        for path in index.pages:
            summary = summaries.get(path)
            if summary is not None:
                out[path] = PageTimes(
                    created_at=summary.first_at,
                    updated_at=summary.latest.at,
                    updated_by=summary.latest.author,
                )
            else:
                out[path] = PageTimes(updated_at=mtimes.get(path))
        return out

    def _summary(self, index: WikiIndex, path: str, times: PageTimes | None) -> WikiPageSummary:
        info = times or PageTimes()
        return index.summary(path, updated_at=info.updated_at, updated_by=info.updated_by)

    def list_pages(self, *, prefix: str | None = None, tag: str | None = None) -> WikiPageList:
        """페이지 요약 목록(경로 순). 상한을 넘으면 `truncated`·`total`."""
        index = self.index()
        times = self._times(index)
        key = self.syntax.key
        items = [
            self._summary(index, path, times.get(path))
            for path in index.pages
            if (not prefix or key(path).startswith(key(prefix)))
            and (not tag or key(tag) in {key(t) for t in index.pages[path].tags})
        ]
        total: int | None = None
        truncated = False
        for issue in self._list_issues:
            if issue.code == KnownIssueCodes.WIKI_TOO_MANY_PAGES:
                truncated = True
                total = int(issue.details.get("total") or 0) or None
        return WikiPageList(items=items, truncated=truncated, total=total)

    def view(self, path: str) -> WikiPageView:
        """페이지 하나 보기(본문·링크·백링크). 기록이 있으면 앱 밖 변경을 먼저 기록한다.

        Raises:
            WikiPageNotFoundError: 없음.
        """
        found = self.read(path)
        with self._lock:
            self._sync_external(found)
        index = self.index()
        if found.path not in index.pages:
            # 크기 상한을 넘어 색인에 없는 페이지: 링크 없이 본문만.
            parsed = parse_page(found.path, found.data, self.syntax)
            summary = WikiPageSummary(path=found.path, title=parsed.title, bytes=parsed.bytes)
            return WikiPageView(
                page=summary,
                content=found.text,
                content_hash=found.content_hash,
                front_matter=parsed.front_matter,
                headings=parsed.headings,
                issues=list(parsed.issues),
            )
        page = index.pages[found.path]
        times = self._times(index)
        return WikiPageView(
            page=self._summary(index, found.path, times.get(found.path)),
            content=found.text,
            content_hash=found.content_hash,
            front_matter=page.front_matter,
            headings=page.headings,
            links=index.page_links(found.path),
            backlinks=index.backlinks(found.path),
            issues=list(page.issues),
        )

    def graph(
        self, center: str | None = None, *, depth: int = 1, limit: int | None = None
    ) -> WikiGraph:
        """링크 그래프(칸 수 상한 = `min(limit, graph_max_nodes)`)."""
        cap = self.limits.graph_max_nodes
        return neighborhood(self.index(), center, depth, min(limit or cap, cap))

    def link_text(
        self,
        from_page: str,
        target: str,
        *,
        label: str | None = None,
        rule_id: str | None = None,
    ) -> WikiLinkText:
        """링크 넣기 글. `label` 생략 = 대상 페이지 제목(없으면 `target`)."""
        if not label:
            index = self.index()
            found = index.pages.get(check_page_path(target))
            label = found.title if found is not None and found.title else None
        return render_link_text(
            self.syntax, from_page=from_page, target=target, label=label, rule_id=rule_id
        )

    def render_template(
        self,
        template_id: str,
        *,
        title: str | None = None,
        values: Mapping[str, str] | None = None,
    ) -> WikiTemplateRender:
        """합친 규칙의 페이지 틀 하나를 채운다(쓰지 않음, 날짜 = 시계의 로컬 날짜).

        Raises:
            WikiTemplateNotFoundError: 없는 틀.
        """
        sourced = self.rules.template(template_id)
        if sourced is None:
            raise WikiTemplateNotFoundError(template_id)
        content = self.rules.template_contents.get(template_id) or ""
        today = _dt.datetime.fromtimestamp(self.clock()).date()
        return render_page_template(sourced.item, content, title=title, values=values, today=today)

    def lint(self) -> WikiLintReport:
        """점검(기본 점검 + 점검 규칙 + 쓰기 규칙 다시 보기)."""
        index = self.index()
        times = self._times(index)

        def read(path: str) -> str | None:
            found = self.current(path)
            return found.text if found is not None else None

        return lint(
            index,
            self.rules,
            now=self.clock(),
            times=times,
            read=read,
            operators=self.operators,
            write_rules=self._write_rules,
        )

    def search(
        self,
        query: str,
        *,
        prefix: str | None = None,
        tags: Sequence[str] = (),
        limit: int = 20,
    ) -> WikiSearchResult:
        """검색 색인으로 찾는다. 색인이 없으면 빈 결과(`degraded`)."""
        if self.search_index is None:
            return WikiSearchResult(degraded=True)
        return self.search_index.search(query, prefix=prefix, tags=tags, limit=limit)

    def sync_search(self) -> int:
        """검색 색인을 지금 파일에 맞춘다(바뀐 것만 씀). Returns: 쓴·뺀 문서 수 합."""
        if self.search_index is None:
            return 0
        index = self.index()
        docs = []
        for path in index.pages:
            found = self.current(path)
            if found is not None:
                docs.append(search_document(index.pages[path], found.data))
        result = sync_search_index(self.search_index, docs)
        return result.updated + result.removed

    # ------------------------------------------------------------ 기록

    def _require_history(self) -> WikiHistory:
        if self.history is None:
            raise WikiHistoryUnavailableError()
        return self.history

    def has_history(self, path: str) -> bool:
        """그 경로에 기록이 있다(파일이 없어도)."""
        if self.history is None:
            return False
        try:
            return self.history.latest(self.wiki_id, path) is not None
        except Exception:
            return False

    def page_history(self, path: str, *, limit: int | None = None) -> WikiHistoryPage:
        """페이지 기록(파일이 없어도 기록이 있으면 나온다).

        Raises:
            WikiHistoryUnavailableError: 기록 저장소 없음.
            WikiPageNotFoundError: 기록도 파일도 없음.
        """
        history = self._require_history()
        path = check_page_path(path)
        page = history.list(self.wiki_id, path, limit=limit)
        if not page.items and self.current(path) is None:
            raise WikiPageNotFoundError(path)
        return page

    def version(self, path: str, version: int) -> tuple[WikiPageVersion, bytes]:
        """기록 버전 하나와 그 본문.

        Raises:
            WikiHistoryUnavailableError: 기록 저장소 없음.
            WikiVersionNotFoundError: 없는(지운) 버전이거나 본문이 없음.
        """
        history = self._require_history()
        path = check_page_path(path)
        found = history.get(self.wiki_id, path, version)
        data = history.read(self.wiki_id, path, version) if found is not None else None
        if found is None or data is None:
            raise WikiVersionNotFoundError(path, version)
        return found, data

    def changes(
        self,
        *,
        author_run: str | None = None,
        ops: Collection[str] = (),
        limit: int = 50,
        cursor: str | None = None,
    ) -> WikiChangePage:
        """이 위키의 최근 변경."""
        return self._require_history().changes(
            self.wiki_id, author_run=author_run, ops=ops, limit=limit, cursor=cursor
        )

    def _record(
        self, entries: Sequence[HistoryEntry], issues: list[WikiIssue]
    ) -> list[WikiPageVersion]:
        if self.history is None or not entries:
            return []
        try:
            versions = self.history.record(entries)
            keep = self.limits.max_versions_per_page
            for path in dict.fromkeys(e.path for e in entries):
                self.history.prune(self.wiki_id, path, keep=keep)
        except Exception as exc:  # 기록 DB를 못 써도 페이지 쓰기는 그대로 둔다
            issues.append(_history_issue(exc))
            return []
        return versions

    def _sync_external(
        self, found: PageContent | None, issues: list[WikiIssue] | None = None
    ) -> None:
        """그 페이지 파일이 마지막 기록과 다르면 `external`(기록 없으면 `import`)을 남긴다."""
        if self.history is None or found is None:
            return
        try:
            latest = self.history.latest(self.wiki_id, found.path)
        except Exception:
            return
        if (
            latest is not None
            and latest.op not in _GONE_OPS
            and latest.sha256 == found.content_hash
        ):
            return
        op = (
            KnownWikiVersionOps.IMPORT
            if latest is None or latest.op in _GONE_OPS
            else KnownWikiVersionOps.EXTERNAL
        )
        self._record(
            [
                HistoryEntry.of(
                    self.wiki_id, found.path, op, found.data, author=_external(), at=self.clock()
                )
            ],
            issues if issues is not None else [],
        )

    # ------------------------------------------------------------ 판단

    def _parse(self, path: str, data: bytes) -> ParsedPage:
        return parse_page(path, data, self.syntax, timeout_ms=self.limits.parse_timeout_ms)

    def _facts(
        self, index: WikiIndex, parsed: ParsedPage, *, path: str | None = None
    ) -> dict[str, Any]:
        items = index.resolve_page(parsed)
        links_out = sum(1 for i in items if i.status != "scheme")
        broken = sum(1 for i in items if i.broken)
        facts = page_facts(parsed, links_out=links_out, broken_links=broken)
        if path is not None:
            facts["path"] = path
        return facts

    def _decide(
        self,
        *,
        op: str,
        author: WikiAuthor,
        page: Mapping[str, Any],
        before: Mapping[str, Any] | None,
        content: str,
        from_: str | None = None,
        to: str | None = None,
    ) -> tuple[dict[str, Any], WriteDecision, WriteDecision]:
        """(판단 대상, 규칙·X50 판단, 비밀 판단)."""
        subject = write_subject(op=op, author=author, page=page, before=before, from_=from_, to=to)
        rules = check_write(self._write_rules, subject, content=content)
        rules.extend(run_write_checks(self.checks, subject, content))
        if op == KnownWikiChangeOps.DELETE or op == KnownWikiChangeOps.MOVE:
            secrets = WriteDecision()
        else:
            secrets = self.secrets.check(content, author.kind, page=str(page.get("path") or ""))
        return subject, rules, secrets

    @staticmethod
    def _raise(rules: WriteDecision, secrets: WriteDecision) -> list[WikiIssue]:
        """거부면 예외, 아니면 경고 목록."""
        warnings = [*rules.warnings, *secrets.warnings]
        if rules.rejected:
            raise WikiRuleRejectedError(rules.rejections, warnings=warnings)
        if secrets.rejected:
            lines = [int(n) for n in secrets.rejections[0].details.get("lines") or []]
            raise WikiSecretRejectedError(lines, issues=secrets.rejections)
        return warnings

    def _check_size(self, data: bytes) -> None:
        if len(data) > self.limits.max_page_bytes:
            raise WikiTooLargeError(
                f"페이지는 {self.limits.max_page_bytes}바이트까지입니다.",
                limit="max_page_bytes",
                value=self.limits.max_page_bytes,
            )

    def _check_count(self) -> None:
        if len(self._files()) >= self.limits.max_pages:
            raise WikiTooLargeError(
                f"페이지는 {self.limits.max_pages}개까지입니다.",
                limit="max_pages",
                value=self.limits.max_pages,
            )

    def preview(
        self, path: str, content: str, *, author: WikiAuthor | None = None
    ) -> WikiPagePreview:
        """저장 전 시험: 쓰기와 같은 판단(쓴 주체 기본 사람). 파일·기록·색인·검색을 건드리지 않는다.

        Raises:
            WikiPathError: 경로 규칙.
            WikiTooLargeError: 크기 상한(쓰기와 같은 오류).
        """
        who = author or _user()
        path = check_page_path(path)
        data = content.encode("utf-8")
        self._check_size(data)
        current = self.current(path)
        index = self.index()
        parsed = self._parse(path, data)
        before = self._before(index, current)
        op = KnownWikiChangeOps.UPDATE if current is not None else KnownWikiChangeOps.CREATE
        _, rules, secrets = self._decide(
            op=op,
            author=who,
            page=self._facts(index, parsed),
            before=before,
            content=content,
        )
        items = index.resolve_page(parsed)
        links_out = sum(1 for i in items if i.status != "scheme")
        summary = WikiPageSummary(
            path=path,
            title=parsed.title,
            tags=list(parsed.tags),
            aliases=list(parsed.aliases),
            bytes=parsed.bytes,
            links_out=links_out,
            backlinks=len(index.incoming.get(path, {})),
            broken_links=sum(1 for i in items if i.broken),
            home=path == self.home,
            issues=list(parsed.issues),
        )
        return WikiPagePreview(
            page=summary,
            links=index.link_views(parsed, items),
            headings=parsed.headings,
            issues=[*parsed.issues, *rules.issues, *secrets.issues],
            rule_results=rules.results,
            would_reject=rules.rejected or secrets.rejected,
        )

    def _before(self, index: WikiIndex, current: PageContent | None) -> dict[str, Any] | None:
        if current is None:
            return None
        if current.path in index.pages:
            return index.facts(current.path)
        return self._facts(index, self._parse(current.path, current.data))

    # ------------------------------------------------------------ 쓰기

    def write(
        self,
        path: str,
        content: str,
        *,
        author: WikiAuthor | None = None,
        if_hash: str | None = None,
        create_only: bool = False,
        message: str | None = None,
    ) -> WriteOutcome:
        """페이지를 쓴다(만들기·고치기).

        Args:
            path: 페이지 경로(확장자 없음).
            content: 새 본문(머리말 포함).
            author: 쓴 쪽(기본 사람). `label`은 그대로 기록한다.
            if_hash: 지금 본문 해시와 같을 때만 쓴다(없는 페이지면 충돌).
            create_only: 새 페이지만(있으면 `WikiPageExistsError`).
            message: 기록에 남길 한 줄.

        Raises:
            WikiPathError · WikiTooLargeError · WikiConflictError · WikiPageExistsError ·
            WikiRuleRejectedError · WikiSecretRejectedError.
        """
        data = content.encode("utf-8")
        with self._lock:
            return self._write(
                check_page_path(path),
                data,
                author=author or _user(),
                if_hash=if_hash,
                create_only=create_only,
                message=message,
                record_op=None,
            )

    def import_page(
        self,
        path: str,
        data: bytes,
        *,
        author: WikiAuthor,
        record_op: str | None = None,
        message: str | None = None,
    ) -> WriteOutcome:
        """바이트 본문 그대로 쓴다(zip 가져오기 — 쓰기와 같은 판단, 기록 동작은 `record_op`).

        Raises:
            `write`와 같다.
        """
        with self._lock:
            return self._write(
                check_page_path(path),
                data,
                author=author,
                if_hash=None,
                create_only=False,
                message=message,
                record_op=record_op,
            )

    def _write(
        self,
        path: str,
        data: bytes,
        *,
        author: WikiAuthor,
        if_hash: str | None,
        create_only: bool,
        message: str | None,
        record_op: str | None,
    ) -> WriteOutcome:
        self._check_size(data)
        current = self.current(path)
        if create_only and current is not None:
            raise WikiPageExistsError(path)
        if if_hash is not None and (current is None or current.content_hash != if_hash):
            raise WikiConflictError(
                path, expected=if_hash, actual=current.content_hash if current else None
            )
        if current is None:
            self._check_count()
        index = self.index()
        parsed = self._parse(path, data)
        op = KnownWikiChangeOps.UPDATE if current is not None else KnownWikiChangeOps.CREATE
        _, rules, secrets = self._decide(
            op=op,
            author=author,
            page=self._facts(index, parsed),
            before=self._before(index, current),
            content=decode_page(data)[0],
        )
        issues = self._raise(rules, secrets)
        sha = _sha(data)
        if current is not None and current.content_hash == sha:
            self._sync_external(current, issues)
            latest = self.history.latest(self.wiki_id, path) if self.history else None
            return WriteOutcome(path, sha, latest, created=False, changed=False, issues=issues)
        self._sync_external(current, issues)
        file = current.file if current is not None else self._new_file(path)
        self.pages.write(file, data)
        if self._cache is not None:
            self._cache.pop(file, None)
        recorded = record_op or (
            KnownWikiVersionOps.UPDATE if current is not None else KnownWikiVersionOps.CREATE
        )
        versions = self._record(
            [
                HistoryEntry.of(
                    self.wiki_id,
                    path,
                    recorded,
                    data,
                    author=author,
                    at=self.clock(),
                    message=message,
                )
            ],
            issues,
        )
        self._search_update([(parsed, data)])
        return WriteOutcome(
            path,
            sha,
            versions[0] if versions else None,
            created=current is None,
            changed=True,
            issues=issues,
        )

    def _search_update(
        self, pages: Sequence[tuple[ParsedPage, bytes]], removed: Sequence[str] = ()
    ) -> None:
        if self.search_index is None:
            return
        try:
            if removed:
                self.search_index.remove(removed)
            if pages:
                self.search_index.update(search_document(p, d) for p, d in pages)
        except Exception:  # 색인은 캐시 — 다음 동기화에서 다시 맞춘다
            return

    def delete(
        self,
        path: str,
        *,
        author: WikiAuthor | None = None,
        if_hash: str | None = None,
        message: str | None = None,
    ) -> WriteOutcome:
        """페이지를 지운다(파일 삭제 + 기록 `delete` — 본문은 지우기 직전 것을 가리킨다).

        Raises:
            WikiPageNotFoundError · WikiConflictError · WikiRuleRejectedError.
        """
        who = author or _user()
        with self._lock:
            path = check_page_path(path)
            current = self.read(path)
            if if_hash is not None and current.content_hash != if_hash:
                raise WikiConflictError(path, expected=if_hash, actual=current.content_hash)
            index = self.index()
            before = self._before(index, current)
            assert before is not None
            _, rules, secrets = self._decide(
                op=KnownWikiChangeOps.DELETE, author=who, page=before, before=before, content=""
            )
            issues = self._raise(rules, secrets)
            self._sync_external(current, issues)
            self.pages.delete(current.file)
            if self._cache is not None:
                self._cache.pop(current.file, None)
            versions = self._record(
                [
                    HistoryEntry.of(
                        self.wiki_id,
                        path,
                        KnownWikiVersionOps.DELETE,
                        current.data,
                        author=who,
                        at=self.clock(),
                        message=message,
                    )
                ],
                issues,
            )
            self._search_update([], [path])
            return WriteOutcome(
                path, current.content_hash, versions[0] if versions else None, issues=issues
            )

    def restore(
        self,
        path: str,
        version: int,
        *,
        author: WikiAuthor | None = None,
        message: str | None = None,
    ) -> WriteOutcome:
        """그 버전 본문으로 새 버전(`restore`)을 만든다. 쓰기 규칙을 통과해야 한다(없는 경로면 판단
        `create`).

        Raises:
            WikiHistoryUnavailableError · WikiVersionNotFoundError · WikiRuleRejectedError ·
            WikiSecretRejectedError · WikiTooLargeError.
        """
        _, data = self.version(path, version)
        with self._lock:
            return self._write(
                check_page_path(path),
                data,
                author=author or _user(),
                if_hash=None,
                create_only=False,
                message=message,
                record_op=KnownWikiVersionOps.RESTORE,
            )

    def move(
        self,
        path: str,
        to: str,
        *,
        author: WikiAuthor | None = None,
        rewrite_links: bool = True,
        if_hash: str | None = None,
        dry_run: bool = False,
        message: str | None = None,
    ) -> WikiMoveResult:
        """페이지를 옮긴다(이름 바꾸기). 다른 페이지의 링크 문자열만 고친다(쓰기 규칙은 옮기기
        자체에만 건다 — 링크 고치기는 그 결과다).

        Raises:
            WikiPathError · WikiPageNotFoundError · WikiPageExistsError · WikiConflictError ·
            WikiRuleRejectedError.
        """
        who = author or _user()
        with self._lock:
            old = check_page_path(path)
            new = check_page_path(to)
            if old == new:
                raise WikiPathError(to, "invalid")
            current = self.read(old)
            if if_hash is not None and current.content_hash != if_hash:
                raise WikiConflictError(old, expected=if_hash, actual=current.content_hash)
            existing = self._find_file(new)
            if existing is not None and existing.casefold() != current.file.casefold():
                raise WikiPageExistsError(new)
            index = self.index()
            before = self._before(index, current)
            assert before is not None
            _, rules, secrets = self._decide(
                op=KnownWikiChangeOps.MOVE,
                author=who,
                page={**before, "path": new},
                before=before,
                content=current.text,
                from_=old,
                to=new,
            )
            issues = self._raise(rules, secrets)

            ext = current.file[len(old) :]
            new_file = check_page_path(new + ext)
            conflicts: list[str] = []
            planned: list[tuple[str, PageContent, str, int]] = []
            self_text = current.text
            self_count = 0
            indexed = index.pages.get(old)
            if indexed is not None and indexed.content_hash == current.content_hash:
                result = _rewrite_links(
                    self_text,
                    index.links.get(old, []),
                    page=old,
                    old=old,
                    new=new,
                    syntax=self.syntax,
                )
                if result.skipped:
                    conflicts.append(old)
                else:
                    self_text, self_count = result.text, result.count
            elif indexed is not None:
                conflicts.append(old)
            if rewrite_links:
                for src in sorted(index.incoming.get(old, {})):
                    found = self.current(src)
                    page = index.pages.get(src)
                    if found is None or page is None or found.content_hash != page.content_hash:
                        conflicts.append(src)
                        continue
                    result = _rewrite_links(
                        found.text,
                        index.links.get(src, []),
                        page=src,
                        old=old,
                        new=new,
                        syntax=self.syntax,
                    )
                    if result.skipped:
                        conflicts.append(src)
                    elif result.count:
                        planned.append((src, found, result.text, result.count))
            rewritten = [WikiRewrittenPage(path=p, count=n) for p, _, _, n in planned]
            if self_count:
                rewritten.insert(0, WikiRewrittenPage(path=new, count=self_count))
            if dry_run:
                return WikiMoveResult.model_validate(
                    {
                        "moved": False,
                        "from": old,
                        "to": new,
                        "rewritten": rewritten,
                        "conflicts": conflicts,
                        "issues": issues,
                    }
                )

            self._sync_external(current, issues)
            self.pages.move(current.file, new_file)
            new_data = self_text.encode("utf-8") if self_count else current.data
            if self_count:
                self.pages.write(new_file, new_data)
            if self._cache is not None:
                self._cache.pop(current.file, None)
                self._cache.pop(new_file, None)
            now = self.clock()
            entries = [
                HistoryEntry.of(
                    self.wiki_id,
                    old,
                    KnownWikiVersionOps.MOVE_OUT,
                    current.data,
                    author=who,
                    at=now,
                    message=message,
                    to=new,
                ),
                HistoryEntry.of(
                    self.wiki_id,
                    new,
                    KnownWikiVersionOps.MOVE_IN,
                    new_data,
                    author=who,
                    at=now,
                    message=message,
                    from_=old,
                ),
            ]
            changed: list[tuple[ParsedPage, bytes]] = [(self._parse(new, new_data), new_data)]
            done: list[WikiRewrittenPage] = [r for r in rewritten if r.path == new]
            for src, found, text, count in planned:
                again = self.current(src)
                if again is None or again.content_hash != found.content_hash:
                    conflicts.append(src)
                    continue
                data = text.encode("utf-8")
                self._sync_external(again, issues)
                self.pages.write(found.file, data)
                if self._cache is not None:
                    self._cache.pop(found.file, None)
                entries.append(
                    HistoryEntry.of(
                        self.wiki_id,
                        src,
                        KnownWikiVersionOps.UPDATE,
                        data,
                        author=who,
                        at=now,
                        message=message,
                    )
                )
                changed.append((self._parse(src, data), data))
                done.append(WikiRewrittenPage(path=src, count=count))
            self._record(entries, issues)
            self._search_update(changed, [old])
            return WikiMoveResult.model_validate(
                {
                    "moved": True,
                    "from": old,
                    "to": new,
                    "rewritten": done,
                    "conflicts": conflicts,
                    "issues": issues,
                }
            )

    # ------------------------------------------------------------ 외부 변경

    def scan(self) -> WikiScanResult:
        """앱 밖 변경을 기록한다(모듈 설명). 기록 저장소가 없으면 감지할 기준이 없어
        `recorded=False`."""
        if self.history is None:
            return WikiScanResult(recorded=False)
        with self._lock:
            summaries = self._summaries()
            entries: list[HistoryEntry] = []
            external: list[str] = []
            imported: list[str] = []
            deleted: list[str] = []
            changed: list[tuple[ParsedPage, bytes]] = []
            present: set[str] = set()
            now = self.clock()
            for info in self._files():
                path = page_path_for_file(info.file, self.syntax.page_extensions)
                if path is None or path in present:
                    continue
                present.add(path)
                data = self.pages.read(info.file)
                if data is None:
                    continue
                sha = _sha(data)
                summary = summaries.get(path)
                latest = summary.latest if summary is not None else None
                if latest is not None and latest.op not in _GONE_OPS and latest.sha256 == sha:
                    continue
                if latest is None or latest.op in _GONE_OPS:
                    op = KnownWikiVersionOps.IMPORT
                    imported.append(path)
                else:
                    op = KnownWikiVersionOps.EXTERNAL
                    external.append(path)
                entries.append(
                    HistoryEntry.of(self.wiki_id, path, op, data, author=_external(), at=now)
                )
                if info.size <= self.limits.max_page_bytes:
                    changed.append((self._parse(path, data), data))
            for path, summary in sorted(summaries.items()):
                if path in present or summary.latest.op in _GONE_OPS:
                    continue
                deleted.append(path)
                entries.append(
                    HistoryEntry(
                        wiki=self.wiki_id,
                        path=path,
                        op=KnownWikiVersionOps.DELETE,
                        sha256=summary.latest.sha256,
                        bytes=summary.latest.bytes,
                        author=_external(),
                        at=now,
                    )
                )
            issues: list[WikiIssue] = []
            self._record(entries, issues)
            self._search_update(changed, deleted)
            return WikiScanResult(
                external=external, imported=imported, deleted=deleted, recorded=not issues
            )
