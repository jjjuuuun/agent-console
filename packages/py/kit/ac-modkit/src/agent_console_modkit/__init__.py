"""agent-console-modkit: 서버 모듈 키트(design §3R.1.2, modularity §3.2).

기능 모듈·연동 모듈이 따르는 인터페이스와 조립기. 기능·모듈·연동 이름을 모른다.

공개 API(코어, FastAPI 불필요):
    - ``PortKey[T](name, multi=False)`` / ``Topic[T](name)``: 이름으로 식별하는 포트·이벤트 토픽.
    - ``ModuleDescriptor`` / ``ModuleParts`` / ``Module``: 모듈 서술·빌드 결과·프로토콜.
    - ``ModuleContext``: build가 받는 것(포트 읽기·제공, 이벤트, 기본 서비스).
    - ``assemble(modules, config, base=)`` → ``Assembly``(위상 정렬·상태 5종·bindings·multi 목록).
    - ``ModulesConfig`` / ``ModuleState`` / ``ModuleReport``: 설정·상태·보고.
    - ``EventBus``: 모듈 이벤트 버스(구독자 예외 격리). ``Hub``: WS 토픽 팬아웃.
    - ``BaseServices`` / ``Paths``: 호스트 기본 서비스.
    - ``DatabaseHandle``(프로토콜) / ``MigrationBranch``: 공용 DB 핸들과 모듈이 선언하는
      마이그레이션 계보(구현은 저장 계층, 예: ``agent_console_store.SqliteDatabase``).
    - ``load_installed_modules`` / ``MODULES_GROUP``: entry point로 설치된 모듈 찾기.
    - ``FeatureUnavailableError`` / ``FEATURE_UNAVAILABLE``: 선택 포트가 없어 꺼진 동작
      (호스트가 409).
    - ``ErrorReply`` / ``ErrorMapper`` / ``ErrorMapping`` / ``error_reply``: 모듈 ``error_map`` 값
      (코드 문자열 또는 예외 → 코드·메시지·상세·헤더).
    - WS 토픽 처리기 형식: ``WsSubscribeRequest``·``WsReject``·``WsForward``·``WsTopicHandler``.
    - 호스트 기본 서비스 확장 지점(3R.16): ``load_host_plugins``(레지스트리 묶음 공장·플러그인 로더
      entry point + ``register(registries)`` 플러그인), ``open_host_database``(DB 공장 entry point),
      ``env_secret_lookup``·``secret_lookup``(비밀 해석 사슬), ``PluginLoadContext``.
    - 설정 호환 선언(3R.16): ``SettingsCompat``(``MovedSetting``·``EnvSetting``·``FlagSetting``·
      ``SeedSetting``)과 적용 함수 ``migrate_settings``·``env_settings``·``flag_settings``.
    - ``NOT_READY``: 호스트 준비 전 ``/health`` 오류 코드(503), ``Assembly.running``.
    - 모듈 옵션 읽기 전용 보기(5.2R.29): ``read_module_options``·``Assembly.module_options`` →
      ``ModuleOptions``(스키마·가린 값), ``mask_values``·``OPTIONS_MASK``·``SECRET_SCHEMA_KEY``.
      비밀 의심 판정은 ``SecretPathFinder``로 주입한다. 쓰기는 없다.

HTTP 호스트(보안·토큰·``/health``·WS 다중화)는 ``agent_console_modkit.host``(extra ``[host]``),
모듈 하나 단독 실행은 ``agent_console_modkit.standalone``(extra ``[host]``).
"""

from __future__ import annotations

