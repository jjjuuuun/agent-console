"""기본 내보내기 형식 `claude-dir`: 정의 → Claude Code 프로젝트 산출물(확장 지점 X8의 첫 구현).

- 에이전트 → `.claude/agents/<파일>.md`(frontmatter + 시스템 프롬프트). 붙은 skill·MCP·hook은
  frontmatter `skills`·`mcpServers`·`hooks`로, 지침은 본문 뒤에 붙인다.
- 지침 리소스 → `CLAUDE.md`에 이어 붙이기(`inline`) 또는 `.claude/instructions/<id>.md` +
  `CLAUDE.md`의 `@경로`(`separate_files`).
- 규칙 리소스 → `.claude/rules/<이름>.md`(`paths` frontmatter).
- skill 리소스 → `.claude/skills/<이름>/`(파일 그대로).
- hook·도구 권한 리소스 → `.claude/settings.json`의 `hooks`·`permissions`.
- MCP 서버 리소스 → `.mcp.json`(`secret://이름` → `${이름}`, 평문 값은 쓰지 않음).
- 팀 구성 → 위 산출물 + 경고 `export.semantics_approximate`. 옵션 `main_node`의 에이전트가
  `CLAUDE.md` 본문(기본 없음 — 추론하지 않는다).

종류 이름·리소스 종류 id는 `ClaudeMapping`, 경로는 `ClaudeLayout` 데이터다(설치자 옵션
`exports.options.claude-dir.mapping`·`layout`으로 바꾼다). 형식이 다루지 않는 리소스 종류는 경고와
함께 건너뛴다. 이 모듈은 파일을 쓰지 않는다(쓰기는 `ExportService`).
"""

from __future__ import annotations

import json
import mimetypes
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agent_console_claude_format import (
    AgentFile,
    ClaudeLayout,
    ClaudeMapping,
    HookSpec,
    SecretStyle,
    agent_file_from_document,
    dump_json,
    mcp_entry_from_config,
    parse_hooks,
    render_agent_md,
    render_hooks,
    render_mcp,
    render_rule,
    render_settings,
    render_skill,
)
from agent_console_contracts import ExporterDescriptor, ExportSelection, Issue

from ._interfaces import DependencyLike, ExportCatalog, ExportIssueCodes, ExportOutput, OutputFile
from ._paths import path_problem

__all__ = [
    "CLAUDE_DIR_ID",
    "DEFAULT_AGENT_FILE_NAME",
    "ClaudeDirExporter",
    "claude_dir_exporter",
    "claude_dir_options_schema",
]

CLAUDE_DIR_ID: Final = "claude-dir"
DEFAULT_AGENT_FILE_NAME: Final = "{id}.md"
"""에이전트 파일 이름 템플릿 기본값(`{id}`·`{name}`)."""

_MARKDOWN = "text/markdown"
_JSON = "application/json"
_ATTACHMENT_ONLY_FIELDS = frozenset({"resources"})
"""에이전트 정의에서 첨부로 따로 내보내는 필드(빠진 설정 경고에서 뺀다)."""


def claude_dir_options_schema() -> dict[str, Any]:
    """옵션 스키마(`ExporterDescriptor.config_schema`). 기본값은 표시용이며 생략 = 기본값."""
    return {
        "type": "object",
        "properties": {
            "main_node": {
                "type": "string",
                "minLength": 1,
                "title": "주 노드",
                "description": "팀 구성을 내보낼 때 CLAUDE.md 본문이 될 노드 id. "
                "비우면 없음(자동으로 고르지 않는다).",
            },
            "agent_file_name": {
                "type": "string",
                "minLength": 1,
                "default": DEFAULT_AGENT_FILE_NAME,
                "title": "에이전트 파일 이름",
                "description": "{id}·{name} 자리를 바꾼다.",
            },
            "instructions_mode": {
                "type": "string",
                "enum": ["inline", "separate_files"],
                "default": "inline",
                "title": "지침 쓰는 방식",
                "description": "inline: CLAUDE.md에 이어 붙임, separate_files: 지침마다 파일 + "
                "CLAUDE.md에서 @경로로 불러옴.",
            },
            "include_shared_resources": {
                "type": "boolean",
                "default": True,
                "title": "공유 리소스 포함",
                "description": "팀 구성 층·공통 층에 붙은 리소스도 내보낸다.",
            },
            "secret_style": {
                "type": "string",
                "enum": ["env_var", "omit"],
                "default": "env_var",
                "title": "비밀 참조",
                "description": "env_var: secret://이름 → ${이름}, omit: 비밀 칸을 쓰지 않음.",
            },
        },
        "additionalProperties": False,
    }


