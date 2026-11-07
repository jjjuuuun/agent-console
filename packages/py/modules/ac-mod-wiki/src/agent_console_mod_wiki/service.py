"""위키 서비스: 공간 고르기·사용자 설정·저장소 조립·캐시·요약·규칙·변경 알림(``wiki.service``).

``ac-wiki``의 순수 함수·저장소 위에 서버 몫만 더한다(design §7R.3 ``mod-wiki``, 조립 순서
``[7R.8 구현]``):

1. 정의 종류 ``definition_kinds(...)``(설치자 이름·폴더).
2. 위키 정의의 규칙 → ``load_wiki_rules`` → ``merge_rules``.
3. ``effective_syntax(settings, rules=merged.syntax_layers)`` → ``compile_syntax``.
4. 공간·위키마다 ``WikiRepository``를 캐시한다. 위키 정의·규칙 버전·사용자 설정·쓰기 검사·기록
   저장소가 바뀌면 다시 만든다(검색 색인 객체는 옵션이 같으면 이어 쓴다).

- 공간: 요청의 공간 이름(``?project=``) → ``WikiScope``. 이름이 없으면 단독 루트
  (``standalone_root``).
  이름이 왔는데 ``wiki.spaces``가 없으면 409 ``wiki.spaces_unavailable``.
- 규칙 저장소: 프로젝트 공간은 그 공간 저장소, 단독 공간은 라이브러리(``definitions.store``에 규칙
  종류가 있을 때) → 없으면 단독 루트.
- 기록: 단독 = 호스트 DB(없으면 메모리), 프로젝트 = ``records.spaces``의 기록 DB(없으면 기록 없음).
- 검색 색인: 사용자 ``search_backend`` → 설치자 ``search.backend`` → 설치자 ``search.fallback``.
  파일 위치는 공간의 ``index_dir``(프로젝트) 또는 호스트 상태 폴더(단독), 없으면 메모리.
- 요약(``WikiSummary``)은 무거운 점검을 포함하므로 (저장소, 페이지 파일 크기·시각) 키로 캐시한다.

실행·프로젝트를 모른다. 공간 이름은 불투명 문자열이다.
"""

from __future__ import annotations

import contextlib
import json
import posixpath
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Callable, Collection, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_console_conditions import ConditionOperator
from agent_console_contracts import ErrorCodes, Issue, SpaceRef
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import (
    KnownWikiAuthorKinds,
    WikiAuthor,
    WikiCapabilities,
    WikiChanged,
    WikiChangePage,
    WikiCreateRequest,
    WikiDefinition,
    WikiInfo,
    WikiIssue,
    WikiLimits,
    WikiRef,
    WikiRuleCounts,
    WikiRulesDefinition,
    WikiRulesListItem,
    WikiRulesView,
    WikiScanResult,
    WikiSettings,
    WikiSummary,
    WikiView,
)
from agent_console_registry import Registry
from agent_console_secret_rules import SecretRules, default_rules
from agent_console_store import DefinitionKind, DefinitionStore, NotFound, StoredDefinition
from agent_console_wiki import (
    LocalWikiPages,
    SearchIndexFactory,
    SecretScan,
    WikiHistory,
    WikiHistoryUnavailableError,
    WikiRepository,
    WikiSearchIndex,
    WikiSecretPolicy,
    WikiToolTarget,
    WikiWriteCheck,
    check_rules,
    compile_syntax,
    default_operator_map,
    effective_syntax,
    load_wiki_rules,
    merge_rules,
)

from .config import parse_wiki_settings, section_of, settings_issue
from .errors import SpaceError, WikiNotFound, WikiRequestError
from .history import RecordsWikiHistory, close_history
from .plugins import WriteCheckFactory, make_write_check
from .ports import INTEGRATION_RUNS, WikiIntegration, WikiSpace, WikiSpaces
from .settings import WikiModuleSettings, package_defaults

_USER = WikiAuthor(kind=KnownWikiAuthorKinds.USER)


def user_author() -> WikiAuthor:
    """REST·화면 쓰기의 쓴 주체(사람). 1인 로컬이라 ``label``은 비운다(§7R.18 Q13)."""
    return _USER.model_copy()


_BAD_ID = re.compile(r"[^A-Za-z0-9_-]+")
_MAX_ID = 120


