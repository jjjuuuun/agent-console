"""X5 `claude-code-jsonl`: Claude Code 세션 기록 폴더를 읽는 출처(기본 꺼짐, F-5).

폴더 구조(루트 = Claude Code `projects` 폴더):

- `<프로젝트 키>/<세션 id>.jsonl` — 메인 세션
- `<프로젝트 키>/<세션 id>/<subagents_dir>/**/agent-<id>.jsonl` — 서브에이전트 기록
- 그 옆 `agent-<id><meta_suffix>` — 서브에이전트 메타(역할·설명·위임 호출 id)

증분 읽기 규칙(오프셋·미완성 줄 보류·파일 축소 시 처음부터)은 `JsonlFileSource`가 맡는다.
메타 파일도 `ctx.open_read`로만 연다. 이 모듈에는 쓰기·이동·삭제 경로가 없다.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from agent_console_claude_format import project_key
from agent_console_contracts.logs import LogSourceDescriptor
from agent_console_logs import (
    JsonlFileSource,
    JsonValue,
    LogSourceContext,
    expand_user_path,
    json_pointer,
)

from ._schemas import source_config_schema

__all__ = [
    "CLAUDE_CODE_FORMAT",
    "CLAUDE_CODE_SOURCE_ID",
    "META_KIND_SESSION",
    "META_KIND_SUBAGENT",
    "ClaudeCodeJsonlSource",
    "project_key",
]

CLAUDE_CODE_SOURCE_ID = "claude-code-jsonl"
"""출처 id(entry point 이름과 같다)."""

CLAUDE_CODE_FORMAT = "claude-code"
"""기본 분류기 id(디스크립터 `format`)."""

META_KIND_SESSION = "session"
META_KIND_SUBAGENT = "subagent"

_SUBAGENT_PREFIX = "agent-"
_JSONL = ".jsonl"


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


class ClaudeCodeJsonlSource(JsonlFileSource):
    """Claude Code 세션·서브에이전트 기록 출처.

    `SourceRef.meta`(분류기에 넘기는 맥락):

    - 공통: `kind`(`session`·`subagent`), `project`(프로젝트 폴더 키), `session`, `thread`
    - 서브에이전트: `parent`(= 세션 id), `role`·`description`·`tool_use_id`(메타 파일)
    - 메인 세션: `subagents`(위임 호출 id → 서브에이전트 thread, 지금 있는 메타 파일 기준)

    메타 파일은 (경로, 크기, 수정 시각)으로 캐시한다(같은 내용을 수집마다 다시 읽지 않음).
    """

    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id=CLAUDE_CODE_SOURCE_ID,
        title="Claude Code 세션 로그",
        format=CLAUDE_CODE_FORMAT,
        description=(
            "Claude Code가 남긴 세션 기록(서브에이전트 포함)을 읽는다. "
            "원본은 읽기만 하고, 색인에는 비밀 의심 값을 가린 사본이 들어간다."
        ),
        config_schema=source_config_schema(),
        default_enabled=False,
        reads_paths=True,
        setup_help=(
            "켜면 기본으로 `~/.claude/projects`(환경 변수 `CLAUDE_CONFIG_DIR`가 있으면 그 아래 "
            "`projects`)를 읽는다. 다른 폴더는 `roots`에 적는다. 대화 원문이 색인에 복사되므로 "
            "기본은 꺼져 있다."
        ),
    )

    def __init__(self) -> None:
        self._meta_cache: dict[str, tuple[int, float, dict[str, JsonValue]]] = {}
        self._cwd_cache: dict[str, tuple[int, float, str]] = {}

    # ---------------------------------------------------------------- 루트

    def default_roots(self, ctx: LogSourceContext) -> list[Path]:
        """`roots`가 비었을 때 두 곳(5.7R.30b): CLI 세션 + 앱 자격 폴더의 세션.

        - 앱 실행 세션: 호스트 경로 `ctx.paths["workspace"]`(앱 workspace) 기준 `workspace_roots`
          (기본 `.state/claude/projects` — 앱 하나에 하나인 구독 자격 폴더 아래). 절대 경로도 된다.
          workspace를 모르면(단독 사용) 상대 경로는 건너뛴다.
        - CLI 세션: `config_dir_env` 환경 변수 아래 하위 경로, 없으면 `default_root`
          (`~/.claude/projects`, 읽기만 한다).

        어느 루트든 수집기가 같은 프로젝트 범위(`in_scope`, 등록된 프로젝트 폴더 키)로 거른다.
        환경 변수는 주입된 `ctx.environ`에서만 읽는다(프로세스 환경을 몰래 읽지 않음).
        """
        env_name = _str(ctx.config.get("config_dir_env"))
        config_dir = ctx.environ.get(env_name, "") if env_name else ""
        roots: list[Path] = []
        if config_dir:
            sub = _str(ctx.config.get("config_dir_subpath"))
            base = expand_user_path(config_dir, ctx.environ)
            roots.append(base / sub if sub else base)
        else:
            default_root = _str(ctx.config.get("default_root"))
            if default_root:
                roots.append(expand_user_path(default_root, ctx.environ))
        workspace = ctx.paths.get("workspace")
        subs = ctx.config.get("workspace_roots")
        for sub in subs if isinstance(subs, list) else []:
            if not isinstance(sub, str) or not sub:
                continue
            path = expand_user_path(sub, ctx.environ)
            if not path.is_absolute():
                if workspace is None:
                    continue  # 앱 workspace를 모름(단독 사용)
                path = workspace / path
            if path not in roots:
                roots.append(path)
        return roots

    # ---------------------------------------------------------------- 프로젝트 범위

    def allowed_keys(self, ctx: LogSourceContext) -> set[str] | None:
        """등록된 프로젝트 폴더 → `projects` 아래 폴더 이름 집합(범위 = 등록 전체, 5.7R.33i).

        옛 설정 `project_scope`(`current`·`registered`)는 읽지 않는다(스키마 `deprecated`).
        `ctx.projects`가 없으면 None(필터 없음).
        """
        if ctx.projects is None:
            return None
        keep, rep = self._key_rules(ctx)
        return {project_key(f, keep=keep, replacement=rep) for f in ctx.projects.registered}

    def _key_rules(self, ctx: LogSourceContext) -> tuple[str, str]:
        keep = _str(ctx.config.get("project_key_keep"))
        replacement = ctx.config.get("project_key_replacement")
        return keep, replacement if isinstance(replacement, str) else "-"

    def accepts(self, rel: str, ctx: LogSourceContext) -> bool:
        """범위 밖 단위는 발견할 때 메타 파일을 읽지 않는다."""
        return self.in_scope(rel, ctx)

    def in_scope(self, ref: str, ctx: LogSourceContext) -> bool:
        """`ScopedLogSource`: ref가 등록 프로젝트(하위 폴더 포함)의 기록인가.

        1. 첫 폴더(프로젝트 키)를 등록 폴더 키와 비교한다. 같거나 `키 + 바꿈 글자`로 시작하지 않으면
           범위 밖이다(파일·메타를 열지 않는다).
        2. 맞으면 세션 cwd(파일 앞부분의 `cwd_pointer`)로 확정한다: cwd가 등록 폴더(하위 포함)
           안이면 범위 안. 키는 손실 변환이라(`/w/a-b`와 `/w/a/b`가 같은 키) 키만으로 정하지 않는다.
           cwd가 없는 파일은 키가 정확히 같을 때만 받는다. 파일이 사라졌으면(색인 유지 판정) 키로만.
        """
        keys = self.allowed_keys(ctx)
        if keys is None:
            return True
        if "/" not in ref:
            return False
        head = ref.split("/", 1)[0]
        _keep, rep = self._key_rules(ctx)
        exact = head in keys
        if not exact and not any(rep and head.startswith(k + rep) for k in keys):
            return False
        projects = ctx.projects
        if projects is None:  # pragma: no cover - allowed_keys가 None을 냈다
            return True
        path = self.resolve(ref, ctx)
        if path is None:
            return True  # 지금 파일이 없음: 이미 색인된 단위를 지우지 않는다
        cwd = self._session_cwd(path, ctx)
        if not cwd:
            return exact
        return projects.contains(cwd)

    def _session_cwd(self, path: Path, ctx: LogSourceContext) -> str:
        """파일 앞부분(설정 `cwd_peek_bytes`)에서 처음 나온 cwd(`cwd_pointer`). 없으면 빈 문자열.

        경로별로 캐시한다. 찾은 cwd는 파일이 자라도 그대로 쓰고(앞부분은 바뀌지 않음), 줄어들면
        (회전) 다시 본다. 못 찾았으면 크기·수정 시각이 바뀔 때 다시 본다. 줄이 깨졌으면 건너뛴다.
        """
        try:
            stat = path.stat()
        except OSError:
            return ""
        key = str(path)
        cached = self._cwd_cache.get(key)
        if cached is not None:
            size, mtime, value = cached
            if (value and stat.st_size >= size) or (
                stat.st_size == size and stat.st_mtime == mtime
            ):
                return value
        limit = ctx.config.get("cwd_peek_bytes")
        max_bytes = limit if isinstance(limit, int) and limit > 0 else 262144
        pointer = _str(ctx.config.get("cwd_pointer")) or "/cwd"
        found = ""
        try:
            with ctx.open_read(path) as stream:
                head = stream.read(max_bytes)
        except OSError:
            head = b""
        for line in head.splitlines():
            try:
                value = json_pointer(json.loads(line), pointer)
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(value, str) and value:
                found = value
                break
        self._cwd_cache[key] = (stat.st_size, stat.st_mtime, found)
        return found

    # ---------------------------------------------------------------- 파일별 맥락

    def ref_meta(self, root: Path, path: Path, ctx: LogSourceContext) -> Mapping[str, JsonValue]:
        """루트 기준 위치로 메인 세션·서브에이전트를 가르고 맥락을 만든다."""
        parts = path.relative_to(root).parts
        subagents_dir = _str(ctx.config.get("subagents_dir")) or "subagents"
        stem = path.name[: -len(_JSONL)] if path.name.endswith(_JSONL) else path.stem
        project = parts[0] if len(parts) > 1 else ""
        if len(parts) >= 4 and parts[2] == subagents_dir:
            session = parts[1]
            meta: dict[str, JsonValue] = {
                "kind": META_KIND_SUBAGENT,
                "project": project,
                "session": session,
                "thread": stem,
                "parent": session,
            }
            info = self._read_meta(path.with_name(stem + self._meta_suffix(ctx)), ctx)
            for key in ("role", "description", "tool_use_id"):
                if isinstance(info.get(key), str) and info[key]:
                    meta[key] = info[key]
            return meta
        meta = {
            "kind": META_KIND_SESSION,
            "project": project,
            "session": stem,
            "thread": stem,
        }
        links = self._subagent_links(path.parent / stem / subagents_dir, ctx)
        if links:
            meta["subagents"] = links
        return meta

    def _meta_suffix(self, ctx: LogSourceContext) -> str:
        return _str(ctx.config.get("meta_suffix")) or ".meta.json"

    def _subagent_links(self, folder: Path, ctx: LogSourceContext) -> dict[str, JsonValue]:
        """서브에이전트 폴더의 메타 파일 → {위임 호출 id: 서브에이전트 thread}."""
        if not folder.is_dir():
            return {}
        suffix = self._meta_suffix(ctx)
        links: dict[str, JsonValue] = {}
        for current, dirs, files in os.walk(folder, followlinks=False):
            dirs.sort()
            for name in sorted(files):
                if not (name.startswith(_SUBAGENT_PREFIX) and name.endswith(suffix)):
                    continue
                info = self._read_meta(Path(current) / name, ctx)
                call_id = info.get("tool_use_id")
                if isinstance(call_id, str) and call_id:
                    links.setdefault(call_id, name[: -len(suffix)])
        return links

    def _read_meta(self, path: Path, ctx: LogSourceContext) -> dict[str, JsonValue]:
        """메타 파일 하나를 읽어 `meta_fields` 포인터로 값을 꺼낸다(없거나 깨지면 빈 객체)."""
        try:
            stat = path.stat()
        except OSError:
            return {}
        key = str(path)
        cached = self._meta_cache.get(key)
        if cached is not None and cached[0] == stat.st_size and cached[1] == stat.st_mtime:
            return cached[2]
        limit = ctx.config.get("max_meta_bytes")
        max_bytes = limit if isinstance(limit, int) and limit > 0 else 65536
        values: dict[str, JsonValue] = {}
        if stat.st_size <= max_bytes:
            try:
                with ctx.open_read(path) as stream:
                    data = json.loads(stream.read(max_bytes + 1))
            except (OSError, ValueError, UnicodeDecodeError):
                data = None
            fields = ctx.config.get("meta_fields")
            if isinstance(data, Mapping) and isinstance(fields, Mapping):
                for name, pointer in fields.items():
                    value = json_pointer(data, str(pointer))
                    if isinstance(value, str | int | float | bool):
                        values[str(name)] = value if isinstance(value, str) else str(value)
        self._meta_cache[key] = (stat.st_size, stat.st_mtime, values)
        return values