from ._assemble import (
    Assembly,
    ModuleContext,
    ModuleReport,
    ModulesConfig,
    ModuleState,
    UndeclaredPortError,
    assemble,
    default_paths,
)
from ._compat import (
    PATHSEP,
    CompatFlag,
    EnvSetting,
    FlagSetting,
    MovedSetting,
    RemovedSetting,
    SeedSetting,
    SettingsCompat,
    SettingsMove,
    compat_flags,
    compat_of,
    env_settings,
    flag_settings,
    migrate_settings,
    removed_settings,
)
from ._database import DatabaseHandle, MigrationBranch
from ._errors import (
    FEATURE_UNAVAILABLE,
    NOT_READY,
    ErrorMapper,
    ErrorMapping,
    ErrorReply,
    FeatureUnavailableError,
    error_reply,
)
from ._events import EventBus, Handler
from ._hostext import (
    HOST_DATABASE_GROUP,
    HOST_EXTENSIONS_REPORT_GROUP,
    HOST_PLUGIN_LOADERS_GROUP,
    HOST_REGISTRIES_GROUP,
    PLUGIN_MODULES_REPORT_GROUP,
    SECRET_PROVIDERS_REGISTRY,
    ExtensionRegistries,
    HostPlugins,
    PluginLoadContext,
    PluginLoader,
    RegistryBundle,
    env_secret_lookup,
    load_host_plugins,
    open_host_database,
    secret_lookup,
    secret_providers_of,
)
from ._hub import Hub, HubSubscription
from ._loading import MODULES_GROUP, as_module, load_installed_modules
from ._module import (
    KNOWN_MODULE_KINDS,
    Module,
    ModuleDescriptor,
    ModuleParts,
    WsForward,
    WsReject,
    WsSend,
    WsSubscribeRequest,
    WsTopicHandler,
)
from ._options import (
    OPTIONS_MASK,
    SECRET_SCHEMA_KEY,
    ModuleOptions,
    SecretPathFinder,
    mask_values,
    read_module_options,
)
from ._ports import PortKey, Topic
from ._services import BaseServices, Paths, utc_now

__all__ = [
    "FEATURE_UNAVAILABLE",
    "HOST_DATABASE_GROUP",
    "HOST_EXTENSIONS_REPORT_GROUP",
    "HOST_PLUGIN_LOADERS_GROUP",
    "HOST_REGISTRIES_GROUP",
    "KNOWN_MODULE_KINDS",
    "MODULES_GROUP",
    "NOT_READY",
    "OPTIONS_MASK",
    "PATHSEP",
    "PLUGIN_MODULES_REPORT_GROUP",
    "SECRET_PROVIDERS_REGISTRY",
    "SECRET_SCHEMA_KEY",
    "Assembly",
    "BaseServices",
    "CompatFlag",
    "DatabaseHandle",
    "EnvSetting",
    "ErrorMapper",
    "ErrorMapping",
    "ErrorReply",
    "EventBus",
    "ExtensionRegistries",
    "FeatureUnavailableError",
    "FlagSetting",
    "Handler",
    "HostPlugins",
    "Hub",
    "HubSubscription",
    "MigrationBranch",
    "Module",
    "ModuleContext",
    "ModuleDescriptor",
    "ModuleOptions",
    "ModuleParts",
    "ModuleReport",
    "ModuleState",
    "ModulesConfig",
    "MovedSetting",
    "Paths",
    "PluginLoadContext",
    "PluginLoader",
    "PortKey",
    "RegistryBundle",
    "RemovedSetting",
    "SecretPathFinder",
    "SeedSetting",
    "SettingsCompat",
    "SettingsMove",
    "Topic",
    "UndeclaredPortError",
    "WsForward",
    "WsReject",
    "WsSend",
    "WsSubscribeRequest",
    "WsTopicHandler",
    "as_module",
    "assemble",
    "compat_flags",
    "compat_of",
    "default_paths",
    "env_secret_lookup",
    "env_settings",
    "error_reply",
    "flag_settings",
    "load_host_plugins",
    "load_installed_modules",
    "mask_values",
    "migrate_settings",
    "open_host_database",
    "read_module_options",
    "removed_settings",
    "secret_lookup",
    "secret_providers_of",
    "utc_now",
]
