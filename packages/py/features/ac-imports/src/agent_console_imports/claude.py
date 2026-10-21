"""기본 가져오기 출처: Claude Code 설정 폴더(`~/.claude`, 프로젝트 `.claude/`) — 확장 지점의 첫
구현.

원본은 **읽기만 한다**(쓰기·지우기·이름 바꾸기·권한 변경 없음). 읽는 것:

| 원본 | 만드는 정의 |
| --- | --- |
| 지침 파일(`CLAUDE.md`) | 리소스(지침 종류) + 본문 |
| `agents/*.md`(frontmatter + 본문) | 에이전트(name·description·tools·model, 본문 = system_prompt) |
| `rules/**/*.md` | 리소스(규칙 종류: config `paths`·`name`, 본문 = frontmatter 뺀 내용) |
| `skills/<이름>/`(`SKILL.md` + 부속 파일) | 리소스(skill 종류, 여러 파일 본문) |
| `settings.json`의 `permissions.allow/deny` | 리소스(도구 권한 종류) |
| `settings.json`의 `hooks`(명령형) | 리소스(hook 종류) — 처리기마다 하나 |
| `.mcp.json`의 `mcpServers` | 리소스(MCP 서버 종류). `env`·`headers` 평문은 `secret://` 참조로 |

`.claude` 형식 변환은 `ac-claude-format`(내보내기와 공용)이다. 만드는 정의 종류 이름·리소스 종류
id는 `ClaudeMapping`, 경로는 `ClaudeLayout` 데이터다. 링크라서 건너뛴 항목은 미리보기 경고
(`import.skipped_link`)로 알린다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agent_console_claude_format import (
    ClaudeLayout,
    ClaudeMapping,
    agent_document,
    mcp_config_from_entry,
    parse_agent_md,
    parse_env_ref,
    parse_frontmatter,
    parse_mcp,
    parse_rule,
    parse_settings,
    parse_skill,
    valid_skill_name,
)
from agent_console_contracts import ImportCandidate, ImportSourceDescriptor, ImportWarning
from agent_console_secret_rules import SecretRules, default_rules

from ._interfaces import ImportItem, ImportSource, ImportSourceContext, ScanResult

__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_MAX_SKILL_BYTES",
    "PROJECT_SOURCE_ID",
    "USER_SOURCE_ID",
    "ClaudeDirectorySource",
    "ClaudeLayout",
    "ClaudeMapping",
    "ImportWarningCodes",
    "claude_sources",
    "parse_frontmatter",
    "slugify",
]

_log = logging.getLogger(__name__)

USER_SOURCE_ID = "user-claude"
PROJECT_SOURCE_ID = "project-claude"
DEFAULT_MAX_FILE_BYTES = 1024 * 1024
"""이보다 큰 원본 파일은 후보로 만들지 않는다(경고 없이 건너뜀)."""
DEFAULT_MAX_SKILL_BYTES = 10 * 1024 * 1024
"""skill 폴더 하나의 파일 총량 한도(넘으면 그 skill을 후보로 만들지 않는다)."""

SECRET_PREFIX = "secret://"
_SLUG_BAD = re.compile(r"[^A-Za-z0-9_-]+")
_SECRET_NAME_BAD = re.compile(r"[^A-Za-z0-9_]+")
_MCP_NAME_BAD = re.compile(r"[^A-Za-z0-9_.-]+")
_RULE_NAME_BAD = re.compile(r"[^A-Za-z0-9._-]+")


class ImportWarningCodes:
    """후보·미리보기 경고 코드(값은 싣지 않고 위치만)."""

    SECRET_REPLACED = "import.secret_replaced"
    SECRET_SUSPECTED = "import.secret_suspected"
    UNREADABLE = "import.unreadable"
    FIELDS_IGNORED = "import.fields_ignored"
    SKIPPED_LINK = "import.skipped_link"
    """심볼릭 링크(또는 출처 밖을 가리키는 경로)라서 건너뛴 항목(미리보기 경고, keys = 경로)."""
    HOOK_UNSUPPORTED = "import.hook_unsupported"
    """명령형이 아니라서 가져오지 않은 hook 처리기(keys = 설정 파일 안 JSON Pointer)."""


def slugify(text: str, *, fallback: str = "item", limit: int = 120) -> str:
    """정의 id로 쓸 수 있는 문자열(영숫자로 시작, 영숫자·`_`·`-`)."""
    slug = _SLUG_BAD.sub("-", text.strip()).strip("-_").lower()
    slug = slug[:limit].strip("-_")
    return slug if slug and slug[0].isalnum() else fallback


@dataclass
class _Read:
    path: Path
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace")


@dataclass
class _Scan:
    """스캔 한 번의 상태(링크라서 건너뛴 경로, 그 밖의 경고)."""

    skipped_links: list[str] = field(default_factory=list)
    warnings: list[ImportWarning] = field(default_factory=list)

    def link(self, path: Path) -> None:
        text = str(path)
        if text not in self.skipped_links:
            self.skipped_links.append(text)

    def result_warnings(self) -> list[ImportWarning]:
        links = [
            ImportWarning(
                code=ImportWarningCodes.SKIPPED_LINK,
                message="심볼릭 링크(또는 출처 밖을 가리키는 경로)라서 건너뛰었습니다",
                keys=[path],
            )
            for path in self.skipped_links
        ]
        return [*links, *self.warnings]


class ClaudeDirectorySource:
    """Claude Code 설정 폴더 하나를 읽는 가져오기 출처(`ImportSource`).

    Args:
        id: 출처 id(화면·API).
        title: 화면 이름.
        root: 설정 폴더(`.claude`). `agents/`·`rules/`·`skills/`를 여기서 찾는다(이름은 `layout`).
        description: 설명.
        instruction_files: 지침 파일 목록(예: `CLAUDE.md`). 없는 파일은 건너뛴다.
        settings_files: `permissions`·`hooks`를 읽을 설정 파일 목록.
        mcp_files: `mcpServers`를 읽을 파일 목록(예: 프로젝트 `.mcp.json`).
        id_prefix: 이름이 없는 항목(지침 파일·권한·hook)의 제안 id 앞에 붙일 문자열.
        mapping: 만드는 정의 종류·리소스 종류 이름.
        layout: 설정 폴더 안 하위 폴더·파일 이름.
        max_file_bytes: 이보다 큰 파일은 건너뛴다.
        max_skill_bytes: skill 폴더 하나의 총량 한도.
        secret_rules: 지금의 비밀 의심 규칙을 돌려주는 함수(MCP 인자·URL, hook 명령의 비밀을 가릴
            때). 없으면 기본 규칙(`ac-secret-rules`).
    """

    def __init__(
        self,
        *,
        id: str,
        title: str,
        root: Path,
        description: str = "",
        instruction_files: Sequence[Path] = (),
        settings_files: Sequence[Path] = (),
        mcp_files: Sequence[Path] = (),
        id_prefix: str = "",
        mapping: ClaudeMapping | None = None,
        layout: ClaudeLayout | None = None,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        max_skill_bytes: int = DEFAULT_MAX_SKILL_BYTES,
        secret_rules: Callable[[], SecretRules] | None = None,
    ) -> None:
        self.root = root
        self._secret_rules = secret_rules or default_rules
        self.instruction_files = tuple(instruction_files)
        self.settings_files = tuple(settings_files)
        self.mcp_files = tuple(mcp_files)
        self.id_prefix = id_prefix
        self.mapping = mapping or ClaudeMapping()
        self.layout = layout or ClaudeLayout()
        self.max_file_bytes = max_file_bytes
        self.max_skill_bytes = max_skill_bytes
        self._id = id
        self._title = title
        self._description = description

    @property
    def descriptor(self) -> ImportSourceDescriptor:
        """현재 읽을 수 있는지(`available`)를 매번 확인한다."""
        available = self.root.is_dir() or any(
            p.is_file() for p in (*self.instruction_files, *self.mcp_files)
        )
        return ImportSourceDescriptor(
            id=self._id,
            title=self._title,
            description=self._description,
            path=str(self.root),
            available=available,
        )

    # ------------------------------------------------------------ 읽기(쓰기 없음)

    def _boundary(self, path: Path) -> Path:
        """읽어도 되는 범위: 설정 폴더 아래면 설정 폴더, 아니면(지정한 파일) 그 파일의 폴더."""
        return self.root if path.is_relative_to(self.root) else path.parent

    def _read(self, path: Path, scan: _Scan, *, limit: int | None = None) -> _Read | None:
        """원본 파일 하나를 읽는다(쓰기 없음).

        건너뛰는 것: 심볼릭 링크 파일, 실제 위치가 범위(`_boundary`) 밖인 파일(링크된 상위 폴더
        포함), 정규 파일이 아닌 것, 너무 큰 파일. 링크·범위 밖은 `scan`에 위치를 남긴다.
        """
        max_bytes = self.max_file_bytes if limit is None else limit
        try:
            if path.is_symlink():
                _log.warning("가져오기: 심볼릭 링크는 건너뜁니다: %s", path)
                scan.link(path)
                return None
            if not path.is_file():
                return None
            boundary = self._boundary(path).resolve()
            if not path.resolve().is_relative_to(boundary):
                _log.warning("가져오기: 출처 밖을 가리키는 경로는 건너뜁니다: %s", path)
                scan.link(path)
                return None
            if path.stat().st_size > max_bytes:
                return None
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            fd = os.open(path, flags)  # 읽기 전용, 마지막 구성 요소 링크 거부
            with os.fdopen(fd, "rb") as handle:
                return _Read(path, handle.read(max_bytes + 1))
        except OSError:
            return None

    def _origin(self, read: _Read) -> dict[str, Any]:
        return {
            "imported_from": {"source": self._id, "path": str(read.path), "sha256": read.sha256}
        }

    def scan(self) -> ScanResult:
        scan = _Scan()
        items: list[ImportItem] = []
        seen: set[str] = set()

        def add(item: ImportItem | None) -> None:
            if item is not None and item.candidate.id not in seen:
                seen.add(item.candidate.id)
                items.append(item)

        layout = self.layout
        for path in self.instruction_files:
            add(self._instruction_file(path, scan))
        for path in self._walk(self.root / layout.agents_dir, scan, recursive=False):
            if path.name.lower().endswith(".md"):
                add(self._agent(path, scan))
        rules_root = self.root / layout.rules_dir
        for path in self._walk(rules_root, scan, recursive=True):
            if path.name.lower().endswith(".md"):
                add(self._rule(path, rules_root, scan))
        for folder in self._skill_folders(scan):
            add(self._skill(folder, scan))
        for path in self.settings_files:
            for item in self._settings(path, scan):
                add(item)
        for path in self.mcp_files:
            for item in self._mcp_servers(path, scan):
                add(item)
        return ScanResult(root=str(self.root), items=items, warnings=scan.result_warnings())

    def _walk(self, folder: Path, scan: _Scan, *, recursive: bool) -> list[Path]:
        """폴더 아래 파일(이름 순). 링크된 폴더는 따라가지 않고 위치를 남긴다."""
        if folder.is_symlink():
            scan.link(folder)
            return []
        if not folder.is_dir():
            return []
        found: list[Path] = []
        for current, dirs, files in os.walk(folder, followlinks=False):
            base = Path(current)
            for name in sorted(dirs):
                if (base / name).is_symlink():
                    scan.link(base / name)
            dirs[:] = sorted(d for d in dirs if not (base / d).is_symlink())
            if not recursive:
                dirs.clear()
            found += [base / f for f in sorted(files)]
        return found

    def _candidate(
        self,
        key: str,
        read: _Read,
        *,
        kind: str,
        name: str,
        suggested: str,
        resource_type: str | None = None,
        warnings: Iterable[ImportWarning] = (),
        size: int | None = None,
    ) -> ImportCandidate:
        return ImportCandidate(
            id=key,
            path=str(read.path),
            kind=kind,
            resource_type=resource_type,
            name=name,
            suggested_id=suggested,
            size=len(read.data) if size is None else size,
            content_hash=read.sha256,
            warnings=list(warnings),
        )

    def _content_ref(self) -> dict[str, str]:
        m = self.mapping
        return {"file": m.content_file, "media_type": m.content_media_type}

    def _instruction_doc(self, read: _Read, *, name: str, title: str) -> dict[str, Any]:
        m = self.mapping
        return {
            "kind": m.resource_kind,
            "type": m.instruction_type,
            "name": name,
            "config": {"title": title},
            "content": self._content_ref(),
            "attributes": self._origin(read),
        }

    def _instruction_file(self, path: Path, scan: _Scan) -> ImportItem | None:
        read = self._read(path, scan)
        if read is None:
            return None
        rel = self._relative(path)
        suggested = slugify(f"{self.id_prefix}{rel.removesuffix('.md')}", fallback="instruction")
        return ImportItem(
            candidate=self._candidate(
                f"instruction:{rel}",
                read,
                kind=self.mapping.resource_kind,
                resource_type=self.mapping.instruction_type,
                name=path.name,
                suggested=suggested,
            ),
            document=self._instruction_doc(read, name=path.name, title=path.name),
            content=read.data,
        )

    def _relative(self, path: Path) -> str:
        for base in (self.root.parent, self.root):
            try:
                return path.relative_to(base).as_posix()
            except ValueError:
                continue
        return path.name

    def _agent(self, path: Path, scan: _Scan) -> ImportItem | None:
        read = self._read(path, scan)
        if read is None:
            return None
        agent = parse_agent_md(read.text, default_name=path.stem)
        doc = agent_document(agent, mapping=self.mapping)
        doc["attributes"] = {**self._origin(read), **doc["attributes"]}
        warnings = []
        if agent.extra:
            warnings.append(
                ImportWarning(
                    code=ImportWarningCodes.FIELDS_IGNORED,
                    message="실행 설정으로 옮기지 않은 항목이 있습니다(속성에만 보관)",
                    keys=sorted(agent.extra),
                )
            )
        return ImportItem(
            candidate=self._candidate(
                f"agent:{self._relative(path)}",
                read,
                kind=self.mapping.agent_kind,
                name=agent.name,
                suggested=slugify(agent.name, fallback=slugify(path.stem, fallback="agent")),
                warnings=warnings,
            ),
            document=doc,
        )

    def _rule(self, path: Path, rules_root: Path, scan: _Scan) -> ImportItem | None:
        read = self._read(path, scan)
        if read is None:
            return None
        rel = path.relative_to(rules_root).as_posix()
        m = self.mapping
        key = f"rule:{rel}"
        suggested = slugify(f"rule-{rel.removesuffix('.md')}", fallback="rule")
        rule = parse_rule(read.text)
        name = _RULE_NAME_BAD.sub("-", rel.removesuffix(".md")).strip("-.")[:64]
        config: dict[str, Any] = {}
        if rule.paths:
            config["paths"] = list(rule.paths)
        if name and name[0].isalnum():
            config["name"] = name
        warnings = []
        if rule.extra:
            warnings.append(
                ImportWarning(
                    code=ImportWarningCodes.FIELDS_IGNORED,
                    message="규칙 설정으로 옮기지 않은 항목이 있습니다",
                    keys=sorted(rule.extra),
                )
            )
        return ImportItem(
            candidate=self._candidate(
                key,
                read,
                kind=m.resource_kind,
                resource_type=m.rule_type,
                name=rel,
                suggested=suggested,
                warnings=warnings,
            ),
            document={
                "kind": m.resource_kind,
                "type": m.rule_type,
                "name": rel,
                "config": config,
                "content": self._content_ref(),
                "attributes": self._origin(read),
            },
            content=rule.body.encode("utf-8"),
        )

    def _skill_folders(self, scan: _Scan) -> list[Path]:
        root = self.root / self.layout.skills_dir
        if root.is_symlink():
            scan.link(root)
            return []
        if not root.is_dir():
            return []
        folders: list[Path] = []
        for entry in sorted(root.iterdir()):
            if entry.is_symlink():
                scan.link(entry)
            elif entry.is_dir():
                folders.append(entry)
        return folders

    def _skill(self, folder: Path, scan: _Scan) -> ImportItem | None:
        main_path = folder / self.layout.skill_file
        main = self._read(main_path, scan)
        if main is None:
            return None
        files: dict[str, bytes] = {}
        total = 0
        digest = hashlib.sha256()
        for path in self._walk(folder, scan, recursive=True):
            read = self._read(path, scan)
            if read is None:
                continue
            rel = path.relative_to(folder).as_posix()
            total += len(read.data)
            if total > self.max_skill_bytes:
                _log.warning("가져오기: skill이 너무 커서 건너뜁니다: %s", folder)
                return None
            files[rel] = read.data
            digest.update(rel.encode("utf-8") + b"\0" + read.data)
        skill = parse_skill(folder.name, files, skill_file=self.layout.skill_file)
        m = self.mapping
        config = {"name": skill.name} if valid_skill_name(skill.name) else {}
        origin = self._origin(main)
        origin["imported_from"]["sha256"] = digest.hexdigest()
        return ImportItem(
            candidate=self._candidate(
                f"skill:{folder.name}",
                main,
                kind=m.resource_kind,
                resource_type=m.skill_type,
                name=skill.title,
                suggested=slugify(f"skill-{folder.name}", fallback="skill"),
                size=total,
            ).model_copy(update={"path": str(folder), "content_hash": digest.hexdigest()}),
            document={
                "kind": m.resource_kind,
                "type": m.skill_type,
                "name": skill.title,
                "description": skill.description,
                "config": config,
                "content": {"file": self.layout.skill_file, "media_type": "text/markdown"},
                "attributes": origin,
            },
            files=files,
        )

    def _json(self, path: Path, scan: _Scan) -> tuple[_Read, Any] | None:
        read = self._read(path, scan)
        if read is None:
            return None
        try:
            return read, json.loads(read.text)
        except ValueError:
            return None

    def _settings(self, path: Path, scan: _Scan) -> list[ImportItem]:
        loaded = self._json(path, scan)
        if loaded is None:
            return []
        read, data = loaded
        settings = parse_settings(data)
        items: list[ImportItem] = []
        permissions = self._permissions(path, read, settings.allow, settings.deny)
        if permissions is not None:
            items.append(permissions)
        if settings.skipped_hooks:
            scan.warnings.append(
                ImportWarning(
                    code=ImportWarningCodes.HOOK_UNSUPPORTED,
                    message=f"{path.name}: 명령형이 아닌 hook 처리기는 가져오지 않습니다",
                    keys=list(settings.skipped_hooks),
                )
            )
        m = self.mapping
        rel = self._relative(path)
        rules = self._secret_rules()
        for index, hook in enumerate(settings.hooks):
            config: dict[str, Any] = {"event": hook.event, "command": hook.command}
            warnings: list[ImportWarning] = []
            if rules.find_suspected(hook.command):
                config["command"] = rules.redact_suspected(hook.command)
                warnings.append(
                    ImportWarning(
                        code=ImportWarningCodes.SECRET_SUSPECTED,
                        message="명령에서 비밀로 보이는 값을 가렸습니다. "
                        "비밀은 환경 변수로 옮기세요",
                        keys=["command"],
                    )
                )
            if hook.matcher:
                config["matcher"] = hook.matcher
            if hook.timeout_seconds is not None:
                config["timeout_seconds"] = hook.timeout_seconds
            if hook.extra:
                warnings.append(
                    ImportWarning(
                        code=ImportWarningCodes.FIELDS_IGNORED,
                        message="hook 설정으로 옮기지 않은 항목이 있습니다",
                        keys=sorted(hook.extra),
                    )
                )
            name = f"{hook.event} {hook.matcher}" if hook.matcher else hook.event
            items.append(
                ImportItem(
                    candidate=self._candidate(
                        f"hook:{rel}:{index}",
                        read,
                        kind=m.resource_kind,
                        resource_type=m.hook_type,
                        name=name,
                        suggested=slugify(
                            f"{self.id_prefix}hook-{hook.event}-{hook.matcher or 'all'}",
                            fallback="hook",
                        ),
                        warnings=warnings,
                    ),
                    document={
                        "kind": m.resource_kind,
                        "type": m.hook_type,
                        "name": name,
                        "config": config,
                        "attributes": self._origin(read),
                    },
                )
            )
        return items

    def _permissions(
        self, path: Path, read: _Read, allow: list[str] | None, deny: list[str] | None
    ) -> ImportItem | None:
        config: dict[str, Any] = {}
        if allow:
            config["tools"] = allow
        if deny:
            config["disallowed_tools"] = deny
        if not config:
            return None
        name = f"{path.name} 권한"
        m = self.mapping
        return ImportItem(
            candidate=self._candidate(
                f"permissions:{self._relative(path)}",
                read,
                kind=m.resource_kind,
                resource_type=m.permission_type,
                name=name,
                suggested=slugify(f"{self.id_prefix}permissions", fallback="permissions"),
            ),
            document={
                "kind": m.resource_kind,
                "type": m.permission_type,
                "name": name,
                "config": config,
                "attributes": self._origin(read),
            },
        )

    def _mcp_servers(self, path: Path, scan: _Scan) -> list[ImportItem]:
        loaded = self._json(path, scan)
        if loaded is None:
            return []
        read, data = loaded
        m = self.mapping
        items: list[ImportItem] = []
        for raw_name, raw in parse_mcp(data).items():
            name = _MCP_NAME_BAD.sub("-", raw_name).strip("-.")[:64] or "server"
            config, replaced, suspected = _mcp_config(name, raw, self._secret_rules())
            warnings = []
            if suspected:
                warnings.append(
                    ImportWarning(
                        code=ImportWarningCodes.SECRET_SUSPECTED,
                        message="인자·URL에서 비밀로 보이는 값을 저장하지 않고 secret:// 참조로 "
                        "바꿨습니다. 인자·URL 칸은 참조를 풀지 않으니 환경 변수·헤더로 옮기세요",
                        keys=suspected,
                    )
                )
            if replaced:
                warnings.append(
                    ImportWarning(
                        code=ImportWarningCodes.SECRET_REPLACED,
                        message="평문 값을 저장하지 않고 secret:// 참조로 바꿨습니다. "
                        "같은 이름의 비밀을 환경변수 등에 등록하세요",
                        keys=replaced,
                    )
                )
            items.append(
                ImportItem(
                    candidate=self._candidate(
                        f"mcp:{name}",
                        read,
                        kind=m.resource_kind,
                        resource_type=m.mcp_type,
                        name=name,
                        suggested=slugify(f"mcp-{name}", fallback="mcp"),
                        warnings=warnings,
                    ),
                    document={
                        "kind": m.resource_kind,
                        "type": m.mcp_type,
                        "name": name,
                        "config": config,
                        "attributes": self._origin(read),
                    },
                )
            )
        return items


def _secret_name(server: str, key: str) -> str:
    return _SECRET_NAME_BAD.sub("_", f"{server}_{key}").strip("_").upper() or "SECRET"


def _mask_args(server: str, args: list[str], found: list[str], rules: SecretRules) -> list[str]:
    """비밀로 보이는 인자(`--token x`, `--api-key=x`, 토큰 모양 값)를 `secret://` 참조로 바꾼다."""
    out: list[str] = []
    expect_value: str | None = None
    for index, arg in enumerate(args):
        if expect_value is not None and not arg.startswith("-"):
            out.append(SECRET_PREFIX + _secret_name(server, expect_value))
            found.append(f"args/{index}")
            expect_value = None
            continue
        expect_value = None
        flag, sep, value = arg.partition("=")
        if flag.startswith("-") and rules.name_suspected(flag):
            if sep and value and not value.startswith(SECRET_PREFIX):
                out.append(f"{flag}={SECRET_PREFIX}{_secret_name(server, flag.lstrip('-'))}")
                found.append(f"args/{index}")
                continue
            if not sep:
                expect_value = flag.lstrip("-")
        elif rules.value_suspected(arg):
            out.append(SECRET_PREFIX + _secret_name(server, f"arg{index}"))
            found.append(f"args/{index}")
            continue
        out.append(arg)
    return out


def _mask_url(server: str, url: str, found: list[str], rules: SecretRules) -> str:
    """URL 쿼리·사용자 정보에 든 비밀로 보이는 값을 `secret://` 참조로 바꾼다."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    query = parse_qsl(parts.query, keep_blank_values=True)
    masked: list[tuple[str, str]] = []
    for key, value in query:
        if (
            value
            and not value.startswith(SECRET_PREFIX)
            and (rules.name_suspected(key) or rules.value_suspected(value))
        ):
            masked.append((key, SECRET_PREFIX + _secret_name(server, key)))
            found.append(f"url/query/{key}")
        else:
            masked.append((key, value))
    netloc = parts.netloc
    if "@" in netloc:  # https://user:pass@host — 사용자 정보는 버린다
        netloc = netloc.rsplit("@", 1)[1]
        found.append("url/userinfo")
    if masked == query and netloc == parts.netloc:
        return url
    return urlunsplit(
        (parts.scheme, netloc, parts.path, urlencode(masked, safe=":/"), parts.fragment)
    )


