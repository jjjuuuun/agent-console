"""대조 검사(extpoints-check) 테스트: 임시 저장소로 규칙 하나씩."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import build_notes, notes_tool
from extdocs import main
from extdocs_common import TOOL_DIR, Finding, SymbolResolver, collect, member_src_paths
from extdocs_points import check_points
from extdocs_testkit import REPO_ROOT, Repo, tool_data


def run(repo: Repo, **overrides: object) -> list[Finding]:
    data = tool_data(**overrides)
    col = collect(repo.root, data)
    resolver = SymbolResolver(member_src_paths(col.members))
    findings, _ = check_points(repo.root, col, data, resolver, tool_dir=TOOL_DIR)
    return findings


def errors(findings: list[Finding], allowed: tuple[str, ...] = ()) -> list[str]:
    return sorted(f.code for f in findings if f.is_error(allowed))


def test_complete_repo_passes(repo: Repo) -> None:
    assert errors(run(repo)) == []


def test_undeclared_group_constant_fails(repo: Repo) -> None:
    m = repo.mod("notes")
    repo.write(
        f"packages/py/features/ac-notes/src/{m}/extra.py",
        'TAG_SOURCES_GROUP: str = "agent_console.tag_sources"\nOTHER = "agent_console.x"\n',
    )
    found = run(repo)
    assert errors(found) == ["group-undeclared"]
    assert any("agent_console.tag_sources" in f.where for f in found)


def test_entry_point_group_without_declaration_fails(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    build_notes(repo)
    repo.package(
        "ac-other",
        "agent-console-other",
        entry_points='[project.entry-points."agent_console.config_schemas"]\nx = "a:b"\n',
    )
    found = run(repo)
    assert errors(found) == ["group-undeclared"]
    assert found[0].where == "agent_console.config_schemas" or any(
        f.where == "agent_console.config_schemas" for f in found
    )


def test_internal_group_with_reason_passes(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    build_notes(repo)
    repo.package(
        "ac-other",
        "agent-console-other",
        entry_points='[project.entry-points."agent_console.config_schemas"]\nx = "a:b"\n',
        tool=(
            "[tool.agent-console]\n"
            'internal-groups = [{ group = "agent_console.config_schemas", reason = "r" }]\n'
        ),
    )
    assert errors(run(repo)) == []


def test_internal_port_without_reason_fails(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    tool = notes_tool(repo).replace(', reason = "노트 모듈 안에서만 쓴다"', "")
    build_notes(repo, tool=tool)
    found = run(repo)
    assert "schema-invalid" in errors(found)


def test_undeclared_port_fails(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    tool = notes_tool(repo).replace(
        'internal-ports = [{ port = "notes.store", reason = "노트 모듈 안에서만 쓴다" }]', ""
    )
    build_notes(repo, tool=tool)
    found = run(repo)
    assert errors(found) == ["port-undeclared"]
    assert errors(found, ("declarations",)) == []


def test_missing_symbol_fails(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    tool = notes_tool(repo).replace(':NoteKind"]', ':NoSuchThing"]')
    build_notes(repo, tool=tool)
    assert errors(run(repo)) == ["symbol-unresolved"]


def test_example_points_mismatch_fails(repo: Repo) -> None:
    repo.example("example-notes", ["note-hooks"])  # 선언은 note-kind가 이 예제를 가리킨다
    found = errors(run(repo))
    assert found.count("example-points-mismatch") == 2


def test_example_points_undeclared_is_missing_declaration(repo: Repo) -> None:
    repo.example("example-other", ["not-declared"])
    found = run(repo)
    assert errors(found) == ["example-point-undeclared"]
    assert errors(found, ("declarations",)) == []


def test_readme_section_missing_fails(repo: Repo) -> None:
    repo.example("example-notes", ["note-kind"], readme="# 예제\n\n## 최소 코드\n\n## 설치·제거\n")
    found = run(repo)
    assert errors(found) == ["readme-section-missing"]
    message = next(f.message for f in found if f.code == "readme-section-missing")
    assert "등록" in message
    assert "테스트" in message


def test_readme_section_alias_contains(repo: Repo) -> None:
    readme = (
        "# 예제\n\n## 새 노드 만들기 — 최소 코드\n\n## 등록과 설정\n\n## 설치·제거\n\n## 테스트\n"
    )
    repo.example("example-notes", ["note-kind"], readme=readme)
    assert errors(run(repo)) == []


def test_example_missing_is_staged(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    tool = notes_tool(repo).replace('example = { kind = "snippet" }\n', "")
    build_notes(repo, tool=tool)
    found = run(repo)
    assert errors(found) == ["example-missing"]
    assert errors(found, ("examples",)) == []


def test_example_path_missing_fails(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    tool = notes_tool(repo).replace(
        'example = { kind = "snippet" }', 'example = { kind = "reference", path = "packages/nope" }'
    )
    build_notes(repo, tool=tool)
    assert errors(run(repo)) == ["example-path-missing"]


def test_unknown_area_and_duplicate_slug_fail(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    build_notes(
        repo,
        tool=notes_tool(repo).replace(
            'area = "memory"\nsummary = "노트 종류', 'area = "nope"\nsummary = "노트 종류'
        ),
    )
    repo.package(
        "ac-dup",
        "agent-console-dup",
        tool=(
            "[tool.agent-console.extension-points.note-hooks]\n"
            'title = "t"\narea = "memory"\nsummary = "s"\nregistration = { kind = "injection" }\n'
            'example = { kind = "snippet" }\n'
        ),
    )
    found = errors(run(repo))
    assert "area-unknown" in found
    assert "slug-duplicate" in found


def test_bad_slug_and_unknown_field_fail(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    build_notes(repo)
    repo.package(
        "ac-bad",
        "agent-console-bad",
        tool=(
            "[tool.agent-console.extension-points.Bad_Slug]\n"
            'title = "t"\narea = "memory"\nsummary = "s"\nregistration = { kind = "injection" }\n'
            'tyop = "x"\n'
        ),
    )
    found = run(repo)
    assert errors(found) == ["schema-invalid"]


def test_non_member_package_ignored(repo: Repo) -> None:
    """루트 [tool.uv.sources]에 없는 배포(설치해 둔 예제·바깥 플러그인)는 대상이 아니다."""
    repo.package(
        "ac-outside",
        "agent-console-outside",
        files={"outside_pkg/__init__.py": 'X_GROUP = "agent_console.outside"\n'},
        entry_points='[project.entry-points."agent_console.outside"]\nx = "a:b"\n',
        member=False,
    )
    assert errors(run(repo)) == []


def test_open_registration_kind_accepted(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    build_notes(repo)
    repo.package(
        "ac-open",
        "agent-console-open",
        tool=(
            "[tool.agent-console.extension-points.custom-thing]\n"
            'title = "t"\narea = "web"\nsummary = "s"\n'
            'registration = { kind = "my-new-kind", whatever = 1 }\n'
            'example = { kind = "snippet" }\n'
        ),
    )
    assert errors(run(repo)) == []


def test_ts_declarations_are_collected(repo: Repo) -> None:
    repo.write(
        "packages/ts/lib/demo/package.json",
        '{"name": "@x/demo", "agentConsole": {"kind": "lib", "extensionPoints": {"demo-widget": '
        '{"title": "t", "area": "web", "summary": "s", "registration": {"kind": "props", '
        '"export": "@x/demo#Widgets"}, "interface": ["@x/demo#Widget"], '
        '"example": {"kind": "snippet"}}}}}',
    )
    data = tool_data()
    col = collect(repo.root, data)
    assert [d.slug for d in col.declarations if d.language == "ts"] == ["demo-widget"]
    assert errors(run(repo)) == []


def test_cli_allow_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = Repo(tmp_path)
    build_notes(repo, tool="")
    repo.example("example-notes", None)
    root = str(repo.root)
    # 계약 표 기호는 임시 저장소에 없어도 대조에는 쓰지 않는다.
    assert main(["--root", root, "points"]) == 1
    assert main(["--root", root, "--quiet", "points", "--allow-missing"]) == 0
    out = capsys.readouterr().out
    assert "group-undeclared" in out
    assert "port-undeclared" in out
    assert main(["--root", root, "points", "--allow-missing", "examples"]) == 1
    assert main(["--root", root, "points", "--allow-missing", "nope"]) == 2


def test_empty_workspace_passes(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path), "points"]) == 0


def test_real_repo_descriptor_scan_is_fast() -> None:
    """저장소 실제 서버 모듈 서술자 대조가 상한(10초) 안에 끝난다."""
    data = tool_data()
    col = collect(REPO_ROOT, data)
    if not col.members:
        pytest.skip("저장소 루트가 아님")
    resolver = SymbolResolver(member_src_paths(col.members))
    findings, facts = check_points(REPO_ROOT, col, data, resolver, tool_dir=TOOL_DIR)
    assert facts.modules.modules, "서버 모듈을 하나도 읽지 못했다"
    assert facts.modules.seconds <= float(data.s("descriptor_time_limit_seconds"))
    assert not [f for f in findings if f.code in ("descriptor-load-failed", "descriptor-slow")]
