"""호스트 플러그인 로더(entry point ``agent_console.host_plugin_loaders``, 3R.16): 리소스 종류.

호스트 레지스트리 묶음의 리소스 종류 확장(이 모듈 설정 ``types_extension``)에 검사기를 붙이고
entry point 종류와 워크스페이스의 선언형 종류(``declarative_dir``, 기본 ``resource-types/*.yaml``)를
로드한다. 이 모듈 설정은 ``PluginLoadContext.options``의 원본을 검증해 쓴다(틀리면 기본값).
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport
from agent_console_resources import as_resource_type, load_declarative_types, load_resource_types

from .settings import ResourceModuleSettings

MODULE_ID = "mod-resources"
REPORT_GROUP = "resource_types"
"""보고 그룹 이름(선언형은 ``<그룹>.declarative``)."""

_log = logging.getLogger(__name__)


def _settings(ctx: PluginLoadContext) -> ResourceModuleSettings:
    raw = ctx.options.get(MODULE_ID)
    if raw is None:
        return ResourceModuleSettings()
    try:
        return ResourceModuleSettings.model_validate(raw)
    except ValidationError:
        _log.warning("%s 설정이 잘못되어 리소스 종류 로딩에 기본값을 씁니다", MODULE_ID)
        return ResourceModuleSettings()


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """리소스 종류 entry point와 선언형 종류를 묶음에 로드한다."""
    cfg = _settings(ctx)
    registry = ctx.registries.extension(cfg.types_extension, validator=as_resource_type)
    enabled = set(ctx.enabled) if ctx.enabled is not None else None
    reports = [(REPORT_GROUP, r) for r in load_resource_types(registry, enabled=enabled)]
    if ctx.paths is not None:
        folder = ctx.paths.workspace / cfg.declarative_dir
        reports += [
            (f"{REPORT_GROUP}.declarative", r) for r in load_declarative_types(folder, registry)
        ]
    return reports


__all__ = ["REPORT_GROUP", "load_plugins"]
