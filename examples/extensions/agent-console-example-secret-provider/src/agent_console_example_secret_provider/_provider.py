"""로컬 파일의 `KEY=VALUE` 줄에서 비밀 값을 읽는 공급자(X10).

- 값은 이 객체 안에만 있다. 로그·예외·`repr`에는 파일 경로·줄 번호·이름 개수만 나가고 값은 나가지
  않는다(이름도 로그에 넣지 않는다 — 이름이 값의 단서가 될 수 있다).
- 파일이 없거나 읽을 수 없으면 값을 주지 않고(`None`) 경고를 한 번만 남긴다. 예외를 내지 않는다
  (다음 공급자·`SecretNotFoundError`로 이어진다).
- 파일이 바뀌면(수정 시각·크기) 다음 조회 때 다시 읽는다. 서버 재시작이 필요 없다.
- 줄 규칙(주석 표시·이름 모양·따옴표·대문자 대체·크기 상한)은 옵션 데이터(`data/defaults.json`).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections.abc import Mapping
from importlib.resources import files as package_files
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

__all__ = [
    "PROVIDER_ID",
    "EnvFileSecretProvider",
    "FileSecretProvider",
    "SecretFileSettings",
    "default_settings_data",
    "load_settings",
    "parse_secret_lines",
    "register",
]

PROVIDER_ID: Final = "example-file"
"""공급자 key = entry point 이름(`plugins.enabled`가 이 이름으로 고른다)."""

_log = logging.getLogger("agent_console_example_secret_provider")


class SecretFileSettings(BaseModel):
    """줄 규칙과 경로 환경변수 이름(기본값 `data/defaults.json` + 옵션 덮어쓰기).

    Attributes:
        path_env: 파일 경로를 담은 환경변수 이름(`EnvFileSecretProvider`가 읽는다).
        comment_prefixes: 이 문자열로 시작하는 줄은 주석.
        name_pattern: 이름 정규식(맞지 않는 줄은 건너뛰고 줄 번호만 경고).
        strip_quotes: 값 양끝의 같은 따옴표(`"`·`'`) 한 쌍을 벗긴다.
        upper_fallback: 이름이 없으면 대문자 이름으로 한 번 더 찾는다(환경변수 공급자와 같은 규칙).
        max_file_bytes: 이보다 큰 파일은 읽지 않는다.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path_env: str = Field(min_length=1)
    comment_prefixes: tuple[str, ...] = ()
    name_pattern: str = Field(min_length=1)
    strip_quotes: bool = True
    upper_fallback: bool = True
    max_file_bytes: int = Field(ge=1)

    @field_validator("name_pattern")
    @classmethod
    def _compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError("name_pattern이 정규식이 아닙니다") from exc
        return value

    @field_validator("comment_prefixes")
    @classmethod
    def _non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not p for p in value):
            raise ValueError("빈 주석 표시는 쓸 수 없습니다")
        return value


def default_settings_data() -> dict[str, Any]:
    """패키지 데이터의 기본 설정 사본."""
    raw = package_files("agent_console_example_secret_provider").joinpath("data/defaults.json")
    data: dict[str, Any] = json.loads(raw.read_text(encoding="utf-8"))
    return data


def load_settings(options: Mapping[str, Any] | None = None) -> SecretFileSettings:
    """기본값에 옵션을 덮어쓴 설정.

    Raises:
        ValueError: 옵션이 틀렸을 때(틀린 키 이름만 메시지에 넣는다).
    """
    try:
        return SecretFileSettings.model_validate({**default_settings_data(), **(options or {})})
    except ValidationError as exc:
        where = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise ValueError(f"비밀 파일 설정이 잘못됐습니다: {', '.join(where)}") from None


