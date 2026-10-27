"""질의 필터(`LogFilter`), 질의 맥락(`QueryContext`), 질의 스키마(design §4R.6·§4R.10).

필터·차원·지표 이름은 열린 문자열이지만 질의 엔진이 아는 것만 받는다. 모르는 이름은
`LogQueryError(path)`이고 모듈은 422 `validation_failed`(`details.path`)로 답한다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field, fields, replace
from datetime import tzinfo
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent_console_contracts.logs import (
    LogDimensionInfo,
    LogEvent,
    LogFilterFieldInfo,
    LogMetricInfo,
    LogProjectSettings,
    LogQuerySchema,
    LogSettings,
    LogTaxonomy,
)

from ._projects import DEFAULT_UNGROUPED_LABEL
from ._taxonomy import error_categories, hidden_categories, load_default_taxonomy, merge_taxonomy
from ._titles import (
    DEFAULT_SESSION_TITLE_RULES,
    SessionTitleRule,
    load_default_session_title_rules,
)
from ._values import JsonValue, timestamp

__all__ = [
    "DIMENSIONS",
    "FILTER_FIELDS",
    "MAX_LIMIT",
    "MAX_Q",
    "METRICS",
    "EventPredicate",
    "LogFilter",
    "LogQueryError",
    "LogScope",
    "QueryContext",
    "parse_log_filter",
    "parse_tz",
    "query_context",
    "query_schema",
    "require_refined",
]

MAX_LIMIT = 200
"""페이지 크기 상한."""

MAX_Q = 500
"""검색어 길이 상한(넘으면 자른다)."""


class LogQueryError(ValueError):
    """모르는 필터·차원·지표, 형식이 틀린 값. `path`는 문제 위치(예: `filter.foo`, `metric`)."""

    def __init__(self, message: str, path: str) -> None:
        super().__init__(message)
        self.path = path


@dataclass(frozen=True, slots=True)
class LogFilter:
    """모든 목록 공통 필터. 값 필터는 여러 값(OR), 필드끼리는 AND.

    Attributes:
        category: 범주·태그(`log_tags`).
        agent: actor·from·to 중 하나. `from_`·`to`: 그쪽만.
        project: 프로젝트 묶음 id(`"~ungrouped"` = 묶기 규칙에 맞지 않음).
        since·until: 시각(epoch 초, 이벤트 시각 없으면 색인 시각). `since <= t < until`.
        thread: thread id(여러 값, 레인 필터).
        q: 검색어(대소문자 무시 부분 일치, 원문 `raw` 제외, 500자).
        scope: 범위 `<종류>:<값>`(X27). 질의 전에 `LogQueryExtensions.refine`이 세션·run_id
            합집합(`QueryContext.scope`)으로 푼다. 풀지 않은 채 색인에 넘기면 `LogQueryError`.
        max_seq: 이 seq 이하 이벤트만(수집 중에도 같은 경계로 센다).
        extra: 확장 필터(X28) 값 `((이름, 값들), …)`(이름 순). 판정 함수는
            `QueryContext.predicates`로 들어온다.
        order: seq 기준 정렬. cursor: 키셋 커서(마지막 seq 문자열).
    """

    category: tuple[str, ...] = ()
    source: tuple[str, ...] = ()
    session: tuple[str, ...] = ()
    project: tuple[str, ...] = ()
    cwd: tuple[str, ...] = ()
    agent: tuple[str, ...] = ()
    thread: tuple[str, ...] = ()
    from_: tuple[str, ...] = ()
    to: tuple[str, ...] = ()
    via: tuple[str, ...] = ()
    tool: tuple[str, ...] = ()
    call_id: tuple[str, ...] = ()
    model: tuple[str, ...] = ()
    run_id: tuple[str, ...] = ()
    stage: tuple[str, ...] = ()
    status: tuple[str, ...] = ()
    since: float | None = None
    until: float | None = None
    q: str = ""
    scope: str | None = None
    max_seq: int | None = None
    extra: tuple[tuple[str, tuple[str, ...]], ...] = ()
    order: Literal["asc", "desc"] = "asc"
    limit: int = 50
    cursor: str | None = None

    def with_(self, **changes: object) -> LogFilter:
        """일부 필드를 바꾼 사본."""
        return replace(self, **changes)  # type: ignore[arg-type]

    def extra_values(self) -> dict[str, tuple[str, ...]]:
        """확장 필터 값(이름 → 값들)."""
        return dict(self.extra)


type EventPredicate = Callable[[LogEvent], bool]
"""이벤트 판정 함수(X28). 본문(`detail`·`raw`)이 있는 이벤트를 받는다. 예외를 내지 않아야 한다."""


@dataclass(frozen=True, slots=True)
class LogScope:
    """범위 해석 결과(X27): 세션과 run_id의 합집합.

    이벤트는 세션 또는 run_id가 들면 범위 안이다(둘 다 비면 범위에 아무것도 없다).
    """

    sessions: frozenset[str] = frozenset()
    run_ids: frozenset[str] = frozenset()

    @classmethod
    def of(cls, sessions: Iterable[str] = (), run_ids: Iterable[str] = ()) -> LogScope:
        """빈 문자열을 뺀 범위."""
        return cls(frozenset(s for s in sessions if s), frozenset(r for r in run_ids if r))

    def contains(self, session: str, run_id: str) -> bool:
        """세션 또는 run_id가 범위에 드는지."""
        return (bool(session) and session in self.sessions) or (
            bool(run_id) and run_id in self.run_ids
        )


_VALUE_FIELDS: dict[str, str] = {
    f.name.rstrip("_"): f.name for f in fields(LogFilter) if f.type == "tuple[str, ...]"
}
"""필터 이름(`from`) → 필드 이름(`from_`)."""

_NO_SPLIT = frozenset({"cwd", "q"})
"""쉼표로 나누지 않는 필드(경로·검색어)."""

FILTER_FIELDS: tuple[LogFilterFieldInfo, ...] = (
    LogFilterFieldInfo(id="category", title="범주", multi=True),
    LogFilterFieldInfo(id="source", title="출처", multi=True),
    LogFilterFieldInfo(id="session", title="세션", multi=True),
    LogFilterFieldInfo(id="project", title="프로젝트", multi=True),
    LogFilterFieldInfo(id="cwd", title="작업 폴더", multi=False),
    LogFilterFieldInfo(id="agent", title="에이전트", multi=True),
    LogFilterFieldInfo(
        id="thread", title="스레드", multi=True, description="이벤트 thread id(레인)."
    ),
    LogFilterFieldInfo(id="from", title="보낸 쪽", multi=True),
    LogFilterFieldInfo(id="to", title="받는 쪽", multi=True),
    LogFilterFieldInfo(id="via", title="전달 수단", multi=True),
    LogFilterFieldInfo(id="tool", title="도구", multi=True),
    LogFilterFieldInfo(id="call_id", title="호출 id", multi=True),
    LogFilterFieldInfo(id="model", title="모델", multi=True),
    LogFilterFieldInfo(id="run_id", title="실행", multi=True),
    LogFilterFieldInfo(id="stage", title="단계", multi=True),
    LogFilterFieldInfo(id="status", title="상태", multi=True),
    LogFilterFieldInfo(id="since", title="시작 시각"),
    LogFilterFieldInfo(id="until", title="끝 시각"),
    LogFilterFieldInfo(id="q", title="검색어"),
    LogFilterFieldInfo(
        id="scope",
        title="범위",
        description="`<종류>:<값>`. 종류는 등록된 범위 종류(확장)이고 모르면 422.",
    ),
    LogFilterFieldInfo(
        id="max_seq", title="최대 seq", description="이 seq 이하 이벤트만(수집 중 경계)."
    ),
    LogFilterFieldInfo(id="order", title="정렬"),
    LogFilterFieldInfo(id="limit", title="개수"),
    LogFilterFieldInfo(id="cursor", title="커서"),
)
"""`LogFilter`가 받는 이름(`GET /logs/schema`의 filters)."""

DIMENSIONS: tuple[LogDimensionInfo, ...] = (
    LogDimensionInfo(id="project", title="프로젝트"),
    LogDimensionInfo(id="cwd", title="작업 폴더"),
    LogDimensionInfo(id="session", title="세션"),
    LogDimensionInfo(id="agent", title="에이전트"),
    LogDimensionInfo(id="model", title="모델"),
    LogDimensionInfo(id="day", title="날짜", kind="time"),
    LogDimensionInfo(id="hour", title="시간", kind="time"),
    LogDimensionInfo(id="source", title="출처"),
    LogDimensionInfo(id="category", title="범주"),
    LogDimensionInfo(id="tool", title="도구"),
    LogDimensionInfo(id="tag", title="태그"),
)
"""집계 엔진이 아는 차원."""

METRICS: tuple[LogMetricInfo, ...] = (
    LogMetricInfo(id="events", title="이벤트 수", unit="count"),
    LogMetricInfo(id="tool_calls", title="도구 호출 수", unit="count"),
    LogMetricInfo(id="errors", title="오류 수", unit="count"),
    LogMetricInfo(id="tokens.input", title="입력 토큰", unit="tokens"),
    LogMetricInfo(id="tokens.output", title="출력 토큰", unit="tokens"),
    LogMetricInfo(id="tokens.cache_read", title="캐시 읽기 토큰", unit="tokens"),
    LogMetricInfo(id="tokens.cache_creation", title="캐시 쓰기 토큰", unit="tokens"),
    LogMetricInfo(id="tokens.total", title="전체 토큰", unit="tokens"),
    LogMetricInfo(id="duration_ms.sum", title="소요 시간 합", unit="ms"),
    LogMetricInfo(id="duration_ms.avg", title="소요 시간 평균", unit="ms"),
    LogMetricInfo(id="duration_ms.p95", title="소요 시간 p95", unit="ms"),
)
"""집계 엔진이 아는 지표."""


def query_schema(extra_filters: Iterable[LogFilterFieldInfo] = ()) -> LogQuerySchema:
    """`GET /logs/schema` 응답(엔진이 아는 차원·지표·필터 + 확장 필터 `extra_filters`)."""
    return LogQuerySchema(
        dimensions=list(DIMENSIONS),
        metrics=list(METRICS),
        filters=[*FILTER_FIELDS, *extra_filters],
    )


def _values(name: str, value: JsonValue) -> tuple[str, ...]:
    items = value if isinstance(value, list | tuple) else [value]
    out: list[str] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, dict | list):
            raise LogQueryError(f"{name}: 문자열이어야 합니다", name)
        s = str(item)
        parts = [s] if name in _NO_SPLIT else s.split(",")
        out.extend(p.strip() for p in parts if p.strip())
    return tuple(dict.fromkeys(out))


def _blank(value: JsonValue) -> bool:
    """빈 문자열(또는 빈 문자열만 든 목록)인지. None·빈 목록은 아니다."""
    items = value if isinstance(value, list | tuple) else [value]
    return bool(items) and all(isinstance(item, str) and not item.strip() for item in items)


def _single(value: JsonValue) -> JsonValue:
    if isinstance(value, list | tuple):
        return value[-1] if value else None
    return value


def _time(name: str, value: JsonValue) -> float | None:
    value = _single(value)
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass
    parsed = timestamp(value)
    if parsed is None:
        raise LogQueryError(f"{name}: 시각(epoch 초 또는 ISO 8601)이 아닙니다", name)
    return parsed


def _scope(value: JsonValue, where: str) -> str | None:
    value = _single(value)
    if value is None or value == "":
        return None
    if isinstance(value, dict | list):
        raise LogQueryError("scope: 문자열이어야 합니다", where)
    s = str(value).strip()
    kind, sep, rest = s.partition(":")
    if not sep or not kind.strip() or not rest.strip():
        raise LogQueryError("scope: `<종류>:<값>` 형식이어야 합니다", where)
    return s


def _max_seq(value: JsonValue, where: str) -> int | None:
    value = _single(value)
    if value is None or value == "":
        return None
    try:
        n = int(str(value))
    except ValueError:
        raise LogQueryError("max_seq: 정수가 아닙니다", where) from None
    if n < 0:
        raise LogQueryError("max_seq: 0 이상이어야 합니다", where)
    return n


def parse_log_filter(
    params: Mapping[str, JsonValue], *, path: str = "", extra: Collection[str] = ()
) -> LogFilter:
    """쿼리 파라미터·JSON 객체 → `LogFilter`.

    값은 문자열·숫자·목록. 여러 값은 목록 또는 쉼표(`cwd`·`q` 제외).

    Args:
        params: 이름 → 값.
        path: 오류 위치 접두(예: `filter`).
        extra: 받을 확장 필터 이름(X28, 기본 이름과 겹치면 기본이 이긴다). 값은 여러 값(쉼표).
            빈 값(`name=`)은 버리지 않고 값 하나 `""`로 남긴다.

    Raises:
        LogQueryError: 모르는 이름, 형식이 틀린 값(`path`에 위치).
    """
    prefix = f"{path}." if path else ""
    kwargs: dict[str, object] = {}
    extras: dict[str, tuple[str, ...]] = {}
    for name, value in params.items():
        where = prefix + name
        if name in _VALUE_FIELDS:
            kwargs[_VALUE_FIELDS[name]] = _values(name, value)
        elif name in ("since", "until"):
            kwargs[name] = _time(where, value)
        elif name == "scope":
            kwargs["scope"] = _scope(value, where)
        elif name == "max_seq":
            kwargs["max_seq"] = _max_seq(value, where)
        elif name == "q":
            q = _single(value)
            kwargs["q"] = "" if q is None else str(q)[:MAX_Q]
        elif name == "order":
            order = _single(value) or "asc"
            if order not in ("asc", "desc"):
                raise LogQueryError("order: asc 또는 desc", where)
            kwargs["order"] = order
        elif name == "limit":
            try:
                limit = int(str(_single(value)))
            except ValueError:
                raise LogQueryError("limit: 정수가 아닙니다", where) from None
            kwargs["limit"] = min(MAX_LIMIT, max(1, limit))
        elif name == "cursor":
            cursor = _single(value)
            if cursor in (None, ""):
                continue
            if not str(cursor).isdigit():
                raise LogQueryError("cursor: 형식이 틀렸습니다", where)
            kwargs["cursor"] = str(cursor)
        elif name in extra:
            values = _values(name, value)
            if values:
                extras[name] = values
            elif _blank(value):
                # 확장 필터의 빈 값(`name=`)은 "빈 값과 같음"이라는 값이다(예: 이름 없는 묶음
                # `arch_group=`). 기본 필드와 달리 버리지 않는다.
                extras[name] = ("",)
        else:
            raise LogQueryError(f"모르는 필터 이름: {name}", where)
    if extras:
        kwargs["extra"] = tuple(sorted(extras.items()))
    return LogFilter(**kwargs)  # type: ignore[arg-type]


def parse_tz(name: str | None) -> tzinfo | None:
    """IANA 시간대 이름 → tzinfo(None = 서버 로컬).

    Raises:
        LogQueryError: 모르는 시간대(`tz`).
    """
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise LogQueryError(f"모르는 시간대: {name}", "tz") from None


@dataclass(frozen=True, slots=True)
class QueryContext:
    """질의 때 적용하는 사용자 데이터(색인을 다시 만들지 않고 바로 반영된다).

    Attributes:
        projects: 프로젝트 묶기 규칙.
        error_categories: 오류로 셀 범주(분류 체계 `tone == "danger"`, F-25).
        hidden_categories: 타임라인에서 숨길 범주(`visible: false`).
        tz: `day`·`hour` 차원 시간대(None = 서버 로컬).
        pair_start_stages·pair_end_stages: 소요 시간 짝(같은 thread+call_id)의 단계 이름.
        ungrouped_label: 정책 `none` 묶음 표시 이름.
        session_title_rules: 세션 제목 순위 규칙(위에서부터, 후보가 있는 첫 규칙이 이긴다, 5R.19).
        scope: 필터 `scope`의 해석 결과(X27, `LogQueryExtensions.refine`이 채운다).
        predicates: 확장 필터의 이벤트 판정 함수(X28, 모두 참이어야 맞음).
        extra_names: 집계 요청 필터(`LogAggregateRequest.filter`)를 읽을 때 받을 확장 필터 이름.
    """

    projects: LogProjectSettings | None = None
    error_categories: frozenset[str] = frozenset()
    hidden_categories: frozenset[str] = frozenset()
    tz: tzinfo | None = None
    pair_start_stages: frozenset[str] = field(default_factory=lambda: frozenset({"start"}))
    pair_end_stages: frozenset[str] = field(default_factory=lambda: frozenset({"complete"}))
    ungrouped_label: str = DEFAULT_UNGROUPED_LABEL
    session_title_rules: tuple[SessionTitleRule, ...] = DEFAULT_SESSION_TITLE_RULES
    scope: LogScope | None = None
    predicates: tuple[EventPredicate, ...] = ()
    extra_names: frozenset[str] = frozenset()


def require_refined(flt: LogFilter, ctx: QueryContext) -> None:
    """`scope`·확장 필터가 질의 맥락으로 풀렸는지 확인한다(색인 구현이 질의 앞에서 부른다).

    Raises:
        LogQueryError: `flt.scope`가 있는데 `ctx.scope`가 없거나, 확장 필터가 있는데 판정 함수가
            없다(풀지 않은 필터를 조용히 무시하지 않는다).
    """
    if flt.scope is not None and ctx.scope is None:
        raise LogQueryError("scope: 범위를 해석하지 않았습니다(등록된 범위 종류 없음)", "scope")
    if flt.extra and not ctx.predicates:
        name = flt.extra[0][0]
        raise LogQueryError(f"확장 필터를 해석하지 않았습니다: {name}", name)


def query_context(
    settings: LogSettings | None = None,
    *,
    base_taxonomy: LogTaxonomy | None = None,
    tz: tzinfo | None = None,
    session_title_rules: tuple[SessionTitleRule, ...] | None = None,
) -> QueryContext:
    """설정(`WorkspaceSettings.logs`)에서 질의 맥락을 만든다.

    Args:
        settings: 로그 설정(없으면 기본값만).
        base_taxonomy: 기본 분류 체계(없으면 패키지 데이터 `default_taxonomy.yaml`).
        tz: 집계 시간대.
        session_title_rules: 세션 제목 순위 규칙(없으면 패키지 데이터
            `default_session_title_rules.yaml`).
    """
    base = base_taxonomy if base_taxonomy is not None else load_default_taxonomy()
    taxonomy = merge_taxonomy(base, settings.taxonomy if settings else None)
    rules = (
        session_title_rules
        if session_title_rules is not None
        else load_default_session_title_rules()
    )
    return QueryContext(
        projects=settings.projects if settings else None,
        error_categories=error_categories(taxonomy),
        hidden_categories=hidden_categories(taxonomy),
        tz=tz,
        session_title_rules=rules,
    )
