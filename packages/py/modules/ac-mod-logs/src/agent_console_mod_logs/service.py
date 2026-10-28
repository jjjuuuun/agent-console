"""로그 기능 서비스: 수집 스케줄 + 질의(HTTP 없이도 쓴다, design §4R.4·§4R.6·§4R.10).

- 수집: ``LogIngestor``(ac-logs)를 스레드에서 돌린다(``asyncio.to_thread``). 같은 출처 수집은
  ``LogIngestor``가 출처별 잠금으로 겹치지 않게 하고, 이 서비스는 수집 요청을 한 줄로 세운다.
  진행 중인 수집이 요청 범위를 덮으면 새로 돌리지 않고 그 결과를 기다린다.
- 수집 예약(``request_scan``): 어느 스레드에서든 부른다. 쌓인 요청은 하나의 배수 작업이 합쳐서
  처리한다. 시작 전에 온 요청은 시작 때 처리한다.
- 보존: ``retention_days``가 있으면 수집 뒤 그보다 오래된 이벤트를 지운다(색인만, 원본은 그대로).
- 비우기(M-3): ``purge``는 수집과 같은 잠금 안에서 ``purge_index``를 부른다(수집 중인 커서 쓰기와
  섞이지 않게).
- 알림: 새 이벤트가 있으면 ``on_ingested(LogsIngestedPayload)``를 부른다(모듈이 토픽·WS로 보낸다).
- 질의: 지금 설정(``logs.taxonomy``·``logs.projects``)으로 질의 맥락을 만들어 색인에 묻는다.
  필터의 ``scope``·확장 필터는 등록된 범위 종류(X27)·필터 확장(X28)으로 풀어 맥락에 싣는다
  (``LogQueryExtensions``). 등록이 없으면 맥락은 그대로이고, 그 이름은 422다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from agent_console_contracts import HandoffMatrix, Issue, KnownIssueCodes
from agent_console_contracts.logs import (
    LogAggregateRequest,
    LogAggregateRow,
    LogArchive,
    LogClassifierDescriptor,
    LogDashboard,
    LogEventDetail,
    LogEventPage,
    LogQuerySchema,
    LogScanReport,
    LogSessionSummary,
    LogSettings,
    LogSourceInfo,
    LogTaxonomy,
    LogTimeline,
    TokenSample,
)
from agent_console_contracts.modules import LogsIngestedPayload
from agent_console_logs import (
    DEFAULT_ARCHIVE_MAX_BYTES,
    DEFAULT_ARCHIVE_MAX_EVENTS,
    DEFAULT_BATCH_SIZE,
    DEFAULT_BUDGET_BYTES,
    ERROR_UNKNOWN_CLASSIFIER,
    JsonValue,
    LogClassifier,
    LogEventRow,
    LogFilter,
    LogFilterExtension,
    LogIndex,
    LogIngestor,
    LogQueryExtensions,
    LogRegistries,
    LogScopeKind,
    LogSource,
    PageCallback,
    PurgeableLogIndex,
    PurgeResult,
    QueryContext,
    SessionTitleRule,
    build_archive,
    iter_event_rows,
    load_default_session_title_rules,
    load_default_taxonomy,
    merge_taxonomy,
    parse_tz,
    purge_index,
    query_context,
    read_only_open,
)

from .errors import LogPurgeUnsupportedError
from .settings import DEFAULT_MAX_DETAIL_BYTES, DEFAULT_TIMELINE_LIMIT

_log = logging.getLogger("agent_console_mod_logs")

SECONDS_PER_DAY = 86_400.0


@dataclass(frozen=True, slots=True)
class _Running:
    key: frozenset[str] | None
    task: asyncio.Future[LogScanReport]


def _covers(running: frozenset[str] | None, wanted: frozenset[str] | None) -> bool:
    """진행 중인 수집 범위가 요청 범위를 덮는가(None = 켜진 출처 전부)."""
    if running is None:
        return True
    return wanted is not None and wanted <= running


class LogsService:
    """로그 수집·질의 서비스(``logs.query``·``logs.ingest`` 포트 구현).

    Args:
        index: 색인.
        registries: 출처·분류기 레지스트리(이미 로드한 것).
        settings: 지금 로그 설정(``WorkspaceSettings.logs``)을 돌려주는 함수. None이면 기본값.
        redact: 저장 직전 가리기(``LogRedaction`` 등). ``refresh()``가 있으면 수집마다 부른다.
        clock: 현재 시각(epoch 초).
        environ: 출처에 넘길 환경(프로세스 환경을 몰래 읽지 않는다).
        paths: 출처에 넘길 기본 경로(``workspace``·``state``·``base_dir``).
        budget_bytes·batch_size: 수집 예산·트랜잭션 크기.
        retention_days: 보존 기간(None = 영구).
        max_detail_bytes: 상세 detail·raw 상한.
        timeline_limit: 타임라인 이벤트 상한.
        templates: 대시보드 템플릿을 돌려주는 함수.
        base_taxonomy: 기본 분류 체계(None이면 ac-logs 패키지 데이터).
        session_title_rules: 세션 제목 순위 규칙(None이면 ac-logs 패키지 데이터).
        on_ingested: 새 이벤트가 생긴 수집 뒤 부를 함수(이벤트 루프 스레드에서).
        open_read: 원본 읽기 전용 열기(테스트에서 쓰기 감시).
        archive_max_events·archive_max_bytes: 보관본 이벤트 수·바이트 합 상한.
        scope_kinds: 지금 등록된 범위 종류(X27)를 돌려주는 함수(질의마다 부른다).
        filter_predicates: 지금 등록된 필터 확장(X28)을 돌려주는 함수(질의마다 부른다).
    """

    def __init__(
        self,
        index: LogIndex,
        registries: LogRegistries,
        *,
        settings: Callable[[], LogSettings | None] = lambda: None,
        redact: Callable[[JsonValue], JsonValue] | None = None,
        clock: Callable[[], float],
        environ: Mapping[str, str] | None = None,
        paths: Mapping[str, Path] | None = None,
        budget_bytes: int = DEFAULT_BUDGET_BYTES,
        batch_size: int = DEFAULT_BATCH_SIZE,
        retention_days: float | None = None,
        max_detail_bytes: int = DEFAULT_MAX_DETAIL_BYTES,
        timeline_limit: int = DEFAULT_TIMELINE_LIMIT,
        templates: Callable[[], list[LogDashboard]] = list,
        base_taxonomy: LogTaxonomy | None = None,
        session_title_rules: tuple[SessionTitleRule, ...] | None = None,
        on_ingested: Callable[[LogsIngestedPayload], None] | None = None,
        open_read: Callable[[Path], BinaryIO] = read_only_open,
        archive_max_events: int = DEFAULT_ARCHIVE_MAX_EVENTS,
        archive_max_bytes: int = DEFAULT_ARCHIVE_MAX_BYTES,
        scope_kinds: Callable[[], Iterable[LogScopeKind]] = tuple,
        filter_predicates: Callable[[], Iterable[LogFilterExtension]] = tuple,
    ) -> None:
        self._index = index
        self._registries = registries
        self._settings = settings
        self._redact = redact
        self._clock = clock
        self._ingestor = LogIngestor(
            index,
            registries,
            redact=redact,
            clock=clock,
            environ=environ,
            paths=paths,
            open_read=open_read,
            budget_bytes=budget_bytes,
            batch_size=batch_size,
        )
        self._retention = retention_days
        self._max_detail = max_detail_bytes
        self._timeline_limit = timeline_limit
        self._templates = templates
        self._base_taxonomy = base_taxonomy
        self._title_rules = session_title_rules
        self._on_ingested = on_ingested
        self._loop: asyncio.AbstractEventLoop | None = None
        self._scan_lock: asyncio.Lock | None = None
        self._running: _Running | None = None
        self._guard = threading.Lock()
        self._requested: set[str] | None = None
        self._requested_all = False
        self._drain: asyncio.Task[None] | None = None
        self._last_report: LogScanReport | None = None
        self._archive_max_events = archive_max_events
        self._archive_max_bytes = archive_max_bytes
        self._scope_kinds = scope_kinds
        self._filter_predicates = filter_predicates
        self._extensions: tuple[tuple[int, ...], LogQueryExtensions] | None = None

    # ---------------------------------------------------------------- 설정·맥락

    @property
    def index(self) -> LogIndex:
        return self._index

    @property
    def registries(self) -> LogRegistries:
        return self._registries

    @property
    def last_report(self) -> LogScanReport | None:
        """마지막 수집 결과(없으면 None)."""
        return self._last_report

    def log_settings(self) -> LogSettings | None:
        """지금 로그 설정(읽기 실패는 호출자에게 그대로 낸다)."""
        return self._settings()

    def _base(self) -> LogTaxonomy:
        if self._base_taxonomy is None:
            self._base_taxonomy = load_default_taxonomy()
        return self._base_taxonomy

    def query_context(self, *, tz: str | None = None) -> QueryContext:
        """지금 설정으로 만든 질의 맥락.

        Raises:
            LogQueryError: 모르는 시간대(``tz``).
        """
        if self._title_rules is None:
            self._title_rules = load_default_session_title_rules()
        return query_context(
            self._settings(),
            base_taxonomy=self._base(),
            tz=parse_tz(tz),
            session_title_rules=self._title_rules,
        )

    def taxonomy(self) -> LogTaxonomy:
        """유효 분류 체계(기본 + 설정 ``logs.taxonomy``)."""
        settings = self._settings()
        return merge_taxonomy(self._base(), settings.taxonomy if settings else None)

    def extensions(self) -> LogQueryExtensions:
        """지금 등록된 범위 종류·필터 확장 묶음(등록이 같으면 다시 만들지 않는다).

        겹치는 이름은 먼저 온 것만 남기고 경고 로그를 남긴다.
        """
        kinds = tuple(self._scope_kinds())
        filters = tuple(self._filter_predicates())
        key = tuple(id(x) for x in (*kinds, None, *filters))
        cached = self._extensions
        if cached is not None and cached[0] == key:
            return cached[1]
        ext = LogQueryExtensions.collect(kinds, filters)
        for reason in ext.skipped:
            _log.warning("로그 질의 확장을 건너뜁니다: %s", reason)
        self._extensions = (key, ext)
        return ext

    def parse_filter(self, params: Mapping[str, JsonValue], *, path: str = "") -> LogFilter:
        """쿼리 이름별 값 → ``LogFilter``(등록된 확장 필터 이름도 받는다).

        Raises:
            LogQueryError: 모르는 이름·틀린 값.
        """
        return self.extensions().parse(params, path=path)

    def _context_for(self, flt: LogFilter | None, *, path: str = "") -> QueryContext:
        """지금 설정 맥락 + ``flt``의 ``scope``·확장 필터 풀이.

        Raises:
            LogQueryError: 모르는 범위 종류·필터 이름, 틀린 값.
        """
        return self.extensions().refine(flt or LogFilter(), self.query_context(), path=path)

    def schema(self) -> LogQuerySchema:
        """집계 차원·지표·필터 이름(``GET /logs/schema``, 등록된 확장 필터 포함)."""
        return self.extensions().schema()

    def dashboard_templates(self) -> list[LogDashboard]:
        return self._templates()

    # ---------------------------------------------------------------- 출처

    def sources(self) -> list[LogSourceInfo]:
        """출처 목록과 상태(플러그인 + 런타임)."""
        return self._ingestor.sources(self._settings())

    def classifiers(self) -> list[LogClassifierDescriptor]:
        return self._registries.classifier_descriptors()

    def add_runtime_source(self, source: LogSource, *, classifier: LogClassifier) -> None:
        """런타임 출처를 더한다.

        Raises:
            ValueError: 같은 id의 출처가 이미 있다(플러그인이 이긴다).
        """
        self._ingestor.add_runtime_source(source, classifier=classifier)

    def source_issues(self) -> list[Issue]:
        """마지막 수집에서 실패한 출처(``server.warnings``). 메시지에 원본 경로·예외 문장 없음."""
        out: list[Issue] = []
        for info in self._ingestor.sources(self._settings()):
            code = info.status.error_code
            if not code or not info.enabled:
                continue
            issue_code = (
                KnownIssueCodes.LOGS_UNKNOWN_CLASSIFIER
                if code == ERROR_UNKNOWN_CLASSIFIER
                else KnownIssueCodes.LOGS_SOURCE_FAILED
            )
            out.append(
                Issue(
                    severity="warning",
                    code=issue_code,
                    message=f"로그 출처 {info.descriptor.id}를 수집하지 못했습니다({code})",
                    details={"source": info.descriptor.id, "error_code": code},
                )
            )
        return out

    # ---------------------------------------------------------------- 수집

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """이벤트 루프에 붙인다(모듈 시작 훅). 시작 전에 쌓인 수집 요청을 처리한다."""
        self._loop = loop or asyncio.get_running_loop()
        self._scan_lock = asyncio.Lock()
        self._kick()

    async def stop(self) -> None:
        """예약 처리 작업을 멈춘다(진행 중인 스레드 수집은 끝까지 간다)."""
        task, self._drain = self._drain, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._loop = None

    def _scan_sync(self, key: frozenset[str] | None) -> LogScanReport:
        settings = self._settings()
        refresh = getattr(self._redact, "refresh", None)
        if callable(refresh):
            refresh()
        report = self._ingestor.scan(settings, source_ids=key)
        if self._retention is not None:
            removed = self._index.prune(self._clock() - self._retention * SECONDS_PER_DAY)
            if removed:
                _log.info("보존 기간이 지난 로그 이벤트 %d개를 색인에서 지웠습니다", removed)
        return report

    async def _scan_task(self, key: frozenset[str] | None) -> LogScanReport:
        report = await asyncio.to_thread(self._scan_sync, key)
        self._last_report = report
        if report.new_events and self._on_ingested is not None:
            payload = LogsIngestedPayload(
                source_ids=[s.source_id for s in report.sources if s.new_events],
                count=report.new_events,
                max_seq=report.max_seq,
            )
            try:
                self._on_ingested(payload)
            except Exception:
                _log.exception("로그 수집 알림 실패")
        return report

    async def scan(self, source_ids: Collection[str] | None = None) -> LogScanReport:
        """지금 한 번 수집한다(켜진 출처 중 ``source_ids``만, None = 전부).

        진행 중인 수집이 요청 범위를 덮으면 새로 돌리지 않고 그 결과를 기다린다.
        """
        key = None if source_ids is None else frozenset(source_ids)
        running = self._running
        if running is not None and not running.task.done() and _covers(running.key, key):
            return await asyncio.shield(running.task)
        if self._scan_lock is None:
            self._scan_lock = asyncio.Lock()
        async with self._scan_lock:
            task = asyncio.ensure_future(self._scan_task(key))
            self._running = _Running(key, task)
            return await asyncio.shield(task)

    def request_scan(
        self, source_ids: Collection[str] | None = None, *, ref_hint: str | None = None
    ) -> None:
        """수집을 예약한다(막히지 않음, 스레드 안전). ``ref_hint``는 참고용이다(출처 전체를 읽는다
        — 바뀌지 않은 단위는 커서 덕분에 읽지 않는다)."""
        del ref_hint
        with self._guard:
            if source_ids is None:
                self._requested_all = True
            else:
                self._requested = (self._requested or set()) | set(source_ids)
        loop = self._loop
        if loop is None or loop.is_closed():
            return  # 시작 때 처리한다
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._kick()
        else:
            loop.call_soon_threadsafe(self._kick)

    def _take_requests(self) -> tuple[bool, frozenset[str] | None]:
        with self._guard:
            if self._requested_all:
                self._requested_all, self._requested = False, None
                return True, None
            if self._requested:
                ids, self._requested = frozenset(self._requested), None
                return True, ids
            return False, None

    def _kick(self) -> None:
        if self._loop is None:
            return
        if self._drain is not None and not self._drain.done():
            return
        with self._guard:
            if not self._requested_all and not self._requested:
                return
        self._drain = asyncio.ensure_future(self._drain_requests())

    async def _drain_requests(self) -> None:
        while True:
            has, ids = self._take_requests()
            if not has:
                return
            try:
                await self.scan(ids)
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("예약된 로그 수집 실패")

    async def run_periodic(self, interval: float, *, startup: bool) -> None:
        """배경 수집: ``startup``이면 바로 한 번, 그 뒤 ``interval``초마다(0이면 반복 없음)."""
        if startup:
            await self._safe_scan()
        if interval <= 0:
            return
        while True:
            await asyncio.sleep(interval)
            await self._safe_scan()

    async def _safe_scan(self) -> None:
        try:
            await self.scan()
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("배경 로그 수집 실패")

    async def purge(
        self,
        *,
        sources: Collection[str] | None = None,
        categories: Collection[str] | None = None,
        before: float | None = None,
        rescan: bool = True,
        dry_run: bool = True,
    ) -> PurgeResult:
        """색인에서 범위의 행을 지운다(``dry_run``이 기본, 의미는 ``purge_index``).

        진행 중인 수집이 끝난 뒤 수집 잠금 안에서 돈다. 원본 파일은 건드리지 않는다.

        Raises:
            ValueError: 빈 목록·빈 이름.
            LogPurgeUnsupportedError: 색인이 비우기를 지원하지 않는다(``PurgeableLogIndex`` 아님).
        """
        if not isinstance(self._index, PurgeableLogIndex):
            raise LogPurgeUnsupportedError(type(self._index).__name__)
        if self._scan_lock is None:
            self._scan_lock = asyncio.Lock()
        async with self._scan_lock:
            result = await asyncio.to_thread(
                purge_index,
                self._index,
                sources=sources,
                categories=categories,
                before=before,
                rescan=rescan,
                dry_run=dry_run,
            )
        if not dry_run and result.events:
            _log.info("로그 색인에서 이벤트 %d개를 지웠습니다(비우기)", result.events)
        return result

    # ---------------------------------------------------------------- 질의(막히는 호출)

    def events(self, flt: LogFilter, *, with_total: bool = False) -> LogEventPage:
        return self._index.query_events(flt, self._context_for(flt), with_total=with_total)

    def iter_event_rows(
        self, flt: LogFilter, *, on_page: PageCallback | None = None
    ) -> Iterator[LogEventRow]:
        """``flt.cursor``부터 끝까지 ``events``와 같은 이벤트를 모델 없이 JSON 행으로
        (``ac-logs`` ``iter_event_rows``, ``flt.limit``개씩 읽는다).

        범위 전체를 읽어 판정·집계만 하는 쪽(예: 구조도 연동)이 쓴다. ``on_page``는 쪽을 읽을 때마다
        그 쪽의 행 수로 부른다.

        Raises:
            LogQueryError: ``events``와 같은 경우(첫 쪽을 읽을 때).
        """
        return iter_event_rows(self._index, flt, self._context_for(flt), on_page=on_page)

    def event(self, uid: str) -> LogEventDetail | None:
        return self._index.get_event(uid, self.query_context(), max_detail_bytes=self._max_detail)

    def sessions(self, flt: LogFilter) -> list[LogSessionSummary]:
        return self._index.list_sessions(flt, self._context_for(flt))

    def timeline(self, session: str, flt: LogFilter | None = None) -> LogTimeline | None:
        return self._index.timeline(
            session, self._context_for(flt), flt=flt, limit=self._timeline_limit
        )

    def aggregate(self, request: LogAggregateRequest) -> list[LogAggregateRow]:
        """집계. 시간대는 요청 ``tz``(색인이 해석), 없으면 서버 로컬.

        Raises:
            LogQueryError: 모르는 차원·지표·필터·시간대.
        """
        flt = self.parse_filter(request.filter, path="filter")
        return self._index.aggregate(request, self._context_for(flt, path="filter"))

    def handoffs(self, flt: LogFilter) -> HandoffMatrix:
        return self._index.handoffs(flt, self._context_for(flt))

    def token_samples(self, flt: LogFilter) -> list[TokenSample]:
        return self._index.token_samples(flt, self._context_for(flt))

    def archive(self, flt: LogFilter) -> LogArchive:
        """필터 범위의 오프라인 보관본(``LogArchive`` v1, 본문 포함, 크기 한도 적용).

        색인 사본은 수집 때 가려졌고, 가리기(``redact``)가 있으면 지금 규칙으로 한 번 더 가린다
        (수집 뒤 규칙이 바뀐 경우). ``flt.limit``·``cursor``는 쓰지 않는다.
        """
        refresh = getattr(self._redact, "refresh", None)
        if callable(refresh):
            refresh()
        return build_archive(
            self._index,
            flt,
            self._context_for(flt),
            exported_at=self._clock(),
            taxonomy=self.taxonomy(),
            max_events=self._archive_max_events,
            max_bytes=self._archive_max_bytes,
            max_detail_bytes=self._max_detail,
            redact=self._redact,
        )


__all__ = ["LogsService"]
