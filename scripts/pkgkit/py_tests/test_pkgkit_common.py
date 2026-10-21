from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from pkgkit_common import (
    FROM_PACKAGE,
    PkgkitError,
    classify,
    compatible_range,
    discover,
    expand_members,
    names_for,
    normalize_dist,
    parse_config,
    render,
    requirement_name,
    requirement_specifier,
    resolve_ranges,
    select,
    toml_list_block,
    toml_value,
    workspace_versions,
)
from pkgkit_testkit import add_app, add_package, config, contracts_range, make_workspace


def test_names_strip_folder_prefix() -> None:
    n = names_for("ac-mod-chat", config())
    assert (n.dist_name, n.import_name) == ("agent-console-mod-chat", "agent_console_mod_chat")


@pytest.mark.parametrize("bad", ["Ac-x", "ac_x", "ac-", "-x", "ac-x-"])
def test_names_reject_bad_folder(bad: str) -> None:
    with pytest.raises(PkgkitError):
        names_for(bad, config())


@pytest.mark.parametrize(
    ("req", "name", "spec"),
    [
        ("agent-console-contracts>=0.4,<0.5", "agent-console-contracts", ">=0.4,<0.5"),
        ("Agent_Console.Store", "agent-console-store", ""),
        ("pydantic[email] >=2.9 ; python_version>'3'", "pydantic", ">=2.9"),
    ],
)
def test_requirement_parts(req: str, name: str, spec: str) -> None:
    assert requirement_name(req) == name
    assert requirement_specifier(req) == spec


def test_internal_and_ranges() -> None:
    cfg = config()
    assert cfg.is_internal("Agent_Console_Chat")
    assert not cfg.is_internal("pydantic")
    assert cfg.range_for("agent-console-contracts") == contracts_range()
    assert cfg.range_for("agent-console-chat") == ">=0.1,<0.2"


def test_contracts_range_follows_package_version() -> None:
    """계약 범위는 설정에 고정하지 않고 워크스페이스 계약 패키지 버전에서 만든다(3R.12)."""
    data = tomllib.loads((Path(__file__).parents[1] / "pkgkit_py.toml").read_text(encoding="utf-8"))
    assert data["python"]["internal_ranges"]["agent-console-contracts"] == FROM_PACKAGE
    root = Path(__file__).resolve().parents[3]
    version = workspace_versions(root)["agent-console-contracts"]
    assert contracts_range() == compatible_range(version)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.5.0", ">=0.5,<0.6"),
        ("0.12.3", ">=0.12,<0.13"),
        ("1.2.0", ">=1.2,<2"),
        ("2.0", ">=2.0,<3"),
    ],
)
def test_compatible_range(version: str, expected: str) -> None:
    assert compatible_range(version) == expected


def test_compatible_range_rejects_bad_version() -> None:
    with pytest.raises(PkgkitError, match="버전 형식"):
        compatible_range("dev")


def test_resolve_ranges_and_unresolved() -> None:
    data = tomllib.loads((Path(__file__).parents[1] / "pkgkit_py.toml").read_text(encoding="utf-8"))
    raw = parse_config(data)
    with pytest.raises(PkgkitError, match="from-package"):
        raw.range_for("agent-console-contracts")
    assert raw.range_for("agent-console-chat") == ">=0.1,<0.2"
    unresolved = resolve_ranges(raw, {"agent-console-other": "9.9.9"})
    with pytest.raises(PkgkitError):
        unresolved.range_for("agent-console-contracts")
    resolved = resolve_ranges(raw, {"Agent_Console_Contracts": "0.7.1"})
    assert resolved.range_for("agent-console-contracts") == ">=0.7,<0.8"


def test_workspace_versions(tmp_path: Path) -> None:
    cfg = make_workspace(tmp_path)
    add_package(tmp_path, cfg, "feature", "ac-notes")
    assert workspace_versions(tmp_path) == {"agent-console-notes": cfg.initial_version}
    assert workspace_versions(tmp_path / "missing") == {}


def test_parse_config_requires_default_range() -> None:
    data = tomllib.loads((Path(__file__).parents[1] / "pkgkit_py.toml").read_text(encoding="utf-8"))
    del data["python"]["internal_ranges"]["default"]
    with pytest.raises(PkgkitError, match="default"):
        parse_config(data)
    with pytest.raises(PkgkitError, match="키가 없습니다"):
        parse_config({})


def test_render_placeholders() -> None:
    assert render("a {{ x }} {{y}}", {"x": "1", "y": "2"}) == "a 1 2"
    with pytest.raises(PkgkitError, match="z"):
        render("{{z}}", {})


def test_toml_writer_round_trip() -> None:
    value = {"a": 'q"uo\\te', "b": [1, True, "x"], "c": {"d": "e"}}
    text = "\n".join(f"{k} = {toml_value(v)}" for k, v in value.items())
    assert tomllib.loads(text) == value
    assert tomllib.loads(toml_list_block("k", ["a", "b"])) == {"k": ["a", "b"]}
    assert normalize_dist("A.B_c") == "a-b-c"


def test_classify() -> None:
    cfg = config()
    folders = {"features": "feature"}
    assert classify("packages/py/features/ac-x", cfg, folders) == ("feature", False)
    assert classify("packages/py/ac-x", cfg, folders) == (None, False)
    assert classify("apps/server", cfg, folders) == ("app", True)


def test_discover_and_select(tmp_path: Path) -> None:
    cfg = make_workspace(tmp_path)
    add_package(tmp_path, cfg, "feature", "ac-notes")
    add_package(tmp_path, cfg, "base", "ac-core")
    add_app(tmp_path, "server", "agent_console_server")
    (tmp_path / "packages/py/features/not-a-project").mkdir()
    pkgs = discover(tmp_path, cfg, {})
    assert [(p.rel, p.kind, p.import_name) for p in pkgs] == [
        ("packages/py/base/ac-core", "base", "agent_console_core"),
        ("packages/py/features/ac-notes", "features", "agent_console_notes"),
        ("apps/server", "app", "agent_console_server"),
    ]
    assert [p.dist_name for p in select(pkgs, ["ac-notes", "agent_console_server"])] == [
        "agent-console-notes",
        "agent-console-server",
    ]
    with pytest.raises(PkgkitError, match="찾을 수 없습니다"):
        select(pkgs, ["nope"])


def test_expand_members_exclude(tmp_path: Path) -> None:
    for name in ("a", "b"):
        (tmp_path / "p" / name).mkdir(parents=True)
        (tmp_path / "p" / name / "pyproject.toml").write_text("", encoding="utf-8")
    found = expand_members(tmp_path, ["p/*"], ["p/b"])
    assert [p.name for p in found] == ["a"]