def _default(key: str) -> Any:
    return claude_dir_options_schema()["properties"][key].get("default")


@dataclass(frozen=True, slots=True)
class _Options:
    main_node: str | None
    agent_file_name: str
    instructions_mode: str
    include_shared: bool
    secret_style: SecretStyle

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> _Options:
        def get(key: str) -> Any:
            return raw[key] if key in raw else _default(key)

        main = raw.get("main_node")
        style = get("secret_style")
        return cls(
            main_node=main if isinstance(main, str) and main else None,
            agent_file_name=str(get("agent_file_name")),
            instructions_mode=str(get("instructions_mode")),
            include_shared=bool(get("include_shared_resources")),
            secret_style="omit" if style == "omit" else "env_var",
        )


@dataclass(frozen=True, slots=True)
class _Use:
    """리소스 하나의 쓰임(덮어쓰기 포함)."""

    id: str
    override: Mapping[str, Any] | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.id, json.dumps(self.override or {}, sort_keys=True, default=str)


@dataclass
class _AgentPlan:
    id: str
    uses: list[_Use] = field(default_factory=list)


def _issue(
    code: str, message: str, *, severity: str = "warning", path: str | None = None, **details: Any
) -> Issue:
    return Issue(
        severity=severity,  # type: ignore[arg-type]
        code=code,
        message=message,
        path=path,
        details={k: v for k, v in details.items() if v is not None},
    )


def _text(data: bytes | None) -> str | None:
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


