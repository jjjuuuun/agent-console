"""위키 검색 색인(X48): 프로토콜 `WikiSearchIndex`와 파일 훑기
구현 `ScanSearchIndex`(design §7R, 7R.9).

색인은 **다시 만들 수 있는 캐시**다. 페이지 파일이 진실이고, 색인은
`WikiSearchDocument`(경로·제목·태그·
별칭·본문)를 받아 찾기만 한다. 증분 갱신 키는 `content_hash`(`ParsedPage.content_hash`)다.

검색 의미(모든 구현이 같다 — `testing.WikiSearchContractTests`):

- 질의는 공백으로 낱말을 나눈다(`query_terms`, 따옴표는 뺀다). **모든 낱말**이
  경로·제목·태그·별칭·본문
  중 어디에든 부분 문자열로 들어 있어야 한다(한국어도 부분 일치: "위키는" 안의 "위키").
- 대소문자는 `case_insensitive` 설정을 따른다(위키 문법 `case_insensitive`). 접기는 `str.casefold`.
- `prefix`: 경로가 이 글로 시작하는 페이지만. `tags`: 모든 태그를 가진 페이지만.
- 점수 = (낱말마다) 제목 8 + 경로 4 + 태그·별칭 4, 그리고 맞은 페이지마다 1.
  큰 것이 앞, 같으면 경로 순.
  본문은 점수에 세지 않는다(색인마다 같은 순서가 나오도록 — 본문 빈도는 색인마다 달라진다).
- 조각은 **비밀을 가린 본문**에서 자른다. 비밀 가리기는 색인에 넣기 전에
  한다(`redact`) — 색인에는 원문이
  없다. `marks`는 조각 기준 UTF-16 범위이며 `search_marks` 한 곳에서 계산한다.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from agent_console_contracts.wiki import WikiSearchHit, WikiSearchResult, WikiTextRange

from ._marks import query_terms, search_marks
from ._parse import PageText, ParsedPage, decode_page

__all__ = [
    "DEFAULT_MAX_BODY_CHARS",
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_MAX_TERMS",
    "DEFAULT_SNIPPET_CHARS",
    "Redactor",
    "ScanSearchIndex",
    "SearchLimits",
    "SearchSyncResult",
    "WikiSearchDocument",
    "WikiSearchIndex",
    "default_redactor",
    "search_document",
    "sync_search_index",
]

DEFAULT_MAX_RESULTS = 100
"""한 번에 돌려줄 결과 상한(요청 `limit`이 더 커도 이 값으로 줄인다)."""
DEFAULT_MAX_TERMS = 8
"""질의 낱말 상한(넘는 낱말은 버린다)."""
DEFAULT_MAX_TERM_CHARS = 200
DEFAULT_MAX_BODY_CHARS = 524_288
"""색인에 넣는 본문 글자 상한(넘는 뒷부분은 색인하지 않는다)."""
DEFAULT_SNIPPET_CHARS = 160
"""조각 길이(글자, 줄임표 제외)."""

W_TITLE = 8.0
W_PATH = 4.0
W_META = 4.0
W_BASE = 1.0

Redactor = Callable[[str], str]


def _identity(text: str) -> str:
    return text


def default_redactor() -> Redactor:
    """기본 비밀 가리기(`ac-secret-rules` 기본 규칙의 `redact_suspected`).

    색인 구현의 `redact`를 생략하면 이것을 쓴다(안전한 쪽이 기본).
    끄려면 `lambda text: text`를 준다.
    """
    from agent_console_secret_rules import default_rules

    return default_rules().redact_suspected


@dataclass(frozen=True, slots=True)
class SearchLimits:
    """검색 상한(모두 설정으로 받는다).

    Attributes:
        max_results: 결과 상한.
        max_terms: 질의 낱말 상한.
        max_term_chars: 낱말 하나의 글자 상한(넘으면 앞부분만).
        max_body_chars: 색인할 본문 글자 상한.
        snippet_chars: 조각 길이.
    """

    max_results: int = DEFAULT_MAX_RESULTS
    max_terms: int = DEFAULT_MAX_TERMS
    max_term_chars: int = DEFAULT_MAX_TERM_CHARS
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS
    snippet_chars: int = DEFAULT_SNIPPET_CHARS


@dataclass(frozen=True, slots=True)
class WikiSearchDocument:
    """색인에 넣는 페이지 하나(`search_document`로 만든다).

    Attributes:
        path: 페이지 경로(확장자 없음).
        title: 제목.
        tags: 태그.
        aliases: 별칭.
        text: 머리말 뒤 본문.
        content_hash: 원문 sha256(증분 갱신 키).
    """

    path: str
    title: str = ""
    tags: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    text: str = ""
    content_hash: str = ""


def search_document(parsed: ParsedPage, text: PageText) -> WikiSearchDocument:
    """파싱 결과 + 원문 → 색인 문서(본문 = 머리말 뒤).

    Args:
        parsed: `parse_page` 결과.
        text: 같은 원문(글 또는 바이트).
    """
    body = decode_page(text)[0][parsed.body_start :]
    return WikiSearchDocument(
        path=parsed.path,
        title=parsed.title,
        tags=tuple(parsed.tags),
        aliases=tuple(parsed.aliases),
        text=body,
        content_hash=parsed.content_hash,
    )


@runtime_checkable
class WikiSearchIndex(Protocol):
    """위키 검색 색인. 스레드에서 불러도 안전해야 한다.

    구현은 `id`(백엔드 이름)와 `degraded`(느린 대체 방식인지)를 가진다.
    """

    @property
    def id(self) -> str:
        """백엔드 id(`scan`·`sqlite-fts`…)."""
        ...

    @property
    def degraded(self) -> bool:
        """원하던 방식을 못 써서 느린 대체 방식으로 돌고 있으면 True(`wiki.search_degraded`)."""
        ...

    def hashes(self) -> dict[str, str]:
        """색인된 페이지 경로 → `content_hash`."""
        ...

    def update(self, documents: Iterable[WikiSearchDocument]) -> int:
        """문서를 넣거나 바꾼다. 해시가 같은 문서는 건너뛴다.

        Returns:
            실제로 쓴 문서 수.
        """
        ...

    def remove(self, paths: Iterable[str]) -> int:
        """경로의 문서를 뺀다. Returns: 뺀 문서 수."""
        ...

    def rebuild(self, documents: Iterable[WikiSearchDocument]) -> int:
        """색인을 비우고 `documents`로 다시 만든다. Returns: 넣은 문서 수."""
        ...

    def search(
        self,
        query: str,
        *,
        prefix: str | None = None,
        tags: Sequence[str] = (),
        limit: int = 20,
    ) -> WikiSearchResult:
        """검색. 빈 질의는 빈 결과. `limit`은 `max_results`로 줄인다."""
        ...

    def close(self) -> None:
        """자원을 닫는다(여러 번 불러도 된다)."""
        ...


@dataclass(frozen=True, slots=True)
class SearchSyncResult:
    """`sync_search_index` 결과: 쓴·뺀 문서 수."""

    updated: int
    removed: int


def sync_search_index(
    index: WikiSearchIndex, documents: Iterable[WikiSearchDocument]
) -> SearchSyncResult:
    """색인을 `documents`(위키의 현재 전체)에 맞춘다: 바뀐 것만 쓰고 없어진 것은 뺀다.

    색인 파일을 지웠거나 설정이 바뀌어 비었으면 전부 다시 쓰게 된다.
    """
    docs = list(documents)
    present = {d.path for d in docs}
    gone = [p for p in index.hashes() if p not in present]
    removed = index.remove(gone) if gone else 0
    return SearchSyncResult(updated=index.update(docs), removed=removed)


# ----------------------------------------------------------------------------- 공용 계산


class _Prepared:
    """검색 한 번의 질의 준비(낱말·접기)."""

    __slots__ = ("fold", "terms")

    def __init__(self, query: str, case_insensitive: bool, limits: SearchLimits) -> None:
        self.fold: Callable[[str], str] = str.casefold if case_insensitive else _identity
        raw = [t[: limits.max_term_chars] for t in query_terms(query)]
        seen: list[str] = []
        for term in raw:
            folded = self.fold(term)
            if folded not in seen:
                seen.append(folded)
            if len(seen) >= limits.max_terms:
                break
        self.terms = seen


def clamp_limit(limit: int, limits: SearchLimits) -> int:
    """요청 `limit`을 1 이상 `max_results` 이하로."""
    return max(1, min(int(limit), limits.max_results))


def meta_score(
    terms: Sequence[str], fold: Callable[[str], str], path: str, title: str, meta: str
) -> float:
    """점수(모듈 설명 참고). `meta` = 태그·별칭을 한 글로 이은 것."""
    fpath, ftitle, fmeta = fold(path), fold(title), fold(meta)
    score = W_BASE
    for term in terms:
        if term in ftitle:
            score += W_TITLE
        if term in fpath:
            score += W_PATH
        if term in fmeta:
            score += W_META
    return score


def make_snippet(
    body: str, title: str, query: str, *, case_insensitive: bool, chars: int
) -> tuple[str, list[WikiTextRange]]:
    """조각과 강조 범위. 본문에서 첫 맞은 곳 주변을 자르고, 본문에 없으면 본문 앞부분을 쓴다.

    본문이 없으면 제목을 조각으로 쓴다. 공백 연속은 한 칸으로 줄인다.
    """
    terms = query_terms(query)
    flags = re.IGNORECASE if case_insensitive else 0
    source = body if body.strip() else title
    hit = -1
    if terms and source:
        m = re.search("|".join(re.escape(t) for t in terms), source, flags)
        if m is not None:
            hit = m.start()
    if len(source) <= chars:
        start, end = 0, len(source)
    else:
        start = 0 if hit < 0 else max(0, min(hit - chars // 4, len(source) - chars))
        end = min(len(source), start + chars)
    piece = source[start:end]
    # 자른 경계가 낱말 가운데여도 그대로 둔다(글자 단위 — 한국어는 공백 경계가 맞지 않는다).
    piece = re.sub(r"\s+", " ", piece).strip()
    snippet = ("…" if start > 0 else "") + piece + ("…" if end < len(source) else "")
    return snippet, search_marks(snippet, query, case_insensitive=case_insensitive)


def make_hit(
    *,
    path: str,
    title: str,
    body: str,
    query: str,
    score: float,
    case_insensitive: bool,
    chars: int,
) -> WikiSearchHit:
    """결과 하나(조각·강조 포함)."""
    snippet, marks = make_snippet(
        body, title, query, case_insensitive=case_insensitive, chars=chars
    )
    return WikiSearchHit(path=path, title=title, snippet=snippet, score=score, marks=marks)


def prepared(query: str, case_insensitive: bool, limits: SearchLimits) -> _Prepared:
    """질의 → 낱말·접기."""
    return _Prepared(query, case_insensitive, limits)


def clip_body(text: str, limits: SearchLimits) -> str:
    """본문 글자 상한."""
    return text[: limits.max_body_chars]


# ----------------------------------------------------------------------------- scan 구현


@dataclass(slots=True)
class _Row:
    doc: WikiSearchDocument
    folded_body: str
    folded_tags: frozenset[str] = field(default_factory=frozenset)


class ScanSearchIndex:
    """파일 훑기 색인(X48 `scan`): 문서를 메모리에 두고 훑어 찾는다. 파일을 만들지 않는다.

    느리지만 어디서나 돈다(FTS5가 없는 SQLite의 대체). 프로세스가 끝나면 사라지므로 시작할 때
    `sync_search_index`로 채운다. 스레드 안전(잠금 하나).

    Args:
        case_insensitive: 대소문자 무시(위키 문법 값).
        redact: 본문·제목을 색인에 넣기 전에 비밀을 가리는 함수. 생략하면 `default_redactor()`
            (기본 비밀 규칙). 사용자 규칙을 더했으면 그 `redact_suspected`를 넘긴다.
        limits: 검색 상한.
        degraded: 대체 방식으로 돌고 있음을 알린다(`sqlite-fts`가 못 쓰는 환경에서 대신 쓸 때).
        backend_id: 결과에 적는 백엔드 id.
    """

    def __init__(
        self,
        *,
        case_insensitive: bool = True,
        redact: Redactor | None = None,
        limits: SearchLimits | None = None,
        degraded: bool = False,
        backend_id: str = "scan",
    ) -> None:
        self._ci = case_insensitive
        self._fold: Callable[[str], str] = str.casefold if case_insensitive else _identity
        self._redact = redact or default_redactor()
        self._limits = limits or SearchLimits()
        self._degraded = degraded
        self._id = backend_id
        self._rows: dict[str, _Row] = {}
        self._lock = threading.Lock()

    @property
    def id(self) -> str:
        return self._id

    @property
    def degraded(self) -> bool:
        return self._degraded

    def hashes(self) -> dict[str, str]:
        with self._lock:
            return {p: r.doc.content_hash for p, r in self._rows.items()}

    def _prepare(self, doc: WikiSearchDocument) -> _Row:
        clean = WikiSearchDocument(
            path=doc.path,
            title=self._redact(doc.title),
            tags=doc.tags,
            aliases=doc.aliases,
            text=self._redact(clip_body(doc.text, self._limits)),
            content_hash=doc.content_hash,
        )
        return _Row(
            doc=clean,
            folded_body=self._fold(clean.text),
            folded_tags=frozenset(self._fold(t) for t in doc.tags),
        )

    def update(self, documents: Iterable[WikiSearchDocument]) -> int:
        written = 0
        for doc in documents:
            with self._lock:
                old = self._rows.get(doc.path)
                if (
                    old is not None
                    and old.doc.content_hash == doc.content_hash
                    and doc.content_hash
                ):
                    continue
            row = self._prepare(doc)
            with self._lock:
                self._rows[doc.path] = row
            written += 1
        return written

    def remove(self, paths: Iterable[str]) -> int:
        with self._lock:
            return sum(1 for p in paths if self._rows.pop(p, None) is not None)

    def rebuild(self, documents: Iterable[WikiSearchDocument]) -> int:
        with self._lock:
            self._rows.clear()
        return self.update(documents)

    def search(
        self,
        query: str,
        *,
        prefix: str | None = None,
        tags: Sequence[str] = (),
        limit: int = 20,
    ) -> WikiSearchResult:
        q = prepared(query, self._ci, self._limits)
        if not q.terms:
            return WikiSearchResult(items=[], backend=self._id, degraded=self._degraded)
        want_tags = {self._fold(t) for t in tags}
        with self._lock:
            rows = list(self._rows.values())
        scored: list[tuple[float, str, _Row]] = []
        for row in rows:
            doc = row.doc
            if prefix and not doc.path.startswith(prefix):
                continue
            if want_tags and not want_tags <= row.folded_tags:
                continue
            meta = " ".join((*doc.tags, *doc.aliases))
            fold = self._fold
            haystacks = (fold(doc.path), fold(doc.title), fold(meta), row.folded_body)
            if not all(any(t in h for h in haystacks) for t in q.terms):
                continue
            scored.append((meta_score(q.terms, fold, doc.path, doc.title, meta), doc.path, row))
        scored.sort(key=lambda s: (-s[0], s[1]))
        cap = clamp_limit(limit, self._limits)
        items = [
            make_hit(
                path=row.doc.path,
                title=row.doc.title,
                body=row.doc.text,
                query=query,
                score=score,
                case_insensitive=self._ci,
                chars=self._limits.snippet_chars,
            )
            for score, _path, row in scored[:cap]
        ]
        return WikiSearchResult(
            items=items,
            backend=self._id,
            degraded=self._degraded,
            truncated=len(scored) > cap,
        )

    def close(self) -> None:
        return None
