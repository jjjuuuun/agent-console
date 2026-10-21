"""호스트 설정(단독 실행·테스트용). 통합 서버는 자기 설정 모델을 쓰고 같은 모양만 맞춘다.

설정 파일은 통합 서버 설정(``agent-console.yaml``)과 같은 키를 쓴다. 호스트가 모르는 최상위 키는
무시하므로 통합 설정 파일을 그대로 넘겨도 된다. 형식은 확장자로 고른다: ``.json``, ``.toml``,
그 밖은 YAML(``ruamel.yaml``, extra ``[host]``).
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from agent_console_modkit._assemble import ModulesConfig, default_paths
from agent_console_modkit._services import Paths


class HostSecuritySettings(BaseModel):
    """``security`` 절(통합 서버와 같은 이름·기본값). 모르는 키는 무시한다."""

    model_config = ConfigDict(extra="ignore")

    token: SecretStr | None = Field(
        default=None, description="로컬 API 토큰. 비우면 시작할 때마다 무작위로 만든다."
    )
    allow_remote: bool = Field(
        default=False,
        description="루프백이 아닌 주소에 바인딩하려면 true(명시적으로 켤 때만 외부 공개).",
    )
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_origins: list[str] = Field(default_factory=list)
    max_request_bytes: int = Field(default=1024 * 1024, ge=1024)
    max_ws_message_bytes: int = Field(default=1024 * 1024, ge=1024)
    max_ws_subscriptions: int = Field(default=256, ge=1)


class HostSettings(BaseModel):
    """호스트 설정. 기본 바인딩은 127.0.0.1(루프백)이다.

    Attributes:
        base_dir: 상대 경로 기준. None이면 설정 파일 폴더, 파일도 없으면 현재 폴더.
        workspace: 정의 폴더(``Paths.workspace``).
        state: 상태 폴더(``Paths.state``).
        api_prefix: REST 접두.
        ws_path: WS 경로.
    """

    model_config = ConfigDict(extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=0, le=65535)
    base_dir: Path | None = None
    workspace: Path = Path(".agent-console")
    state: Path = Path(".agent-console/state")
    log_level: str = "info"
    api_prefix: str = "/api/v1"
    ws_path: str = "/ws"
    security: HostSecuritySettings = Field(default_factory=HostSecuritySettings)
    modules: ModulesConfig = Field(default_factory=ModulesConfig)

    def paths(self, fallback_base: Path) -> Paths:
        """``base_dir``(없으면 ``fallback_base``) 기준 경로."""
        base = self.base_dir if self.base_dir is not None else fallback_base
        return default_paths(base, workspace=self.workspace, state=self.state)


def read_config_file(path: Path) -> dict[str, Any]:
    """설정 파일을 매핑으로 읽는다(``.json``·``.toml``·그 밖은 YAML). 빈 파일은 ``{}``.

    Raises:
        OSError: 읽기 실패.
        ValueError: 형식 오류 또는 최상위가 매핑이 아님.
    """
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    data: Any
    if suffix == ".json":
        data = json.loads(text) if text.strip() else {}
    elif suffix == ".toml":
        data = tomllib.loads(text)
    else:
        from ruamel.yaml import YAML

        data = YAML(typ="safe").load(text) or {}
    if not isinstance(data, Mapping):
        raise ValueError(f"설정 파일의 최상위는 매핑이어야 합니다: {path}")
    return dict(data)


def load_host_settings(
    path: Path | None = None, *, overrides: Mapping[str, Any] | None = None
) -> HostSettings:
    """설정 파일(선택) + 덮어쓰기(최상위 키 단위)로 ``HostSettings``를 만든다."""
    data: dict[str, Any] = read_config_file(path) if path is not None else {}
    data.update(dict(overrides or {}))
    return HostSettings.model_validate(data)


__all__ = [
    "HostSecuritySettings",
    "HostSettings",
    "load_host_settings",
    "read_config_file",
]
