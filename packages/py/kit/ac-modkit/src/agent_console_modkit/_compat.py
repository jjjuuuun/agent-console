"""모듈이 선언하는 호스트 설정 호환(design §3R.1.6, 3R.16): 옛 키·환경변수·명령행 별칭.

호스트는 모듈 이름을 모른다. 옛 최상위 설정 키(예: 3R 전 ``usage:``)를 어느 모듈 설정
(``modules.options.<id>``)으로 옮길지, 어떤 환경변수·명령행 옵션이 그 모듈 설정의 어느 위치로
들어갈지는 **모듈이** ``ModuleDescriptor.settings_compat``으로 선언한다. 호스트는 설치된 모듈의
선언을 모아(``compat_of``) 설정을 읽을 때 적용한다.

- ``MovedSetting``: 옛 최상위 키 → 이 모듈 설정(통째로 병합 또는 한 키 아래). 새 위치 값이 이기고,
  옮긴 키는 경고(``SettingsMove``)로 보고한다. 읽기 호환은 한 단계 동안만 둔다.
- ``EnvSetting``: ``<호스트 접두어><name>`` 환경변수 → 이 모듈 설정 위치(경고 없음).
- ``FlagSetting``: 명령행 ``--<flag>`` → 이 모듈 설정 위치.
- ``SeedSetting``: 다른 설정 값을 이 모듈 설정의 기본값으로(새 위치에 값이 없을 때만, 경고 없음).
- ``RemovedSetting``: 지운 옛 키(점 경로). 남아 있으면 호스트가 이유·새 위치와 함께 거부한다
  (서버 오류 코드 ``settings.removed_key``). 읽기 호환 기간(``MovedSetting``)이 끝난 옛 키는
  ``RemovedSetting(old, new=...)``로 바꿔 새 위치를 알린다.
"""

from __future__ import annotations

import copy
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

PATHSEP = "<pathsep>"
"""``EnvSetting.split`` 값: 운영체제 경로 구분자(``os.pathsep``)로 나눈다."""


@dataclass(frozen=True)
class MovedSetting:
    """옛 최상위 설정 키 하나.

    Args:
        old: 옛 최상위 키(예: ``"usage"``).
        into: None이면 옛 값(객체)을 이 모듈 설정에 하위 키 단위로 병합한다. 문자열이면 옛 값을
            통째로 그 키 아래에 둔다(예: ``"runtime"``).
    """

    old: str
    into: str | None = None


@dataclass(frozen=True)
class EnvSetting:
    """환경변수 하나(호스트 접두어 뒤 이름).

    Args:
        name: 접두어 뒤 이름(예: ``"WORKING_DIRECTORY"``).
        path: 이 모듈 설정 안 위치(예: ``("runtime", "max_concurrency")``).
        split: 목록이면 구분자(``","`` 또는 ``PATHSEP``). None이면 문자열 그대로.
    """

    name: str
    path: tuple[str, ...]
    split: str | None = None


@dataclass(frozen=True)
class FlagSetting:
    """명령행 옵션 하나(``--<flag>``).

    Args:
        flag: 옵션 이름(앞의 ``--`` 없이, 예: ``"apply-preset"``).
        path: 이 모듈 설정 안 위치.
        help: 도움말.
        metavar: 값 이름.
        repeat: 참이면 여러 번 줄 수 있고 값은 목록이다.
    """

    flag: str
    path: tuple[str, ...]
    help: str = ""
    metavar: str = "VALUE"
    repeat: bool = False


@dataclass(frozen=True)
class SeedSetting:
    """다른 설정 값을 이 모듈 설정의 기본값으로 넣는다(새 위치에 값이 없을 때만).

    Args:
        key: 이 모듈 설정의 키.
        source: 설정 전체 기준 점 경로(예: ``"security.expose_paths"``).
        before_moves: 참이면 옛 키를 옮기기 전 설정에서 읽는다(옛 키에만 있던 값).
    """

    key: str
    source: str
    before_moves: bool = False