class _Build:
    """한 번의 내보내기 계산(상태를 들고 다니는 도우미)."""

    def __init__(
        self,
        exporter: ClaudeDirExporter,
        catalog: ExportCatalog,
        options: _Options,
    ) -> None:
        self.m = exporter.mapping
        self.layout = exporter.layout
        self.catalog = catalog
        self.options = options
        self.issues: list[Issue] = []
        self.project: list[_Use] = []
        self._project_keys: set[tuple[str, str]] = set()
        self.agents: dict[str, _AgentPlan] = {}
        self.main_agents: list[str] = []
        self.main_found = options.main_node is None
        self.files: dict[str, OutputFile] = {}
        self.graphs: set[str] = set()

    # ------------------------------------------------------------ 모으기

    def add_project(self, use: _Use) -> None:
        if use.key not in self._project_keys:
            self._project_keys.add(use.key)
            self.project.append(use)

    def _deps(self, kind: str, id: str) -> Sequence[DependencyLike]:
        return self.catalog.dependencies(kind, id)

    def _removed(self, owner: str, dep: DependencyLike) -> bool:
        if dep.mode != "remove":
            return False
        self.issues.append(
            _issue(
                ExportIssueCodes.SEMANTICS_APPROXIMATE,
                "위 층 첨부를 빼는 설정(remove)은 내보내지 않습니다",
                owner=owner,
                resource=dep.id,
            )
        )
        return True

    def add_agent(self, agent_id: str) -> None:
        if agent_id in self.agents:
            return
        plan = _AgentPlan(agent_id)
        self.agents[agent_id] = plan
        for dep in self._deps(self.m.agent_kind, agent_id):
            if dep.kind != self.m.resource_kind or self._removed(agent_id, dep):
                continue
            use = _Use(dep.id, dep.config_override)
            if dep.shared:
                if self.options.include_shared:
                    self.add_project(use)
            else:
                plan.uses.append(use)

    def set_main(self, agent_id: str) -> None:
        if agent_id not in self.main_agents:
            self.main_agents.append(agent_id)
        for dep in self._deps(self.m.agent_kind, agent_id):
            if dep.kind != self.m.resource_kind or self._removed(agent_id, dep):
                continue
            if dep.shared and not self.options.include_shared:
                continue
            self.add_project(_Use(dep.id, dep.config_override))

    def add_graph(self, graph_id: str, *, nested: bool = False) -> None:
        """팀 구성 하나. 쓰는 정의 중 팀 구성(중첩 팀 노드의 자식, 5R.15)은 따라 들어가 그 구성원도
        에이전트로 내보낸다. 주 노드(`main_node`)는 고른 팀 구성의 노드만 본다. 순환은 한 번만."""
        if graph_id in self.graphs:
            return
        self.graphs.add(graph_id)
        self.issues.append(
            _issue(
                ExportIssueCodes.SEMANTICS_APPROXIMATE,
                "팀 구성은 Claude Code 산출물로 정확히 옮겨지지 않습니다. 연결·검토·노드별 설정은 "
                "빠지며 같은 실행을 보장하지 않습니다",
                graph=graph_id,
            )
        )
        deps = list(self._deps(self.m.graph_kind, graph_id))
        agent_at = {
            d.node_id: d.id for d in deps if d.kind == self.m.agent_kind and d.node_id is not None
        }
        main = None if nested else self.options.main_node
        if main is not None and main in agent_at:
            self.main_found = True
        for dep in deps:
            if self._removed(graph_id, dep):
                continue
            if dep.kind == self.m.graph_kind:
                self.add_graph(dep.id, nested=True)
            elif dep.kind == self.m.agent_kind:
                if main is not None and dep.node_id == main:
                    self.set_main(dep.id)
                else:
                    self.add_agent(dep.id)
            elif dep.kind == self.m.resource_kind:
                use = _Use(dep.id, dep.config_override)
                if dep.shared:
                    if self.options.include_shared:
                        self.add_project(use)
                elif dep.node_id is not None and dep.node_id == main:
                    self.add_project(use)
                elif dep.node_id in agent_at:
                    self.add_agent(agent_at[dep.node_id])
                    self.agents[agent_at[dep.node_id]].uses.append(use)

    # ------------------------------------------------------------ 리소스 읽기

    def _resource(self, use: _Use) -> tuple[Mapping[str, Any], dict[str, Any]] | None:
        doc = self.catalog.document(self.m.resource_kind, use.id)
        if doc is None:
            self.issues.append(
                _issue(ExportIssueCodes.NOT_FOUND, "리소스를 찾지 못해 건너뜁니다", resource=use.id)
            )
            return None
        raw = doc.get("config")
        config = dict(raw) if isinstance(raw, Mapping) else {}
        config.update(use.override or {})
        return doc, config

    def _body(self, doc: Mapping[str, Any], use: _Use) -> str | None:
        content = doc.get("content")
        file = content.get("file") if isinstance(content, Mapping) else None
        files = self.catalog.files(self.m.resource_kind, use.id)
        if isinstance(file, str) and file in files:
            return _text(files[file])
        return None

    def _text_of(self, doc: Mapping[str, Any], config: Mapping[str, Any], use: _Use) -> str:
        body = self._body(doc, use)
        if body is None:
            text = config.get("text")
            body = text if isinstance(text, str) else ""
        return body

    def _instruction(self, doc: Mapping[str, Any], config: Mapping[str, Any], use: _Use) -> str:
        text = self._text_of(doc, config, use).strip("\n")
        if text and config.get("heading"):
            title = config.get("title") or doc.get("name") or use.id
            text = f"## {title}\n\n{text}"
        return text

    # ------------------------------------------------------------ 쓰기 준비

    def put(self, path: str, data: bytes, media_type: str | None) -> None:
        self.files[path] = OutputFile(path, data, media_type)

    def put_text(self, path: str, text: str, media_type: str = _MARKDOWN) -> None:
        self.put(path, text.encode("utf-8"), media_type)


