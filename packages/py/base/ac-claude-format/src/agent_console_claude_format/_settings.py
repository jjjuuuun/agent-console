"""`settings.json`의 권한(`permissions.allow/deny`)과 hook(`hooks`).

hook 구조: 이벤트 이름 → 매처 묶음 목록 `[{matcher?, hooks: [{type, command, timeout?}]}]`.
이벤트 이름은 문자열 그대로 다룬다(목록을 갖지 않는다). 명령형(`type: command`) 처리기만
`HookSpec`이 되고, 다른 형식은 위치만 `skipped`로 알린다. 같은 구조가 에이전트 파일
frontmatter `hooks`에도 쓰인다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from ._frontmatter import json_safe, str_list

__all__ = [
    "COMMAND_HOOK_TYPE",
    "ClaudeSettings",
    "HookSpec",
    "parse_hooks",
    "parse_settings",
    "render_hooks",
    "render_settings",
]

COMMAND_HOOK_TYPE: Final = "command"
"""명령형 hook 처리기의 `type` 값."""

_HANDLER_KEYS: Final = ("type", "command", "timeout")


@dataclass(frozen=True, slots=True)
class HookSpec:
    """명령형 hook 하나.

    Attributes:
        event: 이벤트 이름(자유 문자열).
        command: 명령.
        matcher: 매처(None = 모두·매처 없는 이벤트).
        timeout_seconds: 시간 제한(초, None = 기본값).
        extra: 처리기의 다른 키(`args` 등, JSON 호환). Agent Console hook 종류에는 없는 키다.
    """

    event: str
    command: str
    matcher: str | None = None
    timeout_seconds: float | int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClaudeSettings:
    """`settings.json`에서 읽은 권한과 hook.

    Attributes:
        allow / deny: 권한 목록(None = 키 없음).
        hooks: 명령형 hook(파일 순서).
        skipped_hooks: 명령형이 아니거나 형식이 틀린 처리기의 JSON Pointer.
    """

    allow: list[str] | None = None
    deny: list[str] | None = None
    hooks: list[HookSpec] = field(default_factory=list)
    skipped_hooks: list[str] = field(default_factory=list)


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _timeout(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return None
    return value


def parse_hooks(hooks: Any, *, base: str = "/hooks") -> tuple[list[HookSpec], list[str]]:
    """hook 구조 → (명령형 hook 목록, 건너뛴 처리기의 JSON Pointer 목록)."""
    specs: list[HookSpec] = []
    skipped: list[str] = []
    if not isinstance(hooks, Mapping):
        return specs, skipped
    for event, groups in hooks.items():
        event_path = f"{base}/{_escape(str(event))}"
        if not isinstance(groups, list):
            skipped.append(event_path)
            continue
        for g, group in enumerate(groups):
            group_path = f"{event_path}/{g}"
            handlers = group.get("hooks") if isinstance(group, Mapping) else None
            if not isinstance(handlers, list):
                skipped.append(group_path)
                continue
            matcher = group.get("matcher") if isinstance(group, Mapping) else None
            for h, handler in enumerate(handlers):
                path = f"{group_path}/hooks/{h}"
                if (
                    not isinstance(handler, Mapping)
                    or handler.get("type", COMMAND_HOOK_TYPE) != COMMAND_HOOK_TYPE
                    or not isinstance(handler.get("command"), str)
                    or not handler["command"]
                ):
                    skipped.append(path)
                    continue
                extra = {k: v for k, v in handler.items() if k not in _HANDLER_KEYS}
                specs.append(
                    HookSpec(
                        event=str(event),
                        command=handler["command"],
                        matcher=matcher if isinstance(matcher, str) and matcher else None,
                        timeout_seconds=_timeout(handler.get("timeout")),
                        extra=json_safe(extra),
                    )
                )
    return specs, skipped


def parse_settings(data: Any) -> ClaudeSettings:
    """`settings.json` 내용(JSON 값) → `ClaudeSettings`. 형식이 다르면 빈 결과."""
    if not isinstance(data, Mapping):
        return ClaudeSettings()
    perms = data.get("permissions")
    allow = deny = None
    if isinstance(perms, Mapping):
        allow = str_list(perms.get("allow"))
        deny = str_list(perms.get("deny"))
    hooks, skipped = parse_hooks(data.get("hooks"))
    return ClaudeSettings(allow=allow, deny=deny, hooks=hooks, skipped_hooks=skipped)


def render_hooks(hooks: Sequence[HookSpec]) -> dict[str, list[dict[str, Any]]]:
    """hook 목록 → hook 구조. 같은 (이벤트, 매처)는 한 묶음으로, 순서는 처음 나온 순서."""
    out: dict[str, list[dict[str, Any]]] = {}
    groups: dict[tuple[str, str | None], dict[str, Any]] = {}
    for spec in hooks:
        key = (spec.event, spec.matcher)
        group = groups.get(key)
        if group is None:
            group = {"matcher": spec.matcher} if spec.matcher else {}
            group["hooks"] = []
            groups[key] = group
            out.setdefault(spec.event, []).append(group)
        handler: dict[str, Any] = {"type": COMMAND_HOOK_TYPE, "command": spec.command}
        if spec.timeout_seconds is not None:
            handler["timeout"] = spec.timeout_seconds
        for k, v in spec.extra.items():
            handler.setdefault(k, v)
        group["hooks"].append(handler)
    return out


def render_settings(
    *,
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    hooks: Sequence[HookSpec] = (),
) -> dict[str, Any]:
    """권한·hook → `settings.json` 내용(JSON 값). 빈 부분은 쓰지 않는다."""
    data: dict[str, Any] = {}
    permissions: dict[str, list[str]] = {}
    if allow:
        permissions["allow"] = list(allow)
    if deny:
        permissions["deny"] = list(deny)
    if permissions:
        data["permissions"] = permissions
    if hooks:
        data["hooks"] = render_hooks(hooks)
    return data
