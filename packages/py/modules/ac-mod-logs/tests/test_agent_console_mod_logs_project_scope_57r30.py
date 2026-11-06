"""5.7R.30 후속: ``projects.folders``(등록된 프로젝트 폴더)를 범위를 아는 출처에 넘긴다.

- 포트가 없으면 등록된 프로젝트가 없는 것으로 보고 범위 출처는 아무것도 읽지 않는다
  (``logs.no_projects``).
- 포트가 있으면 범위 안 단위만 읽는다. 설정 ``roots``가 넓으면 ``logs.out_of_scope``로 알린다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from agent_console_contracts import WorkspaceSettings
from agent_console_contracts.logs import LogClassifierDescriptor, LogSourceDescriptor
from agent_console_logs import (
    ClassifyContext,
    Cursor,
    LogEventDraft,
    LogSourceContext,
    RawRecord,
    ReadResult,
    SourceRef,
)
from agent_console_mod_logs import LOGS_QUERY, SERVER_WARNINGS, LogsService, module
from agent_console_mod_logs.testing import (
    RuntimeSource,
    project_folders_module,
    runtime_sources_module,
    static_settings_module,
)
from agent_console_modkit import Assembly, BaseServices, Module, ModulesConfig, Paths, assemble

QUIET = {"startup_scan": False, "scan_interval_seconds": 0}
SID = "scoped-mem"


class _ScopedSource:
    """프로젝트 폴더 이름을 ref 첫 칸으로 쓰는 가짜 출처(``ScopedLogSource``)."""

    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id=SID, title="범위", format="mem", default_enabled=True, reads_paths=False
    )

    def discover(self, ctx: LogSourceContext) -> Iterator[SourceRef]:
        for name in ("demo", "other"):
            yield SourceRef(ref=f"{name}/s.jsonl", size=1)

    def in_scope(self, ref: str, ctx: LogSourceContext) -> bool:
        assert ctx.projects is not None
        names = {p.name for p in ctx.projects.registered}
        return ref.split("/", 1)[0] in names

    def read(
        self, ref: SourceRef, cursor: Cursor, ctx: LogSourceContext, *, budget: int, final: bool
    ) -> ReadResult:
        rows = [] if cursor.offset else [RawRecord(origin=ref.ref, offset=0, data={"t": ref.ref})]
        return ReadResult(records=rows, cursor=Cursor(offset=1), read_bytes=1, exhausted=True)


class _Classifier:
    descriptor: ClassVar[LogClassifierDescriptor] = LogClassifierDescriptor(
        id="mem", formats=["mem"], title="메모리"
    )

    def classify(self, record: RawRecord, ctx: ClassifyContext) -> list[LogEventDraft]:
        return [LogEventDraft(category="run", title=str(record.origin), session="s")]


def _assembly(tmp_path: Path, modules: list[Module], *, roots: bool = False) -> Assembly:
    config = {"roots": ["/wide"]} if roots else {}
    settings = WorkspaceSettings.model_validate(
        {"logs": {"sources": [{"id": SID, "enabled": True, "config": config}]}}
    )
    services = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "st")
    )
    return assemble(
        [
            module,
            static_settings_module(settings),
            runtime_sources_module([RuntimeSource(_ScopedSource(), _Classifier())]),
            *modules,
        ],
        ModulesConfig(options={"mod-logs": QUIET}),
        base=services,
    )


def _service(assembly: Assembly) -> LogsService:
    found = assembly.port(LOGS_QUERY)
    assert isinstance(found, LogsService)
    return found


async def _scan(assembly: Assembly) -> set[str]:
    await assembly.start(fail_fast=True)
    try:
        service = _service(assembly)
        await service.scan()
        return {c.ref for c in service.index.list_cursors(SID)}
    finally:
        await assembly.stop()


def _codes(assembly: Assembly) -> list[str]:
    return [i.code for source in assembly.ports(SERVER_WARNINGS) for i in source()]


async def test_without_projects_nothing_is_read(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path, [])
    assert await _scan(assembly) == set()
    assert "logs.no_projects" in _codes(assembly)


async def test_all_registered_projects(tmp_path: Path) -> None:
    """5.7R.33i: 범위는 등록 전체 하나(옛 current 없음)."""
    assembly = _assembly(tmp_path, [project_folders_module([Path("/w/demo"), Path("/w/other")])])
    assert await _scan(assembly) == {"demo/s.jsonl", "other/s.jsonl"}
    assert "logs.no_projects" not in _codes(assembly)
    only = _assembly(tmp_path, [project_folders_module([Path("/w/demo")])])
    assert await _scan(only) == {"demo/s.jsonl"}
    assert "logs.no_projects" not in _codes(assembly)
    assert "logs.out_of_scope" not in _codes(assembly)  # 기본 루트는 알리지 않는다


async def test_wide_roots_are_filtered_and_reported(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path, [project_folders_module([Path("/w/demo")])], roots=True)
    assert await _scan(assembly) == {"demo/s.jsonl"}
    assert "logs.out_of_scope" in _codes(assembly)


class _DeprecatedKeySource(_ScopedSource):
    """5.7R.30b: 스키마가 `deprecated: true`로 표시한 키(옛 `project_roots`)를 둔 출처."""

    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id=SID,
        title="범위",
        format="mem",
        default_enabled=True,
        reads_paths=False,
        config_schema={
            "type": "object",
            "properties": {
                "project_roots": {"type": "array", "deprecated": True},
                "workspace_roots": {"type": "array", "default": []},
            },
        },
    )
    seen_workspace: ClassVar[list[Path | None]] = []

    def discover(self, ctx: LogSourceContext) -> Iterator[SourceRef]:
        self.seen_workspace.append(ctx.paths.get("workspace"))
        yield from super().discover(ctx)


async def test_deprecated_key_is_ignored_with_info_issue(tmp_path: Path) -> None:
    """옛 키는 읽고 무시 + 정보 이슈(`logs.ignored_key`), 출처는 앱 workspace 경로를 받는다."""
    settings = WorkspaceSettings.model_validate(
        {
            "logs": {
                "sources": [
                    {"id": SID, "enabled": True, "config": {"project_roots": [".agent-console/x"]}}
                ]
            }
        }
    )
    assembly = assemble(
        [
            module,
            static_settings_module(settings),
            runtime_sources_module([RuntimeSource(_DeprecatedKeySource(), _Classifier())]),
            project_folders_module([Path("/w/demo")]),
        ],
        ModulesConfig(options={"mod-logs": QUIET}),
        base=BaseServices(
            paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "st")
        ),
    )
    assert await _scan(assembly) == {"demo/s.jsonl"}
    issues = [i for source in assembly.ports(SERVER_WARNINGS) for i in source()]
    [ignored] = [i for i in issues if i.code == "logs.ignored_key"]
    assert ignored.severity == "info"
    assert ignored.details == {"source": SID, "key": "project_roots"}
    assert _DeprecatedKeySource.seen_workspace[-1] == tmp_path / "ws"


async def test_old_log_projects_setting_is_ignored_with_info(tmp_path: Path) -> None:
    """5.7R.33i(K33-15): 옛 ``logs.projects``가 있어도 결과가 같고 정보 ``settings.ignored_key``."""
    settings = WorkspaceSettings.model_validate(
        {
            "logs": {
                "sources": [{"id": SID, "enabled": True}],
                "projects": {"groups": [{"id": "g", "match": ["/w/**"]}], "ungrouped": "none"},
            }
        }
    )
    assembly = assemble(
        [
            module,
            static_settings_module(settings),
            runtime_sources_module([RuntimeSource(_ScopedSource(), _Classifier())]),
            project_folders_module({"demo-id": Path("/w/demo")}),
        ],
        ModulesConfig(options={"mod-logs": QUIET}),
        base=BaseServices(
            paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "st")
        ),
    )
    await assembly.start(fail_fast=True)
    try:
        service = _service(assembly)
        await service.scan()
        assert {c.ref for c in service.index.list_cursors(SID)} == {"demo/s.jsonl"}
        issues = [i for source in assembly.ports(SERVER_WARNINGS) for i in source()]
        [ignored] = [i for i in issues if i.code == "settings.ignored_key"]
        assert ignored.severity == "info"
        assert ignored.details == {"key": "logs.projects"}
        ctx = service.query_context()
        assert ctx.project_for is not None
        assert ctx.project_for("/w/demo/sub") == "demo-id"
        assert ctx.project_for("/w/other") is None
    finally:
        await assembly.stop()


async def test_archived_folders_are_retained_not_read(tmp_path: Path) -> None:
    """보관 폴더는 읽지 않는다(범위 밖이지만 색인을 지우는 판정에서는 남김)."""
    assembly = _assembly(
        tmp_path, [project_folders_module([Path("/w/demo")], archived=[Path("/w/other")])]
    )
    assert await _scan(assembly) == {"demo/s.jsonl"}