class ClaudeDirExporter:
    """`.claude` 산출물 형식(`Exporter`).

    Args:
        mapping: 정의 종류·리소스 종류 이름(데이터).
        layout: 산출물 경로(데이터).
        id / title / description: 디스크립터(같은 형식을 다른 이름으로 등록할 때).
    """

    def __init__(
        self,
        *,
        mapping: ClaudeMapping | None = None,
        layout: ClaudeLayout | None = None,
        id: str = CLAUDE_DIR_ID,
        title: str = "Claude Code 프로젝트(.claude)",
        description: str = "에이전트·지침·규칙·skill·hook·권한·MCP 서버를 Claude Code 프로젝트 "
        "형식(.claude/, CLAUDE.md, .mcp.json)으로 내보냅니다.",
    ) -> None:
        self.mapping = mapping or ClaudeMapping()
        self.layout = layout or ClaudeLayout()
        m = self.mapping
        self.descriptor = ExporterDescriptor(
            id=id,
            title=title,
            description=description,
            config_schema=claude_dir_options_schema(),
            kinds=[m.agent_kind, m.resource_kind, m.graph_kind],
        )

    def plan(
        self,
        items: Sequence[ExportSelection],
        catalog: ExportCatalog,
        options: Mapping[str, Any],
    ) -> ExportOutput:
        """고른 정의 → 산출물(순수: 카탈로그를 읽기만 한다)."""
        opts = _Options.parse(options)
        build = _Build(self, catalog, opts)
        m = self.mapping
        for item in items:
            if item.kind == m.agent_kind:
                build.add_agent(item.id)
            elif item.kind == m.resource_kind:
                build.add_project(_Use(item.id))
            elif item.kind == m.graph_kind:
                build.add_graph(item.id)
        if not build.main_found:
            build.issues.append(
                _issue(
                    ExportIssueCodes.MAIN_NODE_NOT_FOUND,
                    "주 노드가 고른 팀 구성의 에이전트 노드가 아닙니다",
                    severity="error",
                    path="/options/main_node",
                )
            )
        _render(build)
        files = [build.files[p] for p in sorted(build.files)]
        return ExportOutput(files=files, warnings=build.issues)


def claude_dir_exporter(options: Mapping[str, Any]) -> ClaudeDirExporter:
    """형식 공장(entry point `claude-dir`).

    설치자 옵션 `mapping`·`layout`(dict)으로 이름·경로를 바꾼다.

    Raises:
        ValueError: 모르는 옵션 키·잘못된 값.
    """
    unknown = sorted(str(k) for k in options if k not in ("mapping", "layout"))
    if unknown:
        raise ValueError(f"claude-dir: 모르는 옵션 {', '.join(unknown)}")
    return ClaudeDirExporter(
        mapping=ClaudeMapping.from_options(options.get("mapping")),
        layout=ClaudeLayout.from_options(options.get("layout")),
    )


# ---------------------------------------------------------------- 산출물 만들기


@dataclass
class _Project:
    instructions_front: list[tuple[str, str]] = field(default_factory=list)
    instructions: list[tuple[str, str]] = field(default_factory=list)
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    model: str | None = None
    hooks: list[HookSpec] = field(default_factory=list)
    servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    server_owner: dict[str, str] = field(default_factory=dict)
    skill_owner: dict[str, str] = field(default_factory=dict)
    rule_owner: dict[str, str] = field(default_factory=dict)


def _unique(items: list[str], values: Sequence[str]) -> None:
    for value in values:
        if value not in items:
            items.append(value)


