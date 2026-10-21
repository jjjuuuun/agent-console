from __future__ import annotations

import tomllib
from pathlib import Path

import importlinter_sync as il
import pytest
from pkgkit_common import PkgkitError, PyPackage, get_path
from pkgkit_testkit import add_app, add_package, make_workspace

GROUPS = {
    "all": ["a_base", "a_feat1", "a_feat2", "a_mod1", "a_mod2", "a_app"],
    "packages": ["a_base", "a_feat1", "a_feat2", "a_mod1", "a_mod2"],
    "app": ["a_app"],
    "base": ["a_base"],
    "feature": ["a_feat1", "a_feat2"],
    "module": ["a_mod1", "a_mod2"],
    "link": [],
}


def _pkg(name: str, kind: str | None, is_app: bool = False) -> PyPackage:
    return PyPackage(Path(name), name, name, name, kind, is_app, {})


def test_builtin_groups() -> None:
    groups = il.builtin_groups(
        [_pkg("b", "feature"), _pkg("a", "feature"), _pkg("s", "app", True), _pkg("old", None)],
        ["feature", "link"],
    )
    assert groups == {
        "all": ["a", "b", "old", "s"],
        "packages": ["a", "b", "old"],
        "app": ["s"],
        "feature": ["a", "b"],
        "link": [],
    }


def test_expand_groups_and_removal() -> None:
    user = {"libs": ["@feature", "!a_feat2"], "loop": ["@loop"]}
    assert il.expand(["@packages", "!@module", "x", "a_base"], GROUPS, user) == [
        "a_base",
        "a_feat1",
        "a_feat2",
        "x",
    ]
    assert il.expand(["@libs", "@base"], GROUPS, user) == ["a_feat1", "a_base"]
    with pytest.raises(PkgkitError, match="모르는 그룹"):
        il.expand(["@nope"], GROUPS, user)
    with pytest.raises(PkgkitError, match="순환"):
        il.expand(["@loop"], GROUPS, user)


def test_expand_group_suffix() -> None:
    assert il.expand(["@module.ports", "a_base.x"], GROUPS, {}) == [
        "a_mod1.ports",
        "a_mod2.ports",
        "a_base.x",
    ]
    assert il.expand(["@module", "!@module.ports"], GROUPS, {}) == ["a_mod1", "a_mod2"]


def test_expand_import_expressions_product() -> None:
    out = il.expand_imports(["** -> @module.ports", "@feature -> a_base", "x -> y"], GROUPS, {})
    assert out == [
        "** -> a_mod1.ports",
        "** -> a_mod2.ports",
        "a_feat1 -> a_base",
        "a_feat2 -> a_base",
        "x -> y",
    ]
    with pytest.raises(PkgkitError, match="->"):
        il.expand_imports(["no arrow"], GROUPS, {})


def test_build_table_expands_ignore_imports() -> None:
    rules = {
        "contracts": [
            {
                "name": "연동은 포트만",
                "type": "forbidden",
                "source_modules": ["@feature"],
                "forbidden_modules": ["@module"],
                "ignore_imports": ["** -> @module.ports"],
            }
        ]
    }
    [c] = il.build_table(rules, GROUPS).table["contracts"]
    assert c["ignore_imports"] == ["** -> a_mod1.ports", "** -> a_mod2.ports"]


def test_build_table_drops_self_and_skips_empty() -> None:
    rules = {
        "options": {"include_external_packages": True},
        "contracts": [
            {
                "name": "기능은 서로를 모른다",
                "type": "forbidden",
                "source_modules": ["a_feat1"],
                "forbidden_modules": ["@feature", "fastapi"],
                "allow_indirect_imports": True,
            },
            {"name": "모듈 독립", "type": "independence", "modules": ["@module"]},
            {"name": "연동 독립", "type": "independence", "modules": ["@link"]},
            {"name": "층", "type": "layers", "layers": ["@feature", "a_base"], "containers": ["x"]},
        ],
    }
    result = il.build_table(rules, GROUPS)
    t = result.table
    assert t["root_packages"] == GROUPS["all"]
    assert t["include_external_packages"] is True
    c0 = t["contracts"][0]
    assert c0["forbidden_modules"] == ["a_feat2", "fastapi"]
    assert c0["allow_indirect_imports"] is True
    assert [c["name"] for c in t["contracts"]] == ["기능은 서로를 모른다", "모듈 독립", "층"]
    assert t["contracts"][2]["layers"] == ["@feature", "a_base"], "expand_keys 밖은 그대로"
    assert result.skipped == ["연동 독립"]


def test_build_table_rejects_bad_rules() -> None:
    with pytest.raises(PkgkitError, match="겹칩니다"):
        il.build_table({"groups": {"all": []}}, GROUPS)
    with pytest.raises(PkgkitError, match="name·type"):
        il.build_table({"contracts": [{"name": "x"}]}, GROUPS)


