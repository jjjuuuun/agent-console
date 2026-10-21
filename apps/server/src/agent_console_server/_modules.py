"""모듈 켜고 끄기·보고(design §3R.1.8, E-12): modkit 보고 → 계약 `ModuleInfo`, 명령행 덮어쓰기.

서버는 모듈 이름을 모른다. 설치자 설정 `modules`와 명령행 `--enable-module`·`--disable-module`만
적용하고, 조립·상태 판정은 `agent_console_modkit.assemble`이 한다.
"""

from __future__ import annotations

from collections.abc import Iterable

from agent_console_contracts import ModuleInfo
from agent_console_modkit import ModuleReport

from ._config import ServerSettings


def module_info(report: ModuleReport) -> ModuleInfo:
    """modkit `ModuleReport` → 계약 `ModuleInfo`.

    `requires`는 필수·선택 포트를 함께 담는다(계약 설명: 상태 판단 근거). `reason`은 modkit이
    이미 가린 문구다(`failed`는 예외 형식만).
    """
    return ModuleInfo(
        id=report.id,
        kind=report.kind,
        version=report.version,
        contracts=dict(report.contracts),
        status=report.state.value,
        reason=report.reason,
        web_roles=list(report.web_roles),
        provides=list(report.provides),
        requires=list(dict.fromkeys([*report.requires, *report.optional])),
    )


def apply_module_flags(
    settings: ServerSettings, *, enable: Iterable[str] = (), disable: Iterable[str] = ()
) -> ServerSettings:
    """명령행 `--enable-module`·`--disable-module`을 설정 `modules`에 적용한 사본(설정보다 우선).

    규칙은 `ModulesConfig.with_overrides`(같은 id가 둘 다 있으면 끄기가 이긴다).
    """
    enable = list(enable)
    disable = list(disable)
    if not enable and not disable:
        return settings
    modules = settings.modules.with_overrides(enable=enable, disable=disable)
    return settings.model_copy(update={"modules": modules})


__all__ = ["apply_module_flags", "module_info"]