def _strings(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _hook(config: Mapping[str, Any]) -> HookSpec | None:
    event, command = config.get("event"), config.get("command")
    if not isinstance(event, str) or not event or not isinstance(command, str) or not command:
        return None
    matcher = config.get("matcher")
    timeout = config.get("timeout_seconds")
    return HookSpec(
        event=event,
        command=command,
        matcher=matcher if isinstance(matcher, str) and matcher else None,
        timeout_seconds=timeout
        if isinstance(timeout, int | float) and not isinstance(timeout, bool) and timeout > 0
        else None,
    )


def _name(config: Mapping[str, Any], fallback: str) -> str:
    value = config.get("name")
    return value if isinstance(value, str) and value else fallback


def _claim(owners: dict[str, str], name: str, resource: str, build: _Build) -> bool:
    """이름을 처음 쓰는 리소스면 참. 같은 이름을 다른 리소스가 이미 쓰면 경고하고 거짓."""
    owner = owners.setdefault(name, resource)
    if owner == resource:
        return True
    build.issues.append(
        _issue(
            ExportIssueCodes.NAME_CONFLICT,
            "같은 이름의 산출물이 이미 있어 건너뜁니다",
            name=name,
            resource=resource,
            other=owner,
        )
    )
    return False


def _write_skill(
    build: _Build, project: _Project, doc: Mapping[str, Any], config: Mapping[str, Any], use: _Use
) -> str | None:
    name = _name(config, use.id)
    if path_problem(name) is not None or "/" in name:
        build.issues.append(
            _issue(
                ExportIssueCodes.UNSAFE_PATH,
                "skill 이름을 폴더 이름으로 쓸 수 없습니다",
                resource=use.id,
            )
        )
        return None
    if not _claim(project.skill_owner, name, use.id, build):
        return None
    files = build.catalog.files(build.m.resource_kind, use.id)
    rendered = render_skill(
        name,
        files,
        description=str(doc.get("description") or ""),
        skill_file=build.layout.skill_file,
    )
    base = build.layout.in_claude_dir(build.layout.skills_dir, name)
    for path, data in rendered.items():
        media = _MARKDOWN if path.lower().endswith(".md") else mimetypes.guess_type(path)[0]
        build.put(f"{base}/{path}", data, media)
    return name


def _write_rule(
    build: _Build, project: _Project, doc: Mapping[str, Any], config: Mapping[str, Any], use: _Use
) -> None:
    name = _name(config, use.id)
    if path_problem(f"{name}.md") is not None or "/" in name:
        build.issues.append(
            _issue(
                ExportIssueCodes.UNSAFE_PATH,
                "규칙 이름을 파일 이름으로 쓸 수 없습니다",
                resource=use.id,
            )
        )
        return
    if not _claim(project.rule_owner, name, use.id, build):
        return
    paths = [p for p in _strings(config.get("paths")) if p]
    text = build._text_of(doc, config, use)
    path = build.layout.in_claude_dir(build.layout.rules_dir, f"{name}.md")
    build.put_text(path, render_rule(paths, text))


def _add_mcp(build: _Build, project: _Project, config: Mapping[str, Any], use: _Use) -> str | None:
    entry = mcp_entry_from_config(
        config, fallback_name=use.id, secret_style=build.options.secret_style
    )
    if entry.omitted:
        build.issues.append(
            _issue(
                ExportIssueCodes.SECRET_OMITTED,
                "비밀 값(참조가 아니거나 생략 방식)은 쓰지 않았습니다",
                resource=use.id,
                keys=entry.omitted,
            )
        )
    if not _claim(project.server_owner, entry.name, use.id, build):
        return None
    project.servers[entry.name] = entry.entry
    return entry.name


def _add_permissions(
    build: _Build, project: _Project, config: Mapping[str, Any], use: _Use
) -> None:
    _unique(project.allow, _strings(config.get("tools")))
    _unique(project.deny, _strings(config.get("disallowed_tools")))
    if config.get("commands"):
        build.issues.append(
            _issue(
                ExportIssueCodes.FIELDS_DROPPED,
                "명령 허용 목록은 이 형식으로 옮기지 않습니다",
                resource=use.id,
                keys=["commands"],
            )
        )


def _project_resource(build: _Build, project: _Project, use: _Use) -> None:
    found = build._resource(use)
    if found is None:
        return
    doc, config = found
    m = build.m
    kind = doc.get("type")
    if kind == m.instruction_type:
        text = build._instruction(doc, config, use)
        if text:
            target = (
                project.instructions_front
                if config.get("position") == "prepend"
                else project.instructions
            )
            target.append((use.id, text))
    elif kind == m.rule_type:
        _write_rule(build, project, doc, config, use)
    elif kind == m.skill_type:
        _write_skill(build, project, doc, config, use)
    elif kind == m.hook_type:
        hook = _hook(config)
        if hook is not None:
            project.hooks.append(hook)
    elif kind == m.permission_type:
        _add_permissions(build, project, config, use)
    elif kind == m.mcp_type:
        _add_mcp(build, project, config, use)
    else:
        build.issues.append(
            _issue(
                ExportIssueCodes.TYPE_UNSUPPORTED,
                "이 형식이 다루지 않는 리소스 종류라 건너뜁니다",
                resource=use.id,
                resource_type=str(kind),
            )
        )


def _agent_file_name(build: _Build, agent_id: str, name: str) -> str:
    template = build.options.agent_file_name
    file = template.replace("{id}", agent_id).replace("{name}", name)
    if "/" in file or path_problem(file) is not None:
        build.issues.append(
            _issue(
                ExportIssueCodes.UNSAFE_PATH,
                "에이전트 파일 이름 템플릿 결과를 쓸 수 없어 기본 이름을 씁니다",
                path="/options/agent_file_name",
                agent=agent_id,
            )
        )
        file = DEFAULT_AGENT_FILE_NAME.replace("{id}", agent_id)
    return file


def _agent(build: _Build, project: _Project, plan: _AgentPlan, names: dict[str, str]) -> None:
    m = build.m
    doc = build.catalog.document(m.agent_kind, plan.id)
    if doc is None:
        build.issues.append(
            _issue(ExportIssueCodes.NOT_FOUND, "에이전트를 찾지 못해 건너뜁니다", agent=plan.id)
        )
        return
    agent, dropped = agent_file_from_document(doc)
    dropped = [k for k in dropped if k not in _ATTACHMENT_ONLY_FIELDS]
    if dropped:
        build.issues.append(
            _issue(
                ExportIssueCodes.FIELDS_DROPPED,
                "에이전트 파일로 옮기지 못한 설정이 있습니다",
                agent=plan.id,
                keys=dropped,
            )
        )
    name = agent.name or plan.id
    if names.setdefault(name, plan.id) != plan.id:
        build.issues.append(
            _issue(
                ExportIssueCodes.NAME_CONFLICT,
                "같은 이름의 에이전트가 있어 id를 이름으로 씁니다",
                agent=plan.id,
                other=names[name],
            )
        )
        name = plan.id
    prompt_parts = [agent.prompt] if agent.prompt else []
    skills = _strings(agent.extra.get("skills"))
    servers = list(agent.extra.get("mcpServers") or [])
    hooks: list[HookSpec] = []
    for use in plan.uses:
        found = build._resource(use)
        if found is None:
            continue
        rdoc, config = found
        kind = rdoc.get("type")
        if kind == m.instruction_type:
            text = build._instruction(rdoc, config, use)
            if text:
                prompt_parts.append(text)
        elif kind == m.skill_type:
            skill = _write_skill(build, project, rdoc, config, use)
            if skill is not None:
                _unique(skills, [skill])
        elif kind == m.mcp_type:
            server = _add_mcp(build, project, config, use)
            if server is not None and server not in servers:
                servers.append(server)
        elif kind == m.hook_type:
            hook = _hook(config)
            if hook is not None:
                hooks.append(hook)
        elif kind in (m.rule_type, m.permission_type):
            build.issues.append(
                _issue(
                    ExportIssueCodes.SCOPE_WIDENED,
                    "구성원 하나에 붙은 리소스를 프로젝트 전체에 적용되는 곳에 씁니다",
                    agent=plan.id,
                    resource=use.id,
                )
            )
            _project_resource(build, project, use)
        else:
            build.issues.append(
                _issue(
                    ExportIssueCodes.TYPE_UNSUPPORTED,
                    "이 형식이 다루지 않는 리소스 종류라 건너뜁니다",
                    agent=plan.id,
                    resource=use.id,
                    resource_type=str(kind),
                )
            )
    extra = dict(agent.extra)
    if skills:
        extra["skills"] = skills
    if servers:
        extra["mcpServers"] = servers
    if hooks:
        kept, _ = parse_hooks(extra.get("hooks"), base="")
        extra["hooks"] = render_hooks([*kept, *hooks])
    final = AgentFile(
        name=name,
        description=agent.description,
        prompt="\n\n".join(p.strip("\n") for p in prompt_parts),
        tools=agent.tools,
        disallowed_tools=agent.disallowed_tools,
        model=agent.model,
        extra=extra,
    )
    file = _agent_file_name(build, plan.id, name)
    path = build.layout.in_claude_dir(build.layout.agents_dir, file)
    if path in build.files:
        build.issues.append(
            _issue(
                ExportIssueCodes.NAME_CONFLICT,
                "같은 이름의 에이전트 파일이 있어 건너뜁니다",
                agent=plan.id,
            )
        )
        return
    build.put_text(path, render_agent_md(final))


def _main(build: _Build, project: _Project) -> list[str]:
    parts: list[str] = []
    for agent_id in build.main_agents:
        doc = build.catalog.document(build.m.agent_kind, agent_id)
        if doc is None:
            build.issues.append(
                _issue(
                    ExportIssueCodes.NOT_FOUND, "에이전트를 찾지 못해 건너뜁니다", agent=agent_id
                )
            )
            continue
        agent, dropped = agent_file_from_document(doc)
        if agent.prompt:
            parts.append(agent.prompt)
        _unique(project.allow, agent.tools or [])
        _unique(project.deny, agent.disallowed_tools or [])
        if agent.model and project.model is None:
            project.model = agent.model
        dropped = [k for k in dropped if k not in _ATTACHMENT_ONLY_FIELDS]
        if dropped:
            build.issues.append(
                _issue(
                    ExportIssueCodes.FIELDS_DROPPED,
                    "주 에이전트 설정 중 옮기지 못한 것이 있습니다",
                    agent=agent_id,
                    keys=dropped,
                )
            )
    return parts


def _render(build: _Build) -> None:
    project = _Project()
    main_parts = _main(build, project)
    for use in build.project:
        _project_resource(build, project, use)
    names: dict[str, str] = {}
    for plan in build.agents.values():
        _agent(build, project, plan, names)
    layout = build.layout
    claude_md: list[str] = list(main_parts)
    for resource_id, text in [*project.instructions_front, *project.instructions]:
        if build.options.instructions_mode == "separate_files":
            path = layout.in_claude_dir(layout.instructions_dir, f"{resource_id}.md")
            build.put_text(path, text.rstrip("\n") + "\n")
            claude_md.append(f"@{path}")
        else:
            claude_md.append(text)
    if claude_md:
        build.put_text(
            layout.instruction_file, "\n\n".join(p.strip("\n") for p in claude_md) + "\n"
        )
    settings = render_settings(allow=project.allow, deny=project.deny, hooks=project.hooks)
    if project.model:
        settings["model"] = project.model
    if settings:
        build.put_text(layout.in_claude_dir(layout.settings_file), dump_json(settings), _JSON)
    if project.servers:
        build.put_text(layout.mcp_file, dump_json(render_mcp(project.servers)), _JSON)
