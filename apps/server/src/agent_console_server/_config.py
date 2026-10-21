"""서버 설정(`agent-console.yaml` + 환경변수).

설치자가 정하는 값(포트, workspace 경로, 활성 플러그인, 보안 한도 등)만 담는다.
사용자가 화면에서 고치는
데이터(공통 설정, 채팅 설정 등)는 workspace의 `settings.yaml`(`WorkspaceSettings`)에 있다.

우선순위: 명령행 덮어쓰기 > 환경변수 > 설정 파일 > 기본값. 모든 상대 경로는 `base_dir` 기준이다
(설정 파일이 있으면 그 파일의 폴더, 없으면 현재 작업 폴더).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    PrivateAttr,
    SecretStr,
    ValidationError,
    ValidationInfo,
    model_validator,
)
from ruamel.yaml import YAML

from agent_console_modkit import (
    Module,
    ModulesConfig,
    RemovedSetting,
    SettingsCompat,
    compat_of,
    env_settings,
    load_installed_modules,
    migrate_settings,
    removed_settings,
)
from agent_console_modkit.host import is_loopback_host as is_loopback_host

CONFIG_FILENAME = "agent-console.yaml"
"""`base_dir`에서 자동으로 찾는 설정 파일 이름."""

ENV_PREFIX = "AGENT_CONSOLE_"
"""설정 환경변수 접두어."""

DEFAULT_STATE_DIR = ".state"
"""workspace 안에서 시스템 기록(SQLite)을 두는 폴더. 정의 YAML과 섞이지 않게 분리한다."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PluginSettings(_Section):
    enabled: list[str] | None = Field(
        default=None,
        description="로드할 entry point 이름(모든 그룹 공통). null이면 설치된 것 전부.",
    )
    modules: list[str] = Field(
        default_factory=list,
        description="설치하지 않은 플러그인 모듈 `pkg.mod:attr`(`register(registries)` 호출).",
    )


class SecuritySettings(_Section):
    token: SecretStr | None = Field(
        default=None, description="로컬 API 토큰. 비우면 시작할 때마다 무작위로 만든다."
    )
    allow_remote: bool = Field(
        default=False,
        description="루프백이 아닌 주소에 바인딩하려면 true(명시적으로 켤 때만 외부 공개).",
    )
    allowed_hosts: list[str] = Field(
        default_factory=list,
        description="추가로 허용할 Host 헤더 값(`이름` 또는 `이름:포트`). 루프백은 항상 허용.",
    )
    allowed_origins: list[str] = Field(
        default_factory=list,
        description="같은 출처 외에 허용할 Origin(예: 웹 개발 서버 `http://localhost:5173`).",
    )
    expose_paths: bool = Field(
        default=True,
        description="`GET /server-info`에 workspace 절대 경로를 보일지(로컬 앱이라 기본 표시).",
    )
    max_request_bytes: int = Field(default=1024 * 1024, ge=1024, description="REST 본문 최대 크기.")
    max_ws_message_bytes: int = Field(default=1024 * 1024, ge=1024, description="WS 메시지 최대.")
    max_ws_subscriptions: int = Field(default=256, ge=1, description="연결 하나의 구독 수 한도.")


class SecretSettings(_Section):
    env_prefix: str = Field(
        default="", description="`secret://name` → 환경변수 `<env_prefix>name`(없으면 대문자)."
    )
    min_redact_chars: int = Field(default=4, ge=1)


class WebOpenSettings(_Section):
    """서버가 준비되면 웹 화면을 연다(`serve --open`, design §2R.13a). 기본 꺼짐."""

    enabled: bool = Field(
        default=False,
        description="준비되면 URL을 연다. 명령행 `--open`/`--no-open`이 이 값을 덮어쓴다.",
    )
    url: str | None = Field(
        default=None,
        description=(
            "열 주소. `{host}`·`{port}` 자리는 실제 값으로 바꾼다(포트 0이면 OS가 고른 포트). "
            "비우면 `serve_static`이 켜졌을 때 서버 주소, 꺼졌으면 열지 않는다."
        ),
    )
    command: list[str] | None = Field(
        default=None,
        description=(
            "기본 브라우저 대신 실행할 명령과 인자(셸 없이 실행). `{url}` 자리에 주소가 들어간다. "
            '예: 설치한 PWA 창 `["msedge", "--app={url}"]`, WSL `["explorer.exe", "{url}"]`.'
        ),
    )
    wait_seconds: float = Field(
        default=30.0, gt=0, description="준비 신호를 기다리는 최대 초(넘으면 열지 않고 경고)."
    )


