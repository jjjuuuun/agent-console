"""링크 색인: 링크 대상 해석·백링크·끊긴 링크·고아·제목 겹침, 그래프 주변(design §7R.1·§7R.18
Q2·Q6).

색인은 저장하지 않는 계산 결과다(원본은 페이지 파일, K7R-2). 해석은 링크 규칙의 `resolve` 순서대로
`path`(위키 폴더 기준 경로)·`title`(제목)·`alias`(별칭)·`relative_path`(링크가 있는 페이지 폴더 기준
상대 경로) 중 처음 맞는 것이다. 비교는 문법 `case_insensitive`를 따른다.

링크 상태 우선순위(Q2): `scheme` > `outside` > `broken` > `ok`. 위키 폴더 밖 상대 링크는 읽지 않고
`outside`로만 표시한다.
"""

from __future__ import annotations

import posixpath
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts.common import LabelDisplayTarget
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import (
    KnownWikiLinkStatuses,
    KnownWikiResolvers,
    WikiAuthor,
    WikiBacklink,
    WikiGraph,
    WikiGraphEdge,
    WikiGraphNode,
    WikiIssue,
    WikiLink,
    WikiPageSummary,
    WikiScheme,
)
from agent_console_text_template import render_template

from ._compiled import CompiledWikiSyntax
from ._errors import WikiPageNotFoundError, WikiPathError
from ._glob import glob_match
from ._parse import ParsedLink, ParsedPage
from ._paths import check_page_path, split_extension

__all__ = ["IndexedLink", "WikiIndex", "build_index", "neighborhood"]


@dataclass(frozen=True, slots=True)
class IndexedLink:
    """해석한 링크 하나(위치는 코드 포인트). 계약 보기는 `WikiIndex.page_links`.

    Attributes:
        link: 원문 링크.
        status: `ok`·`broken`·`outside`·`scheme`.
        resolved: 찾은 페이지 경로(없으면 None).
        resolver: 찾은 방법(`path`·`title`·`alias`·`relative_path`, 못 찾으면 None).
        suggested_path: 끊긴 링크에서 만들 페이지 경로 제안(없으면 None).
        scheme: 링크 스킴이면 그 규칙.
        scheme_value: 스킴 접두 뒤 값.
    """

    link: ParsedLink
    status: str
    resolved: str | None = None
    resolver: str | None = None
    suggested_path: str | None = None
    scheme: WikiScheme | None = None
    scheme_value: str | None = None

    @property
    def broken(self) -> bool:
        return self.status == KnownWikiLinkStatuses.BROKEN

    @property
    def node_key(self) -> str:
        """그래프에서 이 링크가 가리키는 칸의 경로(페이지·끊긴 대상·스킴 대상)."""
        if self.resolved is not None:
            return self.resolved
        return self.suggested_path or self.link.target


