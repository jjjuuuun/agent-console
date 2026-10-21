"""`ExportService`·`FolderWriter`·로딩.

요청 검사, 보관 파일, 허용 폴더 쓰기 안전 규칙, 비밀 안전망.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from collections.abc import Mapping, Sequence
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import (
    ExporterDescriptor,
    ExportRequest,
    ExportSelection,
    ExportWriteRequest,
    Issue,
)
from agent_console_exports import (
    EXPORTERS_GROUP,
    ExportConflictError,
    ExportIssueCodes,
    ExportItemNotFoundError,
    ExportOutput,
    ExportRoot,
    ExportService,
    ExportValidationError,
    FolderWriter,
    OutputFile,
    UnknownExporterError,
    UnknownExportRootError,
    build_exporters,
    build_zip,
    load_exporter_factories,
    new_exporter_factories,
    path_problem,
)
from agent_console_secret_rules import SecretRules

TOKEN = "ghp_plain_value_123456"


class Catalog:
    def document(self, kind: str, id: str) -> Mapping[str, Any] | None:
        return {"id": id} if id != "missing" else None

    def files(self, kind: str, id: str) -> Mapping[str, bytes]:
        return {}

    def dependencies(self, kind: str, id: str) -> Sequence[Any]:
        return []


class EchoExporter:
    """테스트 형식: 항목마다 `<kind>/<id>.txt`. 옵션 `extra`로 파일을 더한다."""

    def __init__(self, files: Sequence[OutputFile] = (), warnings: Sequence[Issue] = ()) -> None:
        self.descriptor = ExporterDescriptor(
            id="echo-x",
            title="에코",
            config_schema={
                "type": "object",
                "properties": {"flag": {"type": "boolean"}},
                "additionalProperties": False,
            },
            kinds=["thing"],
        )
        self._files = list(files)
        self._warnings = list(warnings)

    def plan(
        self, items: Sequence[ExportSelection], catalog: Any, options: Mapping[str, Any]
    ) -> ExportOutput:
        files = [
            OutputFile(f"{i.kind}/{i.id}.txt", f"{i.id}\n".encode(), "text/plain") for i in items
        ]
        return ExportOutput(files=[*files, *self._files], warnings=list(self._warnings))


def request(*ids: str, **extra: Any) -> ExportRequest:
    return ExportRequest(
        exporter="echo-x", items=[ExportSelection(kind="thing", id=i) for i in ids], **extra
    )


def service(tmp_path: Path, exporter: Any = None, **kw: Any) -> ExportService:
    root = tmp_path / "out"
    root.mkdir(exist_ok=True)
    writer = FolderWriter(
        [ExportRoot("out", root, "출력"), ExportRoot("prot", tmp_path / "home" / ".claude")],
        protected=[tmp_path / "home" / ".claude"],
    )
    return ExportService({"echo-x": exporter or EchoExporter()}, Catalog(), writer=writer, **kw)


def test_paths() -> None:
    assert path_problem("a/b.md") is None
    assert path_problem("", allow_empty=True) is None
    for bad in (
        "",
        "/abs",
        "a/../b",
        "a//b",
        "a\\b",
        "c:x",
        "NUL.txt",
        "con",
        "dot.",
        "sp ",
        "a\x01",
    ):
        assert path_problem(bad) is not None, bad


def test_request_checks(tmp_path: Path) -> None:
    svc = service(tmp_path)
    assert [d.id for d in svc.descriptors()] == ["echo-x"]
    with pytest.raises(UnknownExporterError):
        svc.plan(request("a").model_copy(update={"exporter": "nope"}))
    with pytest.raises(ExportValidationError) as bad_kind:
        svc.plan(ExportRequest(exporter="echo-x", items=[ExportSelection(kind="other", id="a")]))
    assert bad_kind.value.issues[0].path == "/items/0/kind"
    assert bad_kind.value.issues[0].code == ExportIssueCodes.KIND_UNSUPPORTED
    with pytest.raises(ExportValidationError) as bad_opt:
        svc.plan(request("a", options={"flag": "yes"}))
    assert bad_opt.value.issues[0].path == "/options/flag"
    with pytest.raises(ExportItemNotFoundError):
        svc.plan(request("missing"))


def test_plan_and_archive(tmp_path: Path) -> None:
    svc = service(tmp_path)
    plan = svc.plan(request("a", "b"))
    assert [(f.path, f.action, f.size) for f in plan.files] == [
        ("thing/a.txt", "create", 2),
        ("thing/b.txt", "create", 2),
    ]
    archive = svc.archive(request("a", "b", root="out"))  # 보관 파일은 root 무시
    assert archive.filename == "echo-x.zip"
    with zipfile.ZipFile(io.BytesIO(archive.data)) as z:
        assert z.namelist() == ["thing/a.txt", "thing/b.txt"]
        assert z.read("thing/a.txt") == b"a\n"
    assert archive.data == svc.archive(request("a", "b")).data  # 같은 입력 = 같은 바이트
    assert not any((tmp_path / "out").iterdir())  # 디스크에 쓰지 않음


def test_error_warning_blocks_archive_and_write(tmp_path: Path) -> None:
    blocked = EchoExporter(warnings=[Issue(severity="error", code="x.bad", message="불가")])
    svc = service(tmp_path, blocked)
    assert svc.plan(request("a")).warnings[0].code == "x.bad"  # 미리보기는 보인다
    with pytest.raises(ExportValidationError):
        svc.archive(request("a"))
    with pytest.raises(ExportValidationError):
        svc.write(
            ExportWriteRequest(
                exporter="echo-x", root="out", items=[ExportSelection(kind="thing", id="a")]
            )
        )


def write_req(*ids: str, **kw: Any) -> ExportWriteRequest:
    return ExportWriteRequest(
        exporter="echo-x",
        root="out",
        items=[ExportSelection(kind="thing", id=i) for i in ids],
        **kw,
    )


def test_write_conflict_policies(tmp_path: Path) -> None:
    svc = service(tmp_path)
    out = tmp_path / "out"
    assert [r.id for r in svc.roots()] == ["out"]  # 보호 위치 루트는 목록에서 빠진다
    assert svc.roots(expose_paths=False)[0].path == ""
    first = svc.write(write_req("a", subdir="proj/x"))
    assert [f.action for f in first.files] == ["create"]
    assert (out / "proj" / "x" / "thing" / "a.txt").read_bytes() == b"a\n"

    (out / "proj" / "x" / "thing" / "a.txt").write_bytes(b"changed")
    plan = svc.plan(request("a", "b", root="out", subdir="proj/x"))
    assert [f.action for f in plan.files] == ["conflict", "create"]
    with pytest.raises(ExportConflictError) as conflict:
        svc.write(write_req("a", "b", subdir="proj/x"))
    assert conflict.value.details["paths"] == ["thing/a.txt"]
    assert not (out / "proj" / "x" / "thing" / "b.txt").exists()  # fail = 아무것도 안 씀

    skipped = svc.write(write_req("a", "b", subdir="proj/x", on_conflict="skip"))
    assert [f.action for f in skipped.files] == ["skip", "create"]
    assert (out / "proj" / "x" / "thing" / "a.txt").read_bytes() == b"changed"
    over = svc.write(write_req("a", "b", subdir="proj/x", on_conflict="overwrite"))
    assert [f.action for f in over.files] == ["overwrite", "skip"]
    assert (out / "proj" / "x" / "thing" / "a.txt").read_bytes() == b"a\n"
    assert not [p for p in out.rglob("*") if p.name.endswith(".ac-export-tmp")]


def test_write_rejects_unsafe_targets(tmp_path: Path) -> None:
    svc = service(tmp_path)
    out = tmp_path / "out"
    with pytest.raises(UnknownExportRootError):
        svc.write(write_req("a").model_copy(update={"root": "nope"}))
    with pytest.raises(UnknownExportRootError):  # 보호 위치 루트는 등록돼 있어도 쓸 수 없다
        svc.write(write_req("a").model_copy(update={"root": "prot"}))
    for subdir in ("../x", "/abs", "a/./b", "a:b"):
        with pytest.raises(ExportValidationError) as bad:
            svc.write(write_req("a", subdir=subdir))
        assert bad.value.issues[0].path == "/subdir"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (out / "link").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ExportValidationError):
        svc.write(write_req("a", subdir="link"))
    (out / "deep").mkdir()
    (out / "deep" / "thing").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ExportValidationError):
        svc.write(write_req("a", subdir="deep"))
    assert not any(elsewhere.iterdir())


def test_protected_location_under_root(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    writer = FolderWriter([ExportRoot("home", home)], protected=[home / ".claude"])
    files = [OutputFile(".claude/agents/a.md", b"x"), OutputFile("CLAUDE.md", b"y")]
    with pytest.raises(ExportValidationError) as bad:
        writer.write(files, "home")
    assert bad.value.issues[0].details["file"] == ".claude/agents/a.md"
    upper = [OutputFile(".CLAUDE/agents/a.md", b"x")]  # 대소문자만 다른 경로도 막는다
    with pytest.raises(ExportValidationError):
        writer.write(upper, "home")
    assert writer.write([OutputFile("CLAUDE.md", b"y")], "home")[0].action == "create"
    assert not any((home / ".claude").iterdir())


def test_output_paths_are_checked(tmp_path: Path) -> None:
    svc = service(tmp_path, EchoExporter(files=[OutputFile("../escape.txt", b"x")]))
    with pytest.raises(ExportValidationError) as bad:
        svc.plan(request("a"))
    assert bad.value.issues[0].code == ExportIssueCodes.UNSAFE_PATH
    dup = service(tmp_path, EchoExporter(files=[OutputFile("THING/a.txt", b"x")]))
    with pytest.raises(ExportValidationError):
        dup.plan(request("a"))


def test_plain_secrets_never_leave(tmp_path: Path) -> None:
    leak = EchoExporter(
        files=[
            OutputFile(
                "settings.json",
                json.dumps({"env": {"API_KEY": TOKEN, "REF": "${MY_TOKEN}"}, "n": 1}).encode(),
                "application/json",
            ),
            OutputFile("notes.md", f"run --token {TOKEN} now".encode(), "text/markdown"),
            OutputFile("bin.dat", b"\xff\xfe" + TOKEN.encode()),
        ]
    )
    svc = service(tmp_path, leak)
    archive = svc.archive(request("a"))
    with zipfile.ZipFile(io.BytesIO(archive.data)) as z:
        settings = json.loads(z.read("settings.json"))
        notes = z.read("notes.md").decode()
    assert settings["env"]["API_KEY"] != TOKEN
    assert settings["env"]["REF"] == "${MY_TOKEN}"  # 환경 변수 참조는 그대로
    assert TOKEN not in notes
    redacted = [w for w in archive.plan.warnings if w.code == ExportIssueCodes.SECRET_REDACTED]
    assert sorted(w.details["file"] for w in redacted) == ["notes.md", "settings.json"]
    assert all(TOKEN not in json.dumps(w.model_dump()) for w in archive.plan.warnings)
    custom = service(
        tmp_path,
        EchoExporter(files=[OutputFile("x.md", b"corp_123456")]),
        secret_rules=lambda: SecretRules().with_extra(value_patterns=[r"corp_\d{6}"]),
    )
    assert custom.plan(request("a")).warnings[0].code == ExportIssueCodes.SECRET_REDACTED


def good_factory(options: Mapping[str, Any]) -> EchoExporter:
    return EchoExporter()


def bad_factory(options: Mapping[str, Any]) -> EchoExporter:
    raise RuntimeError("boom")


def test_loading_and_building() -> None:
    registry = new_exporter_factories()
    reports = load_exporter_factories(
        registry,
        entry_points=[
            EntryPoint(
                "claude-dir",
                "agent_console_exports.claude_dir:claude_dir_exporter",
                EXPORTERS_GROUP,
            ),
            EntryPoint("notcallable", "agent_console_exports:EXPORTERS_GROUP", EXPORTERS_GROUP),
        ],
    )
    assert sorted((r.key, r.status) for r in reports) == [
        ("claude-dir", "loaded"),
        ("notcallable", "failed"),
    ]
    registry.register("echo-x", good_factory, source="test")
    registry.register("wrong-id", good_factory, source="test")
    registry.register("broken", bad_factory, source="test")
    built = build_exporters(registry, {"claude-dir": {"mapping": {"agent_kind": "persona"}}})
    assert sorted(built) == ["claude-dir", "echo-x"]  # 실패·id 불일치는 건너뜀
    assert built["claude-dir"].descriptor.kinds[0] == "persona"
    installed = new_exporter_factories()
    load_exporter_factories(installed)
    assert "claude-dir" in build_exporters(installed)


def test_zip_is_deterministic() -> None:
    a = build_zip([OutputFile("b", b"2"), OutputFile("a", b"1")])
    b = build_zip([OutputFile("a", b"1"), OutputFile("b", b"2")])
    assert a == b
    with zipfile.ZipFile(io.BytesIO(a)) as z:
        assert [i.date_time for i in z.infolist()] == [(1980, 1, 1, 0, 0, 0)] * 2


@pytest.mark.skipif(os.name == "nt", reason="POSIX 권한 검사")
def test_root_must_be_a_real_folder(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    writer = FolderWriter(
        [
            ExportRoot("alias", tmp_path / "alias"),
            ExportRoot("rel", Path("relative")),
            ExportRoot("missing", tmp_path / "missing"),
            ExportRoot("ok", real),
        ]
    )
    assert [r.id for r in writer.roots()] == ["ok"]
