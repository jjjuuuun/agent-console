"""접근 판단: 리소스 `memory`의 접근 설정(`MemoryAccessConfig`)이 범위 종류·동작을 허용하는가."""

from __future__ import annotations

from agent_console_contracts.memory import MEMORY_ACCESS_OPS, MemoryAccessConfig


def allowed(config: MemoryAccessConfig, op: str, scope_kind: str) -> bool:
    """`scope_kind` 범위에서 동작 `op`(read·search·write·delete)를 허용하는지.

    같은 범위 종류가 설정에 여러 번 나오면 허용 동작을 합친다.

    >>> from agent_console_contracts.memory import MemoryScopeAccess
    >>> cfg = MemoryAccessConfig(scopes=[MemoryScopeAccess(kind="notes", access=["read"])])
    >>> allowed(cfg, "read", "notes"), allowed(cfg, "write", "notes"), allowed(cfg, "read", "x")
    (True, False, False)
    """
    return any(item.kind == scope_kind and op in item.access for item in config.scopes)


def scope_kinds_for(config: MemoryAccessConfig, op: str) -> list[str]:
    """동작 `op`을 허용한 범위 종류(설정 순서, 중복 없음)."""
    out: list[str] = []
    for item in config.scopes:
        if op in item.access and item.kind not in out:
            out.append(item.kind)
    return out


def granted_ops(config: MemoryAccessConfig) -> list[str]:
    """어느 범위에서든 허용된 동작(계약 어휘 순서)."""
    return [op for op in MEMORY_ACCESS_OPS if scope_kinds_for(config, op)]


def default_scope_kind(config: MemoryAccessConfig) -> str | None:
    """범위를 생략했을 때 쓰는 범위 종류: `default_scope`, 없으면 설정의 첫 범위 종류."""
    if config.default_scope:
        return config.default_scope
    return config.scopes[0].kind if config.scopes else None
