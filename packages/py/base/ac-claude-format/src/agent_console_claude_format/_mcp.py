"""`.mcp.json`(`mcpServers`) ↔ MCP 서버 리소스 config(`{name, transport, command?, args?, url?,
env?, headers?}`).

비밀: Agent Console은 `secret://이름` 참조를, Claude Code는 `${이름}` 환경 변수 확장을 쓴다.
`.mcp.json` → config는 값을 그대로 옮긴다(평문을 참조로 바꾸는 일은 가져오는 쪽 몫).
config → `.mcp.json`은 참조를 `${이름}`으로 바꾸고 **참조가 아닌 env·headers 값은 쓰지 않는다**.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

__all__ = [
    "MCP_SERVERS_KEY",
    "SECRET_REF_PREFIX",
    "McpEntry",
    "SecretStyle",
    "env_placeholder",
    "mcp_config_from_entry",
    "mcp_entry_from_config",
    "parse_env_ref",
    "parse_mcp",
    "render_mcp",
]

MCP_SERVERS_KEY: Final = "mcpServers"
SECRET_REF_PREFIX: Final = "secret://"
TRANSPORTS: Final = ("stdio", "http", "sse")
SECRET_MAP_FIELDS: Final = ("env", "headers")

type SecretStyle = Literal["env_var", "omit"]
"""env·headers의 비밀 참조를 쓰는 방식: env_var = `${이름}`, omit = 그 키를 쓰지 않음."""

_ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?\}$")
_SECRET_REF = re.compile(r"secret://([A-Za-z0-9_][A-Za-z0-9_.-]*)")


def env_placeholder(name: str) -> str:
    """환경 변수 확장 자리(`${이름}`)."""
    return "${" + name + "}"


def parse_env_ref(text: str) -> str | None:
    """`${이름}`(또는 `${이름:-기본}`)이면 이름, 아니면 None."""
    match = _ENV_REF.match(text.strip())
    return match.group(1) if match else None


def parse_mcp(data: Any) -> dict[str, dict[str, Any]]:
    """`.mcp.json` 내용(JSON 값) → 서버 이름 → 원본 항목(객체인 것만)."""
    servers = data.get(MCP_SERVERS_KEY) if isinstance(data, Mapping) else None
    if not isinstance(servers, Mapping):
        return {}
    return {str(k): dict(v) for k, v in servers.items() if isinstance(v, Mapping)}


def mcp_config_from_entry(name: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    """`.mcp.json` 항목 하나 → MCP 서버 리소스 config(값은 그대로, env·headers 값은 문자열로)."""
    transport = str(raw.get("type") or ("http" if raw.get("url") else "stdio"))
    if transport not in TRANSPORTS:
        transport = "http" if raw.get("url") else "stdio"
    config: dict[str, Any] = {"name": name, "transport": transport}
    if isinstance(raw.get("command"), str):
        config["command"] = raw["command"]
    if isinstance(raw.get("args"), list):
        config["args"] = [str(a) for a in raw["args"]]
    if isinstance(raw.get("url"), str):
        config["url"] = raw["url"]
    for key in SECRET_MAP_FIELDS:
        values = raw.get(key)
        if isinstance(values, Mapping):
            config[key] = {str(k): str(v) for k, v in values.items()}
    return config


@dataclass(frozen=True, slots=True)
class McpEntry:
    """`mcp_entry_from_config` 결과.

    Attributes:
        name: 서버 이름.
        entry: `.mcp.json`의 `mcpServers[name]` 값.
        omitted: 쓰지 않은 위치(`env/KEY` 등. 참조가 아닌 값이거나 `omit` 방식의 참조).
    """

    name: str
    entry: dict[str, Any]
    omitted: list[str] = field(default_factory=list)


def _refs_to_env(text: str) -> str:
    return _SECRET_REF.sub(lambda m: env_placeholder(_env_name(m.group(1))), text)


def _env_name(ref: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", ref)


def mcp_entry_from_config(
    config: Mapping[str, Any], *, fallback_name: str, secret_style: SecretStyle = "env_var"
) -> McpEntry:
    """MCP 서버 리소스 config → `.mcp.json` 항목.

    - env·headers: `secret://이름` → `${이름}`(`env_var`) 또는 생략(`omit`). 참조가 아닌 값은
      생략하고 `omitted`에 위치를 남긴다(평문 비밀을 쓰지 않는다).
    - args·url: 안의 `secret://이름`을 `${이름}`으로 바꾼다(방식과 무관 — 빼면 서버가
      동작하지 않음).
    """
    raw_name = config.get("name")
    name = raw_name if isinstance(raw_name, str) and raw_name else fallback_name
    transport = config.get("transport")
    entry: dict[str, Any] = {"type": transport if transport in TRANSPORTS else "stdio"}
    if isinstance(config.get("command"), str):
        entry["command"] = config["command"]
    if isinstance(config.get("args"), list):
        entry["args"] = [_refs_to_env(str(a)) for a in config["args"]]
    if isinstance(config.get("url"), str):
        entry["url"] = _refs_to_env(config["url"])
    omitted: list[str] = []
    for key in SECRET_MAP_FIELDS:
        values = config.get(key)
        if not isinstance(values, Mapping):
            continue
        out: dict[str, str] = {}
        for k, v in values.items():
            text = str(v)
            if text.startswith(SECRET_REF_PREFIX) and secret_style == "env_var":
                out[str(k)] = env_placeholder(_env_name(text.removeprefix(SECRET_REF_PREFIX)))
            else:
                omitted.append(f"{key}/{k}")
        if out:
            entry[key] = out
    return McpEntry(name=name, entry=entry, omitted=omitted)


def render_mcp(servers: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """서버 이름 → 항목 → `.mcp.json` 내용(JSON 값)."""
    return {MCP_SERVERS_KEY: {name: dict(entry) for name, entry in servers.items()}}