@dataclass(slots=True)
class WikiIndex:
    """위키 하나의 링크 색인(`build_index`가 만든다). 페이지 순서 = 경로 순.

    Attributes:
        syntax: 쓴 문법.
        home: 위키의 첫 페이지 경로(없으면 None).
        pages: 페이지 경로 → 파싱 결과.
        links: 페이지 경로 → 해석한 링크(위치 순).
        incoming: 대상 페이지 → {가리키는 페이지 → 링크 수}(자기 자신 제외).
        orphans: 고아 페이지(들어오는 링크 없음, 첫 페이지·`orphan_ignore` 제외).
        duplicate_titles: 같은 제목을 가진 페이지 묶음(각 묶음 경로 순).
        issues: 색인 이슈(문법 이슈, `wiki.home_missing`, 페이지 이슈 전부).
    """

    syntax: CompiledWikiSyntax
    home: str | None
    pages: dict[str, ParsedPage]
    links: dict[str, list[IndexedLink]]
    incoming: dict[str, dict[str, int]]
    orphans: frozenset[str]
    duplicate_titles: list[list[str]]
    issues: list[WikiIssue] = field(default_factory=list)
    _by_path: dict[str, str] = field(default_factory=dict, repr=False)
    _by_title: dict[str, str] = field(default_factory=dict, repr=False)
    _by_alias: dict[str, str] = field(default_factory=dict, repr=False)

    def find(self, target: str) -> str | None:
        """경로 → 제목 → 별칭 순으로 페이지를 찾는다(대소문자 규칙 따름)."""
        key = self.syntax.key
        cand = _path_candidate(target, self.syntax)
        if cand is not None and key(cand) in self._by_path:
            return self._by_path[key(cand)]
        return self._by_title.get(key(target)) or self._by_alias.get(key(target))

    def page(self, path: str) -> ParsedPage:
        """페이지 파싱 결과.

        Raises:
            WikiPageNotFoundError: 없는 페이지.
        """
        found = self.pages.get(path)
        if found is None:
            raise WikiPageNotFoundError(path)
        return found

    def resolve_page(self, page: ParsedPage) -> list[IndexedLink]:
        """색인 밖 페이지 하나(새 본문 미리보기·쓰기 전 판단)의 링크를 이 색인으로 해석한다.

        그 페이지 자신의 경로·제목·별칭도 대상으로 친다(새 페이지의 자기 링크가 끊긴 링크가 되지
        않게).
        """
        key = self.syntax.key
        by_path = dict(self._by_path)
        by_path.setdefault(key(page.path), page.path)
        by_title = dict(self._by_title)
        if page.title:
            by_title.setdefault(key(page.title), page.path)
        by_alias = dict(self._by_alias)
        for alias in page.aliases:
            by_alias.setdefault(key(alias), page.path)
        resolver = _Resolver(self.syntax, by_path, by_title, by_alias)
        return [resolver.resolve(link, page.path) for link in page.links]

    def link_views(self, page: ParsedPage, items: Sequence[IndexedLink]) -> list[WikiLink]:
        """해석한 링크들을 계약 보기(UTF-16 범위)로(`resolve_page` 결과와 함께 쓴다)."""
        return [_to_view(item, page) for item in items]

    def page_links(self, path: str) -> list[WikiLink]:
        """페이지의 링크를 계약 보기(UTF-16 범위)로.

        Raises:
            WikiPageNotFoundError: 없는 페이지.
        """
        page = self.page(path)
        return [_to_view(item, page) for item in self.links.get(path, ())]

    def backlinks(self, path: str) -> list[WikiBacklink]:
        """이 페이지를 가리키는 페이지(경로 순, 자기 자신 제외)."""
        sources = self.incoming.get(path, {})
        return [
            WikiBacklink(path=src, title=self.pages[src].title, count=n)
            for src, n in sorted(sources.items())
        ]

    def broken_links(self) -> list[tuple[str, IndexedLink]]:
        """끊긴 링크 전부(페이지 경로 순 → 위치 순)."""
        return [(p, item) for p, items in self.links.items() for item in items if item.broken]

    def counts(self, path: str) -> tuple[int, int]:
        """(나가는 링크 수 — 스킴 링크 제외, 끊긴 링크 수)."""
        items = self.links.get(path, ())
        out = sum(1 for i in items if i.status != KnownWikiLinkStatuses.SCHEME)
        return out, sum(1 for i in items if i.broken)

    def summary(
        self,
        path: str,
        *,
        updated_at: float | None = None,
        updated_by: WikiAuthor | None = None,
    ) -> WikiPageSummary:
        """페이지 목록 한 줄.

        Args:
            path: 페이지 경로.
            updated_at: 마지막 변경 시각(기록·파일 시각, 호출자가 안다).
            updated_by: 마지막으로 쓴 쪽(기록이 있으면).

        Raises:
            WikiPageNotFoundError: 없는 페이지.
        """
        page = self.page(path)
        links_out, broken = self.counts(path)
        return WikiPageSummary(
            path=path,
            title=page.title,
            tags=list(page.tags),
            aliases=list(page.aliases),
            bytes=page.bytes,
            updated_at=updated_at,
            updated_by=updated_by,
            links_out=links_out,
            backlinks=len(self.incoming.get(path, {})),
            broken_links=broken,
            orphan=path in self.orphans,
            home=path == self.home,
            issues=list(page.issues),
        )

    def facts(self, path: str) -> dict[str, Any]:
        """쓰기·점검 판단 대상의 `page` 부분(`/page/...`, design §7R.1.1).

        Raises:
            WikiPageNotFoundError: 없는 페이지.
        """
        page = self.page(path)
        links_out, broken = self.counts(path)
        return page_facts(page, links_out=links_out, broken_links=broken)


