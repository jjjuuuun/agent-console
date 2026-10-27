"""프로필 병합: 패키지 기본 → 플러그인(X23) → 사용자 설정(design §5.5R.2.2)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from agent_console_contracts.architecture import (
    ArchitectureNote,
    ArchitectureProfile,
    ArchitectureProfileInfo,
    ArchitectureSettings,
    KnownArchitectureNoteCodes,
    KnownArchitectureOrigins,
)


@dataclass(frozen=True, slots=True)
class ProfileSource:
    """한 출처가 내는 프로필 묶음.

    Attributes:
        origin: 출처 이름(`default`, `plugin:<배포 이름>`, `user`, 또는 호출자가 정한 열린 문자열).
        profiles: id → 프로필(순서 = 목록 순서).
    """

    origin: str
    profiles: Mapping[str, ArchitectureProfile]


@dataclass(frozen=True, slots=True)
class ProfileEntry:
    """병합된 프로필 하나.

    Attributes:
        id: 프로필 id.
        profile: 프로필 본문.
        origin: 이 본문을 낸 출처.
        overrides: 같은 id의 앞 출처를 덮어썼으면 그 출처, 아니면 None.
        disabled: 사용자 설정에서 null로 끈 프로필(`ProfileCatalog.disabled`에만 있다).
    """

    id: str
    profile: ArchitectureProfile
    origin: str
    overrides: str | None = None
    disabled: bool = False

    @property
    def title(self) -> str:
        """제목(없으면 id)."""
        return self.profile.title or self.id

    def info(self, *, issues: int = 0) -> ArchitectureProfileInfo:
        """목록 항목(`ArchitectureProfileInfo`). `issues`는 호출자가 센 검사 문제 수."""
        return ArchitectureProfileInfo(
            id=self.id,
            title=self.title,
            origin=self.origin,
            overrides=self.overrides,
            disabled=self.disabled,
            issues=issues,
            cells=len(self.profile.cells),
            edges=len(self.profile.edges),
        )


@dataclass(frozen=True, slots=True)
class ProfileCatalog:
    """병합 결과. 프로필이 하나도 없어도 정상 값이다("구조도 규칙 없음").

    Attributes:
        entries: id → 병합된 프로필(병합 순서).
        disabled: 사용자 설정이 null로 지운 프로필(지우기 전 본문, `disabled=True`).
        default_profile: 먼저 열 프로필 id(설정 값이 없거나 지워졌으면 첫 프로필, 없으면 None).
        include_defaults: 병합에 쓴 기본 프로필 사용 값.
    """

    entries: Mapping[str, ProfileEntry] = field(default_factory=dict)
    disabled: tuple[ProfileEntry, ...] = ()
    default_profile: str | None = None
    include_defaults: bool = True

    def __len__(self) -> int:
        return len(self.entries)

    def ids(self) -> list[str]:
        """프로필 id(병합 순서)."""
        return list(self.entries)

    def get(self, profile_id: str) -> ProfileEntry | None:
        """id로 찾는다. 없으면 None."""
        return self.entries.get(profile_id)

    def pick(
        self, requested: str | None = None
    ) -> tuple[ProfileEntry | None, ArchitectureNote | None]:
        """그릴 프로필을 고른다. 예외를 내지 않는다.

        Args:
            requested: 요청한 id. None이면 `default_profile`.

        Returns:
            (프로필, 안내). 요청한 id가 없어 기본 프로필로 바꿨으면 안내
            `architecture.profile_fallback`을 함께 준다. 프로필이 하나도 없으면 (None, None).
        """
        if requested is not None and requested in self.entries:
            return self.entries[requested], None
        chosen = self.entries.get(self.default_profile) if self.default_profile else None
        if chosen is None:
            return None, None
        if requested is None:
            return chosen, None
        note = ArchitectureNote(
            code=KnownArchitectureNoteCodes.PROFILE_FALLBACK,
            message=f"프로필 {requested!r}이(가) 없어 {chosen.title!r}(으)로 그렸습니다",
            details={"requested": requested, "used": chosen.id},
        )
        return chosen, note


def merge_profiles(
    defaults: Mapping[str, ArchitectureProfile],
    plugins: Iterable[ProfileSource] = (),
    user: ArchitectureSettings | None = None,
    *,
    include_defaults: bool | None = None,
) -> ProfileCatalog:
    """프로필을 id 단위로 병합한다.

    순서: 패키지 기본(`include_defaults`일 때) → 플러그인(주어진 순서) → 사용자 설정
    `profiles`. 같은 id면 통째로 바꾸고(목록 위치는 처음 나온 자리), 사용자 값이 null이면 그 id를
    지운다.

    Args:
        defaults: 패키지 기본 프로필(보통 `load_default_profiles()`).
        plugins: 플러그인 프로필 묶음(보통 `plugin_sources(registry)`).
        user: 워크스페이스 설정 `architecture` 섹션. None이면 기본 설정.
        include_defaults: 주면 설정 값 대신 이 값을 쓴다.

    Returns:
        `ProfileCatalog`. 프로필이 하나도 없어도 예외 없이 빈 목록이다.
    """
    settings = user or ArchitectureSettings()
    use_defaults = settings.include_defaults if include_defaults is None else include_defaults
    entries: dict[str, ProfileEntry] = {}

    def put(pid: str, profile: ArchitectureProfile, origin: str) -> None:
        previous = entries.get(pid)
        entries[pid] = ProfileEntry(
            id=pid,
            profile=profile,
            origin=origin,
            overrides=previous.origin if previous is not None else None,
        )

    if use_defaults:
        for pid, profile in defaults.items():
            put(pid, profile, KnownArchitectureOrigins.DEFAULT)
    for source in plugins:
        for pid, profile in source.profiles.items():
            put(pid, profile, source.origin)
    disabled: list[ProfileEntry] = []
    for pid, value in settings.profiles.items():
        if value is None:
            removed = entries.pop(pid, None)
            if removed is not None:
                disabled.append(
                    ProfileEntry(
                        id=pid,
                        profile=removed.profile,
                        origin=KnownArchitectureOrigins.USER,
                        overrides=removed.origin,
                        disabled=True,
                    )
                )
            continue
        put(pid, value, KnownArchitectureOrigins.USER)
    wanted = settings.default_profile
    default_id = wanted if wanted in entries else next(iter(entries), None)
    return ProfileCatalog(
        entries=entries,
        disabled=tuple(disabled),
        default_profile=default_id,
        include_defaults=use_defaults,
    )
