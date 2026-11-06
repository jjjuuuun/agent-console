"""왕복 시험: 정의 저장소(파일 workspace) → 내보내기(폴더에 쓰기) → 빈 workspace로
가져오기 → 같은 정의.

서버 없이 두 라이브러리(`agent_console_exports`·`agent_console_imports`)와 실제 정의
저장소(`agent_console_store.FileDefinitionStore`)로 조립한다. 서버의 내보내기·가져오기
모듈이 하는 조립과 같다(카탈로그 = 정의 읽기, 쓰기 = 정의 저장소).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_console_contracts import (
    ExportSelection,
    ExportWriteRequest,
    ImportRequest,
    ImportSelection,
)
from agent_console_example_transfer import FORMAT_ID, json_bundle_exporter, json_bundle_sources
from agent_console_exports import ExportRoot, ExportService, FolderWriter
from agent_console_exports.testing import MemoryCatalog, MemoryDependency
from agent_console_imports import ImportService, ImportSourceContext
from agent_console_imports.testing import MemoryDefinitionWriter
from agent_console_store import FileDefinitionStore, StoreError

PLAIN = "plain-value-zz42"
AGENT = {"id": "writer", "name": "작성자", "system_prompt": "짧게 쓴다.", "tools": ["Read"]}
SKILL = {"id": "style", "type": "skill", "name": "문체", "content": {"file": "SKILL.md"}}
FILES = {"SKILL.md": "# 문체\n\n짧게.\n".encode(), "img/dot.bin": bytes([0, 1, 254, 255])}


class StoreCatalog:
    """`ExportCatalog`: 정의 저장소를 읽기만 한다. 의존은 시험이 정한 표에서."""

    def __init__(
        self, store: FileDefinitionStore, uses: Mapping[tuple[str, str], list[MemoryDependency]]
    ) -> None:
        self._store = store
        self._uses = uses

    def document(self, kind: str, id: str) -> Mapping[str, Any] | None:
        try:
            return dict(self._store.get(kind, id).document)
        except (StoreError, KeyError, ValueError):
            return None

    def files(self, kind: str, id: str) -> Mapping[str, bytes]:
        try:
            listed = self._store.list_files(kind, id)
        except (StoreError, KeyError, ValueError):
            return {}
        return {f.path: self._store.read_file(kind, id, f.path) for f in listed}

    def dependencies(self, kind: str, id: str) -> Sequence[MemoryDependency]:
        return self._uses.get((kind, id), [])


def _seed(store: FileDefinitionStore) -> None:
    store.create("agent", AGENT)
    created = store.create("resource", SKILL)
    store.write_files("resource", "style", FILES, expected_version=created.version_hash)


def _export(store: FileDefinitionStore, out: Path) -> Path:
    out.mkdir()  # 설치자가 등록한 내보내기 루트(있는 폴더)
    uses = {("agent", "writer"): [MemoryDependency("resource", "style")]}
    service = ExportService(
        {FORMAT_ID: json_bundle_exporter({})},
        StoreCatalog(store, uses),
        writer=FolderWriter([ExportRoot("out", out)]),
    )
    result = service.write(
        ExportWriteRequest(
            exporter=FORMAT_ID,
            items=[ExportSelection(kind="agent", id="writer")],  # 리소스는 의존으로 따라온다
            root="out",
            subdir="project",
        )
    )
    assert [f.action for f in result.files] == ["create"]
    return out / "project"


def _import(project: Path, target: Any) -> list[tuple[str, str, str]]:
    (source,) = json_bundle_sources(ImportSourceContext(project_dir=project))
    service = ImportService([source], target)
    preview = service.preview(FORMAT_ID)
    request = ImportRequest(
        source=FORMAT_ID,
        items=[ImportSelection(candidate_id=c.id) for c in preview.candidates],
    )
    return [(i.kind, i.target_id or "", i.action) for i in service.apply(request).items]


def test_round_trip_through_file_workspaces(tmp_path: Path) -> None:
    source = FileDefinitionStore(tmp_path / "ws-a")
    _seed(source)
    project = _export(source, tmp_path / "exports")

    target = FileDefinitionStore(tmp_path / "ws-b")  # 빈 workspace
    assert _import(project, target) == [
        ("agent", "writer", "created"),
        ("resource", "style", "created"),
    ]
    for kind, ident in (("agent", "writer"), ("resource", "style")):
        assert target.get(kind, ident).document == source.get(kind, ident).document
    copied = {
        f.path: target.read_file("resource", "style", f.path)
        for f in target.list_files("resource", "style")
    }
    assert copied == FILES

    # 다시 가져오면 기본 충돌 처리(rename)로 새 이름이 붙는다 — 원본 파일은 그대로다.
    before = (project / "agent-console-bundle.json").read_bytes()
    assert ("agent", "writer-2", "renamed") in _import(project, target)
    assert (project / "agent-console-bundle.json").read_bytes() == before


def test_round_trip_keeps_references_and_drops_plaintext(tmp_path: Path) -> None:
    doc = {
        "id": "tools",
        "type": "mcp-server",
        "name": "도구",
        "config": {"env": {"API_TOKEN": PLAIN, "OTHER_TOKEN": "secret://other_token"}},
    }
    catalog = MemoryCatalog().add("resource", doc)
    service = ExportService(
        {FORMAT_ID: json_bundle_exporter({})},
        catalog,
        writer=FolderWriter([ExportRoot("out", tmp_path)]),
    )
    service.write(
        ExportWriteRequest(
            exporter=FORMAT_ID,
            items=[ExportSelection(kind="resource", id="tools")],
            root="out",
            subdir="p",
        )
    )
    written = (tmp_path / "p" / "agent-console-bundle.json").read_text(encoding="utf-8")
    assert PLAIN not in written

    store = MemoryDefinitionWriter()
    assert _import(tmp_path / "p", store) == [("resource", "tools", "created")]
    env = store.documents[("resource", "tools")]["config"]["env"]
    assert env["OTHER_TOKEN"] == "secret://other_token"
    assert env["API_TOKEN"] != PLAIN