def unique_id(name: str, taken: Collection[str], *, fallback: str) -> str:
    """이름에서 정의 id(``[A-Za-z0-9][A-Za-z0-9_-]*``)를 만든다. 남는 글자가 없으면 ``fallback``,
    겹치면 ``-2``·``-3``…(대소문자 무시).

    >>> unique_id("Project Notes", ["project-notes"], fallback="wiki")
    'project-notes-2'
    >>> unique_id("프로젝트 노트", [], fallback="wiki")
    'wiki'
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = _BAD_ID.sub("-", ascii_name).strip("-_").lower()[:_MAX_ID].strip("-_") or fallback
    folded = {t.casefold() for t in taken}
    if base.casefold() not in folded:
        return base
    n = 2
    while f"{base}-{n}".casefold() in folded:
        n += 1
    return f"{base}-{n}"


@dataclass(frozen=True)
class WikiScope:
    """요청 하나가 쓰는 공간.

    Attributes:
        name: 공간 이름(단독 루트면 None).
        store: 위키 정의 저장소.
        rules_store: 위키 규칙 저장소(단독 공간은 라이브러리일 수 있다).
        own_rules: 규칙 저장소가 이 공간 것인가(참이면 규칙의 ``used_by``를 채운다).
        pages_root: 페이지 폴더의 부모(절대 경로, 위키 하나 = ``<pages_root>/<id>``).
        pages_dir: ``pages_root``의 표시용 상대 경로(프로젝트 폴더 또는 단독 루트 기준).
        agent_pages_root: 에이전트에게 알릴 페이지 폴더 부모(프로젝트 = 상대, 단독 = 절대 경로).
        writable: 쓸 수 있나.
        history: 기록 저장소(없으면 None).
        index_dir: 검색 색인 파일 폴더(없으면 메모리).
        key: 캐시 키(단독 = 빈 문자열).
    """

    name: str | None
    store: DefinitionStore
    rules_store: DefinitionStore
    own_rules: bool
    pages_root: Path
    pages_dir: str
    agent_pages_root: str
    writable: bool
    history: WikiHistory | None
    index_dir: Path | None
    key: str


@dataclass
class WikiPorts:
    """서비스가 부를 때마다 읽는 바깥 의존(포트 등). 모두 선택이다."""

    spaces: Callable[[], WikiSpaces | None] = lambda: None
    records: Callable[[], Any] = lambda: None
    library: Callable[[], DefinitionStore | None] = lambda: None
    write_checks: Callable[[], Sequence[WikiWriteCheck]] = lambda: ()
    integrations: Callable[[], Sequence[WikiIntegration]] = lambda: ()
    workspace_settings: Callable[[], Any] = lambda: None
    secret_rules: Callable[[], SecretRules | None] = lambda: None
    operators: Callable[[], Mapping[str, ConditionOperator]] | None = None
    publish: Callable[[WikiChanged], None] = lambda _payload: None


class LiveSecretScanner:
    """부를 때마다 지금 비밀 의심 규칙(포트 → 없으면 기본)으로 판정하는 ``WikiSecretScanner``."""

    def __init__(self, rules: Callable[[], SecretRules]) -> None:
        self._rules = rules

    def scan(self, text: str) -> SecretScan:
        rules = self._rules()
        if not text or not rules.value_suspected(text):
            return SecretScan(False)
        lines = tuple(
            n for n, line in enumerate(text.splitlines(), 1) if rules.value_suspected(line)
        )
        return SecretScan(True, lines)

    def redact(self, text: str) -> str:
        return self._rules().redact_suspected(text)


@dataclass
class _SearchSlot:
    options: Hashable
    index: WikiSearchIndex | None


@dataclass
class _Probe:
    degraded: bool
    available: bool


@dataclass
class WikiServiceState:
    """서비스가 들고 있는 캐시(테스트에서 들여다본다)."""

    repos: dict[tuple[str, str], tuple[Hashable, WikiRepository]] = field(default_factory=dict)
    indexes: dict[tuple[str, str], _SearchSlot] = field(default_factory=dict)
    summaries: OrderedDict[tuple[str, str], tuple[Hashable, WikiSummary]] = field(
        default_factory=OrderedDict
    )
    records: dict[str, RecordsWikiHistory] = field(default_factory=dict)
    plugin_checks: dict[tuple[str, str], WikiWriteCheck] = field(default_factory=dict)
    probes: dict[Hashable, _Probe] = field(default_factory=dict)
    check_problems: list[Issue] = field(default_factory=list)


class WikiService:
    """위키 서비스(포트 ``wiki.service`` 구현).

    Args:
        options: 설치자 설정.
        standalone: 단독 루트 정의 저장소(위키·규칙 종류 등록).
        kinds: (위키 종류, 위키 규칙 종류).
        standalone_pages: 단독 공간 페이지 폴더의 부모(절대 경로).
        standalone_index: 단독 공간 검색 색인 폴더(None = 메모리).
        host_history: 단독 공간 기록 저장소(None = 기록 없음).
        search: 검색 색인 공장 레지스트리(X48).
        write_check_plugins: 쓰기 검사 공장 레지스트리(X50 플러그인).
        ports: 바깥 의존.
        clock: 시계(유닉스 초).
    """

    def __init__(
        self,
        options: WikiModuleSettings,
        *,
        standalone: DefinitionStore,
        kinds: tuple[DefinitionKind, DefinitionKind],
        standalone_pages: Path,
        standalone_index: Path | None = None,
        host_history: WikiHistory | None = None,
        search: Registry[SearchIndexFactory] | None = None,
        write_check_plugins: Registry[WriteCheckFactory] | None = None,
        ports: WikiPorts | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.options = options
        self.standalone = standalone
        self.wiki_kind, self.rules_kind = kinds
        self.standalone_pages = standalone_pages
        self.standalone_index = standalone_index
        self.host_history = host_history
        self.search_factories = search
        self.write_check_plugins = write_check_plugins
        self.ports = ports or WikiPorts()
        self.clock = clock
        self.state = WikiServiceState()
        self._lock = threading.RLock()
        self._index_suffix = str(package_defaults()["index_suffix"])

    # ------------------------------------------------------------ 설정·규칙

    def settings_and_issues(self) -> tuple[WikiSettings, list[Issue]]:
        """지금 사용자 설정 ``wiki``(깨진 부분은 뺀 값)와 형식 문제."""
        try:
            raw = section_of(self.ports.workspace_settings())
        except Exception:  # 설정을 못 읽어도 위키 화면은 동작한다
            raw = None
        return parse_wiki_settings(raw)

    def settings(self) -> WikiSettings:
        return self.settings_and_issues()[0]

    def warnings(self) -> list[Issue]:
        """``server.warnings``: 사용자 설정 형식 문제 + 켰는데 설치되지 않은 쓰기 검사."""
        settings, issues = self.settings_and_issues()
        self.write_checks(settings)
        with self._lock:
            return [*issues, *self.state.check_problems]

    def secret_rules(self) -> SecretRules:
        """비밀 의심 규칙(포트 → 없으면 기본)."""
        try:
            found = self.ports.secret_rules()
        except Exception:
            found = None
        return found if isinstance(found, SecretRules) else default_rules()

    def secret_policy(self, settings: WikiSettings) -> WikiSecretPolicy:
        """쓴 주체 종류별 비밀 검사(설정 ``secret_scan`` + 지금 비밀 의심 규칙)."""
        return WikiSecretPolicy(
            modes=dict(settings.secret_scan), scanner=LiveSecretScanner(self.secret_rules)
        )

    def operators(self) -> Mapping[str, ConditionOperator]:
        if self.ports.operators is not None:
            return self.ports.operators()
        return default_operator_map()

    def integrations(self) -> list[WikiIntegration]:
        try:
            return list(self.ports.integrations())
        except Exception:
            return []

    def write_checks(self, settings: WikiSettings) -> list[WikiWriteCheck]:
        """쓸 쓰기 검사(X50): 포트 검사(설정에서 끈 것 제외) + 설정에서 켠 플러그인 검사."""
        configured = {s.id: s for s in settings.write_checks}
        out: list[WikiWriteCheck] = []
        seen: set[str] = set()
        problems: list[Issue] = []
        try:
            ported = list(self.ports.write_checks())
        except Exception:
            ported = []
        for check in ported:
            check_id = str(getattr(check, "id", ""))
            setting = configured.get(check_id)
            if check_id in seen or (setting is not None and not setting.enabled):
                continue
            seen.add(check_id)
            out.append(check)
        registry = self.write_check_plugins
        for index, setting in enumerate(settings.write_checks):
            if not setting.enabled or setting.id in seen:
                continue
            where = f"/wiki/write_checks/{index}"
            if registry is None or setting.id not in registry:
                problems.append(
                    settings_issue(where, f"설치되지 않은 쓰기 검사 {setting.id!r}를 켰습니다")
                )
                continue
            key = (setting.id, json.dumps(setting.options, sort_keys=True, default=str))
            with self._lock:
                made = self.state.plugin_checks.get(key)
            if made is None:
                try:
                    made = make_write_check(registry.get(setting.id), setting.options)
                except Exception:
                    problems.append(
                        settings_issue(where, f"쓰기 검사 {setting.id!r}를 만들지 못했습니다")
                    )
                    continue
                with self._lock:
                    self.state.plugin_checks[key] = made
            seen.add(setting.id)
            out.append(made)
        with self._lock:
            self.state.check_problems = problems
        return out

    def library(self) -> DefinitionStore | None:
        """앱 라이브러리 저장소(위키 규칙 종류가 있을 때만)."""
        try:
            store = self.ports.library()
        except Exception:
            return None
        if store is None or self.rules_kind.name not in store.kinds():
            return None
        return store

    # ------------------------------------------------------------ 공간

    def _ensure_kinds(self, store: DefinitionStore) -> None:
        known = set(store.kinds())
        register = getattr(store, "register_kind", None)
        for kind in (self.wiki_kind, self.rules_kind):
            if kind.name not in known and callable(register):
                register(kind)

    def _records_history(self, space: str) -> WikiHistory | None:
        try:
            port = self.ports.records()
        except Exception:
            port = None
        if port is None:
            return None
        name = self.options.records_space_prefix + space
        with self._lock:
            found = self.state.records.get(name)
            if found is None:
                found = RecordsWikiHistory(self.ports.records, name)
                self.state.records[name] = found
            return found

    def scope(self, space: str | None) -> WikiScope:
        """공간 이름 → 공간(None·빈 값 = 단독 루트).

        Raises:
            SpaceError: 제공자가 없다(``wiki.spaces_unavailable``)·모르는 공간
                (``project.not_found``)·열 수 없다(제공자 예외의 ``code``).
        """
        if not space:
            return self._standalone_scope()
        provider = self.ports.spaces()
        if provider is None:
            raise SpaceError(
                ErrorCodes.WIKI_SPACES_UNAVAILABLE,
                space,
                "프로젝트 연동이 꺼져 있어 이 프로젝트의 위키를 열 수 없습니다.",
            )
        try:
            opened: WikiSpace = provider.open(space)
        except LookupError:
            raise SpaceError(
                ErrorCodes.PROJECT_NOT_FOUND, space, "프로젝트를 찾을 수 없습니다."
            ) from None
        except Exception as exc:
            code = getattr(exc, "code", None)
            raise SpaceError(
                str(code) if isinstance(code, str) and code else ErrorCodes.INTERNAL,
                space,
                "프로젝트 공간을 열 수 없습니다.",
            ) from exc
        self._ensure_kinds(opened.store)
        config_dir = str(getattr(opened, "config_dir", "") or "").strip("/")
        given = str(getattr(opened, "pages_dir", "") or "").strip("/")
        pages_dir = given or (
            posixpath.join(config_dir, self.options.pages_dir)
            if config_dir
            else self.options.pages_dir
        )
        index_dir = getattr(opened, "index_dir", None)
        return WikiScope(
            name=space,
            store=opened.store,
            rules_store=opened.store,
            own_rules=True,
            pages_root=Path(opened.pages_root),
            pages_dir=pages_dir,
            agent_pages_root=pages_dir,
            writable=bool(opened.config_writable),
            history=self._records_history(space),
            index_dir=Path(index_dir) if index_dir else None,
            key=space,
        )

    def _standalone_scope(self) -> WikiScope:
        library = self.library()
        return WikiScope(
            name=None,
            store=self.standalone,
            rules_store=library or self.standalone,
            own_rules=library is None,
            pages_root=self.standalone_pages,
            pages_dir=self.options.pages_dir.strip("/"),
            agent_pages_root=str(self.standalone_pages),
            writable=True,
            history=self.host_history,
            index_dir=self.standalone_index,
            key="",
        )

    @staticmethod
    def require_writable(scope: WikiScope) -> None:
        """쓸 수 없는 공간이면 409 ``project.config_readonly``."""
        if not scope.writable:
            raise WikiRequestError(
                "이 프로젝트 폴더는 쓸 수 없어 보기만 됩니다.",
                code=ErrorCodes.PROJECT_CONFIG_READONLY,
                details={"project_id": scope.name},
            )

    # ------------------------------------------------------------ 위키 정의

    def wiki_ids_of(self, scope: WikiScope) -> list[str]:
        try:
            return sorted(scope.store.list_ids(self.wiki_kind.name))
        except NotFound:
            return []

    def wiki_ids(self, space: str | None) -> list[str]:
        return self.wiki_ids_of(self.scope(space))

    def get_wiki(self, scope: WikiScope, wiki_id: str) -> StoredDefinition:
        """위키 정의. 없으면 ``WikiNotFound``."""
        try:
            return scope.store.get(self.wiki_kind.name, wiki_id)
        except NotFound:
            raise WikiNotFound(wiki_id) from None

    def create_wiki(self, scope: WikiScope, body: WikiCreateRequest) -> StoredDefinition:
        """위키 정의를 만든다(페이지 폴더는 첫 쓰기 때 생긴다)."""
        self.require_writable(scope)
        kind = self.wiki_kind.name
        wiki_id = body.id or unique_id(body.name, self.wiki_ids_of(scope), fallback=kind)
        doc: dict[str, Any] = {"kind": kind, "id": wiki_id, "name": body.name, "rules": body.rules}
        if body.description:
            doc["description"] = body.description
        if body.home:
            doc["home"] = body.home
        WikiDefinition.model_validate(doc)
        stored = scope.store.create(kind, doc, message="만듦")
        self.notify(scope.name, wiki_id)
        return stored

    def save_wiki(
        self, scope: WikiScope, wiki_id: str, body: WikiDefinition, *, expected: str | None
    ) -> StoredDefinition:
        """위키 정의 저장(``If-Match`` 필수 — 종류가 ``require_version``)."""
        self.require_writable(scope)
        if body.id != wiki_id:
            raise WikiRequestError(
                "경로의 id와 본문의 위키 id가 다릅니다.",
                details={"path_id": wiki_id, "body_id": body.id},
            )
        self.get_wiki(scope, wiki_id)
        doc = body.model_dump(mode="json", by_alias=True, exclude_none=True)
        doc["kind"] = self.wiki_kind.name
        stored = scope.store.save(
            self.wiki_kind.name, doc, expected_version=expected, message="위키 저장"
        )
        self.notify(scope.name, wiki_id)
        return stored

    def delete_wiki(self, scope: WikiScope, wiki_id: str, *, expected: str | None) -> None:
        """위키 정의만 지운다(페이지 폴더는 남긴다, K7R-13)."""
        self.require_writable(scope)
        try:
            scope.store.delete(self.wiki_kind.name, wiki_id, expected_version=expected)
        except NotFound:
            raise WikiNotFound(wiki_id) from None
        self._forget(scope.key, wiki_id)
        self.notify(scope.name, wiki_id, deleted=True)

    # ------------------------------------------------------------ 저장소

    def _rule_version(self, store: DefinitionStore, rule_id: str) -> str | None:
        try:
            return store.get(self.rules_kind.name, rule_id).version_hash
        except (NotFound, ValidationError, ValueError):
            return None

    def _search_factory(
        self, settings: WikiSettings
    ) -> tuple[str | None, SearchIndexFactory | None]:
        registry = self.search_factories
        if registry is None:
            return None, None
        wanted = settings.search_backend or self.options.search.backend
        for name in (wanted, self.options.search.fallback):
            if name and name in registry:
                return name, registry.get(name)
        return None, None

    def _search_options(self, case_insensitive: bool) -> dict[str, Any]:
        return {
            "tokenizer": self.options.search.tokenizer,
            "case_insensitive": case_insensitive,
            "max_results": self.options.max_search_results,
        }

    def _search_index(
        self, scope: WikiScope, wiki_id: str, settings: WikiSettings, case_insensitive: bool
    ) -> tuple[WikiSearchIndex | None, bool]:
        used, factory = self._search_factory(settings)
        options_key = (used, self.options.search.tokenizer, case_insensitive, str(scope.index_dir))
        key = (scope.key, wiki_id)
        with self._lock:
            slot = self.state.indexes.get(key)
            if slot is not None and slot.options == options_key:
                return slot.index, False
        if slot is not None:
            close_history(slot.index)
        index: WikiSearchIndex | None = None
        if factory is not None:
            root = (
                scope.index_dir / f"{wiki_id}{self._index_suffix}"
                if scope.index_dir is not None
                else None
            )
            try:
                index = factory(root, self._search_options(case_insensitive))
            except Exception:
                index = None
        with self._lock:
            self.state.indexes[key] = _SearchSlot(options_key, index)
        return index, True

    def repository_of(self, scope: WikiScope, wiki_id: str) -> WikiRepository:
        """그 공간 위키 하나의 저장소(캐시, 설정·규칙이 바뀌면 다시 만든다).

        Raises:
            WikiNotFound: 위키 정의가 없다.
        """
        stored = self.get_wiki(scope, wiki_id)
        wiki = WikiDefinition.model_validate(stored.document)
        settings = self.settings()
        checks = self.write_checks(settings)
        rule_versions = tuple((r, self._rule_version(scope.rules_store, r)) for r in wiki.rules)
        fingerprint = (
            stored.version_hash,
            rule_versions,
            settings.model_dump_json(),
            tuple(id(c) for c in checks),
            id(scope.history),
            str(scope.pages_root),
            id(scope.rules_store),
        )
        key = (scope.key, wiki_id)
        with self._lock:
            found = self.state.repos.get(key)
            if found is not None and found[0] == fingerprint:
                return found[1]
        docs = load_wiki_rules(scope.rules_store, wiki.rules, kind=self.rules_kind.name)
        merged = merge_rules(wiki.rules, docs)
        syntax = compile_syntax(effective_syntax(settings, rules=merged.syntax_layers))
        search, _fresh = self._search_index(scope, wiki_id, settings, syntax.case_insensitive)
        repo = WikiRepository(
            LocalWikiPages(scope.pages_root / wiki.id),
            wiki_id=wiki.id,
            syntax=syntax,
            rules=merged,
            home=wiki.home,
            history=scope.history,
            search=search,
            checks=checks,
            secrets=self.secret_policy(settings),
            limits=self.options.limits(max_versions_per_page=settings.max_versions_per_page),
            operators=self.operators(),
            clock=self.clock,
            parse_cache_entries=self.options.parse_cache_entries,
        )
        # 새로 만든 저장소마다 색인을 맞춘다(규칙이 바뀌면 제목 출처 등이 달라질 수 있다 —
        # 바뀐 문서만 쓴다). 색인은 캐시라 실패하면 다음 scan·쓰기 때 다시 맞춘다.
        with contextlib.suppress(Exception):
            repo.sync_search()
        with self._lock:
            self.state.repos[key] = (fingerprint, repo)
            self.state.summaries.pop(key, None)
        return repo

    def repository(self, space: str | None, wiki_id: str) -> WikiRepository:
        return self.repository_of(self.scope(space), wiki_id)

    def tool_targets(self, space: str | None) -> dict[str, WikiToolTarget]:
        """그 공간의 위키 → 도구 대상(열 수 없는 위키는 뺀다)."""
        scope = self.scope(space)
        out: dict[str, WikiToolTarget] = {}
        for wiki_id in self.wiki_ids_of(scope):
            try:
                repo = self.repository_of(scope, wiki_id)
                name = str(self.get_wiki(scope, wiki_id).document.get("name") or "")
            except Exception:
                continue
            pages_dir = (
                str(Path(scope.agent_pages_root) / wiki_id)
                if scope.name is None
                else posixpath.join(scope.agent_pages_root, wiki_id)
            )
            out[wiki_id] = WikiToolTarget(repository=repo, name=name, pages_dir=pages_dir)
        return out

    def directory(self, scope: WikiScope, wiki_id: str) -> str:
        """위키 페이지 폴더 표시용 상대 경로."""
        return posixpath.join(scope.pages_dir, wiki_id) if scope.pages_dir else wiki_id

    def _forget(self, scope_key: str, wiki_id: str) -> None:
        key = (scope_key, wiki_id)
        with self._lock:
            self.state.repos.pop(key, None)
            self.state.summaries.pop(key, None)
            slot = self.state.indexes.pop(key, None)
        if slot is not None:
            close_history(slot.index)

    # ------------------------------------------------------------ 보기

    def _home_issue(self, wiki: WikiDefinition, repo: WikiRepository) -> list[WikiIssue]:
        if not wiki.home or repo.current(wiki.home) is not None:
            return []
        return [
            WikiIssue(
                severity="info",
                code=KnownIssueCodes.WIKI_HOME_MISSING,
                message="첫 페이지로 정한 페이지가 없습니다.",
                page=wiki.home,
                path="/home",
            )
        ]

    def summary(self, scope: WikiScope, stored: StoredDefinition) -> WikiSummary:
        """위키 목록 카드 하나(공간 캐시 — 페이지 파일이 바뀌면 다시 계산)."""
        wiki = WikiDefinition.model_validate(stored.document)
        repo = self.repository_of(scope, wiki.id)
        files = tuple(
            (f.file, f.size, f.mtime) for f in repo.pages.list(repo.syntax.page_extensions)
        )
        key = (scope.key, wiki.id)
        marker = (id(repo), stored.version_hash, files)
        with self._lock:
            cached = self.state.summaries.get(key)
            if cached is not None and cached[0] == marker:
                self.state.summaries.move_to_end(key)
                return cached[1]
        listing = repo.list_pages()
        report = repo.lint()
        latest = max(
            (p for p in listing.items if p.updated_at is not None),
            key=lambda p: p.updated_at or 0.0,
            default=None,
        )
        issues: list[WikiIssue] = [*repo.issues, *self._home_issue(wiki, repo)]
        if listing.truncated:
            issues.append(
                WikiIssue(
                    severity="warning",
                    code=KnownIssueCodes.WIKI_TOO_MANY_PAGES,
                    message="페이지 수 상한을 넘어 일부 페이지만 색인했습니다.",
                    details={"total": listing.total} if listing.total else {},
                )
            )
        summary = WikiSummary(
            id=wiki.id,
            name=wiki.name,
            description=wiki.description,
            home=wiki.home,
            rules=list(repo.rules.refs),
            pages=len(listing.items),
            broken_links=sum(p.broken_links for p in listing.items),
            orphans=sum(1 for p in listing.items if p.orphan),
            lint_counts=dict(report.counts),
            updated_at=latest.updated_at if latest else None,
            updated_by=latest.updated_by if latest else None,
            directory=self.directory(scope, wiki.id),
            issues=issues,
        )
        cap = self.options.summary_cache_entries
        if cap > 0:
            with self._lock:
                self.state.summaries[key] = (marker, summary)
                self.state.summaries.move_to_end(key)
                while len(self.state.summaries) > cap:
                    self.state.summaries.popitem(last=False)
        return summary

    def summaries(self, scope: WikiScope) -> list[WikiSummary]:
        """공간의 위키 목록(읽을 수 없는 정의는 뺀다)."""
        out: list[WikiSummary] = []
        for wiki_id in self.wiki_ids_of(scope):
            try:
                out.append(self.summary(scope, self.get_wiki(scope, wiki_id)))
            except (WikiNotFound, ValidationError):
                continue
        return out

    def view(self, scope: WikiScope, wiki_id: str) -> tuple[WikiView, str]:
        """위키 하나 보기(정의 + 합친 규칙 요약 + 이슈)와 정의 버전."""
        stored = self.get_wiki(scope, wiki_id)
        wiki = WikiDefinition.model_validate(stored.document)
        repo = self.repository_of(scope, wiki_id)
        view = WikiView(
            wiki=wiki,
            version_hash=stored.version_hash,
            directory=self.directory(scope, wiki_id),
            rules=repo.rules.summary(),
            issues=[*repo.issues, *self._home_issue(wiki, repo)],
        )
        return view, stored.version_hash

    def _search_probe(self, settings: WikiSettings) -> _Probe:
        used, factory = self._search_factory(settings)
        wanted = settings.search_backend or self.options.search.backend
        key = (used, wanted, self.options.search.tokenizer)
        with self._lock:
            found = self.state.probes.get(key)
        if found is not None:
            return found
        degraded = used != wanted
        if factory is not None and not degraded:
            try:
                probe = factory(None, self._search_options(True))
                degraded = bool(getattr(probe, "degraded", False))
                close_history(probe)
            except Exception:
                degraded = True
        result = _Probe(degraded=degraded or factory is None, available=factory is not None)
        with self._lock:
            self.state.probes[key] = result
        return result

    def capabilities(self, scope: WikiScope) -> WikiCapabilities:
        """켜진 연동·포트에 따른 능력(웹이 모듈 id를 몰라도 된다)."""
        runs = any(
            INTEGRATION_RUNS in tuple(getattr(i, "capabilities", ()) or ())
            for i in self.integrations()
        )
        probe = self._search_probe(self.settings())
        return WikiCapabilities(
            history=scope.history is not None,
            search=probe.available,
            runs=runs,
            rules_library=self.library() is not None,
            import_export=True,
        )

    def info(self, scope: WikiScope) -> WikiInfo:
        """``GET /wiki/info``. ``writable`` = 공간 ``config_writable``(단독 루트는 그 판단),
        ``rules_kind`` = 위키 규칙 정의 종류 이름(설치자 데이터)."""
        issues: list[WikiIssue] = []
        probe = self._search_probe(self.settings())
        if probe.degraded:
            issues.append(
                WikiIssue(
                    severity="info",
                    code=KnownIssueCodes.WIKI_SEARCH_DEGRADED,
                    message="빠른 검색 색인을 쓸 수 없어 느린 대체 방식으로 찾습니다.",
                )
            )
        return WikiInfo(
            pages_root=scope.pages_dir,
            capabilities=self.capabilities(scope),
            writable=scope.writable,
            rules_kind=self.rules_kind.name,
            limits=WikiLimits(
                max_page_bytes=self.options.max_page_bytes,
                max_pages=self.options.max_pages,
                graph_max_nodes=self.options.graph_max_nodes,
            ),
            issues=issues,
        )

    def changes(
        self,
        scope: WikiScope,
        *,
        author_run: str | None = None,
        ops: Collection[str] = (),
        limit: int = 50,
        cursor: str | None = None,
    ) -> WikiChangePage:
        """공간 전체(모든 위키) 최근 변경(정의가 지워진 위키의 기록도 id로 나온다)."""
        if scope.history is None:
            raise WikiHistoryUnavailableError()
        return scope.history.changes(
            None,
            author_run=author_run,
            ops=ops,
            limit=min(limit, self.options.max_changes_page),
            cursor=cursor,
        )

    # ------------------------------------------------------------ 위키 규칙

    def rules_store(self, scope: WikiScope) -> DefinitionStore:
        return scope.rules_store

    def rule_ids(self, scope: WikiScope) -> list[str]:
        try:
            return sorted(scope.rules_store.list_ids(self.rules_kind.name))
        except NotFound:
            return []

    def get_rules(self, scope: WikiScope, rule_id: str) -> StoredDefinition:
        """위키 규칙 정의. 없으면 ``NotFound``(404 ``not_found``)."""
        return scope.rules_store.get(self.rules_kind.name, rule_id)

    def used_by(self, scope: WikiScope, rule_id: str) -> list[WikiRef]:
        """이 규칙을 쓰는 위키(공간 자기 규칙일 때만, 공용 라이브러리는 빈 목록)."""
        if not scope.own_rules:
            return []
        out: list[WikiRef] = []
        for wiki_id in self.wiki_ids_of(scope):
            try:
                doc = self.get_wiki(scope, wiki_id).document
            except WikiNotFound:
                continue
            rules = doc.get("rules")
            if isinstance(rules, list) and rule_id in rules:
                out.append(WikiRef(id=wiki_id, name=str(doc.get("name") or "")))
        return out

    def rule_files(self, scope: WikiScope, rule_id: str) -> list[str]:
        try:
            return [f.path for f in scope.rules_store.list_files(self.rules_kind.name, rule_id)]
        except NotFound:
            return []

    def check_rules(
        self, document: Mapping[str, Any], *, files: Collection[str] | None
    ) -> list[WikiIssue]:
        return check_rules(document, files=files, operators=self.operators())

    def rules_view(self, scope: WikiScope, stored: StoredDefinition) -> WikiRulesView:
        definition = WikiRulesDefinition.model_validate(stored.document)
        return WikiRulesView(
            rules=definition,
            version_hash=stored.version_hash,
            used_by=self.used_by(scope, stored.id),
            issues=self.check_rules(stored.document, files=self.rule_files(scope, stored.id)),
        )

    def rules_list(self, scope: WikiScope) -> list[WikiRulesListItem]:
        """위키 규칙 목록(본문 없음, 읽을 수 없는 정의는 뺀다)."""
        out: list[WikiRulesListItem] = []
        for rule_id in self.rule_ids(scope):
            try:
                stored = self.get_rules(scope, rule_id)
                definition = WikiRulesDefinition.model_validate(stored.document)
            except (NotFound, ValidationError):
                continue
            out.append(
                WikiRulesListItem(
                    id=rule_id,
                    name=definition.name,
                    description=definition.description,
                    counts=WikiRuleCounts(
                        write=len(definition.write_rules),
                        lint=len(definition.lint_rules),
                        templates=len(definition.page_templates),
                    ),
                    has_instructions=definition.instructions is not None,
                    used_by=self.used_by(scope, rule_id),
                    issues=self.check_rules(stored.document, files=self.rule_files(scope, rule_id)),
                )
            )
        return out

    def create_rules(self, scope: WikiScope, body: Mapping[str, Any]) -> StoredDefinition:
        """위키 규칙 만들기(``id`` 생략 = 이름에서).

        규칙 저장소가 공간 것이면 쓰기 가능해야 한다."""
        if scope.own_rules:
            self.require_writable(scope)
        kind = self.rules_kind.name
        doc = dict(body)
        doc["kind"] = kind
        name = str(doc.get("name") or "")
        if not doc.get("id"):
            doc["id"] = unique_id(name, self.rule_ids(scope), fallback=kind)
        WikiRulesDefinition.model_validate(doc)
        return scope.rules_store.create(kind, doc, message="만듦")

    def save_rules(
        self, scope: WikiScope, rule_id: str, body: WikiRulesDefinition, *, expected: str | None
    ) -> StoredDefinition:
        if scope.own_rules:
            self.require_writable(scope)
        if body.id != rule_id:
            raise WikiRequestError(
                "경로의 id와 본문의 규칙 id가 다릅니다.",
                details={"path_id": rule_id, "body_id": body.id},
            )
        doc = body.model_dump(mode="json", by_alias=True, exclude_none=True)
        doc["kind"] = self.rules_kind.name
        return scope.rules_store.save(
            self.rules_kind.name, doc, expected_version=expected, message="위키 규칙 저장"
        )

    def delete_rules(self, scope: WikiScope, rule_id: str, *, expected: str | None) -> None:
        if scope.own_rules:
            self.require_writable(scope)
        scope.rules_store.delete(self.rules_kind.name, rule_id, expected_version=expected)

    # ------------------------------------------------------------ 알림·주기 일

    def notify(
        self,
        space: str | None,
        wiki_id: str,
        paths: Sequence[str] = (),
        *,
        deleted: bool = False,
        external: bool = False,
    ) -> None:
        """WS ``wiki.changed``를 내고 그 위키 요약 캐시를 지운다."""
        with self._lock:
            self.state.summaries.pop((space or "", wiki_id), None)
        try:
            ref = SpaceRef(project_id=space or None)
        except ValidationError:
            ref = SpaceRef()
        self.ports.publish(
            WikiChanged(
                space=ref,
                wiki_id=wiki_id,
                paths=list(dict.fromkeys(paths)),
                deleted=deleted,
                external=external,
            )
        )

    def scan(self, scope: WikiScope, wiki_id: str) -> WikiScanResult:
        """외부 변경 다시 읽기 + 색인 맞추기 + 바뀌었으면 알림."""
        repo = self.repository_of(scope, wiki_id)
        result = repo.scan()
        with contextlib.suppress(Exception):
            repo.sync_search()
        changed = [*result.external, *result.imported, *result.deleted]
        if changed:
            self.notify(scope.name, wiki_id, changed, deleted=bool(result.deleted), external=True)
        return result

    def open_standalone(self) -> int:
        """단독 공간의 위키를 모두 열어 검색 색인을 맞춘다(시작할 때). Returns: 연 위키 수."""
        scope = self._standalone_scope()
        opened = 0
        for wiki_id in self.wiki_ids_of(scope):
            try:
                self.repository_of(scope, wiki_id)
            except Exception:
                continue
            opened += 1
        return opened

    def scan_opened(self) -> int:
        """열어 둔(캐시에 있는) 위키를 모두 다시 읽는다(주기 검사). Returns: 바뀐 위키 수."""
        with self._lock:
            keys = list(self.state.repos)
        changed = 0
        for space_key, wiki_id in keys:
            try:
                scope = self.scope(space_key or None)
                result = self.scan(scope, wiki_id)
            except Exception:
                continue
            if result.external or result.imported or result.deleted:
                changed += 1
        return changed

    def close(self) -> None:
        """검색 색인·기록 저장소를 닫는다(모듈 종료)."""
        with self._lock:
            slots = list(self.state.indexes.values())
            records = list(self.state.records.values())
            self.state.indexes.clear()
            self.state.records.clear()
            self.state.repos.clear()
            self.state.summaries.clear()
        for slot in slots:
            close_history(slot.index)
        for item in records:
            item.close()
        close_history(self.host_history)


__all__ = [
    "LiveSecretScanner",
    "WikiPorts",
    "WikiScope",
    "WikiService",
    "WikiServiceState",
    "unique_id",
    "user_author",
]
