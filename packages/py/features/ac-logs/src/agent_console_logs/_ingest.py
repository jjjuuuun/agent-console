"""수집기: 켜진 출처를 증분으로 읽고 분류해 색인에 넣는다(design §4R.4).

1. 발견: 출처마다 `discover`. 한 출처의 실패는 그 출처의 `error_code`만 남기고 계속한다.
2. 읽기: 색인 커서부터, 출처당 수집 한 번에 `budget_bytes`까지(남은 것은 다음 수집).
3. 분류: 설정 `classifier.id`(없으면 디스크립터 `format`). 해석·분류 실패 줄은 진단 이벤트.
4. 가리기: 저장 직전 `redact`(주입).
5. 색인: 이벤트 묶음 + 커서를 한 트랜잭션(`batch_size`).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from agent_console_contracts.logs import (
    LogScanReport,
    LogSettings,
    LogSourceDescriptor,
    LogSourceInfo,
    LogSourceScanResult,
    LogSourceSetting,
    LogSourceStatus,
)
from agent_console_registry import UnknownExtensionError

from ._build import build_record
from ._config import ConfigError, effective_config
from ._draft import TAG_DIAGNOSTIC, LogEventDraft
from ._index import IndexBatch, IndexRecord, LogIndex, StoredCursor
from ._projects import RepoRootResolver
from ._registries import LogRegistries
from ._source import (
    DIAGNOSTIC_META_KEY,
    ClassifyContext,
    Cursor,
    LogClassifier,
    LogSource,
    LogSourceContext,
    RawRecord,
    SourceRef,
    read_only_open,
)
from ._values import JsonValue, bounded

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_BUDGET_BYTES",
    "ERROR_INVALID_CONFIG",
    "ERROR_SOURCE_FAILED",
    "ERROR_UNKNOWN_CLASSIFIER",
    "LogIngestor",
    "source_enabled",
]

DEFAULT_BUDGET_BYTES = 8_000_000
"""출처당 수집 한 번의 읽기 예산(agent_bench 그대로 8 MB)."""

DEFAULT_BATCH_SIZE = 500
"""한 트랜잭션에 쓸 이벤트 수."""

ERROR_SOURCE_FAILED = "logs.source_failed"
ERROR_UNKNOWN_CLASSIFIER = "logs.unknown_classifier"
ERROR_INVALID_CONFIG = "logs.invalid_config"


def source_enabled(descriptor: LogSourceDescriptor, setting: LogSourceSetting | None) -> bool:
    """설정 `enabled`(생략 = 디스크립터 `default_enabled`)."""
    if setting is None or setting.enabled is None:
        return descriptor.default_enabled
    return setting.enabled


@dataclass(frozen=True, slots=True)
class _Runtime:
    source: LogSource
    classifier: LogClassifier


class _SourceFailureError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class LogIngestor:
    """로그 수집기. 서버 없이도 쓴다(스크립트·테스트·모듈 배경 작업).

    Args:
        index: 색인(`LogIndex`).
        registries: 출처·분류기 레지스트리.
        redact: 저장 직전 가리기(제목·detail·raw). None이면 가리지 않는다.
        clock: 현재 시각(epoch 초).
        budget_bytes: 출처당 수집 한 번의 읽기 예산.
        batch_size: 한 트랜잭션의 이벤트 수.
        environ: 출처에 넘길 환경 변수(프로세스 환경을 몰래 읽지 않는다).
        paths: 출처에 넘길 기본 경로(`workspace`·`state` 등).
        open_read: 읽기 전용 열기(출처·worktree 확인이 쓰는 유일한 파일 열기).
        repo_root_of: cwd → 본 저장소 경로. 없으면 `.git` 파일을 읽는 기본 구현(수집마다 캐시).
        diagnostic_category: 진단 이벤트 범주(design §4R.4: `error`).
        diagnostic_source: 진단 이벤트 `source`(계약: `diagnostic`).
    """

    def __init__(
        self,
        index: LogIndex,
        registries: LogRegistries,
        *,
        redact: Callable[[JsonValue], JsonValue] | None = None,
        clock: Callable[[], float] = time.time,
        budget_bytes: int = DEFAULT_BUDGET_BYTES,
        batch_size: int = DEFAULT_BATCH_SIZE,
        environ: Mapping[str, str] | None = None,
        paths: Mapping[str, Path] | None = None,
        open_read: Callable[[Path], BinaryIO] = read_only_open,
        repo_root_of: Callable[[str], str] | None = None,
        diagnostic_category: str = "error",
        diagnostic_source: str = "diagnostic",
    ) -> None:
        if budget_bytes <= 0 or batch_size <= 0:
            raise ValueError("budget_bytes와 batch_size는 0보다 커야 합니다")
        self._index = index
        self._registries = registries
        self._redact = redact
        self._clock = clock
        self._budget = budget_bytes
        self._batch = batch_size
        self._environ = dict(environ or {})
        self._paths = dict(paths or {})
        self._open_read = open_read
        self._repo_root_of = repo_root_of
        self._diag_category = diagnostic_category
        self._diag_source = diagnostic_source
        self._runtime: dict[str, _Runtime] = {}
        self._status: dict[str, LogSourceStatus] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    # ---------------------------------------------------------------- 출처 목록

    def add_runtime_source(self, source: LogSource, *, classifier: LogClassifier) -> None:
        """다른 모듈이 준 출처(X5r)를 더한다. 분류기는 레지스트리 없이 직접 지정한다.

        Raises:
            ValueError: 같은 id의 플러그인·런타임 출처가 이미 있다(플러그인이 이긴다).
        """
        sid = source.descriptor.id
        if sid in self._registries.sources or sid in self._runtime:
            raise ValueError(f"이미 있는 로그 출처 id: {sid}")
        self._runtime[sid] = _Runtime(source=source, classifier=classifier)

    def _all_sources(self) -> list[tuple[str, LogSource, str]]:
        out: list[tuple[str, LogSource, str]] = [
            (e.key, e.item, "plugin") for e in self._registries.sources.list()
        ]
        out += [(sid, rt.source, "runtime") for sid, rt in sorted(self._runtime.items())]
        return out

    @staticmethod
    def _settings_by_id(settings: LogSettings | None) -> dict[str, LogSourceSetting]:
        return {s.id: s for s in (settings.sources or [])} if settings else {}

    def sources(self, settings: LogSettings | None = None) -> list[LogSourceInfo]:
        """출처 목록과 상태(`GET /logs/sources`)."""
        by_id = self._settings_by_id(settings)
        out: list[LogSourceInfo] = []
        for sid, source, origin in self._all_sources():
            desc = source.descriptor.model_copy(update={"id": sid})
            status = self._status.get(sid)
            if status is None:
                status = LogSourceStatus(refs=len(self._index.list_cursors(sid)))
            out.append(
                LogSourceInfo(
                    descriptor=desc,
                    enabled=source_enabled(desc, by_id.get(sid)),
                    origin=origin,
                    status=status,
                )
            )
        return out

    # ---------------------------------------------------------------- 수집

    def _lock(self, sid: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(sid, threading.Lock())

    def scan(
        self,
        settings: LogSettings | None = None,
        *,
        source_ids: Collection[str] | None = None,
        final: bool = False,
    ) -> LogScanReport:
        """켜진 출처를 한 번 수집한다(같은 출처 수집은 겹치지 않게 잠근다).

        Args:
            settings: 로그 설정(없으면 디스크립터 기본값).
            source_ids: 주면 이 출처만(켜진 것 중에서).
            final: 끝나지 않은 마지막 줄도 읽는다.

        Returns:
            수집 결과(출처별 신규 수·오류).
        """
        started = self._clock()
        by_id = self._settings_by_id(settings)
        resolver = self._repo_root_of
        worktrees = not (
            settings is not None
            and settings.projects is not None
            and settings.projects.git_worktrees is False
        )
        if resolver is None:
            resolver = RepoRootResolver(self._open_read) if worktrees else (lambda _cwd: "")
        results: list[LogSourceScanResult] = []
        for sid, source, origin in self._all_sources():
            if source_ids is not None and sid not in source_ids:
                continue
            setting = by_id.get(sid)
            if not source_enabled(source.descriptor, setting):
                continue
            with self._lock(sid):
                results.append(self._scan_source(sid, source, origin, setting, final, resolver))
        return LogScanReport(
            started_at=started,
            finished_at=self._clock(),
            sources=results,
            new_events=sum(r.new_events for r in results),
            max_seq=self._index.max_seq(),
        )

    def _classifier(
        self, sid: str, source: LogSource, cls_setting: Mapping[str, JsonValue]
    ) -> LogClassifier:
        runtime = self._runtime.get(sid)
        if runtime is not None:
            return runtime.classifier
        cid = str(cls_setting.get("id") or source.descriptor.format)
        try:
            return self._registries.classifiers.get(cid)
        except UnknownExtensionError:
            raise _SourceFailureError(ERROR_UNKNOWN_CLASSIFIER, f"모르는 분류기: {cid}") from None

    def _scan_source(
        self,
        sid: str,
        source: LogSource,
        origin: str,
        setting: LogSourceSetting | None,
        final: bool,
        repo_root_of: Callable[[str], str],
    ) -> LogSourceScanResult:
        counters = {"new": 0, "records": 0, "diagnostics": 0, "read": 0}
        refs: list[SourceRef] = []
        offsets: dict[str, int] = {}
        error: _SourceFailureError | None = None
        try:
            config = dict(setting.config or {}) if setting else {}
            cls_setting = config.pop("classifier", None) or {}
            if not isinstance(cls_setting, Mapping):
                raise _SourceFailureError(ERROR_INVALID_CONFIG, "classifier: 객체여야 합니다")
            classifier = self._classifier(sid, source, cls_setting)
            try:
                source_config = effective_config(source.descriptor.config_schema, config)
                classifier_config = effective_config(
                    classifier.descriptor.config_schema,
                    cls_setting.get("config")
                    if isinstance(cls_setting.get("config"), Mapping)
                    else None,
                )
            except ConfigError as exc:
                raise _SourceFailureError(ERROR_INVALID_CONFIG, f"{exc.path}: {exc}") from None
            ctx = LogSourceContext(
                source_id=sid,
                config=source_config,
                environ=self._environ,
                paths=self._paths,
                open_read=self._open_read,
                now=self._clock,
            )
            try:
                refs = list(source.discover(ctx))
            except Exception as exc:
                raise _SourceFailureError(
                    ERROR_SOURCE_FAILED, f"{type(exc).__name__}: {exc}"
                ) from None
            budget = self._budget
            for ref in refs:
                stored = self._index.get_cursor(sid, ref.ref)
                offsets[ref.ref] = stored.offset if stored else 0
                if budget <= 0:
                    continue
                if (
                    stored is not None
                    and ref.size is not None
                    and stored.size == ref.size
                    and stored.mtime == ref.mtime
                    and stored.offset >= ref.size
                ):
                    continue  # 바뀌지 않음
                try:
                    budget = self._read_ref(
                        sid,
                        source,
                        classifier,
                        ref,
                        stored,
                        ctx,
                        classifier_config,
                        budget,
                        final,
                        repo_root_of,
                        counters,
                        offsets,
                    )
                except Exception as exc:  # 단위 하나의 실패(파일이 사라짐 등)는 다음 단위로
                    error = _SourceFailureError(
                        ERROR_SOURCE_FAILED, f"{ref.ref}: {type(exc).__name__}: {exc}"
                    )
        except _SourceFailureError as exc:
            error = exc
        pending = sum(
            max(0, (r.size or 0) - offsets.get(r.ref, 0)) for r in refs if r.size is not None
        )
        message = None
        if error is not None:
            message = str(error)
            if self._redact is not None:
                redacted = self._redact(message)
                message = redacted if isinstance(redacted, str) else message
        self._status[sid] = LogSourceStatus(
            last_scan_at=self._clock(),
            refs=len(refs) if refs or error is None else len(self._index.list_cursors(sid)),
            pending_bytes=pending if refs else None,
            error_code=error.code if error else None,
        )
        return LogSourceScanResult(
            source_id=sid,
            new_events=counters["new"],
            error_code=error.code if error else None,
            message=message,
            refs=len(refs),
            read_bytes=counters["read"],
            records=counters["records"],
            diagnostics=counters["diagnostics"],
            pending_bytes=pending if refs else None,
        )

    def _read_ref(
        self,
        sid: str,
        source: LogSource,
        classifier: LogClassifier,
        ref: SourceRef,
        stored: StoredCursor | None,
        ctx: LogSourceContext,
        classifier_config: Mapping[str, JsonValue],
        budget: int,
        final: bool,
        repo_root_of: Callable[[str], str],
        counters: dict[str, int],
        offsets: dict[str, int],
    ) -> int:
        cursor = Cursor(offset=stored.offset, state=dict(stored.state)) if stored else Cursor()
        cctx = ClassifyContext(source_id=sid, ref=ref, config=classifier_config)
        while budget > 0:
            result = source.read(ref, cursor, ctx, budget=budget, final=final)
            records: list[IndexRecord] = []
            for raw in result.records:
                counters["records"] += 1
                records.extend(self._records(sid, raw, classifier, cctx, repo_root_of, counters))
            changed = (
                stored is None
                or result.cursor.offset != stored.offset
                or dict(result.cursor.state) != dict(stored.state)
                or stored.size != ref.size
                or stored.mtime != ref.mtime
            )
            new_cursor = StoredCursor(
                source=sid,
                ref=ref.ref,
                offset=result.cursor.offset,
                size=ref.size,
                mtime=ref.mtime,
                state=dict(result.cursor.state),
                updated_at=self._clock(),
            )
            chunks = [records[i : i + self._batch] for i in range(0, len(records), self._batch)]
            if not chunks and changed:
                chunks = [[]]
            for i, chunk in enumerate(chunks):
                last = i == len(chunks) - 1
                res = self._index.write(
                    IndexBatch(records=chunk, cursors=[new_cursor] if last and changed else [])
                )
                counters["new"] += res.inserted
            stored = new_cursor
            offsets[ref.ref] = result.cursor.offset
            used = max(0, result.read_bytes)
            counters["read"] += used
            budget -= used
            cursor = result.cursor
            if result.exhausted or used == 0:
                break
        return budget

    def _diagnostic(self, raw: RawRecord, title: str, error: str, sid: str) -> LogEventDraft:
        def meta_str(key: str) -> str:
            value = raw.meta.get(key)
            return value if isinstance(value, str) else ""

        return LogEventDraft(
            category=self._diag_category,
            title=title,
            status="warning",
            thread=meta_str("thread"),
            session=meta_str("session"),
            cwd=meta_str("cwd"),
            tags=(TAG_DIAGNOSTIC,),
            detail={"source_id": sid, "error": error, "original": bounded(raw.data)},
            raw=raw.data,
        )

    def _records(
        self,
        sid: str,
        raw: RawRecord,
        classifier: LogClassifier,
        cctx: ClassifyContext,
        repo_root_of: Callable[[str], str],
        counters: dict[str, int],
    ) -> list[IndexRecord]:
        event_source: str | None = None
        problem = raw.meta.get(DIAGNOSTIC_META_KEY)
        if isinstance(problem, str):
            drafts = [self._diagnostic(raw, "로그 형식 해석 실패", problem, sid)]
            event_source = self._diag_source
        else:
            try:
                drafts = list(classifier.classify(raw, cctx))
            except Exception as exc:
                drafts = [
                    self._diagnostic(raw, "로그 분류 실패", f"{type(exc).__name__}: {exc}", sid)
                ]
                event_source = self._diag_source
        if event_source is not None:
            counters["diagnostics"] += 1
        now = self._clock()
        return [
            build_record(
                d,
                source_id=sid,
                event_source=event_source,
                origin=raw.origin,
                offset=raw.offset,
                index=i,
                observed_at=now,
                repo_root=repo_root_of(d.cwd) if d.cwd else "",
                redact=self._redact,
                generation=raw.generation,
            )
            for i, d in enumerate(drafts)
        ]