class WebSettings(_Section):
    serve_static: bool = Field(
        default=False,
        description=(
            "웹 빌드 정적 서빙(선택 기능, 기본 꺼짐). 켜면 서버 하나가 API·WS·웹을 함께 서빙한다"
            "(단일 실행). 끄면 웹은 별도 프로세스로 띄운다."
        ),
    )
    static_dir: Path | None = Field(
        default=None,
        description="웹 빌드 산출물 폴더(`apps/web/dist` 등). 비우면 패키지 포함 빌드.",
    )
    open: WebOpenSettings = Field(default_factory=WebOpenSettings)


REMOVED_KEYS: dict[str, str] = {  # 호스트 자신이 지운 키(모듈 것은 모듈이 선언)
    "console": (
        "콘솔 섹션은 1R에서 삭제되었습니다(콘솔 보류, 채팅으로 대체). 설정 파일에서 지우세요"
    ),
    "default_manual_route_pattern": (
        "default_manual_route_pattern은 1R에서 삭제되었습니다(라우터 보류). 설정 파일에서 지우세요"
    ),
}
"""호스트가 지운 키(점으로 이은 경로) → 이유(그 키가 남아 있으면 이 문구로 거부한다).
모듈 설정에서 지운 키는 모듈이 ``SettingsCompat.removed``로 알린다."""


SETTINGS_MOVED_KEY = "settings.moved_key"
"""경고 코드: 옛 위치의 설정 키를 읽어 새 위치로 옮겼다(모듈이 `MovedSetting`을 선언한 동안만).

4R.18부터 기본 모듈은 옮기기 선언이 없다(옛 키는 `SETTINGS_REMOVED_KEY` 오류). 다음에 키를
옮기는 모듈이 한 단계 동안 쓰는 장치로 남긴다."""

SETTINGS_REMOVED_KEY = "settings.removed_key"
"""설정 오류 코드: 지운 옛 키가 남아 있다(`ConfigError.code`, 메시지에 새 위치 안내, 4R.18)."""

SETTINGS_COMPAT_CONTEXT = "agent_console.settings_compat"
"""`ServerSettings.model_validate(..., context={이 키: {모듈 id: SettingsCompat}})`.

호스트는 모듈 이름을 모른다. 옛 최상위 키를 어느 모듈 설정으로 옮길지는 설치된 모듈이
`ModuleDescriptor.settings_compat`으로 알린다(`settings_compat()`이 모은다, design §3R.1.6).
문맥이 없으면 옮기지 않는다(옛 키는 모르는 키로 거부된다)."""