@dataclass(frozen=True)
class RemovedSetting:
    """지운 옛 설정 키(옮기기 전 설정 기준 점 경로).

    Args:
        path: 옛 키(점 경로, 예: ``"usage"``·``"presets.set_default_entry"``).
        reason: 거부 이유. 비우면 ``new``로 안내 문구를 만든다.
        new: 새 위치(점 경로, 예: ``"modules.options.mod-usage"``). 옮긴 키면 준다. None이면
            대신할 키가 없다(지우기만 하면 된다).
    """

    path: str
    reason: str = ""
    new: str | None = None

    def message(self) -> str:
        """거부 메시지(이유 + 새 위치 안내)."""
        parts: list[str] = []
        if self.reason:
            parts.append(self.reason)
        if self.new is not None:
            parts.append(
                f"설정 키 {self.path}는 더 이상 읽지 않습니다. {self.new}로 옮기세요"
                if not self.reason
                else f"새 위치: {self.new}"
            )
        if not parts:
            parts.append(f"설정 키 {self.path}는 지웠습니다. 설정 파일에서 지우세요")
        return ". ".join(parts)


@dataclass(frozen=True)
class SettingsCompat:
    """모듈 하나의 호스트 설정 호환 선언."""

    moved: tuple[MovedSetting, ...] = ()
    env: tuple[EnvSetting, ...] = ()
    flags: tuple[FlagSetting, ...] = ()
    seeds: tuple[SeedSetting, ...] = ()
    removed: tuple[RemovedSetting, ...] = ()


@dataclass(frozen=True)
class SettingsMove:
    """옮긴 옛 키 하나(경고용)."""

    old: str
    new: str
    overridden: tuple[str, ...] = ()

    def message(self) -> str:
        text = f"설정 키 {self.old}는 {self.new}로 옮겼습니다(읽기 호환). 옮겨 쓰세요"
        if self.overridden:
            text += f". 새 위치 값이 이긴 키: {', '.join(self.overridden)}"
        return text


@dataclass(frozen=True)
class CompatFlag:
    """명령행 옵션과 그것을 선언한 모듈."""

    module_id: str
    setting: FlagSetting


class _Described(Protocol):
    @property
    def descriptor(self) -> Any: ...


def compat_of(modules: Iterable[_Described]) -> dict[str, SettingsCompat]:
    """모듈 목록 → ``{모듈 id: SettingsCompat}``(선언이 있는 것만, 같은 id면 앞의 것)."""
    found: dict[str, SettingsCompat] = {}
    for module in modules:
        descriptor = module.descriptor
        compat = getattr(descriptor, "settings_compat", None)
        if isinstance(compat, SettingsCompat) and descriptor.id not in found:
            found[descriptor.id] = compat
    return found


def _options(data: dict[str, Any], module_id: str) -> dict[str, Any] | None:
    modules = data.get("modules")
    if modules is None:
        modules = data["modules"] = {}
    if not isinstance(modules, dict):
        return None  # 모델 검증이 형식 오류를 보고한다
    options = modules.get("options")
    if options is None:
        options = modules["options"] = {}
    if not isinstance(options, dict):
        return None
    current = options.get(module_id)
    if current is None:
        current = options[module_id] = {}
    return current if isinstance(current, dict) else None


