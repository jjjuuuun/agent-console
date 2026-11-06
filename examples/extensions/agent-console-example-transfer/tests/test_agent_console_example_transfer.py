"""단위 시험: entry point 선언·로더, 형식 옵션(데이터), 파일 쓰기·읽기, 출처의 안전 규칙."""

from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import tomllib
from pathlib import Path

import pytest

from agent_console_contracts import ExportRequest, ExportSelection
from agent_console_example_transfer import (
    FORMAT_ID,
    BundleEntry,
    JsonBundleExporter,
    JsonBundleSource,
    TransferIssueCodes,
    default_format_data,
    dump_bundle,
    json_bundle_exporter,
    json_bundle_sources,
    load_format,
    read_bundle,
)
from agent_console_exports import (
    EXPORTERS_GROUP,
    ExportService,
    build_exporters,
    load_exporter_factories,
    new_exporter_factories,
)
from agent_console_exports.testing import MemoryCatalog
from agent_console_imports import (
    IMPORT_SOURCES_GROUP,
    ImportSourceContext,
    build_import_sources,
    load_import_source_factories,
    new_import_source_factories,
)

ROOT = Path(__file__).resolve().parents[1]
PLAIN = "plain-value-zz41"  # 비밀 키 이름 아래 평문(값 모양이 아니라 키 이름으로 의심된다)


def test_entry_point_declarations() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    eps = data["project"]["entry-points"]
    assert eps[EXPORTERS_GROUP] == {
        FORMAT_ID: "agent_console_example_transfer:json_bundle_exporter"
    }
    assert eps[IMPORT_SOURCES_GROUP] == {
        FORMAT_ID: "agent_console_example_transfer:json_bundle_sources"
    }


def test_loaded_through_the_library_loaders(tmp_path: Path) -> None:
    exporters = new_exporter_factories()
    ep = importlib.metadata.EntryPoint(
        name=FORMAT_ID,
        value="agent_console_example_transfer:json_bundle_exporter",
        group=EXPORTERS_GROUP,
    )
    assert [r.status for r in load_exporter_factories(exporters, entry_points=[ep])] == ["loaded"]
    built = build_exporters(exporters, {FORMAT_ID: {"file_name": "out/defs.json"}})
    assert built[FORMAT_ID].descriptor.id == FORMAT_ID

    sources = new_import_source_factories()
    ep = importlib.metadata.EntryPoint(
        name=FORMAT_ID,
        value="agent_console_example_transfer:json_bundle_sources",
        group=IMPORT_SOURCES_GROUP,
    )
    assert [r.status for r in load_import_source_factories(sources, entry_points=[ep])] == [
        "loaded"
    ]
    made = build_import_sources(sources, ImportSourceContext(project_dir=tmp_path))
    assert [s.descriptor.id for s in made] == [FORMAT_ID]
    assert made[0].descriptor.available is False  # 파일이 아직 없다
    # 프로젝트 폴더가 없으면 출처를 만들지 않는다(홈 폴더 같은 다른 곳을 읽지 않는다).
    assert build_import_sources(sources, ImportSourceContext(home=tmp_path)) == []


def test_bad_options_skip_the_format_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ValueError, match="file_name"):
        load_format({"file_name": "../escape.json"})
    with pytest.raises(ValueError, match="fields"):
        load_format({"fields": {"kind": "id"}})  # 같은 층 이름이 겹침
    with pytest.raises(ValueError, match="unknown"):
        load_format({"unknown": 1})
    exporters = new_exporter_factories()
    exporters.register(FORMAT_ID, json_bundle_exporter)
    with caplog.at_level(logging.WARNING):
        assert build_exporters(exporters, {FORMAT_ID: {"file_name": "/abs.json"}}) == {}
    assert any(FORMAT_ID in r.getMessage() for r in caplog.records)


def test_field_and_format_names_are_option_data() -> None:
    names = {"fields": {"items": "things", "document": "body"}, "format_name": "my-bundle"}
    fmt = load_format(names)
    data = dump_bundle([BundleEntry("agent", "a", {"id": "a"})], fmt)
    top = json.loads(data)
    assert top["format"] == "my-bundle"
    assert top["things"] == [{"kind": "agent", "id": "a", "body": {"id": "a"}}]
    entries, warnings = read_bundle(data, fmt)
    assert (entries[0].id, warnings) == ("a", [])
    # 다른 설정(기본값)으로는 읽지 않는다.
    assert read_bundle(data, load_format())[1][0].code == TransferIssueCodes.UNKNOWN_FORMAT
    assert default_format_data()["fields"]["items"] == "definitions"  # 기본값은 그대로


def test_files_keep_text_and_binary() -> None:
    fmt = load_format()
    files = {"a/note.md": "안녕".encode(), "bin.dat": bytes([0, 255, 1])}
    data = dump_bundle([BundleEntry("resource", "r", {"id": "r"}, files)], fmt)
    assert json.loads(data)["definitions"][0]["files"]["a/note.md"] == {"text": "안녕"}
    entries, _ = read_bundle(data, fmt)
    assert entries[0].files == files


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b"\xff\xfe not json", TransferIssueCodes.INVALID_FILE),
        (b"[]", TransferIssueCodes.INVALID_FILE),
        (
            b'{"format": "other", "version": 1, "definitions": []}',
            TransferIssueCodes.UNKNOWN_FORMAT,
        ),
        (
            b'{"format": "agent-console-example-bundle", "version": 2, "definitions": []}',
            TransferIssueCodes.UNKNOWN_FORMAT,
        ),
    ],
)
def test_broken_files_give_one_warning(raw: bytes, code: str) -> None:
    entries, warnings = read_bundle(raw, load_format())
    assert entries == []
    assert [w.code for w in warnings] == [code]


