"""메모리 서비스(포트 ``memory.service``의 구현, REST가 부르는 연산).

HTTP를 모른다. 저장소(``MemoryStore``)·사용자 설정 섹션 읽기·범위 종류 플러그인·조건 연산자를
주입받아 다음을 한다.

- 설정 해석: ``memory`` 섹션 원문 → ``MemorySettings``(깨진 부분만 빼고), 범위 종류 병합(패키지
  기본 → 플러그인 → 사용자), 정리 규칙 컴파일. 입력이 바뀔 때만 다시 계산한다(지문 비교).
- 저장소 정책 맞추기: 비밀 처리 방식·버전 보관 수가 바뀌면 저장소 ``policy``를 바꿔 끼운다.
- 사람 연산(쓴 주체 ``user``), 정리 미리보기·적용(쓴 주체 ``system``), 내보내기·가져오기.
- 에이전트 도구 묶음 만들기(``toolkit``, 실행 연동이 쓴다).

모든 쓰기는 변경 알림 감싸개(``ObservedMemoryStore``)를 거친다.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import IO, Any, Final

from agent_console_conditions import ConditionOperator
from agent_console_contracts import Issue
from agent_console_contracts.memory import (
    KnownMemoryAuthorKinds,
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryAuthor,
    MemoryEntry,
    MemoryEntryPage,
    MemoryImportPolicy,
    MemoryImportResult,
    MemoryMoveRequest,
    MemoryRetentionPlan,
    MemoryRetentionPlanRequest,
    MemoryRetentionResult,
    MemoryScopeKindList,
    MemoryScopeRef,
    MemoryScopeSummary,
    MemorySettings,
    MemoryTagCount,
    MemoryTagList,
    MemoryUpdateRequest,
    MemoryVersion,
    MemoryVersionSummary,
    MemoryWriteRequest,
)
from agent_console_memory import (
    EntryNotFoundError,
    EventSink,
    MemoryLimits,
    MemoryPolicy,
    MemoryQuery,
    MemoryScopeKind,
    MemorySecretGuard,
    MemoryStore,
    MemoryToolkit,
    MemoryTransferLimits,
    RetentionRuleSet,
    ScopeKindCatalog,
    SecretRulesScanner,
    SecretScanner,
    ToolText,
    WriteBudget,
    apply_retention,
    compile_retention_rules,
    import_markdown,
    iter_entries,
    load_default_scope_kinds,
    merge_scope_kinds,
    retention_plan,
    write_markdown_archive,
)

from .config import SECTION_KEY, parse_memory_settings
from .observed import ChangeSink, ObservedMemoryStore, observe

_log = logging.getLogger(__name__)

USER_AUTHOR: Final = MemoryAuthor(kind=KnownMemoryAuthorKinds.USER)
"""사람(로컬 단일 사용자)이 화면·REST로 쓴 버전의 쓴 주체."""

SAVED_RULES_PATH: Final = f"/{SECTION_KEY}/retention/rules"
"""저장된 정리 규칙의 이슈 위치(설정 문서 기준)."""

REQUEST_RULES_PATH: Final = "/rules"
"""정리 미리보기 요청 본문 규칙의 이슈 위치(요청 본문 기준)."""

CHECK_RULES_PATH: Final = "/retention/rules"
"""설정 검사(섹션 기준)의 정리 규칙 이슈 위치."""

type SectionReader = Callable[[], Any]
"""``memory`` 섹션 원문(매핑, 없으면 None)을 돌려주는 함수."""


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def _fingerprint(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):  # pragma: no cover - default=repr가 받는다
        return repr(value)


def raw_retention_rules(raw: Any) -> list[Any]:
    """섹션 원문에서 정리 규칙 목록 원문(목록이 아니면 빈 목록)."""
    if not isinstance(raw, Mapping):
        return []
    retention = raw.get("retention")
    if not isinstance(retention, Mapping):
        return []
    rules = retention.get("rules")
    return list(rules) if isinstance(rules, list) else []


@dataclass(frozen=True, slots=True)
class SettingsState:
    """한 시점의 설정 해석 결과(불변).

    Attributes:
        settings: 깨진 부분을 뺀 사용자 설정.
        issues: 섹션 형식 문제(``memory.settings_invalid``, warning).
        rules: 저장된 정리 규칙 컴파일 결과(이슈 경로는 설정 문서 기준).
        catalog: 병합된 범위 종류.
    """

    settings: MemorySettings
    issues: tuple[Issue, ...]
    rules: RetentionRuleSet
    catalog: ScopeKindCatalog


def _as_warning(issue: Issue) -> Issue:
    return (
        issue if issue.severity == "warning" else issue.model_copy(update={"severity": "warning"})
    )


class MemoryService:
    """메모리 서비스.

    Args:
        store: 메모리 저장소. 변경 알림 감싸개로 감싼다.
        section: 사용자 설정 ``memory`` 섹션 원문을 돌려주는 함수(None = 섹션 없음).
        plugins: X29 플러그인 범위 종류를 돌려주는 함수.
        operators: 조건 연산자(X22)를 돌려주는 함수(정리 규칙).
        limits: 설치자 쓰기 한도.
        transfer_limits: 가져오기 상한.
        on_change: 항목 변경 알림을 받는 함수(WS 발행 등, 막히지 않아야 한다).
        clock: 시각(Unix epoch 초) — 정리 규칙의 "지금".
        scanner: 비밀 판정기(기본 ``ac-secret-rules`` 기본 규칙).
        max_page_size: 목록·정리 미리보기 한 번의 최대 항목 수.
        max_tag_list: 태그 목록 최대 수.
        max_search_results: 에이전트 검색 도구 한 번의 최대 결과 수.
        default_scope_kinds: 패키지 기본 범위 종류 데이터를 돌려주는 함수(기본
            ``load_default_scope_kinds``, 처음 한 번 읽는다).
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        section: SectionReader = lambda: None,
        plugins: Callable[[], Sequence[MemoryScopeKind]] = lambda: (),
        operators: Callable[[], Mapping[str, ConditionOperator]] = lambda: {},
        limits: MemoryLimits | None = None,
        transfer_limits: MemoryTransferLimits | None = None,
        on_change: ChangeSink | None = None,
        clock: Callable[[], float] = time.time,
        scanner: SecretScanner | None = None,
        max_page_size: int = 200,
        max_tag_list: int = 500,
        max_search_results: int = 20,
        default_scope_kinds: Callable[[], Mapping[str, Any]] = load_default_scope_kinds,
    ) -> None:
        self._limits = limits if limits is not None else MemoryLimits()
        self._transfer = transfer_limits if transfer_limits is not None else MemoryTransferLimits()
        self._scanner: SecretScanner = scanner if scanner is not None else SecretRulesScanner()
        sink: ChangeSink = on_change if on_change is not None else (lambda _changed: None)
        self._store: ObservedMemoryStore = observe(store, sink)
        self._section = section
        self._plugins = plugins
        self._operators = operators
        self._clock = clock
        self.max_page_size = max(1, max_page_size)
        self.max_tag_list = max(1, max_tag_list)
        self.max_search_results = max(1, max_search_results)
        self._default_reader = default_scope_kinds
        self._defaults: Mapping[str, Any] | None = None
        self._lock = threading.RLock()
        self._apply_lock = threading.Lock()
        self._state: SettingsState | None = None
        self._state_key: str | None = None
        self._policy_key: tuple[str, int] | None = None
        self._refresh()

    # ---- 설정 ---------------------------------------------------------------------------

    def _read_section(self) -> Any:
        try:
            return _plain(self._section())
        except Exception:
            _log.warning("메모리 설정을 읽지 못해 기본값을 씁니다", exc_info=True)
            return None

    def _defaults_data(self) -> Mapping[str, Any]:
        if self._defaults is None:
            self._defaults = self._default_reader()
        return self._defaults

    def _compute(self, raw: Any, plugins: Sequence[MemoryScopeKind]) -> SettingsState:
        settings, issues = parse_memory_settings(raw, rule_issues=False)
        operators = self._operators()
        rules = compile_retention_rules(
            raw_retention_rules(raw), operators, base_path=SAVED_RULES_PATH
        )
        all_issues = [*issues]
        try:
            catalog = merge_scope_kinds(
                defaults=self._defaults_data(),
                include_defaults=settings.include_default_scope_kinds,
                plugins=plugins,
                user=settings.scope_kinds,
            )
        except ValueError:  # pragma: no cover - parse가 틀린 종류를 뺀다
            _log.warning("사용자 범위 종류를 합치지 못해 빼고 씁니다", exc_info=True)
            catalog = merge_scope_kinds(
                defaults=self._defaults_data(),
                include_defaults=settings.include_default_scope_kinds,
                plugins=plugins,
            )
        return SettingsState(settings, tuple(all_issues), rules, catalog)

    def _refresh(self) -> SettingsState:
        raw = self._read_section()
        plugins = list(self._plugins())
        operators = self._operators()
        key = _fingerprint(
            [
                raw,
                [(k.id, k.origin, k.label, k.template) for k in plugins],
                sorted(operators),
            ]
        )
        with self._lock:
            if self._state is None or key != self._state_key:
                self._state = self._compute(raw, plugins)
                self._state_key = key
            state = self._state
            policy_key = (state.settings.secrets, state.settings.max_versions_per_entry)
            if policy_key != self._policy_key:
                self._store.policy = MemoryPolicy(
                    limits=self._limits,
                    secrets=MemorySecretGuard(self._scanner, state.settings.secrets),
                    max_versions_per_entry=state.settings.max_versions_per_entry,
                )
                self._policy_key = policy_key
        return state

    def settings(self) -> MemorySettings:
        """지금 사용자 설정(깨진 부분은 뺀 값)."""
        return self._refresh().settings

    def catalog(self) -> ScopeKindCatalog:
        """병합된 범위 종류."""
        return self._refresh().catalog

    @property
    def limits(self) -> MemoryLimits:
        """설치자 쓰기 한도."""
        return self._limits

    @property
    def transfer_limits(self) -> MemoryTransferLimits:
        """가져오기 상한."""
        return self._transfer

    @property
    def store(self) -> MemoryStore:
        """변경 알림을 내는 저장소(부를 때 정책을 지금 설정에 맞춘다)."""
        self._refresh()
        return self._store

    def warnings(self) -> list[Issue]:
        """서버 경고: 저장된 섹션의 형식·정리 규칙 문제(warning)."""
        state = self._refresh()
        return [*state.issues, *(_as_warning(i) for i in state.rules.issues)]

    def check_settings(self, raw: Any) -> list[Issue]:
        """저장 전 설정 섹션 검사(섹션 기준 경로, 형식·범위 종류 틀·정리 규칙).

        Args:
            raw: 섹션 원문(편집 중인 값).

        Returns:
            이슈 목록(형식 오류는 error, 모르는 연산자 등은 warning).
        """
        data = _plain(raw)
        _settings, issues = parse_memory_settings(
            data, base_path="", severity="error", rule_issues=False
        )
        rules = compile_retention_rules(
            raw_retention_rules(data), self._operators(), base_path=CHECK_RULES_PATH
        )
        return [*issues, *rules.issues]

    # ---- 도구 묶음 -----------------------------------------------------------------------

    def toolkit(
        self,
        access: MemoryAccessConfig,
        context: MemoryAccessContext,
        *,
        on_event: EventSink | None = None,
        author: MemoryAuthor | None = None,
        write_budget: WriteBudget | None = None,
        text: ToolText | None = None,
    ) -> MemoryToolkit:
        """에이전트 도구 묶음(이 저장소·지금 범위 종류·설치자 검색 상한)."""
        state = self._refresh()
        return MemoryToolkit(
            self._store,
            access=access,
            context=context,
            catalog=state.catalog,
            author=author,
            text=text,
            on_event=on_event,
            write_budget=write_budget,
            max_search_results=self.max_search_results,
        )

    # ---- 범위 ---------------------------------------------------------------------------

    def scope_kinds(self) -> MemoryScopeKindList:
        """``GET /memory/scope-kinds``: 병합된 범위 종류(끈 것은 ``disabled``)."""
        return self.catalog().listing()

    def scopes(self, kind: str | None = None) -> list[MemoryScopeSummary]:
        """``GET /memory/scopes``: 항목이 있는 범위 요약(``kind_known`` 채움)."""
        state = self._refresh()
        return state.catalog.annotate(self._store.list_scopes(kind=kind))

    # ---- 항목 ---------------------------------------------------------------------------

    def entries(self, query: MemoryQuery) -> MemoryEntryPage:
        """목록·검색(쪽 크기는 ``max_page_size`` 이하로)."""
        self._refresh()
        limit = min(max(query.limit, 1), self.max_page_size)
        if limit != query.limit:
            query = MemoryQuery(
                scopes=query.scopes,
                text=query.text,
                tags=query.tags,
                author_run=query.author_run,
                author_kind=query.author_kind,
                include_archived=query.include_archived,
                include_deleted=query.include_deleted,
                sort=query.sort,
                order=query.order,
                cursor=query.cursor,
                limit=limit,
            )
        return self._store.search(query)

    def get(self, entry_id: str, *, include_deleted: bool = False) -> MemoryEntry:
        """항목 하나. 없으면 ``EntryNotFoundError``."""
        entry = self._store.get(entry_id, include_deleted=include_deleted)
        if entry is None:
            raise EntryNotFoundError("기록이 없다")
        return entry

    def create(self, request: MemoryWriteRequest) -> MemoryEntry:
        """새 항목(같은 범위·키가 있으면 ``EntryExistsError``)."""
        outcome = self.store.write(
            request.scope,
            request.key,
            request.content,
            author=USER_AUTHOR,
            tags=request.tags,
            content_type=request.content_type,
            pinned=request.pinned,
            create_only=True,
        )
        return outcome.entry

    def update(
        self, entry_id: str, request: MemoryUpdateRequest, *, if_version: int
    ) -> MemoryEntry:
        """고치기(생략 = 그대로, ``if_version``이 다르면 ``VersionConflictError``)."""
        return self.store.update(
            entry_id,
            author=USER_AUTHOR,
            content=request.content,
            content_type=request.content_type,
            tags=request.tags,
            pinned=request.pinned,
            if_version=if_version,
        )

    def move(
        self, entry_id: str, request: MemoryMoveRequest, *, if_version: int | None = None
    ) -> MemoryEntry:
        """범위·키 옮기기."""
        return self.store.move(
            entry_id,
            author=USER_AUTHOR,
            to_scope=request.to_scope,
            to_key=request.to_key,
            if_version=if_version,
        )

    def archive(
        self, entry_id: str, *, archived: bool, if_version: int | None = None
    ) -> MemoryEntry:
        """보관·보관 풀기."""
        return self.store.archive(
            entry_id, author=USER_AUTHOR, archived=archived, if_version=if_version
        )

    def restore(self, entry_id: str, *, version: int | None = None) -> MemoryEntry:
        """되돌리기(지운 항목 되살리기, ``version``이면 그 본문으로)."""
        return self.store.restore(entry_id, author=USER_AUTHOR, version=version)

    def delete(self, entry_id: str, *, if_version: int | None = None) -> MemoryEntry:
        """표시 삭제."""
        return self.store.delete(entry_id, author=USER_AUTHOR, if_version=if_version)

    def purge(self, entry_id: str) -> MemoryEntry:
        """완전 삭제(버전·검색 행까지)."""
        return self.store.purge(entry_id)

    def versions(self, entry_id: str) -> list[MemoryVersionSummary]:
        """버전 목록(오름차순)."""
        return self._store.history(entry_id)

    def version(self, entry_id: str, version: int) -> MemoryVersion:
        """버전 하나(본문 포함). 없으면 ``EntryNotFoundError``."""
        found = self._store.get_version(entry_id, version)
        if found is None:
            raise EntryNotFoundError("그 버전이 없다")
        return found

    def tags(
        self, scopes: Sequence[MemoryScopeRef] | None = None, *, include_archived: bool = False
    ) -> MemoryTagList:
        """태그와 항목 수(항목 수 내림차순, 같으면 이름 순). 지운 항목은 세지 않는다.

        저장소를 훑어 센다(저장소에 태그 집계 능력이 생기면 그것을 쓴다 — ``count_tags``).
        """
        self._refresh()
        counter: Counter[str] = Counter()
        counting = getattr(self._store, "count_tags", None)
        if callable(counting):
            counter.update(dict(counting(scopes=scopes, include_archived=include_archived)))
        else:
            for entry in iter_entries(
                self._store, scopes=scopes, include_archived=include_archived
            ):
                counter.update(set(entry.tags))
        ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        cut = ordered[: self.max_tag_list]
        return MemoryTagList(
            tags=[MemoryTagCount(tag=tag, entries=count) for tag, count in cut],
            truncated=len(ordered) > len(cut),
        )

    # ---- 정리 ---------------------------------------------------------------------------

    def plan_retention(
        self, request: MemoryRetentionPlanRequest | None = None
    ) -> MemoryRetentionPlan:
        """정리 미리보기(아무것도 바꾸지 않는다).

        본문에 ``rules``가 있으면 그 규칙으로(저장 전 시험, 이슈 위치 ``/rules/<i>``), 없으면 저장된
        규칙으로 판단한다. 항목 수는 ``limit``(없으면 ``max_page_size``)에서 자르고 ``count``는 늘
        전체 수다.
        """
        state = self._refresh()
        req = request if request is not None else MemoryRetentionPlanRequest()
        if req.rules is not None:
            rules = compile_retention_rules(
                req.rules, self._operators(), base_path=REQUEST_RULES_PATH
            )
        else:
            rules = state.rules
        limit = min(req.limit or self.max_page_size, self.max_page_size)
        return retention_plan(self._store, rules, now=self._clock(), limit=limit)

    def apply_retention(self) -> MemoryRetentionResult:
        """저장된 규칙으로 정리를 적용한다(잘리지 않은 계획을 다시 만든 뒤 적용).

        버전의 쓴 주체는 ``system``(``label`` = 규칙 id)이라 되돌릴 수 있다.
        동시에 두 번 돌지 않는다.
        """
        state = self._refresh()
        with self._apply_lock:
            plan = retention_plan(self._store, state.rules, now=self._clock())
            result = apply_retention(self._store, plan)
        if result.archived or result.deleted:
            _log.info(
                "메모리 정리: 보관 %d, 지움 %d, 건너뜀 %d",
                result.archived,
                result.deleted,
                result.skipped,
            )
        return result

    def has_retention_rules(self) -> bool:
        """적용할 수 있는 저장된 정리 규칙이 있는지."""
        return bool(self._refresh().rules.rules)

    # ---- 내보내기·가져오기 ------------------------------------------------------------------

    def export_to(
        self,
        target: IO[bytes],
        scopes: Sequence[MemoryScopeRef] | None = None,
        *,
        include_archived: bool = True,
    ) -> int:
        """마크다운 zip을 ``target``에 쓴다(지운 항목 제외). 내보낸 항목 수."""
        self._refresh()
        return write_markdown_archive(
            self._store, target, scopes, include_archived=include_archived
        )

    def import_archive(
        self,
        data: bytes | IO[bytes],
        *,
        policy: MemoryImportPolicy = "skip",
        dry_run: bool = False,
    ) -> MemoryImportResult:
        """마크다운 zip을 가져온다(쓰기 검사·상한은 ``ac-memory`` ``import_markdown``)."""
        return import_markdown(
            self.store, data, policy=policy, dry_run=dry_run, limits=self._transfer
        )


__all__ = [
    "CHECK_RULES_PATH",
    "REQUEST_RULES_PATH",
    "SAVED_RULES_PATH",
    "USER_AUTHOR",
    "MemoryService",
    "SectionReader",
    "SettingsState",
    "raw_retention_rules",
]