def _get(data: Mapping[str, Any], dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def _put(target: dict[str, Any], path: Sequence[str], value: Any) -> None:
    node = target
    for key in path[:-1]:
        nxt = node.setdefault(key, {})
        if not isinstance(nxt, dict):
            return
        node = nxt
    node[path[-1]] = value


def migrate_settings(
    data: Mapping[str, Any], compats: Mapping[str, SettingsCompat]
) -> tuple[dict[str, Any], list[SettingsMove]]:
    """옛 키를 ``modules.options.<모듈 id>``로 옮기고 기본값을 채운 사본.

    순서: 통째 병합(``into`` 없음) → 키 아래 두기(``into``) → 기본값(``SeedSetting``). 모듈은 id 순.
    형식이 틀린 옛 값(통째 병합인데 객체가 아님 등)은 그대로 두어 호스트 모델 검증이 거부하게 한다.

    Returns:
        (옮긴 설정, 옮긴 키 목록).
    """
    original = dict(data)
    out = copy.deepcopy(original)
    moved: list[SettingsMove] = []
    ordered = sorted(compats.items())
    for module_id, compat in ordered:
        for item in compat.moved:
            if item.into is not None or item.old not in out:
                continue
            value = out.pop(item.old)
            target = _options(out, module_id)
            if target is None or not isinstance(value, dict):
                out[item.old] = value
                continue
            overridden = tuple(sorted(k for k in value if k in target))
            merged = {**value, **target}
            target.clear()
            target.update(merged)
            moved.append(SettingsMove(item.old, f"modules.options.{module_id}", overridden))
    for module_id, compat in ordered:
        for item in compat.moved:
            if item.into is None or item.old not in out:
                continue
            value = out.pop(item.old)
            target = _options(out, module_id)
            if target is None:
                out[item.old] = value
                continue
            key = item.into
            lost: tuple[str, ...] = ()
            current = target.get(key)
            if key not in target:
                target[key] = value
            elif isinstance(value, dict) and isinstance(current, dict):
                lost = tuple(sorted(f"{key}.{k}" for k in value if k in current))
                target[key] = {**value, **current}
            else:
                lost = (key,)
            moved.append(SettingsMove(item.old, f"modules.options.{module_id}.{key}", lost))
    for module_id, compat in ordered:
        for seed in compat.seeds:
            value = _get(original if seed.before_moves else out, seed.source)
            if value is None:
                continue
            target = _options(out, module_id)
            if target is not None and seed.key not in target:
                target[seed.key] = copy.deepcopy(value)
    return out, moved


def removed_settings(
    data: Mapping[str, Any], compats: Mapping[str, SettingsCompat]
) -> list[RemovedSetting]:
    """``data``(옮기기 전 설정)에 남아 있는 지운 키(모듈 id 순)."""
    found: list[RemovedSetting] = []
    for _, compat in sorted(compats.items()):
        for item in compat.removed:
            node: Any = data
            present = True
            for part in item.path.split("."):
                if not isinstance(node, Mapping) or part not in node:
                    present = False
                    break
                node = node[part]
            if present:
                found.append(item)
    return found


def _split(value: str, sep: str) -> list[str]:
    real = os.pathsep if sep == PATHSEP else sep
    return [part.strip() for part in value.split(real) if part.strip()]


def env_settings(
    environ: Mapping[str, str], compats: Mapping[str, SettingsCompat], *, prefix: str = ""
) -> dict[str, Any]:
    """환경변수 → 설정 덮어쓰기(``{"modules": {"options": {...}}}``). 빈 값은 무시한다."""
    out: dict[str, Any] = {}
    for module_id, compat in sorted(compats.items()):
        for item in compat.env:
            raw = environ.get(prefix + item.name)
            if not raw:
                continue
            value: Any = _split(raw, item.split) if item.split is not None else raw
            _put(out, ("modules", "options", module_id, *item.path), value)
    return out


def compat_flags(compats: Mapping[str, SettingsCompat]) -> list[CompatFlag]:
    """명령행 옵션 목록(모듈 id 순, 같은 이름이면 앞의 것)."""
    seen: set[str] = set()
    flags: list[CompatFlag] = []
    for module_id, compat in sorted(compats.items()):
        for item in compat.flags:
            if item.flag not in seen:
                seen.add(item.flag)
                flags.append(CompatFlag(module_id, item))
    return flags


def flag_settings(
    values: Mapping[str, Any], compats: Mapping[str, SettingsCompat]
) -> dict[str, Any]:
    """명령행 값(``{flag: 값}``, None·빈 목록은 무시) → 설정 덮어쓰기.

    Raises:
        KeyError: 어느 모듈도 선언하지 않은 옵션 이름.
    """
    by_flag = {f.setting.flag: f for f in compat_flags(compats)}
    out: dict[str, Any] = {}
    for name, value in values.items():
        if value is None or (isinstance(value, (list, tuple)) and not value):
            continue
        found = by_flag.get(name)
        if found is None:
            raise KeyError(name)
        item = list(value) if isinstance(value, (list, tuple)) else value
        _put(out, ("modules", "options", found.module_id, *found.setting.path), item)
    return out


__all__ = [
    "PATHSEP",
    "CompatFlag",
    "EnvSetting",
    "FlagSetting",
    "MovedSetting",
    "RemovedSetting",
    "SeedSetting",
    "SettingsCompat",
    "SettingsMove",
    "compat_flags",
    "compat_of",
    "env_settings",
    "flag_settings",
    "migrate_settings",
    "removed_settings",
]
