"""프로필 카탈로그 서비스(포트 ``architecture.catalog``의 구현).

패키지 기본 프로필 → X23 플러그인 프로필 → 사용자 설정(워크스페이스 ``architecture`` 섹션)을
``merge_profiles``로 합치고, 프로필마다 검사 결과를 붙여 둔다. 입력(설정 원문·플러그인 목록·연산자
목록)이 바뀌면 다시 계산한다(지문 비교, 요청마다 싸게 확인).

로그·실행을 모른다. 투영은 호출자가 넘긴 이벤트로만 한다(단독 투영 경로, 로그 연동 모듈).
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from pydantic import ValidationError

from agent_console_architecture import (
    ProfileCatalog,
    ProfileEntry,
    ProfileSource,
    check_profile_data,
    merge_profiles,
    profile_issues,
    project_architecture,
)
from agent_console_conditions import ConditionOperator
from agent_console_contracts import Issue
from agent_console_contracts.architecture import (
    ArchitectureNote,
    ArchitectureProfile,
    ArchitectureProfileCheckRequest,
    ArchitectureProfileCheckResult,
    ArchitectureProfileDetail,
    ArchitectureProfileInfo,
    ArchitectureProfileList,
    ArchitectureProjectRequest,
    ArchitectureSettings,
    ArchitectureView,
)
from agent_console_contracts.logs import LogEvent, TokenSample

from .errors import ProfileNotFoundError, ScopeTooLargeError
from .ports import ProfileCheck

_log = logging.getLogger(__name__)

SECTION_KEY: Final = "architecture"
"""워크스페이스 설정에서 이 모듈이 소유하는 섹션 이름(설정 문서의 최상위 키)."""

SETTINGS_INVALID: Final = "architecture.settings_invalid"
"""``server.warnings`` 이슈 코드: 저장된 ``architecture`` 섹션 일부가 형식에 맞지 않아 그 부분을
빼고 썼다. ``path`` = 설정 문서 기준 위치."""

INLINE_PROFILE_ID: Final = "inline"
"""인라인 프로필에 id를 주지 않았을 때 쓰는 id(선택 필터 문자열에 쓰인다)."""

type SettingsReader = Callable[[], Any]
"""``architecture`` 섹션 원문(매핑, 없으면 None)을 돌려주는 함수."""


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _invalid(path: str, exc: ValidationError | None, message: str) -> Issue:
    count = len(exc.errors()) if exc is not None else 0
    return Issue(
        severity="warning",
        code=SETTINGS_INVALID,
        message=message,
        path=path,
        details={"errors": count},
    )


def parse_user_settings(
    raw: Any, *, base_path: str = f"/{SECTION_KEY}"
) -> tuple[ArchitectureSettings, list[Issue]]:
    """설정 섹션 원문 → (``ArchitectureSettings``, 형식 문제).

    전체가 맞으면 그대로 쓴다. 틀린 곳이 있으면 맞는 부분만 남긴다: 최상위 키는 키마다, 프로필은
    id마다 따로 검증하고 틀린 것은 빼고 문제로 알린다(같은 id의 기본·플러그인 프로필이 그대로
    남는다). 예외를 내지 않는다(설정 파일을 손으로 고쳐 깨뜨려도 구조도 화면은 동작해야 한다).

    Args:
        raw: 섹션 원문(None = 섹션 없음).
        base_path: 문제 위치 접두(설정 문서 기준 JSON Pointer).

    Returns:
        (설정, 문제 목록). 문제는 모두 ``warning``이고 메시지에 값 원문이 없다.
    """
    if raw is None:
        return ArchitectureSettings(), []
    if isinstance(raw, ArchitectureSettings):
        return raw, []
    if not isinstance(raw, Mapping):
        return ArchitectureSettings(), [
            _invalid(base_path, None, "구조도 설정이 객체가 아니어서 기본값을 씁니다")
        ]
    try:
        return ArchitectureSettings.model_validate(dict(raw)), []
    except ValidationError:
        pass
    issues: list[Issue] = []
    kept: dict[str, Any] = {}
    profiles_key = "profiles"
    for key, value in raw.items():
        name = str(key)
        if name == profiles_key:
            continue
        try:
            ArchitectureSettings.model_validate({name: value})
        except ValidationError as exc:
            issues.append(
                _invalid(
                    f"{base_path}/{_escape(name)}",
                    exc,
                    f"구조도 설정 {name!r} 값이 형식에 맞지 않아 기본값을 씁니다",
                )
            )
            continue
        kept[name] = value
    profiles_raw = raw.get(profiles_key)
    if profiles_raw is not None and not isinstance(profiles_raw, Mapping):
        issues.append(
            _invalid(
                f"{base_path}/{profiles_key}",
                None,
                "구조도 프로필 목록이 객체가 아니어서 사용자 프로필 없이 씁니다",
            )
        )
    elif isinstance(profiles_raw, Mapping):
        profiles: dict[str, Any] = {}
        for pid, body in profiles_raw.items():
            name = str(pid)
            if body is None:
                profiles[name] = None
                continue
            try:
                profiles[name] = ArchitectureProfile.model_validate(body)
            except ValidationError as exc:
                issues.append(
                    _invalid(
                        f"{base_path}/{profiles_key}/{_escape(name)}",
                        exc,
                        f"구조도 프로필 {name!r}이(가) 형식에 맞지 않아 빼고 씁니다"
                        "(같은 id의 기본 프로필이 있으면 그것을 씁니다)",
                    )
                )
        kept[profiles_key] = profiles
    try:
        return ArchitectureSettings.model_validate(kept), issues
    except ValidationError as exc:  # pragma: no cover - 키마다 검증했으므로 오지 않는다
        return ArchitectureSettings(), [*issues, _invalid(base_path, exc, "구조도 설정 오류")]


def section_of(document: Any, key: str = SECTION_KEY) -> Any:
    """워크스페이스 설정(모델 또는 매핑)에서 섹션 원문을 꺼낸다. 없으면 None.

    공통 설정 모델(``WorkspaceSettings``)은 이 섹션을 필드로 두지 않고 모르는 키로 보존한다
    (design §5.5R.2.4 구현 메모).
    """
    if document is None:
        return None
    if isinstance(document, Mapping):
        return document.get(key)
    extra = getattr(document, "model_extra", None)
    if isinstance(extra, Mapping) and key in extra:
        return extra[key]
    return getattr(document, key, None)


def _fingerprint(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):  # pragma: no cover - default=repr가 받는다
        return repr(value)


def _extra_issues(
    checks: Sequence[ProfileCheck], profile: ArchitectureProfile, profile_id: str | None
) -> list[Issue]:
    """검사 보탬(X32) 결과를 모은다. 예외를 낸 검사는 건너뛴다(다른 검사·기본 검사는 그대로)."""
    issues: list[Issue] = []
    for check in checks:
        try:
            issues.extend(check.check(profile, profile_id))
        except Exception:
            _log.warning("구조도 프로필 검사 보탬이 실패해 건너뜁니다: %r", check, exc_info=True)
    return issues


@dataclass(frozen=True, slots=True)
class CatalogState:
    """한 시점의 병합 결과(불변).

    Attributes:
        catalog: 병합된 프로필 목록.
        problems: 프로필 id → 검사 문제(켜진 것과 끈 것 모두).
        settings: 해석한 사용자 설정.
        settings_issues: 사용자 설정 형식 문제(``server.warnings``로 알린다).
        operators: 이 상태를 만들 때 쓴 조건 연산자.
    """

    catalog: ProfileCatalog
    problems: Mapping[str, tuple[Issue, ...]] = field(default_factory=dict)
    settings: ArchitectureSettings = field(default_factory=ArchitectureSettings)
    settings_issues: tuple[Issue, ...] = ()
    operators: Mapping[str, ConditionOperator] = field(default_factory=dict)

    def info(self, entry: ProfileEntry) -> ArchitectureProfileInfo:
        """목록 항목(검사 문제 수 포함)."""
        return entry.info(issues=len(self.problems.get(entry.id, ())))

    def find(self, profile_id: str) -> ProfileEntry | None:
        """켜진 프로필, 없으면 끈 프로필에서 찾는다."""
        found = self.catalog.get(profile_id)
        if found is not None:
            return found
        return next((e for e in self.catalog.disabled if e.id == profile_id), None)


class ArchitectureCatalogService:
    """병합된 프로필·연산자·검사·투영(포트 ``architecture.catalog``).

    외부 의존은 모두 함수로 받는다(부를 때마다 읽는다 — 설정·플러그인이 바뀌면 다음 요청에 반영).

    Args:
        defaults: 패키지 기본 프로필을 돌려주는 함수(보통 ``load_default_profiles``).
        plugins: 플러그인 프로필 묶음을 돌려주는 함수(보통 ``plugin_sources(registry)``).
        settings: 사용자 설정 섹션 원문을 돌려주는 함수. None이면 기본 설정.
        operators: 조건 연산자를 돌려주는 함수(X22).
        max_request_events: 단독 투영 이벤트 상한.
        max_scope_events: 로그 범위 투영 상한(연동 모듈이 쓴다).
        filters: 하위 구조도가 쓸 수 있는 필터 이름(검사용). None이면 보지 않는다.
        checks: 검사 보탬(X32 ``architecture.profile_checks``)을 돌려주는 함수(부를 때마다 읽는다).
            결과는 기본 검사 뒤에 붙는다. 예외를 낸 검사는 건너뛴다(로그에만 남긴다).
    """

    def __init__(
        self,
        *,
        defaults: Callable[[], Mapping[str, ArchitectureProfile]],
        plugins: Callable[[], Sequence[ProfileSource]] = list,
        settings: SettingsReader | None = None,
        operators: Callable[[], Mapping[str, ConditionOperator]],
        max_request_events: int = 20_000,
        max_scope_events: int = 100_000,
        filters: Collection[str] | None = None,
        checks: Callable[[], Sequence[ProfileCheck]] = tuple,
    ) -> None:
        self._defaults = defaults
        self._checks = checks
        self._plugins = plugins
        self._settings = settings
        self._operators = operators
        self._filters = filters
        self.max_request_events = max_request_events
        self.max_scope_events = max_scope_events
        self._lock = threading.Lock()
        self._key: tuple[Any, ...] | None = None
        self._state: CatalogState | None = None
        self._default_profiles: Mapping[str, ArchitectureProfile] | None = None

    # ------------------------------------------------------------------ 상태
    def _read_settings(self) -> Any:
        if self._settings is None:
            return None
        return self._settings()

    def state(self) -> CatalogState:
        """지금 병합 결과. 입력이 바뀌지 않았으면 이전 결과를 그대로 준다."""
        raw = self._read_settings()
        sources = list(self._plugins())
        operators = dict(self._operators())
        checks = tuple(self._checks())
        key = (
            _fingerprint(raw),
            tuple((s.origin, id(s), tuple(s.profiles)) for s in sources),
            tuple(sorted((name, id(op)) for name, op in operators.items())),
            tuple(id(c) for c in checks),
        )
        with self._lock:
            if self._state is not None and key == self._key:
                return self._state
            if self._default_profiles is None:
                self._default_profiles = dict(self._defaults())
            settings, settings_issues = parse_user_settings(raw)
            catalog = merge_profiles(self._default_profiles, sources, settings)
            problems: dict[str, tuple[Issue, ...]] = {}
            for entry in [*catalog.entries.values(), *catalog.disabled]:
                problems[entry.id] = (
                    *profile_issues(
                        entry.profile,
                        operators=operators,
                        filters=self._filters,
                        profile_id=entry.id,
                    ),
                    *_extra_issues(checks, entry.profile, entry.id),
                )
            state = CatalogState(
                catalog=catalog,
                problems=problems,
                settings=settings,
                settings_issues=tuple(settings_issues),
                operators=operators,
            )
            self._state, self._key = state, key
            return state

    def catalog(self) -> ProfileCatalog:
        """병합된 프로필 목록(``ProfileCatalog``)."""
        return self.state().catalog

    def operators(self) -> Mapping[str, ConditionOperator]:
        """조건 연산자(X22)."""
        return self.state().operators

    def pick(self, requested: str | None = None) -> tuple[ProfileEntry, ArchitectureNote | None]:
        """그릴 프로필을 고른다(없는 id면 기본 프로필 + 대체 안내).

        Raises:
            ProfileNotFoundError: 프로필이 하나도 없을 때.
        """
        entry, note = self.catalog().pick(requested)
        if entry is None:
            raise ProfileNotFoundError(requested)
        return entry, note

    def warnings(self) -> list[Issue]:
        """``server.warnings``: 사용자 설정 형식 문제. 읽기 실패는 조용히 빈 목록."""
        try:
            return list(self.state().settings_issues)
        except Exception:  # 손상된 설정 파일: 정의 모듈이 따로 알린다
            return []

    # ------------------------------------------------------------------ REST 모양
    def profile_list(self) -> ArchitectureProfileList:
        """``GET /architecture/profiles``: 켜진 프로필(병합 순서) 뒤에 끈 프로필(``disabled``)."""
        state = self.state()
        catalog = state.catalog
        infos = [state.info(e) for e in catalog.entries.values()]
        infos += [state.info(e) for e in catalog.disabled]
        return ArchitectureProfileList(
            profiles=infos,
            default_profile=catalog.default_profile,
            include_defaults=catalog.include_defaults,
        )

    def profile_detail(self, profile_id: str) -> ArchitectureProfileDetail:
        """``GET /architecture/profiles/{id}``: 목록 항목 + 본문 + 검사 결과.

        Raises:
            ProfileNotFoundError: 켜진 것·끈 것 어디에도 없을 때.
        """
        state = self.state()
        entry = state.find(profile_id)
        if entry is None:
            raise ProfileNotFoundError(profile_id)
        info = state.info(entry)
        return ArchitectureProfileDetail(
            **info.model_dump(),
            profile=entry.profile,
            problems=list(state.problems.get(entry.id, ())),
        )

    def check(self, request: ArchitectureProfileCheckRequest) -> ArchitectureProfileCheckResult:
        """``POST /architecture/profiles/check``: 형식 오류도 문제로 알린다(저장을 막지 않는다)."""
        issues = check_profile_data(
            request.profile,
            operators=self.operators(),
            filters=self._filters,
            profile_id=request.id,
        )
        checks = tuple(self._checks())
        if checks:
            try:
                profile = ArchitectureProfile.model_validate(request.profile)
            except ValidationError:
                pass  # 형식 오류는 위 검사가 ``architecture.invalid``로 알렸다
            else:
                issues.extend(_extra_issues(checks, profile, request.id))
        return ArchitectureProfileCheckResult(issues=issues)

    # ------------------------------------------------------------------ 투영
    def ensure_within(self, events: int, limit: int | None) -> None:
        """이벤트 수가 상한 안인지 본다.

        Raises:
            ScopeTooLargeError: ``limit``이 있고 넘을 때.
        """
        if limit is not None and events > limit:
            raise ScopeTooLargeError(events, limit)

    def project(
        self,
        events: Sequence[LogEvent],
        *,
        profile: str | None = None,
        inline: ArchitectureProfile | None = None,
        inline_id: str | None = None,
        tokens: Iterable[TokenSample] = (),
        source_kinds: Mapping[str, str] | None = None,
        error_categories: Collection[str] = frozenset(),
        max_seq: int | None = None,
        limit: int | None = None,
    ) -> ArchitectureView:
        """이벤트를 프로필로 투영한다.

        ``inline``을 주면 저장하지 않은 그 본문으로, 아니면 ``profile`` id(없으면 기본 프로필,
        없는 id면 기본 프로필 + 대체 안내)로 그린다.

        Raises:
            ScopeTooLargeError: ``limit``을 넘을 때.
            ProfileNotFoundError: 인라인 본문이 없고 프로필이 하나도 없을 때.
        """
        self.ensure_within(len(events), limit)
        notes: list[ArchitectureNote] = []
        if inline is not None:
            body, pid = inline, inline_id or INLINE_PROFILE_ID
        else:
            entry, note = self.pick(profile)
            body, pid = entry.profile, entry.id
            if note is not None:
                notes.append(note)
        return project_architecture(
            events,
            body,
            profile_id=pid,
            operators=self.operators(),
            source_kinds=source_kinds,
            tokens=tokens,
            error_categories=frozenset(error_categories),
            max_seq=max_seq,
            notes=notes,
        )

    def project_request(self, request: ArchitectureProjectRequest) -> ArchitectureView:
        """``POST /architecture/project``: 본문 상한은 ``max_request_events``."""
        return self.project(
            request.events,
            profile=request.profile,
            inline=request.inline,
            inline_id=request.inline_id,
            tokens=request.tokens,
            source_kinds=request.source_kinds,
            error_categories=request.error_categories,
            limit=self.max_request_events,
        )


__all__ = [
    "INLINE_PROFILE_ID",
    "SECTION_KEY",
    "SETTINGS_INVALID",
    "ArchitectureCatalogService",
    "CatalogState",
    "SettingsReader",
    "parse_user_settings",
    "section_of",
]