def page_facts(page: ParsedPage, *, links_out: int, broken_links: int) -> dict[str, Any]:
    """판단 대상의 페이지 사실(`path`·`title`·`tags`·`aliases`·`front_matter`·`bytes`·`links_out`·
    `broken_links`). 색인 없이 페이지 하나만 볼 때(새 페이지 미리보기 등) 호출자가 수를 준다."""
    return {
        "path": page.path,
        "title": page.title,
        "tags": list(page.tags),
        "aliases": list(page.aliases),
        "front_matter": dict(page.front_matter),
        "bytes": page.bytes,
        "links_out": links_out,
        "broken_links": broken_links,
    }


def _to_view(item: IndexedLink, page: ParsedPage) -> WikiLink:
    link = item.link
    u16 = page.utf16
    scheme_target = None
    if item.scheme is not None and item.scheme_value:
        # 스킴 대상의 `id_from`은 풀린 id 값이다(계약 `WikiLink.scheme_target` 설명). 접두 뒤가 비면
        # 열 항목이 없어 대상도 없다.
        target = item.scheme.target
        value = item.scheme_value
        query = render_template(target.query, {"value": value}) if target.query else None
        scheme_target = LabelDisplayTarget(role=target.role, id_from=value, query=query)
    return WikiLink(
        start=u16(link.start),
        end=u16(link.end),
        raw=link.raw,
        kind=link.kind,
        rule_id=link.rule_id,
        target=link.target,
        label=link.label,
        anchor=link.anchor,
        resolved=item.resolved,
        broken=item.broken,
        outside=item.status == KnownWikiLinkStatuses.OUTSIDE,
        suggested_path=item.suggested_path,
        status=item.status,
        scheme_target=scheme_target,
    )


def _path_candidate(target: str, syntax: CompiledWikiSyntax) -> str | None:
    value = target[1:] if target.startswith("/") else target
    split = split_extension(value, syntax.page_extensions)
    if split is not None:
        value = split[0]
    try:
        return check_page_path(value)
    except WikiPathError:
        return None


def _relative_candidate(
    target: str, from_page: str, syntax: CompiledWikiSyntax
) -> tuple[str | None, bool]:
    """(위키 폴더 기준 페이지 경로 후보, 폴더 밖인지)."""
    if not target or target.startswith("/"):
        return None, False
    base = posixpath.dirname(from_page)
    joined = posixpath.normpath(posixpath.join(base, target) if base else target)
    if joined == ".." or joined.startswith("../"):
        return None, True
    split = split_extension(joined, syntax.page_extensions)
    value = split[0] if split is not None else joined
    try:
        return check_page_path(value), False
    except WikiPathError:
        return None, False