def test_render_round_trip() -> None:
    result = il.build_table(
        {"contracts": [{"name": 'q"x', "type": "independence", "modules": ["@feature"]}]}, GROUPS
    )
    text = il.render_table(result.table, "rules.toml")
    assert text.startswith(il.BEGIN_MARK)
    assert text.rstrip().endswith(il.END_MARK)
    assert get_path(tomllib.loads(text), "tool.importlinter") == result.table


BEFORE = """\
[project]
name = "x"

# ---- import-linter
[tool.importlinter]
root_packages = ["a"]

[[tool.importlinter.contracts]]
name = "c"
type = "independence"
modules = ["a", "b"]

# ---- 다음 표
[tool.other]
k = 1
"""


def test_replace_region_without_markers_keeps_neighbours() -> None:
    block = '[tool.importlinter]\nroot_packages = ["z"]\n'
    out = il.replace_region(BEFORE, il.BEGIN_MARK + "\n" + block + il.END_MARK + "\n")
    data = tomllib.loads(out)
    assert data["tool"]["importlinter"] == {"root_packages": ["z"]}
    assert data["tool"]["other"] == {"k": 1}
    assert "# ---- import-linter" in out
    assert "# ---- 다음 표" in out
    again = il.replace_region(
        out, il.BEGIN_MARK + "\n[tool.importlinter]\nroot_packages = []\n" + il.END_MARK + "\n"
    )
    assert tomllib.loads(again)["tool"]["importlinter"] == {"root_packages": []}
    assert again.count(il.BEGIN_MARK) == 1


def test_replace_region_appends_when_absent() -> None:
    out = il.replace_region('[project]\nname = "x"', "[tool.importlinter]\nroot_packages = []\n")
    assert tomllib.loads(out)["tool"]["importlinter"] == {"root_packages": []}


def test_find_region_broken_markers() -> None:
    with pytest.raises(PkgkitError, match="끝 표식"):
        il.find_region(il.BEGIN_MARK + "\n[tool.importlinter]\n")


def test_diff_tables() -> None:
    exp = {
        "root_packages": ["a", "b"],
        "contracts": [{"name": "c", "type": "independence", "modules": ["a", "b"]}],
    }
    assert il.diff_tables(exp, exp) == []
    assert il.diff_tables(exp, {"root_packages": ["b", "a"], "contracts": exp["contracts"]}) == []
    got = il.diff_tables(
        exp,
        {
            "root_packages": ["a", "zz"],
            "x": 1,
            "contracts": [
                {"name": "c", "type": "forbidden", "modules": ["a"]},
                {"name": "old", "type": "independence", "modules": []},
            ],
        },
    )
    assert "root_packages에 빠짐: b" in got
    assert "root_packages에 남는 것: zz" in got
    assert any(g.startswith("옵션 x") for g in got)
    assert "규칙에 없는 계약: old" in got
    assert any("'c'.modules" in g and "['b']" in g for g in got)
    assert any("'c'.type" in g for g in got)
    assert il.diff_tables(exp, None) == ["대상에 [tool.importlinter]가 없습니다"]


def test_init_then_sync_is_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = make_workspace(tmp_path)
    add_package(tmp_path, cfg, "feature", "ac-notes")
    add_package(tmp_path, cfg, "base", "ac-core")
    add_app(tmp_path, "server", "agent_console_server")
    with (tmp_path / "pyproject.toml").open("a", encoding="utf-8") as fh:
        fh.write(
            "\n[tool.importlinter]\n"
            'root_packages = ["agent_console_server", "agent_console_core",'
            ' "agent_console_notes"]\n\n'
            "[[tool.importlinter.contracts]]\n"
            'name = "패키지는 앱을 모른다"\ntype = "forbidden"\n'
            'source_modules = ["agent_console_core", "agent_console_notes"]\n'
            'forbidden_modules = ["agent_console_server"]\n'
        )
    monkeypatch.setattr(il, "load_config", lambda _p=None: cfg)
    assert il.main(["--root", str(tmp_path), "--init"]) == 0
    rules = (tmp_path / cfg.importlinter_rules).read_text(encoding="utf-8")
    assert 'root_packages = ["@all"]' in rules
    assert il.main(["--root", str(tmp_path), "--init"]) == 2, "덮어쓰기는 --force"
    assert il.main(["--root", str(tmp_path), "--check"]) == 0
    # 규칙을 그룹으로 바꾸고 새 패키지를 더하면 드리프트 → 쓰기 → 다시 통과
    (tmp_path / cfg.importlinter_rules).write_text(
        rules.replace(
            'source_modules = ["agent_console_core", "agent_console_notes"]',
            'source_modules = ["@packages"]',
        ).replace('forbidden_modules = ["agent_console_server"]', 'forbidden_modules = ["@app"]'),
        encoding="utf-8",
    )
    add_package(tmp_path, cfg, "feature", "ac-extra")
    assert il.main(["--root", str(tmp_path), "--check"]) == 1
    assert il.main(["--root", str(tmp_path)]) == 0
    assert il.main(["--root", str(tmp_path), "--check"]) == 0
    data = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    contract = data["tool"]["importlinter"]["contracts"][0]
    assert "agent_console_extra" in contract["source_modules"]
    assert data["project"]["name"] == "ws"