class MovedKey(BaseModel):
    """옛 위치에서 옮긴 설정 키 하나(`settings.moved_key`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    old: str = Field(description="옛 키(점 경로).")
    new: str = Field(description="새 키(점 경로).")
    overridden: list[str] = Field(
        default_factory=list, description="새 위치에도 있어 새 값이 이긴 하위 키."
    )

    def message(self) -> str:
        text = f"설정 키 {self.old}는 {self.new}로 옮겼습니다(읽기 호환). 옮겨 쓰세요"
        if self.overridden:
            text += f". 새 위치 값이 이긴 키: {', '.join(self.overridden)}"
        return text


class RemovedKey(BaseModel):
    """설정에 남아 있는 지운 옛 키 하나(`settings.removed_key`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    old: str = Field(description="옛 키(점 경로).")
    new: str | None = Field(default=None, description="새 위치(점 경로). 없으면 지우기만 한다.")
    message: str = Field(description="안내 문구(이유·새 위치).")


class RemovedKeyError(ValueError):
    """설정 검증 중 지운 옛 키를 찾았다(`ServerSettings` 검증기가 던진다).

    `load_settings`는 이것을 `ConfigError(code=SETTINGS_REMOVED_KEY)`로 바꾼다.
    """

    def __init__(self, keys: list[RemovedKey]) -> None:
        self.keys = keys
        super().__init__("; ".join(f"{k.old}: {k.message}" for k in keys))


def removed_keys(data: Mapping[str, Any], compat: Mapping[str, SettingsCompat]) -> list[RemovedKey]:
    """`data`(옮기기 전 설정)에 남아 있는 지운 키 — 호스트 것(`REMOVED_KEYS`) 다음 모듈 선언 순."""
    host = [RemovedSetting(path, reason) for path, reason in REMOVED_KEYS.items()]
    found = removed_settings(data, {"": SettingsCompat(removed=tuple(host))})
    found += removed_settings(data, compat)
    return [RemovedKey(old=r.path, new=r.new, message=r.message()) for r in found]


def settings_compat(modules: Iterable[Module] | None = None) -> dict[str, SettingsCompat]:
    """모듈의 설정 호환 선언(`{모듈 id: SettingsCompat}`). None이면 설치된 모듈(entry point)."""
    if modules is None:
        modules, _ = load_installed_modules()
    return compat_of(modules)


def migrate_moved_keys(
    data: Mapping[str, Any], compat: Mapping[str, SettingsCompat]
) -> tuple[dict[str, Any], list[MovedKey]]:
    """옛 키를 `modules.options.<모듈 id>`로 옮긴 사본과 옮긴 키 목록(새 키가 이긴다).

    무엇을 어디로 옮길지는 `compat`(모듈 선언)이 정한다(`agent_console_modkit.migrate_settings`).
    """
    out, moves = migrate_settings(data, compat)
    return out, [MovedKey(old=m.old, new=m.new, overridden=list(m.overridden)) for m in moves]


def _compat_from(info: ValidationInfo) -> Mapping[str, SettingsCompat]:
    context = info.context
    if isinstance(context, Mapping):
        found = context.get(SETTINGS_COMPAT_CONTEXT)
        if isinstance(found, Mapping):
            return found
    return {}


class ServerSettings(_Section):
    """서버 앱 설정. `load_settings()`로 만든다(직접 생성도 가능: 테스트·내장)."""

    @model_validator(mode="wrap")
    @classmethod
    def _reject_removed_and_migrate(
        cls, data: Any, handler: ModelWrapValidatorHandler[ServerSettings], info: ValidationInfo
    ) -> ServerSettings:
        moved: list[MovedKey] = []
        if isinstance(data, dict):
            compat = _compat_from(info)
            removed = removed_keys(data, compat)
            if removed:
                raise RemovedKeyError(removed)
            data, moved = migrate_moved_keys(data, compat)
        settings = handler(data)
        if moved:
            settings._moved_keys = moved
        return settings

    _moved_keys: list[MovedKey] = PrivateAttr(default_factory=list)

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=0, le=65535)
    base_dir: Path = Field(
        default_factory=Path.cwd, description="상대 경로의 기준(설정 파일 폴더 또는 현재 폴더)."
    )
    workspace: Path = Field(default=Path(".agent-console"), description="정의 YAML 폴더.")
    database: Path | None = Field(
        default=None, description="SQLite 파일. 비우면 `<workspace>/.state/console.sqlite3`."
    )
    log_level: str = "info"
    plugins: PluginSettings = Field(default_factory=PluginSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    secrets: SecretSettings = Field(default_factory=SecretSettings)
    web: WebSettings = Field(default_factory=WebSettings)
    modules: ModulesConfig = Field(
        default_factory=ModulesConfig,
        description=(
            "서버 모듈 켜고 끄기(design §3R.1.8): `enabled`(null = 설치된 것 전부)·`disabled`·"
            "`bindings`(같은 포트를 여러 모듈이 줄 때 고름)·`options`(모듈 id → 그 모듈 설정). "
            "웹에서는 읽기 전용이다. 명령행 `--enable-module`·`--disable-module`이 "
            "이 값보다 우선한다."
        ),
    )

    @property
    def moved_keys(self) -> list[MovedKey]:
        """읽는 중 옛 위치에서 옮긴 키(`settings.moved_key` 경고). 새로 읽을 때만 채워진다."""
        return list(self._moved_keys)

    # ------------------------------------------------------------ 해석된 경로

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.base_dir / path)

    @property
    def workspace_path(self) -> Path:
        return self.resolve(self.workspace)

    @property
    def state_path(self) -> Path:
        """workspace 시스템 기록 폴더(`<workspace>/.state`). SQLite 기본 위치·사용량 브리지 파일."""
        return self.workspace_path / DEFAULT_STATE_DIR

    @property
    def database_path(self) -> Path:
        if self.database is not None:
            return self.resolve(self.database)
        return self.state_path / "console.sqlite3"

    @property
    def static_path(self) -> Path | None:
        return self.resolve(self.web.static_dir) if self.web.static_dir is not None else None

    @property
    def is_loopback(self) -> bool:
        return is_loopback_host(self.host)


