"""출처 옵션(사용자 설정 `sdd.verification_sources[].options`)과 검사.

기본값은 패키지 데이터 `data/defaults.json`이고, 사용자가 준 값이 키마다 덮어쓴다. 파일 패턴은
프로젝트 폴더 기준 상대 경로만 받는다(`..`·절대 경로·드라이브·역슬래시 거부). 정규식은
`ac-safe-regex` 규칙(길이·위험 반복 거부, 매치 시간 제한)으로 검사한다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import cache
from importlib.resources import files as package_files
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from agent_console_safe_regex import SafePattern, UnsafeRegexError, compile_user_regex

__all__ = [
    "MAX_PATTERN_CHARS",
    "JUnitOptions",
    "JUnitOptionsError",
    "check_file_pattern",
    "check_options",
    "default_options",
    "parse_options",
]

MAX_PATTERN_CHARS = 512
"""파일 패턴 하나의 최대 길이."""

_WINDOWS_FORBIDDEN = frozenset('<>:"|')


class JUnitOptionsError(ValueError):
    """옵션이 틀렸다. `problems` = (옵션 위치, 이유) 목록(값 원문은 싣지 않는다)."""

    def __init__(self, problems: list[tuple[str, str]]) -> None:
        self.problems = problems
        super().__init__("; ".join(f"{where}: {why}" for where, why in problems))


def check_file_pattern(pattern: str) -> str:
    """파일 패턴이 프로젝트 폴더 안 상대 경로 모양인지 검사하고 정규화(앞의 `./` 제거)한다.

    글롭 문자 `*`·`?`·`[...]`는 구성요소 안에서, `**`는 구성요소 전체로만 쓴다(0개 이상 폴더).

    Raises:
        ValueError: 빈 값, 너무 긺, 제어 문자·역슬래시, 절대 경로, 드라이브·Windows 금지 문자,
            `.`·`..`·빈 구성요소, 구성요소 안의 `**`.
    """
    if not pattern:
        raise ValueError("파일 패턴이 비었습니다")
    if len(pattern) > MAX_PATTERN_CHARS:
        raise ValueError(f"파일 패턴이 너무 깁니다(최대 {MAX_PATTERN_CHARS}자)")
    if any(ord(ch) < 32 for ch in pattern) or "\\" in pattern:
        raise ValueError("파일 패턴에 제어 문자나 역슬래시가 있습니다")
    if pattern.startswith("/") or pattern.startswith("~"):
        raise ValueError("파일 패턴은 프로젝트 폴더 기준 상대 경로여야 합니다")
    if any(ch in _WINDOWS_FORBIDDEN for ch in pattern):
        raise ValueError("파일 패턴에 드라이브나 쓸 수 없는 문자가 있습니다")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    parts = pattern.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise ValueError("파일 패턴은 프로젝트 폴더 밖이나 빈 구성요소를 가리킬 수 없습니다")
        if "**" in part and part != "**":
            raise ValueError("'**'는 경로 구성요소 전체로만 씁니다(예: reports/**/*.xml)")
    if parts[-1] == "**":
        raise ValueError("파일 패턴은 파일 이름으로 끝나야 합니다(예: reports/**/*.xml)")
    return "/".join(parts)


FilePattern = Annotated[str, AfterValidator(check_file_pattern)]


class JUnitOptions(BaseModel):
    """검증 출처 옵션(모두 데이터). 기본값 = 패키지 데이터 `data/defaults.json`.

    Attributes:
        paths: JUnit XML 파일 패턴(프로젝트 폴더 기준, 글롭). 비면 결과 없음.
        requirement_pattern: 테스트 이름에서 요구 id를 찾는 정규식(이름 그룹 `id`가 있으면 그 값,
            없으면 매치 전체). null이면 그 스펙의 요구 id를 단어 경계로 찾는다.
        task_pattern: 테스트 이름에서 작업 키를 찾는 정규식(이름 그룹 `task` 또는 매치 전체).
            null이면 작업에 붙이지 않는다. 스펙에 없는 작업 키는 버린다.
        match_fields: 테스트 케이스에서 살펴볼 속성(`classname`·`name`, 다른 속성 이름도 된다).
        result_map: 테스트 결과(`passed`·`failed`·`error`·`skipped`) → 추적 표 결과 값.
        status_priority: 여러 테스트가 한 요구에 붙을 때 앞에 있을수록 우선(목록 밖은 맨 뒤).
        label: 결과 라벨 앞머리.
        max_files·max_file_bytes·max_dirs·max_testcases: 읽기 상한(넘으면 그만 읽는다).
        regex_timeout_ms: 정규식 매치 1회 시간 제한.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    paths: list[FilePattern] = Field(default_factory=list)
    requirement_pattern: str | None = None
    task_pattern: str | None = None
    match_fields: list[str] = Field(default_factory=list, min_length=1)
    result_map: dict[str, str] = Field(default_factory=dict)
    status_priority: list[str] = Field(default_factory=list)
    label: str = ""
    max_files: int = Field(ge=1, le=10_000)
    max_file_bytes: int = Field(ge=1, le=200_000_000)
    max_dirs: int = Field(ge=1, le=1_000_000)
    max_testcases: int = Field(ge=1, le=10_000_000)
    regex_timeout_ms: int = Field(ge=1, le=5_000)

    @field_validator("requirement_pattern")
    @classmethod
    def _req(cls, value: str | None) -> str | None:
        if value is not None:
            _compile(value, 50)
        return value

    @field_validator("task_pattern")
    @classmethod
    def _task(cls, value: str | None) -> str | None:
        if value is not None:
            _compile(value, 50)
        return value

    def requirement_regex(self) -> SafePattern | None:
        """요구 id 정규식(시간 제한 적용). null이면 None."""
        return _compile(self.requirement_pattern, self.regex_timeout_ms)

    def task_regex(self) -> SafePattern | None:
        """작업 키 정규식(시간 제한 적용). null이면 None."""
        return _compile(self.task_pattern, self.regex_timeout_ms)


