"""타입드 레지스트리 본체. 전역 상태 없이 생성해서 주입한다."""

from __future__ import annotations

import builtins
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

type Validator[T] = Callable[[Any], T]
"""등록 검사기: 받은 객체를 검사해 등록할 ``T`` 를 돌려준다(변환 가능, 예: 클래스 → 인스턴스).
거부할 때는 예외를 던진다. 이미 검사를 통과한 값을 다시 넣어도 같은 값을 돌려줘야 한다(멱등)."""


class RegistryError(Exception):
    """이 패키지가 던지는 모든 예외의 베이스."""


class DuplicateKeyError(RegistryError):
    """같은 ``(key, version)`` 이 이미 등록되어 있을 때 (``replace=True`` 가 아니면)."""

    def __init__(self, registry_name: str, key: str, version: int, existing_source: str) -> None:
        self.registry_name = registry_name
        self.key = key
        self.version = version
        self.existing_source = existing_source
        where = f" (기존 출처: {existing_source})" if existing_source else ""
        super().__init__(f"[{registry_name}] 중복 등록: key={key!r} version={version}{where}")


class InvalidExtensionError(RegistryError, TypeError):
    """레지스트리 검사기가 등록하려는 객체를 거부했을 때. ``TypeError`` 로도 잡힌다."""

    def __init__(self, registry_name: str, key: str, reason: str) -> None:
        self.registry_name = registry_name
        self.key = key
        self.reason = reason
        super().__init__(f"[{registry_name}] 등록 거부: key={key!r} ({reason})")


class UnknownExtensionError(RegistryError, KeyError):
    """등록되지 않은 key 또는 version을 조회했을 때. ``KeyError`` 로도 잡힌다."""

    def __init__(self, registry_name: str, key: str, version: int | None = None) -> None:
        self.registry_name = registry_name
        self.key = key
        self.version = version
        ver = "" if version is None else f" version={version}"
        self.message = f"[{registry_name}] 등록되지 않은 확장: key={key!r}{ver}"
        super().__init__(self.message)

    def __str__(self) -> str:  # KeyError는 인자를 repr로 감싸므로 메시지를 그대로 쓴다.
        return self.message


@dataclass(frozen=True, slots=True)
class RegistryEntry[T]:
    """레지스트리에 등록된 한 항목.

    Attributes:
        key: 확장 식별자(예: 노드 타입 id). 의미는 호출자가 정한다.
        version: 같은 key 안에서의 버전(정수, 클수록 최신).
        item: 등록된 구현 객체.
        source: 사람이 읽는 출처 설명(entry point·모듈 경로 등). 화면 노출용.
    """

    key: str
    version: int
    item: T
    source: str