class _Resolver:
    def __init__(
        self,
        syntax: CompiledWikiSyntax,
        by_path: Mapping[str, str],
        by_title: Mapping[str, str],
        by_alias: Mapping[str, str],
    ) -> None:
        self.syntax = syntax
        self.by_path = by_path
        self.by_title = by_title
        self.by_alias = by_alias
        # 같은 대상 글이 여러 페이지에 되풀이되므로 경로 후보 계산(경로 규칙 검사)을 한 번만 한다.
        self._paths: dict[str, str | None] = {}
        self._relative: dict[tuple[str, str], tuple[str | None, bool]] = {}

    def _path(self, target: str) -> str | None:
        try:
            return self._paths[target]
        except KeyError:
            cand = self._paths[target] = _path_candidate(target, self.syntax)
            return cand

    def _rel(self, target: str, from_page: str) -> tuple[str | None, bool]:
        key = (posixpath.dirname(from_page), target)
        try:
            return self._relative[key]
        except KeyError:
            found = self._relative[key] = _relative_candidate(target, from_page, self.syntax)
            return found

    def resolve(self, link: ParsedLink, from_page: str) -> IndexedLink:
        syntax = self.syntax
        target = link.target
        for scheme in syntax.schemes:
            if target.startswith(scheme.prefix):
                return IndexedLink(
                    link=link,
                    status=KnownWikiLinkStatuses.SCHEME,
                    scheme=scheme,
                    scheme_value=target[len(scheme.prefix) :],
                )
        key = syntax.key
        outside = False
        suggested: str | None = None
        for resolver in link.resolve:
            found: str | None = None
            if resolver == KnownWikiResolvers.PATH:
                cand = self._path(target)
                if cand is not None:
                    found = self.by_path.get(key(cand))
                    suggested = suggested or cand
            elif resolver == KnownWikiResolvers.TITLE:
                found = self.by_title.get(key(target))
            elif resolver == KnownWikiResolvers.ALIAS:
                found = self.by_alias.get(key(target))
            elif resolver == KnownWikiResolvers.RELATIVE_PATH:
                cand, out = self._rel(target, from_page)
                outside = outside or out
                if cand is not None:
                    found = self.by_path.get(key(cand))
                    suggested = suggested or cand
            if found is not None:
                return IndexedLink(
                    link=link, status=KnownWikiLinkStatuses.OK, resolved=found, resolver=resolver
                )
        if outside and suggested is None:
            return IndexedLink(link=link, status=KnownWikiLinkStatuses.OUTSIDE)
        return IndexedLink(link=link, status=KnownWikiLinkStatuses.BROKEN, suggested_path=suggested)


def build_index(
    pages: Iterable[ParsedPage],
    syntax: CompiledWikiSyntax,
    *,
    home: str | None = None,
) -> WikiIndex:
    """파싱한 페이지들로 링크 색인을 만든다(서버 없이 쓰는 순수 함수).

    Args:
        pages: `parse_page` 결과들(같은 경로가 여럿이면 뒤의 것).
        syntax: 파싱에 쓴 컴파일 문법(대소문자·확장자·스킴·고아 제외 경로).
        home: 위키의 첫 페이지(고아 점검에서 뺀다). None·빈 값 = 없음(Q21).

    Returns:
        `WikiIndex`. 제목·별칭이 여러 페이지에 겹치면 경로 순으로 앞 페이지로 해석한다(제목 겹침은
        `duplicate_titles`).
    """
    by_page: dict[str, ParsedPage] = {}
    for page in pages:
        by_page[page.path] = page
    ordered = {p: by_page[p] for p in sorted(by_page)}
    key = syntax.key
    by_path: dict[str, str] = {}
    by_title: dict[str, str] = {}
    by_alias: dict[str, str] = {}
    title_groups: dict[str, list[str]] = {}
    for path, page in ordered.items():
        by_path.setdefault(key(path), path)
        if page.title:
            tkey = key(page.title)
            by_title.setdefault(tkey, path)
            title_groups.setdefault(tkey, []).append(path)
        for alias in page.aliases:
            by_alias.setdefault(key(alias), path)

    resolver = _Resolver(syntax, by_path, by_title, by_alias)
    links: dict[str, list[IndexedLink]] = {}
    incoming: dict[str, dict[str, int]] = {}
    for path, page in ordered.items():
        items = [resolver.resolve(link, path) for link in page.links]
        links[path] = items
        for item in items:
            if item.resolved is not None and item.resolved != path:
                sources = incoming.setdefault(item.resolved, {})
                sources[path] = sources.get(path, 0) + 1

    home_path = home or None
    orphans = frozenset(
        path
        for path in ordered
        if path not in incoming
        and path != home_path
        and not any(
            glob_match(g, path, case_insensitive=syntax.case_insensitive)
            for g in syntax.orphan_ignore
        )
    )
    duplicates = [group for group in title_groups.values() if len(group) > 1]

    issues: list[WikiIssue] = list(syntax.issues)
    if home_path is not None and home_path not in ordered:
        issues.append(
            WikiIssue(
                severity="info",
                code=KnownIssueCodes.WIKI_HOME_MISSING,
                message="위키의 첫 페이지가 없습니다.",
                page=home_path,
            )
        )
    for page in ordered.values():
        issues.extend(page.issues)
    return WikiIndex(
        syntax=syntax,
        home=home_path,
        pages=ordered,
        links=links,
        incoming=incoming,
        orphans=orphans,
        duplicate_titles=duplicates,
        issues=issues,
        _by_path=by_path,
        _by_title=by_title,
        _by_alias=by_alias,
    )