def _compile(pattern: str | None, timeout_ms: int) -> SafePattern | None:
    if pattern is None:
        return None
    try:
        return compile_user_regex(pattern, timeout=timeout_ms / 1000)
    except UnsafeRegexError as exc:
        raise ValueError(f"정규식을 쓸 수 없습니다: {exc}") from None


@cache
def _defaults_text() -> str:
    return (package_files(__package__ or __name__) / "data" / "defaults.json").read_text("utf-8")


def default_options() -> dict[str, Any]:
    """패키지 기본 옵션(새 사본)."""
    loaded: dict[str, Any] = json.loads(_defaults_text())
    return loaded


def parse_options(options: Mapping[str, Any] | None) -> JUnitOptions:
    """기본값 위에 사용자 옵션을 덮어 검사한다.

    Raises:
        JUnitOptionsError: 모르는 키, 형식이 틀린 값, 폴더 밖 파일 패턴, 쓸 수 없는 정규식.
    """
    merged = default_options()
    merged.update(dict(options or {}))
    try:
        return JUnitOptions.model_validate(merged)
    except ValidationError as exc:
        problems = [
            ("/" + "/".join(str(p) for p in err["loc"]), _reason(err)) for err in exc.errors()
        ]
        raise JUnitOptionsError(problems) from None


def _reason(err: Mapping[str, Any]) -> str:
    ctx = err.get("ctx") or {}
    inner = ctx.get("error")
    return str(inner) if isinstance(inner, ValueError) else str(err.get("msg", "잘못된 값"))


def check_options(options: Mapping[str, Any] | None) -> list[tuple[str, str]]:
    """옵션 문제 목록(없으면 빈 목록). 설정을 저장하기 전 검사에 쓴다."""
    try:
        parse_options(options)
    except JUnitOptionsError as exc:
        return exc.problems
    return []
