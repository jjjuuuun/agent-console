"""메모리 안 낱말 역색인 검색 방식(X48 예제).

본문을 낱말로 나눠 `낱말 -> 경로 집합` 표(역색인)를 만든다. 질의 낱말은 색인된 낱말 중 그것을
포함하는 것을 찾아(부분 일치 — 한국어 "위키는" 안의 "위키") 경로 집합을 합치고, 모든 질의 낱말이
맞은 페이지만 남긴다. 제목·경로·태그·별칭은 문서가 작으므로 부분 문자열로 바로 본다. 점수·조각·
강조는 위키 검색 계약(`agent_console_wiki.testing.WikiSearchContractTests`)과 같다.

낱말 나누기 규칙(정규식)은 코드에 두지 않고 옵션 데이터다: 패키지 데이터 `data/defaults.json`의
이름 표(`tokenizers`)를 `tokenizer` 옵션 이름으로 고르거나, `token_pattern` 옵션으로 직접 준다.
모르는 이름이면 기본 규칙을 쓴다(mod-wiki가 자기 기본 방식 이름 `trigram` 같은 값을 그대로 넘기기
때문이다). 기본 규칙(공백 단위)에서는 부분 문자열 검색과 결과가 같다. 다른 규칙은 낱말 경계에 걸친
질의를 놓칠 수 있다.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib.resources import files as package_files
from pathlib import Path
from typing import Any, Final

from agent_console_contracts.wiki import WikiSearchHit, WikiSearchResult
from agent_console_wiki import (
    SearchLimits,
    WikiSearchDocument,
    WikiSearchIndex,
    query_terms,
    search_marks,
)

__all__ = [
    "BACKEND_ID",
    "InvertedSearchIndex",
    "default_options",
    "index_factory",
    "make_index",
]

BACKEND_ID: Final = "example-inverted"
"""검색 방식 id(= entry point 이름 = 사용자 설정 `wiki.search_backend`)."""

_W_TITLE, _W_PATH, _W_META, _W_BASE = 8.0, 4.0, 4.0, 1.0


@cache
def _defaults() -> dict[str, Any]:
    raw = package_files("agent_console_example_wiki_search").joinpath("data/defaults.json")
    return json.loads(raw.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def default_options() -> dict[str, Any]:
    """패키지 기본 옵션 사본(`tokenizer` 이름과 `tokenizers` 이름 표)."""
    return json.loads(json.dumps(_defaults()))  # type: ignore[no-any-return]


def _identity(text: str) -> str:
    return text


def _limits(options: Mapping[str, Any]) -> SearchLimits:
    names = ("max_results", "max_terms", "max_term_chars", "max_body_chars", "snippet_chars")
    return SearchLimits(**{k: int(options[k]) for k in names if options.get(k) is not None})


def _token_pattern(options: Mapping[str, Any]) -> re.Pattern[str]:
    """`token_pattern` 옵션 → 없으면 `tokenizer` 이름 → 모르는 이름이면 기본 이름의 규칙.

    Raises:
        ValueError: `token_pattern`이 정규식이 아니거나 빈 문자열과 맞음(낱말이 안 나뉨).
    """
    data = _defaults()
    table: Mapping[str, str] = {**data["tokenizers"], **(options.get("tokenizers") or {})}
    raw = options.get("token_pattern")
    if raw is None:
        raw = table.get(str(options.get("tokenizer") or ""), table[data["tokenizer"]])
    try:
        pattern = re.compile(str(raw))
    except re.error as exc:
        raise ValueError(f"token_pattern이 정규식이 아닙니다: {exc}") from exc
    if pattern.match(""):
        raise ValueError("token_pattern은 빈 문자열과 맞으면 안 됩니다")
    return pattern


@dataclass(slots=True)
class _Row:
    doc: WikiSearchDocument
    tokens: frozenset[str]


class InvertedSearchIndex:
    """낱말 역색인 `WikiSearchIndex`(스레드 안전 — 잠금 하나, 파일을 만들지 않는다).

    Args:
        case_insensitive: 대소문자 무시(`str.casefold`).
        redact: 색인에 넣기 전에 비밀을 가리는 함수. 생략하면 기본 비밀 규칙.
        limits: 검색 상한.
        token_pattern: 낱말을 뽑는 정규식(`findall`).
        backend_id: 결과에 적는 백엔드 id.
    """

    def __init__(
        self,
        *,
        case_insensitive: bool = True,
        redact: Callable[[str], str] | None = None,
        limits: SearchLimits | None = None,
        token_pattern: re.Pattern[str] | None = None,
        backend_id: str = BACKEND_ID,
    ) -> None:
        if redact is None:
            from agent_console_secret_rules import default_rules

            redact = default_rules().redact_suspected
        self._ci = case_insensitive
        self._fold: Callable[[str], str] = str.casefold if case_insensitive else _identity
        self._redact = redact
        self._limits = limits or SearchLimits()
        self._pattern = token_pattern or re.compile(r"\S+")
        self._id = backend_id
        self._rows: dict[str, _Row] = {}
        self._postings: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    @property
    def id(self) -> str:
        return self._id

    @property
    def degraded(self) -> bool:
        return False

    def hashes(self) -> dict[str, str]:
        with self._lock:
            return {p: r.doc.content_hash for p, r in self._rows.items()}

    def _drop(self, path: str) -> bool:
        row = self._rows.pop(path, None)
        if row is None:
            return False
        for token in row.tokens:
            paths = self._postings.get(token)
            if paths is not None:
                paths.discard(path)
                if not paths:
                    del self._postings[token]
        return True

    def update(self, documents: Iterable[WikiSearchDocument]) -> int:
        written = 0
        for doc in documents:
            with self._lock:
                old = self._rows.get(doc.path)
                if (
                    old is not None
                    and doc.content_hash
                    and old.doc.content_hash == doc.content_hash
                ):
                    continue
            clean = WikiSearchDocument(
                path=doc.path,
                title=self._redact(doc.title),
                tags=doc.tags,
                aliases=doc.aliases,
                text=self._redact(doc.text[: self._limits.max_body_chars]),
                content_hash=doc.content_hash,
            )
            tokens = frozenset(self._pattern.findall(self._fold(clean.text)))
            with self._lock:
                self._drop(doc.path)
                self._rows[doc.path] = _Row(clean, tokens)
                for token in tokens:
                    self._postings.setdefault(token, set()).add(doc.path)
            written += 1
        return written

    def remove(self, paths: Iterable[str]) -> int:
        with self._lock:
            return sum(1 for p in paths if self._drop(p))

    def rebuild(self, documents: Iterable[WikiSearchDocument]) -> int:
        with self._lock:
            self._rows.clear()
            self._postings.clear()
        return self.update(documents)

    def _body_paths(self, term: str) -> set[str]:
        found: set[str] = set()
        for token, paths in self._postings.items():
            if term in token:
                found |= paths
        return found

    def _snippet(self, doc: WikiSearchDocument, query: str) -> WikiSearchHit:
        chars = self._limits.snippet_chars
        source = doc.text if doc.text.strip() else doc.title
        hit = -1
        terms = query_terms(query)
        if terms and source:
            flags = re.IGNORECASE if self._ci else 0
            m = re.search("|".join(re.escape(t) for t in terms), source, flags)
            hit = m.start() if m else -1
        if len(source) <= chars:
            start, end = 0, len(source)
        else:
            start = 0 if hit < 0 else max(0, min(hit - chars // 4, len(source) - chars))
            end = min(len(source), start + chars)
        piece = re.sub(r"\s+", " ", source[start:end]).strip()
        snippet = ("…" if start > 0 else "") + piece + ("…" if end < len(source) else "")
        return WikiSearchHit(
            path=doc.path,
            title=doc.title,
            snippet=snippet,
            score=None,
            # 강조 범위(UTF-16)를 이 색인이 직접 준다: 조각 안 질의 낱말 위치.
            marks=search_marks(snippet, query, case_insensitive=self._ci),
        )

    def search(
        self,
        query: str,
        *,
        prefix: str | None = None,
        tags: Sequence[str] = (),
        limit: int = 20,
    ) -> WikiSearchResult:
        lim = self._limits
        terms: list[str] = []
        for raw in query_terms(query):
            folded = self._fold(raw[: lim.max_term_chars])
            if folded not in terms:
                terms.append(folded)
            if len(terms) >= lim.max_terms:
                break
        empty = WikiSearchResult(items=[], backend=self._id, degraded=False)
        if not terms:
            return empty
        want_tags = {self._fold(t) for t in tags}
        with self._lock:
            body = {t: self._body_paths(t) for t in terms}
            rows = list(self._rows.values())
        scored: list[tuple[float, str, WikiSearchDocument]] = []
        for row in rows:
            doc = row.doc
            if prefix and not doc.path.startswith(prefix):
                continue
            if want_tags and not want_tags <= {self._fold(t) for t in doc.tags}:
                continue
            fpath, ftitle = self._fold(doc.path), self._fold(doc.title)
            fmeta = self._fold(" ".join((*doc.tags, *doc.aliases)))
            score = _W_BASE
            matched = True
            for t in terms:
                in_title, in_path, in_meta = t in ftitle, t in fpath, t in fmeta
                if not (in_title or in_path or in_meta or doc.path in body[t]):
                    matched = False
                    break
                score += _W_TITLE * in_title + _W_PATH * in_path + _W_META * in_meta
            if matched:
                scored.append((score, doc.path, doc))
        scored.sort(key=lambda s: (-s[0], s[1]))
        cap = max(1, min(int(limit), lim.max_results))
        items = []
        for score, _path, doc in scored[:cap]:
            hit = self._snippet(doc, query)
            items.append(hit.model_copy(update={"score": score}))
        return WikiSearchResult(
            items=items, backend=self._id, degraded=False, truncated=len(scored) > cap
        )

    def close(self) -> None:
        return None


def make_index(options: Mapping[str, Any] | None = None) -> WikiSearchIndex:
    """옵션 매핑으로 색인 하나를 만든다(서버 없이 쓸 때).

    Args:
        options: `tokenizer`·`token_pattern`·`case_insensitive`·`redact`와 `SearchLimits` 필드.

    Raises:
        ValueError: `token_pattern`이 틀림.
    """
    opts = options or {}
    return InvertedSearchIndex(
        case_insensitive=bool(opts.get("case_insensitive", True)),
        redact=opts.get("redact"),
        limits=_limits(opts),
        token_pattern=_token_pattern(opts),
    )


def index_factory() -> Callable[[Path | None, Mapping[str, Any]], WikiSearchIndex]:
    """entry point 값: 인자 없는 함수. 색인 공장 `(root, options) -> WikiSearchIndex`를 돌려준다.

    `root`(색인 파일 위치)는 파일을 쓰지 않으므로 쓰지 않는다.
    """

    def factory(root: Path | None, options: Mapping[str, Any]) -> WikiSearchIndex:
        return make_index(options)

    return factory