class ConfigError(ValueError):
    """설정 파일·환경변수 값이 잘못됨.

    Attributes:
        code: 기계가 읽는 오류 코드(예: `SETTINGS_REMOVED_KEY`). 일반 값 오류는 None.
        removed: 지운 옛 키가 원인이면 그 목록(`code == SETTINGS_REMOVED_KEY`).
    """

    def __init__(
        self, message: str, *, code: str | None = None, removed: list[RemovedKey] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.removed = list(removed or [])


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _env_overrides(environ: Mapping[str, str]) -> dict[str, Any]:
    """호스트 환경변수 → 설정 dict(중첩). 값이 빈 문자열이면 무시한다.

    모듈 설정으로 들어가는 환경변수는 모듈이 `SettingsCompat.env`로 알린다(`load_settings`)."""

    def get(name: str) -> str | None:
        value = environ.get(ENV_PREFIX + name)
        return value if value else None

    out: dict[str, Any] = {}

    def put(path: tuple[str, ...], value: Any) -> None:
        node = out
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value

    simple = {
        "HOST": ("host",),
        "PORT": ("port",),
        "WORKSPACE": ("workspace",),
        "DATABASE": ("database",),
        "LOG_LEVEL": ("log_level",),
        "TOKEN": ("security", "token"),
        "WEB_DIR": ("web", "static_dir"),
        "SECRET_ENV_PREFIX": ("secrets", "env_prefix"),
    }
    for name, path in simple.items():
        if (value := get(name)) is not None:
            put(path, value)
    flags = {
        "ALLOW_REMOTE": ("security", "allow_remote"),
        "SERVE_STATIC": ("web", "serve_static"),
        "OPEN": ("web", "open", "enabled"),
    }
    for name, path in flags.items():
        if (value := get(name)) is not None:
            put(path, value.lower() in ("1", "true", "yes", "on"))
    lists = {
        "PLUGINS_ENABLED": ("plugins", "enabled"),
        "PLUGIN_MODULES": ("plugins", "modules"),
        "ALLOWED_HOSTS": ("security", "allowed_hosts"),
        "ALLOWED_ORIGINS": ("security", "allowed_origins"),
    }
    for name, path in lists.items():
        if (value := get(name)) is not None:
            put(path, _split(value))
    return out


def _merge(base: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(
            f"설정 파일을 읽을 수 없습니다: {path} ({exc.__class__.__name__})"
        ) from exc
    except Exception as exc:
        raise ConfigError(f"설정 파일 형식 오류: {path}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"설정 파일 최상위는 객체여야 합니다: {path}")
    return data


def load_settings(
    config_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    overrides: Mapping[str, Any] | None = None,
    compat: Mapping[str, SettingsCompat] | None = None,
) -> ServerSettings:
    """설정 파일과 환경변수에서 `ServerSettings`를 만든다.

    Args:
        config_path: 설정 파일. None이면 환경변수 `AGENT_CONSOLE_CONFIG`, 그것도 없으면
            `<cwd>/agent-console.yaml`이 있을 때 그것.
        environ: 환경변수(기본 `os.environ`). 테스트에서 주입.
        cwd: 기준 폴더(기본 현재 작업 폴더).
        overrides: 명령행 인자 등 마지막으로 덮어쓸 값(중첩 dict).
        compat: 모듈 설정 호환 선언(옛 키·환경변수, `settings_compat()`). None이면 설치된 모듈.

    Raises:
        ConfigError: 파일을 읽을 수 없거나 값이 잘못됐을 때.
    """
    env = os.environ if environ is None else environ
    base = (cwd or Path.cwd()).resolve()
    path: Path | None
    if config_path is not None:
        path = Path(config_path)
    elif env.get(ENV_PREFIX + "CONFIG"):
        path = Path(env[ENV_PREFIX + "CONFIG"])
    else:
        candidate = base / CONFIG_FILENAME
        path = candidate if candidate.is_file() else None
    data: dict[str, Any] = {}
    if path is not None:
        path = path if path.is_absolute() else base / path
        data = _read_yaml(path)
        data.setdefault("base_dir", str(path.parent))
    rules = settings_compat() if compat is None else compat
    data = _merge(data, _env_overrides(env))
    data = _merge(data, env_settings(env, rules, prefix=ENV_PREFIX))
    if overrides:
        data = _merge(data, overrides)
    data.setdefault("base_dir", str(base))
    try:
        return ServerSettings.model_validate(data, context={SETTINGS_COMPAT_CONTEXT: rules})
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_url=False)
        for error in errors:
            cause = (error.get("ctx") or {}).get("error")
            if isinstance(cause, RemovedKeyError):
                raise ConfigError(
                    f"설정 값 오류({SETTINGS_REMOVED_KEY}): {cause}",
                    code=SETTINGS_REMOVED_KEY,
                    removed=cause.keys,
                ) from None
        # 입력 값(토큰 등)이 메시지에 섞이지 않게 위치와 사유만 남긴다.
        problems = "; ".join(_describe_error(e) for e in errors)
        raise ConfigError(f"설정 값 오류: {problems}") from None


def _describe_error(error: Mapping[str, Any]) -> str:
    """검증 오류 하나를 "위치: 사유"로. 위치가 없으면(모델 전체 검사) 사유만 쓴다."""
    loc = ".".join(str(p) for p in error.get("loc", ()))
    ctx = error.get("ctx") or {}
    # 검증기가 던진 ValueError는 pydantic 접두어("Value error, ") 없이 원문만 쓴다.
    cause = ctx.get("error") if error.get("type") == "value_error" else None
    msg = str(cause) if cause is not None else str(error.get("msg", ""))
    return f"{loc}: {msg}" if loc else msg