def _mcp_config(
    name: str, raw: Mapping[str, Any], rules: SecretRules
) -> tuple[dict[str, Any], list[str], list[str]]:
    """`.mcp.json` 서버 하나 → MCP 서버 리소스 config(형식 변환은 `ac-claude-format`).

    Returns:
        (config, env·headers에서 참조로 바꾼 위치, 인자·URL에서 비밀로 보여 참조로 바꾼 위치).
    """
    config = mcp_config_from_entry(name, raw)
    suspected: list[str] = []
    if "args" in config:
        config["args"] = _mask_args(name, config["args"], suspected, rules)
    if "url" in config:
        config["url"] = _mask_url(name, config["url"], suspected, rules)
    replaced: list[str] = []
    for field_name in ("env", "headers"):
        values = config.get(field_name)
        if not isinstance(values, dict):
            continue
        out: dict[str, str] = {}
        for key, text in values.items():
            if text.startswith(SECRET_PREFIX):
                out[key] = text
                continue
            ref = parse_env_ref(text)
            out[key] = SECRET_PREFIX + (ref or _secret_name(name, key))
            if ref is None:
                replaced.append(f"{field_name}/{key}")
        config[field_name] = out
    return config, replaced, suspected


@dataclass(frozen=True, slots=True)
class _Titles:
    user: str = "사용자 ~/.claude"
    user_description: str = "사용자 전역 Claude Code 설정(원본은 읽기만 합니다)"
    project: str = "프로젝트 .claude/"
    project_description: str = "작업 폴더의 Claude Code 설정과 .mcp.json(원본은 읽기만 합니다)"


