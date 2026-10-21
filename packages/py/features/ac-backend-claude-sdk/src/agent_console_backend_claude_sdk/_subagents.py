"""`AgentRequest.subagents`(`SubagentSpec`) → SDK `agents={이름: AgentDefinition}`.

설계: design §R3.3·§R12.5.

I/O 없음. 서브에이전트는 위임자 세션 안에서 돌기 때문에 `AgentDefinition`이 받는 필드만 대상별로
적용된다. 나눌 수 없는 것(파일 폴더, 명령 허용)은 위임자 세션에 합치고 경고를 남긴다.

| SubagentSpec | AgentDefinition |
| --- | --- |
| `name` | `agents`의 키(위임 대상 노드 id) |
| `description` | `description`(위임자 모델이 보고 판단) |
| `prompt` + 묶음 `instructions` (+ 파일 안내) | `prompt` |
| `tools` + 묶음 `tools`(괄호 규칙 제거, 금지 우선) | `tools`(둘 다 없으면 None = SDK 기본 상속) |
| `disallowed_tools` + 묶음 `disallowed_tools` | `disallowedTools` |
| `model` | `model`(전체 모델 id 또는 별칭) |
| 묶음 `mcp_servers` | `mcpServers`(인라인 `{이름: 설정}` 목록) |
| 묶음 `skills` | `skills`(플러그인 skill 이름, 플러그인 폴더는 세션에 함께 올린다) |
| 묶음 `rules`(지침으로) | `prompt`에 이어 붙임 |
| `options` | 그 밖의 `AgentDefinition` 필드 이름 그대로(`maxTurns`, `effort`, `skills`, …) |
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import AgentDefinition

from agent_console_contracts import LogWarningPayload
from agent_console_runtime import SubagentSpec

from ._bundle import (
    RESOURCE_SLOTS,
    BundleOptions,
    SecretLookup,
    files_notice,
    map_bundle,
    tool_base,
    union,
    without_disallowed,
)
from ._hooks import HookSpec

AGENT_DEFINITION_FIELDS: frozenset[str] = frozenset(
    f.name for f in dataclasses.fields(AgentDefinition)
)
"""설치된 SDK의 `AgentDefinition` 필드 이름."""

MANAGED_AGENT_FIELDS: frozenset[str] = frozenset(
    {"description", "prompt", "tools", "disallowedTools", "model", "mcpServers"}
)
"""`SubagentSpec.options`로 덮어쓸 수 없는 필드(스펙의 다른 필드에서 온다)."""


@dataclass
class SubagentMapping:
    """서브에이전트 목록을 SDK 재료로 바꾼 결과.

    - `agents`: `ClaudeAgentOptions.agents`
    - `actors`: 이름 → 대상 에이전트 정의 id(이벤트 actor)
    - `allowed_rules`: 세션 사전 승인(`allowed_tools`)에 더할 대상들의 도구 규칙
    - `file_dirs`·`commands`: 대상별로 나눌 수 없어 위임자 세션에 합칠 폴더·명령
    - `plugin_dirs`: 대상 skill이 든 플러그인 폴더(세션에 함께 올린다, 이름은 대상별 `skills`)
    - `rule_dirs`·`hooks`: 대상별로 나눌 수 없어 위임자 세션에 합칠 규칙 폴더·hook
    """

    agents: dict[str, AgentDefinition] = field(default_factory=dict)
    actors: dict[str, str | None] = field(default_factory=dict)
    allowed_rules: list[str] = field(default_factory=list)
    file_dirs: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    plugin_dirs: list[str] = field(default_factory=list)
    rule_dirs: list[str] = field(default_factory=list)
    hooks: list[HookSpec] = field(default_factory=list)
    secret_values: list[str] = field(default_factory=list)
    warnings: list[LogWarningPayload] = field(default_factory=list)


def build_agent_definitions(
    specs: Sequence[SubagentSpec],
    *,
    resolve: SecretLookup | None = None,
    files_template: str | None = None,
    slots: Iterable[str] = RESOURCE_SLOTS,
    options: BundleOptions | None = None,
    skill_tool: str | None = None,
) -> SubagentMapping:
    """`SubagentSpec` 목록 → `AgentDefinition` dict 등.

    Args:
        specs: 위임 방식이 채운 서브에이전트 목록.
        resolve: 대상 묶음의 `secret://` 해석 함수.
        files_template: 대상 프롬프트에 붙일 파일 안내 템플릿(`{files}`), None이면 붙이지 않는다.
        slots: 받을 묶음 칸.
        options: skill 이름 형식·규칙 전달 방식(`map_bundle`과 같다).
        skill_tool: 대상에 skill이 있고 도구 목록이 정해져 있으면 그 목록에 더할 도구 이름.

    Raises:
        ValueError: 이름 중복, 관리 필드·모르는 필드를 `options`로 준 경우(`BundleError` 포함).
        SecretNotFoundError: 대상 묶음의 비밀 참조를 풀 수 없을 때.
    """
    out = SubagentMapping()
    for spec in specs:
        if not spec.name:
            raise ValueError("서브에이전트 이름(name)이 비었습니다")
        if spec.name in out.agents:
            raise ValueError(f"서브에이전트 이름 {spec.name!r}가 중복됐습니다")
        bundle = map_bundle(
            spec.bundle, resolve=resolve, slots=slots, label=spec.name, options=options
        )
        out.secret_values.extend(bundle.secret_values)
        out.warnings.extend(bundle.warnings)
        if bundle.file_dirs:
            out.file_dirs = union(out.file_dirs, bundle.file_dirs)
            out.warnings.append(
                LogWarningPayload(
                    message="서브에이전트별 파일은 나눌 수 없어 위임자 세션의 추가 폴더로 합칩니다",
                    details={"subagent": spec.name, "slot": "files"},
                )
            )
        if bundle.commands:
            out.commands = union(out.commands, bundle.commands)
            out.warnings.append(
                LogWarningPayload(
                    message="서브에이전트별 명령 허용은 나눌 수 없어 "
                    "위임자 세션 실행 범위에 합칩니다",
                    details={"subagent": spec.name, "slot": "tools", "commands": bundle.commands},
                )
            )
        if bundle.plugin_dirs:
            out.plugin_dirs = union(out.plugin_dirs, bundle.plugin_dirs)
        for shared, attr in (("rules", "rule_dirs"), ("hooks", "hooks")):
            values = getattr(bundle, attr)
            if not values:
                continue
            current = getattr(out, attr)
            current.extend(v for v in values if v not in current)
            out.warnings.append(
                LogWarningPayload(
                    message=f"서브에이전트별 {shared}는 나눌 수 없어 위임자 세션에 합칩니다",
                    details={"subagent": spec.name, "slot": shared},
                )
            )
        disallowed = union(spec.disallowed_tools or [], bundle.disallowed_tools)
        rules: list[str] | None = None
        if spec.tools is not None or bundle.tools:
            rules = without_disallowed(union(spec.tools or [], bundle.tools), disallowed)
            out.allowed_rules = union(out.allowed_rules, rules)
        prompt = "\n\n".join(
            part
            for part in (
                spec.prompt,
                *bundle.instructions,
                files_notice(files_template, bundle.files),
            )
            if part
        )
        extra = _extra_fields(spec)
        own_skills = extra.pop("skills", None)
        skills = union(own_skills if isinstance(own_skills, list) else [], bundle.skills)
        tool_names = union(tool_base(r) for r in rules) if rules is not None else None
        if (
            tool_names is not None
            and bundle.skills
            and skill_tool
            and without_disallowed([skill_tool], disallowed)
        ):
            tool_names = union(tool_names, [skill_tool])
        out.agents[spec.name] = AgentDefinition(
            description=spec.description,
            prompt=prompt,
            tools=tool_names,
            disallowedTools=disallowed or None,
            model=spec.model,
            mcpServers=(
                [{name: config} for name, config in bundle.mcp_servers.items()]
                if bundle.mcp_servers
                else None
            ),
            skills=skills or (own_skills if own_skills is not None else None),
            **extra,
        )
        out.actors[spec.name] = spec.actor
    return out


def _extra_fields(spec: SubagentSpec) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key, value in spec.options.items():
        if key in MANAGED_AGENT_FIELDS:
            raise ValueError(
                f"subagents[{spec.name}].options.{key}는 SubagentSpec 필드로 지정합니다"
            )
        if key not in AGENT_DEFINITION_FIELDS:
            raise ValueError(
                f"subagents[{spec.name}].options.{key}는 AgentDefinition 필드가 아닙니다"
            )
        extra[key] = value
    return extra