def test_bad_and_duplicate_entries_are_skipped() -> None:
    fmt = load_format()
    top = {
        "format": fmt.format_name,
        "version": fmt.format_version,
        "definitions": [
            {"kind": "agent", "id": "a", "document": {"id": "a"}},
            {"kind": "agent", "id": "a", "document": {"id": "a"}},
            {"kind": "agent", "document": {}},
            {"kind": "agent", "id": "b", "document": {}, "files": {"x": {"base64": "!!"}}},
            "not an object",
        ],
    }
    entries, warnings = read_bundle(json.dumps(top).encode(), fmt)
    assert [e.id for e in entries] == ["a"]
    assert [(w.code, w.keys) for w in warnings] == [
        (TransferIssueCodes.DUPLICATE_ENTRY, ["/definitions/1"]),
        (TransferIssueCodes.INVALID_ENTRY, ["/definitions/2"]),
        (TransferIssueCodes.INVALID_ENTRY, ["/definitions/3"]),
        (TransferIssueCodes.INVALID_ENTRY, ["/definitions/4"]),
    ]


def test_missing_dependency_is_a_warning_and_drop_fields_apply() -> None:
    from agent_console_exports.testing import MemoryDependency

    catalog = MemoryCatalog().add(
        "graph", {"id": "g", "project": "p1"}, uses=[MemoryDependency("agent", "gone")]
    )
    exporter = JsonBundleExporter(load_format({"drop_fields": ["project"]}))
    out = exporter.plan([ExportSelection(kind="graph", id="g")], catalog, {})
    assert [w.code for w in out.warnings] == ["export.not_found"]
    entry = json.loads(out.files[0].data)["definitions"][0]
    assert "project" not in entry["document"]


def test_plaintext_secret_never_reaches_the_file() -> None:
    catalog = MemoryCatalog().add(
        "resource",
        {
            "id": "mcp",
            "type": "mcp-server",
            "config": {"env": {"API_TOKEN": PLAIN, "REF": "secret://ref"}},
        },
    )
    exporters = {FORMAT_ID: JsonBundleExporter(load_format())}
    request = ExportRequest(exporter=FORMAT_ID, items=[ExportSelection(kind="resource", id="mcp")])
    output = ExportService(exporters, catalog).output(request)
    text = output.files[0].data.decode("utf-8")
    assert PLAIN not in text
    assert "secret://ref" in text  # 참조는 값이 아니라 그대로 간다
    assert [w.code for w in output.warnings] == ["export.secret_redacted"]
    assert PLAIN not in json.dumps([w.model_dump(mode="json") for w in output.warnings])


def _write_bundle(folder: Path, entries: list[BundleEntry]) -> Path:
    path = folder / load_format().file_name
    path.write_bytes(dump_bundle(entries, load_format()))
    return path


def test_source_masks_plaintext_secrets_with_location_only(tmp_path: Path) -> None:
    doc = {"id": "mcp", "name": "도구 서버", "type": "mcp-server", "env": {"API_TOKEN": PLAIN}}
    files = {"notes.md": f"password={PLAIN}\n".encode()}
    _write_bundle(tmp_path, [BundleEntry("resource", "mcp", doc, files)])
    (source,) = json_bundle_sources(ImportSourceContext(project_dir=tmp_path))
    assert source.descriptor.available is True
    scan = source.scan()
    (item,) = scan.items
    dumped = json.dumps(item.document) + str(item.files) + item.candidate.model_dump_json()
    dumped += json.dumps([w.model_dump(mode="json") for w in scan.warnings])
    assert PLAIN not in dumped
    assert item.candidate.resource_type == "mcp-server"
    assert item.candidate.name == "도구 서버"
    (warning,) = item.candidate.warnings
    assert warning.code == "import.secret_suspected"
    assert warning.keys == ["/env/API_TOKEN", "/files/notes.md"]


def test_source_reads_only_inside_the_project_and_not_links(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    real = _write_bundle(outside, [BundleEntry("agent", "a", {"id": "a"})])
    if os.name == "nt":
        pytest.skip("링크 만들기 권한이 필요하다")
    try:
        (project / real.name).symlink_to(real)
    except OSError:
        pytest.skip("링크를 만들 수 없는 파일 시스템")
    (source,) = json_bundle_sources(ImportSourceContext(project_dir=project))
    assert source.descriptor.available is False
    scan = source.scan()
    assert scan.items == []
    assert [w.code for w in scan.warnings] == ["import.skipped_link"]


def test_source_without_file_or_too_large(tmp_path: Path) -> None:
    fmt = load_format({"max_file_bytes": 10})
    source = JsonBundleSource(tmp_path / fmt.file_name, fmt)
    assert source.scan().items == []
    assert source.scan().warnings == []
    (tmp_path / fmt.file_name).write_bytes(b"x" * 11)
    assert [w.code for w in source.scan().warnings] == [TransferIssueCodes.TOO_LARGE]