def _node(index: WikiIndex, key: str, depth: int | None, via: IndexedLink | None) -> WikiGraphNode:
    page = index.pages.get(key)
    if page is not None:
        return WikiGraphNode(
            path=key,
            title=page.title,
            orphan=key in index.orphans,
            home=key == index.home,
            depth=depth,
        )
    scheme = via.scheme.prefix if via is not None and via.scheme is not None else None
    return WikiGraphNode(
        path=key,
        title=via.link.label if via is not None else "",
        broken=scheme is None,
        scheme=scheme,
        depth=depth,
    )


def _graph_links(index: WikiIndex, path: str) -> Sequence[IndexedLink]:
    return [
        i
        for i in index.links.get(path, ())
        if i.status != KnownWikiLinkStatuses.OUTSIDE and i.node_key != path
    ]


def neighborhood(
    index: WikiIndex,
    center: str | None = None,
    depth: int = 1,
    limit: int = 500,
) -> WikiGraph:
    """링크 그래프. `center`가 있으면 그 페이지에서 링크 방향을 가리지 않고 `depth` 단계 안의 칸만.

    Args:
        index: 색인.
        center: 가운데 페이지(None = 전체, 노드 `depth`는 null).
        depth: 가운데에서 몇 단계까지(0 = 가운데만).
        limit: 칸 수 상한(넘으면 가까운 것부터 자르고 `truncated`, `total` = 자르기 전 칸 수).

    Returns:
        `WikiGraph`. 칸 = 페이지 + 끊긴 대상 + 스킴 대상(폴더 밖 링크·자기 자신 링크는 뺀다). 같은
        두 칸 사이 링크는 연결 하나로 묶고 `count`를 센다.

    Raises:
        WikiPageNotFoundError: `center`가 없는 페이지.
    """
    limit = max(1, limit)
    order: list[str] = []
    depths: dict[str, int | None] = {}
    via: dict[str, IndexedLink] = {}
    if center is None:
        for path in index.pages:
            order.append(path)
            depths[path] = None
        for path in index.pages:
            for item in _graph_links(index, path):
                k = item.node_key
                if k not in depths:
                    depths[k] = None
                    order.append(k)
                    via[k] = item
    else:
        if center not in index.pages:
            raise WikiPageNotFoundError(center)
        depths[center] = 0
        order.append(center)
        queue: deque[str] = deque([center])
        while queue:
            current = queue.popleft()
            d = depths[current]
            assert d is not None
            if d >= depth or current not in index.pages:
                continue
            neighbors: list[tuple[str, IndexedLink | None]] = [
                (item.node_key, item) for item in _graph_links(index, current)
            ]
            neighbors.extend((src, None) for src in sorted(index.incoming.get(current, {})))
            for k, edge in sorted(neighbors, key=lambda n: n[0]):
                if k in depths:
                    continue
                depths[k] = d + 1
                order.append(k)
                if edge is not None and k not in index.pages:
                    via[k] = edge
                queue.append(k)
    total = len(order)
    kept = order[:limit]
    kept_set = set(kept)
    nodes = [_node(index, k, depths[k], via.get(k)) for k in kept]
    edge_counts: dict[tuple[str, str], int] = {}
    for src in kept:
        if src not in index.pages:
            continue
        for item in _graph_links(index, src):
            dst = item.node_key
            if dst in kept_set:
                edge_counts[(src, dst)] = edge_counts.get((src, dst), 0) + 1
    edges = [
        WikiGraphEdge.model_validate({"from": a, "to": b, "count": n})
        for (a, b), n in sorted(edge_counts.items())
    ]
    return WikiGraph(nodes=nodes, edges=edges, truncated=total > len(kept), total=total)
