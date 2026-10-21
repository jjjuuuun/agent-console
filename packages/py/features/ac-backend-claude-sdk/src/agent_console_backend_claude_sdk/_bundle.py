"""실행 묶음(`ResourceBundle`) 칸 → SDK 옵션 재료(design §R12.4·§R12.5). I/O 없음.

칸 값 모양은 기본 종류 플러그인(`ac-resources-core`) README를 따른다. 모든 칸은 항목 목록이다.

- `instructions`: 문자열(또는 `{text}`) → 순서대로 이어 붙일 지침 목록
  (prepend 항목은 이미 앞에 있다).
- `files`: 경로 문자열 또는 `{path, root?, name?}` → 파일 경로 목록 + `add_dirs`로 넘길 폴더
  (`root`, 없으면 파일의 부모).
- `mcp_servers`: `{name, type, command?, args?, env?, url?, headers?}` → `name` → SDK
  `McpServerConfig`. 같은 이름은 뒤 항목이 이긴다.
- `tools`: `{tools?, disallowed_tools?, commands?}` → 허용 규칙 합집합, 금지 합집합
  (금지가 허용보다 우선), 명령 합집합.

- `skills`: 노드가 쓴 항목 트리 `{name, root, tree_root, files}`(`ac-nodes-core.write_item_trees`,
  `root = <tree_root>/skills/<name>`) → 로컬 플러그인 폴더(`tree_root`, 플러그인 이름 = 폴더 이름)와
  skill 이름(`skill_name_template`, 기본 `{plugin}:{skill}`). 경로가 없거나 모양이 다르면 경고.
- `rules`: `{name, paths, text, instruction, root?}` → `rule_delivery=instructions`(기본)면
  `instruction`을 지침으로, `files`면 항목 폴더(`root`, 안에 `.claude/rules/…`)를 추가 폴더로
  (`rule_dirs`, 환경변수 `rule_files_env`와 함께 — 미확인 경로).
- `hooks`: `{name, event, matcher?, command, timeout_seconds?}` → `HookSpec`(전달은 `_hooks`).

`files` 칸은 agent 노드가 실행 폴더에 쓴 뒤 경로로 바꿔 넘긴다. 경로가 없는 항목(본문만 있음)은
백엔드가 파일을 쓰지 않으므로 전달하지 않고 경고만 남긴다.
`mcp_servers`의 `env`·`headers` 값은 `secret://` 참조를 주입한 해석기로 풀고, 푼 값은
`secret_values`로 돌려줘 이벤트 raw에서 가리게 한다. 경고·오류에는 값을 넣지 않는다.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from agent_console_contracts import KnownResourceSlots, LogWarningPayload, ResourceBundle
from agent_console_runtime import SecretNotFoundError, is_secret_ref

from ._hooks import HookSpec, parse_hooks

RESOURCE_SLOTS: tuple[str, ...] = (
    KnownResourceSlots.INSTRUCTIONS,
    KnownResourceSlots.FILES,
    KnownResourceSlots.MCP_SERVERS,
    KnownResourceSlots.TOOLS,
    KnownResourceSlots.SKILLS,
    KnownResourceSlots.RULES,
)
"""이 백엔드가 늘 받는 실행 묶음 칸. `hooks`는 설치자 설정 `allow_command_hooks`가 켜졌을 때만
더한다(`COMMAND_HOOK_SLOTS`)."""

COMMAND_HOOK_SLOTS: tuple[str, ...] = (KnownResourceSlots.HOOKS,)
"""명령 실행을 허용했을 때만 받는 칸."""

SUBAGENT_SLOTS: tuple[str, ...] = (
    KnownResourceSlots.INSTRUCTIONS,
    KnownResourceSlots.MCP_SERVERS,
    KnownResourceSlots.TOOLS,
    KnownResourceSlots.SKILLS,
    KnownResourceSlots.RULES,
)
"""서브에이전트(`AgentDefinition`)마다 따로 싣는 칸(`BackendCapabilities.subagent_slots`).
files·hooks는 대상별로 나눌 수 없어 위임자 세션에 합친다(design §R12.5). tools 칸의 명령 허용은
세션 실행 범위에 합쳐지며 실행 때 경고한다(`build_agent_definitions`). skills는
`AgentDefinition.skills`로 대상별 이름을 주지만 플러그인 폴더는 세션에 함께 올린다. rules는
지침으로 내릴 때(기본) 대상별이고, 파일로 내리면 세션 공유다(실행 때 경고)."""

DEFAULT_SKILL_NAME_TEMPLATE = "{plugin}:{skill}"
"""플러그인 안 skill의 이름 형식(SDK 문서: `plugin:skill`). `{plugin}` = 플러그인 폴더 이름."""

DEFAULT_RULE_FILES_ENV: dict[str, str] = {"CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "1"}
"""규칙을 파일로 내릴 때 넣는 환경변수(Claude Code 문서: 추가 폴더의 `.claude/rules` 읽기)."""

SKILLS_DIR = "skills"
"""플러그인 폴더 안 skill 폴더 이름(Claude Code 플러그인 표준 위치). 노드가 칸 이름으로 만든
트리 폴더(`<tree_root>/skills/<name>`)와 같아야 플러그인으로 넘길 수 있다."""


@dataclass(frozen=True)
class BundleOptions:
    """칸 → SDK 재료 변환 선택(`Agent.backend_options`에서 온다)."""

    skill_name_template: str = DEFAULT_SKILL_NAME_TEMPLATE
    rule_delivery: Literal["instructions", "files"] = "instructions"


type SecretLookup = Callable[[str], str]
"""`secret://이름` → 값. 찾지 못하면 `SecretNotFoundError`."""


class BundleError(ValueError):
    """묶음 칸 값의 모양이 틀렸다. 메시지에는 칸·위치·사유만 있고 값은 없다."""


@dataclass
class BundleMapping:
    """묶음 하나를 SDK 옵션 재료로 바꾼 결과."""

    instructions: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    file_dirs: list[str] = field(default_factory=list)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    plugin_dirs: list[str] = field(default_factory=list)
    rule_dirs: list[str] = field(default_factory=list)
    hooks: list[HookSpec] = field(default_factory=list)
    secret_values: list[str] = field(default_factory=list)
    warnings: list[LogWarningPayload] = field(default_factory=list)


def map_bundle(
    bundle: ResourceBundle | Mapping[str, Any] | None,
    *,
    resolve: SecretLookup | None = None,
    slots: Iterable[str] = RESOURCE_SLOTS,
    label: str | None = None,
    options: BundleOptions | None = None,
) -> BundleMapping:
    """묶음을 SDK 옵션 재료로 바꾼다.

    Args:
        bundle: 실행 묶음(`ResourceBundle` 또는 그 dict 모양). None이면 빈 결과.
        resolve: `secret://` 참조 해석 함수. 없는데 참조가 있으면 `SecretNotFoundError`.
        slots: 받을 칸. 그 밖의 칸에 값이 있으면 경고만 남긴다.
        label: 경고에 붙일 출처 이름(예: 서브에이전트 이름).
        options: skill 이름 형식·규칙 전달 방식(기본 `BundleOptions()`).

    Raises:
        BundleError: 칸 값의 모양이 틀렸을 때(값은 메시지에 넣지 않는다).
        SecretNotFoundError: 비밀 참조를 풀 수 없을 때.
    """
    out = BundleMapping()
    opts = options or BundleOptions()
    if bundle is None:
        return out
    values = (
        bundle.slots
        if isinstance(bundle, ResourceBundle)
        else ResourceBundle.model_validate(bundle).slots
    )
    accepted = set(slots)
    for slot, value in values.items():
        if not value:
            continue
        if slot not in accepted:
            out.warnings.append(
                LogWarningPayload(
                    message=f"이 백엔드는 실행 묶음 칸 {slot!r}를 적용하지 않습니다",
                    details=_details(slot=slot, label=label),
                )
            )
            continue
        items = _items(slot, value)
        if slot == KnownResourceSlots.INSTRUCTIONS:
            out.instructions.extend(_instructions(items))
        elif slot == KnownResourceSlots.FILES:
            _files(items, out, label)
        elif slot == KnownResourceSlots.MCP_SERVERS:
            _mcp_servers(items, out, resolve)
        elif slot == KnownResourceSlots.TOOLS:
            _tools(items, out)
        elif slot == KnownResourceSlots.SKILLS:
            _skills(items, out, opts, label)
        elif slot == KnownResourceSlots.RULES:
            _rules(items, out, opts, label)
        elif slot == KnownResourceSlots.HOOKS:
            specs, warnings = parse_hooks(items)
            out.hooks.extend(specs)
            out.warnings.extend(warnings)
    return out


def files_notice(template: str | None, paths: Iterable[str]) -> str | None:
    """파일 목록 안내문(`template`의 `{files}`를 `- 경로` 줄로 바꾼다).

    파일이 없거나 템플릿이 없으면 None.
    """
    listed = list(paths)
    if not template or not listed:
        return None
    return template.replace("{files}", "\n".join(f"- {p}" for p in listed))


def tool_base(rule: str) -> str:
    """`"Bash(git:*)"` → `"Bash"`."""
    return rule.split("(", 1)[0].strip()


def without_disallowed(rules: Iterable[str], disallowed: Iterable[str]) -> list[str]:
    """금지 목록에 걸리는 허용 규칙을 뺀다(금지가 허용보다 우선).

    금지 항목이 도구 이름(괄호 없음)이면 그 도구의 모든 규칙을, 괄호 규칙이면 같은 규칙만 뺀다.
    """
    blocked = list(disallowed)
    names = {d for d in blocked if "(" not in d}
    return [r for r in rules if r not in blocked and tool_base(r) not in names]


def union(*groups: Iterable[str]) -> list[str]:
    """순서를 지키는 합집합."""
    out: list[str] = []
    for group in groups:
        for item in group:
            if item not in out:
                out.append(item)
    return out


# ---------------------------------------------------------------- 칸별


def _items(slot: str, value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(value)
    raise BundleError(f"실행 묶음 칸 {slot!r}의 값은 목록이어야 합니다")


def _instructions(items: list[Any]) -> list[str]:
    out: list[str] = []
    for i, item in enumerate(items):
        if isinstance(item, Mapping):
            item = item.get("text")
        if not isinstance(item, str):
            raise BundleError(f"instructions[{i}]는 문자열이어야 합니다")
        if item.strip():
            out.append(item)
    return out


def _files(items: list[Any], out: BundleMapping, label: str | None) -> None:
    for i, item in enumerate(items):
        path: Any
        root: Any = None
        if isinstance(item, str):
            path = item
        elif isinstance(item, Mapping):
            path, root = item.get("path"), item.get("root")
        else:
            raise BundleError(f"files[{i}]는 경로 문자열이나 {{path, root?}}여야 합니다")
        if not isinstance(path, str) or not path:
            out.warnings.append(
                LogWarningPayload(
                    message="파일 칸 항목에 경로가 없어 전달하지 않습니다"
                    "(실행 폴더에 쓰는 것은 노드의 일입니다)",
                    details=_details(slot="files", index=i, label=label),
                )
            )
            continue
        if root is not None and not isinstance(root, str):
            raise BundleError(f"files[{i}].root는 문자열이어야 합니다")
        folder = root or os.path.dirname(path)
        if path not in out.files:
            out.files.append(path)
        if folder and folder not in out.file_dirs:
            out.file_dirs.append(folder)


def _mcp_servers(items: list[Any], out: BundleMapping, resolve: SecretLookup | None) -> None:
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise BundleError(f"mcp_servers[{i}]는 객체여야 합니다")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise BundleError(f"mcp_servers[{i}].name이 없습니다")
        config: dict[str, Any] = {k: v for k, v in item.items() if k != "name"}
        config.setdefault("type", "stdio")
        for key in ("env", "headers"):
            raw = config.get(key)
            if raw is None:
                continue
            if not isinstance(raw, Mapping):
                raise BundleError(f"mcp_servers[{i}].{key}는 객체여야 합니다")
            config[key] = {
                str(k): _secret(v, resolve, out, f"mcp_servers[{i}].{key}") for k, v in raw.items()
            }
        # 같은 이름은 뒤 항목이 이긴다(앞 항목을 지우고 다시 넣어 순서도 뒤로).
        out.mcp_servers.pop(name, None)
        out.mcp_servers[name] = config


def _tools(items: list[Any], out: BundleMapping) -> None:
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise BundleError(f"tools[{i}]는 객체여야 합니다")
        for key, target in (
            ("tools", out.tools),
            ("disallowed_tools", out.disallowed_tools),
            ("commands", out.commands),
        ):
            values = item.get(key)
            if values is None:
                continue
            if not isinstance(values, list | tuple) or not all(isinstance(v, str) for v in values):
                raise BundleError(f"tools[{i}].{key}는 문자열 목록이어야 합니다")
            target.extend(v for v in values if v not in target)


def _skills(items: list[Any], out: BundleMapping, opts: BundleOptions, label: str | None) -> None:
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise BundleError(f"skills[{i}]는 객체여야 합니다")
        name, root, tree = item.get("name"), item.get("root"), item.get("tree_root")
        if not all(isinstance(v, str) and v for v in (name, root, tree)):
            out.warnings.append(
                LogWarningPayload(
                    message="skill 항목에 실행 폴더 경로가 없어 전달하지 않습니다"
                    "(실행 폴더에 쓰는 것은 노드의 일입니다)",
                    details=_details(slot="skills", index=i, label=label),
                )
            )
            continue
        assert isinstance(name, str)
        assert isinstance(root, str)
        assert isinstance(tree, str)
        expected = os.path.join(tree, SKILLS_DIR, name)
        if os.path.normpath(root) != os.path.normpath(expected):
            out.warnings.append(
                LogWarningPayload(
                    message="skill 폴더가 플러그인 구조(<폴더>/skills/<이름>)가 아니라 "
                    "전달하지 않습니다",
                    details=_details(slot="skills", index=i, label=label),
                )
            )
            continue
        plugin = os.path.basename(os.path.normpath(tree))
        qualified = opts.skill_name_template.replace("{plugin}", plugin).replace("{skill}", name)
        if qualified not in out.skills:
            out.skills.append(qualified)
        if tree not in out.plugin_dirs:
            out.plugin_dirs.append(tree)


def _rules(items: list[Any], out: BundleMapping, opts: BundleOptions, label: str | None) -> None:
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise BundleError(f"rules[{i}]는 객체여야 합니다")
        instruction = item.get("instruction", item.get("text"))
        root = item.get("root")
        if opts.rule_delivery == "files" and isinstance(root, str) and root:
            if root not in out.rule_dirs:
                out.rule_dirs.append(root)
            continue
        if opts.rule_delivery == "files":
            out.warnings.append(
                LogWarningPayload(
                    message="규칙 파일 경로가 없어 지침으로 대신 전달합니다",
                    details=_details(slot="rules", index=i, label=label),
                )
            )
        if not isinstance(instruction, str):
            raise BundleError(f"rules[{i}].instruction은 문자열이어야 합니다")
        if instruction.strip():
            out.instructions.append(instruction)


def _secret(value: Any, resolve: SecretLookup | None, out: BundleMapping, where: str) -> str:
    if not isinstance(value, str):
        raise BundleError(f"{where}의 값은 문자열이어야 합니다")
    text: str = value
    if is_secret_ref(text):
        if resolve is None:
            raise SecretNotFoundError(text.removeprefix("secret://"))
        text = resolve(text)
    out.secret_values.append(text)
    return text


def _details(**values: Any) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}