def parse_secret_lines(text: str, settings: SecretFileSettings) -> tuple[dict[str, str], list[int]]:
    """`KEY=VALUE` 글 → (이름 → 값, 건너뛴 줄 번호). 순수 함수, 예외 없음.

    빈 줄·주석 줄은 무시한다. `=`가 없거나 이름이 규칙에 맞지 않는 줄은 건너뛰고 번호(1부터)만
    돌려준다. 값은 첫 `=` 뒤 전부(앞뒤 공백 제외, 값 안의 `=`는 그대로). 같은 이름은 뒤 줄이 이긴다.
    """
    pattern = re.compile(settings.name_pattern)
    values: dict[str, str] = {}
    skipped: list[int] = []
    for number, raw in enumerate(text.removeprefix("﻿").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(settings.comment_prefixes):
            continue
        name, sep, value = line.partition("=")
        name = name.strip()
        if not sep or not pattern.fullmatch(name):
            skipped.append(number)
            continue
        value = value.strip()
        if (
            settings.strip_quotes
            and len(value) >= 2
            and value[0] == value[-1]
            and value[0] in "\"'"
        ):
            value = value[1:-1]
        values[name] = value
    return values, skipped


class FileSecretProvider:
    """파일 하나에서 비밀 값을 읽는 공급자(`agent_console_runtime.SecretProvider`를 만족).

    Args:
        path: 비밀 파일. None이면 값을 주지 않는다(설정되지 않음).
        settings: 줄 규칙. 없으면 기본값.
    """

    def __init__(self, path: Path | None, *, settings: SecretFileSettings | None = None) -> None:
        self._path = path
        self._settings = settings or load_settings()
        self._lock = threading.Lock()
        self._stamp: tuple[int, int] | None = None
        self._values: dict[str, str] = {}
        self._problem: str | None = None  # 마지막으로 경고한 상태(같은 경고를 되풀이하지 않음)

    @property
    def path(self) -> Path | None:
        """비밀 파일 위치(값이 아니므로 보여도 된다)."""
        return self._path

    def __repr__(self) -> str:
        return f"{type(self).__name__}(path={self._path!s}, names={len(self._values)})"

    def _warn_once(self, state: str, message: str, *args: object) -> None:
        if self._problem != state:
            self._problem = state
            _log.warning(message, *args)

    def _refresh(self) -> None:
        path = self._path
        if path is None:
            return
        try:
            st = path.stat()
        except FileNotFoundError:
            self._stamp, self._values = None, {}
            self._warn_once("missing", "비밀 파일이 없습니다(값을 주지 않음): %s", path)
            return
        except OSError as exc:
            self._stamp, self._values = None, {}
            self._warn_once(
                "stat", "비밀 파일을 확인할 수 없습니다(%s): %s", type(exc).__name__, path
            )
            return
        stamp = (st.st_mtime_ns, st.st_size)
        if stamp == self._stamp:
            return
        self._stamp, self._values = stamp, {}
        if st.st_size > self._settings.max_file_bytes:
            self._warn_once("large", "비밀 파일이 너무 커서 읽지 않습니다: %s", path)
            return
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            self._warn_once(
                "read", "비밀 파일을 읽을 수 없습니다(%s): %s", type(exc).__name__, path
            )
            return
        self._values, skipped = parse_secret_lines(text, self._settings)
        self._problem = None
        if skipped:
            lines = ", ".join(str(n) for n in skipped)
            _log.warning("비밀 파일의 %s번째 줄을 건너뜁니다(KEY=VALUE 형식 아님): %s", lines, path)

    def get_secret(self, name: str) -> str | None:
        """이름의 값(없으면 None). 파일이 바뀌었으면 다시 읽는다."""
        with self._lock:
            self._refresh()
            value = self._values.get(name)
            if value is None and self._settings.upper_fallback:
                value = self._values.get(name.upper())
            return value


class EnvFileSecretProvider(FileSecretProvider):
    """경로를 환경변수(`settings.path_env`)에서 받는 공급자 — entry point 값.

    entry point는 인자 없이 부른다. 그래서 이 클래스만 프로세스 환경을 읽는다(조립 가장자리).
    시험·다른 앱에서는 `environ`을 넘긴다.

    Args:
        environ: 읽을 환경. None이면 프로세스 환경(`os.environ`).
        settings: 줄 규칙. 없으면 기본값.
    """

    def __init__(
        self,
        environ: Mapping[str, str] | None = None,
        *,
        settings: SecretFileSettings | None = None,
    ) -> None:
        cfg = settings or load_settings()
        env = os.environ if environ is None else environ
        raw = env.get(cfg.path_env, "").strip()
        super().__init__(Path(raw).expanduser() if raw else None, settings=cfg)
        if not raw:
            _log.warning(
                "비밀 파일 경로가 설정되지 않아 이 공급자(%s)는 값을 주지 않습니다(환경변수 %s)",
                PROVIDER_ID,
                cfg.path_env,
            )


def register(registries: Any) -> None:
    """`plugins.modules` 플러그인 진입점: 묶음의 비밀 공급자 레지스트리에 이 공급자를 등록한다.

    설치하지 않고 서버 설정 `plugins.modules: ["agent_console_example_secret_provider:register"]`로
    쓸 때 부른다(설치했다면 entry point로 충분하다). 묶음에 `secret_providers` 레지스트리가 있으면
    그것을, 없으면 같은 이름의 확장 레지스트리를 쓴다.
    """
    registry = getattr(registries, "secret_providers", None)
    if registry is None:
        registry = registries.extension("secret_providers")
    registry.register(PROVIDER_ID, EnvFileSecretProvider(), source=f"module {__name__}")