def claude_sources(ctx: ImportSourceContext) -> list[ImportSource]:
    """출처 공장(entry point `claude`): 홈의 `~/.claude`와 프로젝트 `.claude/`.

    `ctx.options`의 `mapping`(dict, `ClaudeMapping` 필드)으로 만드는 종류 이름을, `layout`(dict,
    `ClaudeLayout` 필드)으로 경로 이름을 바꿀 수 있다.
    """
    raw_mapping = ctx.options.get("mapping")
    raw_layout = ctx.options.get("layout")
    mapping = ClaudeMapping.from_options(raw_mapping if isinstance(raw_mapping, Mapping) else None)
    layout = ClaudeLayout.from_options(raw_layout if isinstance(raw_layout, Mapping) else None)
    titles = _Titles()
    sources: list[ImportSource] = []
    if ctx.home is not None:
        root = ctx.home / layout.claude_dir
        sources.append(
            ClaudeDirectorySource(
                id=USER_SOURCE_ID,
                title=titles.user,
                description=titles.user_description,
                root=root,
                instruction_files=[root / layout.instruction_file],
                settings_files=[root / layout.settings_file],
                id_prefix="user-",
                mapping=mapping,
                layout=layout,
                secret_rules=ctx.secret_rules,
            )
        )
    if ctx.project_dir is not None:
        root = ctx.project_dir / layout.claude_dir
        sources.append(
            ClaudeDirectorySource(
                id=PROJECT_SOURCE_ID,
                title=titles.project,
                description=titles.project_description,
                root=root,
                instruction_files=[
                    ctx.project_dir / layout.instruction_file,
                    root / layout.instruction_file,
                ],
                settings_files=[root / layout.settings_file],
                mcp_files=[ctx.project_dir / layout.mcp_file],
                id_prefix="project-",
                mapping=mapping,
                layout=layout,
                secret_rules=ctx.secret_rules,
            )
        )
    return sources
