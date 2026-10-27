"""프로필 문서 읽기(`{version, profiles: {id: 프로필}}`)와 패키지 기본 프로필."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any, Final

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from agent_console_contracts.architecture import ArchitectureProfile

DEFAULT_PROFILES_RESOURCE: Final = "data/default_architecture.yaml"
"""패키지 기본 프로필 데이터(패키지 기준 경로)."""


class ProfileDocumentError(ValueError):
    """프로필 문서를 읽을 수 없다(YAML 문법·최상위 모양·프로필 형식)."""


def _yaml() -> YAML:
    return YAML(typ="safe", pure=True)


def profiles_from_mapping(data: Any) -> dict[str, ArchitectureProfile]:
    """이미 읽은 문서 객체에서 프로필을 꺼낸다(값이 null인 id는 건너뛴다).

    Args:
        data: `{"profiles": {id: 프로필 객체}}` 모양(다른 최상위 키는 무시). None이면 빈 결과.

    Returns:
        id → 프로필(문서 순서).

    Raises:
        ProfileDocumentError: 최상위·`profiles`가 객체가 아니거나 프로필 형식이 틀렸을 때.
    """
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise ProfileDocumentError("프로필 문서의 최상위는 객체여야 합니다")
    raw = data.get("profiles")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ProfileDocumentError("`profiles`는 프로필 id → 프로필 객체여야 합니다")
    found: dict[str, ArchitectureProfile] = {}
    for key, value in raw.items():
        if value is None:
            continue
        try:
            found[str(key)] = ArchitectureProfile.model_validate(value)
        except ValueError as exc:  # pydantic ValidationError는 ValueError다
            raise ProfileDocumentError(f"프로필 {key!r}의 형식이 맞지 않습니다: {exc}") from exc
    return found


def parse_profiles_document(text: str) -> dict[str, ArchitectureProfile]:
    """YAML(또는 JSON) 프로필 문서 글을 읽는다.

    Raises:
        ProfileDocumentError: YAML 문법 오류이거나 `profiles_from_mapping`이 거부할 때.
    """
    try:
        data = _yaml().load(text)
    except YAMLError as exc:
        raise ProfileDocumentError(f"YAML을 읽을 수 없습니다: {exc}") from exc
    return profiles_from_mapping(data)


def load_default_profiles(path: Path | None = None) -> dict[str, ArchitectureProfile]:
    """패키지 기본 프로필을 읽는다(부를 때마다 새로 읽는다, 전역 캐시 없음).

    Args:
        path: 다른 파일을 기본 프로필로 쓸 때. 없으면 패키지 데이터
            `data/default_architecture.yaml`.

    Returns:
        id → 프로필. 파일이 없으면 빈 결과(지워도 동작한다).

    Raises:
        ProfileDocumentError: 파일 내용이 프로필 문서가 아닐 때.
    """
    try:
        if path is not None:
            text = path.read_text(encoding="utf-8")
        else:
            text = (
                resources.files(__package__ or "agent_console_architecture")
                .joinpath(DEFAULT_PROFILES_RESOURCE)
                .read_text(encoding="utf-8")
            )
    except (FileNotFoundError, NotADirectoryError):
        return {}
    return parse_profiles_document(text)