class Registry[T]:
    """key(+version) → 구현 ``T`` 를 담는 타입드 레지스트리.

    확장 지점마다 하나씩 만들어 의존성 주입으로 넘긴다. 모듈 수준 싱글턴은 없다.
    같은 key에 여러 version을 등록할 수 있고, version 없이 조회하면 최신을 돌려준다.

    검사기(``validator``)를 붙이면 **모든 등록 경로**(entry point·모듈·``register(target)``
    플러그인·직접 호출)가 같은 검사를 거친다.

    Args:
        name: 오류 메시지·보고에 쓰는 이름(예: 호출자가 정한 확장 지점 이름).
        validator: 선택. 등록마다 부르는 검사기(``Validator``). 없으면 검사하지 않는다.
    """

    def __init__(self, name: str = "registry", *, validator: Validator[T] | None = None) -> None:
        self.name = name
        self._validator = validator
        self._entries: dict[str, dict[int, RegistryEntry[T]]] = {}

    @property
    def validator(self) -> Validator[T] | None:
        """붙어 있는 검사기(없으면 None)."""
        return self._validator

    def set_validator(self, validator: Validator[T]) -> None:
        """검사기를 붙인다. 이미 등록된 항목도 이 검사기로 다시 검사·변환한다.

        같은 검사기를 다시 붙이면 아무 일도 하지 않는다.

        Raises:
            RegistryError: 다른 검사기가 이미 붙어 있을 때.
            InvalidExtensionError: 이미 등록된 항목이 검사를 통과하지 못할 때(검사기는 붙지 않는다).
        """
        if self._validator is validator:
            return
        if self._validator is not None:
            raise RegistryError(f"[{self.name}] 이미 다른 검사기가 붙어 있다")
        checked = {
            key: {v: self._checked(validator, e.key, e.item, v, e.source) for v, e in vs.items()}
            for key, vs in self._entries.items()
        }
        self._validator = validator
        self._entries = checked

    def _checked(
        self, validator: Validator[T] | None, key: str, item: Any, version: int, source: str
    ) -> RegistryEntry[T]:
        if validator is None:
            return RegistryEntry(key=key, version=version, item=item, source=source)
        try:
            value = validator(item)
        except Exception as exc:
            raise InvalidExtensionError(self.name, key, f"{type(exc).__name__}: {exc}") from exc
        return RegistryEntry(key=key, version=version, item=value, source=source)

    def register(
        self,
        key: str,
        item: T,
        *,
        version: int = 1,
        source: str = "",
        replace: bool = False,
    ) -> RegistryEntry[T]:
        """항목을 등록한다.

        Args:
            key: 확장 식별자. 빈 문자열은 허용하지 않는다.
            item: 등록할 구현.
            version: 버전(기본 1).
            source: 출처 설명(LoadReport·화면 노출용).
            replace: True면 같은 ``(key, version)`` 을 덮어쓴다(명시적 override).

        Returns:
            등록된 ``RegistryEntry`` (검사기가 있으면 검사기가 돌려준 값이 ``item``).

        Raises:
            ValueError: key가 비었을 때.
            DuplicateKeyError: 같은 ``(key, version)`` 이 있고 ``replace`` 가 False일 때.
            InvalidExtensionError: 검사기가 거부했을 때(등록되지 않는다).
        """
        if not key:
            raise ValueError(f"[{self.name}] key는 비어 있을 수 없다")
        existing = self._entries.get(key, {}).get(version)
        if existing is not None and not replace:
            raise DuplicateKeyError(self.name, key, version, existing.source)
        entry = self._checked(self._validator, key, item, version, source)
        self._entries.setdefault(key, {})[version] = entry
        return entry

    def unregister(self, key: str, version: int | None = None) -> None:
        """항목을 지운다. ``version`` 이 None이면 그 key의 모든 버전. 없으면 아무 일도 없다."""
        versions = self._entries.get(key)
        if versions is None:
            return
        if version is None:
            versions.clear()
        else:
            versions.pop(version, None)
        if not versions:
            del self._entries[key]

    def get(self, key: str, version: int | None = None) -> T:
        """구현을 조회한다.

        Args:
            key: 확장 식별자.
            version: 특정 버전. None이면 최신 버전.

        Returns:
            등록된 구현.

        Raises:
            UnknownExtensionError: key 또는 version이 없을 때(``KeyError`` 하위 클래스).
        """
        return self.get_entry(key, version).item

    def get_entry(self, key: str, version: int | None = None) -> RegistryEntry[T]:
        """``get`` 과 같지만 출처·버전이 담긴 ``RegistryEntry`` 를 돌려준다.

        Raises:
            UnknownExtensionError: key 또는 version이 없을 때.
        """
        versions = self._entries.get(key)
        if not versions:
            raise UnknownExtensionError(self.name, key, version)
        if version is None:
            return versions[max(versions)]
        entry = versions.get(version)
        if entry is None:
            raise UnknownExtensionError(self.name, key, version)
        return entry

    def versions(self, key: str) -> builtins.list[int]:
        """key에 등록된 버전 목록(오름차순). 없으면 빈 리스트."""
        return sorted(self._entries.get(key, {}))

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and bool(self._entries.get(key))

    def __len__(self) -> int:
        """등록된 서로 다른 key의 수."""
        return sum(1 for v in self._entries.values() if v)

    def __repr__(self) -> str:
        return f"Registry(name={self.name!r}, keys={len(self)})"

    def list(self, *, all_versions: bool = False) -> builtins.list[RegistryEntry[T]]:
        """등록 항목 목록(key 오름차순).

        Args:
            all_versions: True면 모든 버전을, False(기본)면 key별 최신 버전만.

        Returns:
            ``RegistryEntry`` 리스트. 반환값을 바꿔도 레지스트리는 바뀌지 않는다.
        """
        out: builtins.list[RegistryEntry[T]] = []
        for key in sorted(self._entries):
            versions = self._entries[key]
            if not versions:
                continue
            if all_versions:
                out.extend(versions[v] for v in sorted(versions))
            else:
                out.append(versions[max(versions)])
        return out
