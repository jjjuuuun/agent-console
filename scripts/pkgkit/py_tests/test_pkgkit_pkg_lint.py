"""pkg-lint 규칙마다 가짜 패키지 폴더로 통과·위반을 확인한다."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from pkg_lint import (
    PACKAGE_RULES,
    REPO_RULES,
    Violation,
    build_context,
    count_doctests,
    enabled_rules,
    find_root_lookups,
    lint,
    main,
    readme_section,
)
from pkgkit_common import Config, PkgkitError
from pkgkit_testkit import (
    ROOT_PYPROJECT,
    add_app,
    add_package,
    config,
    contracts_range,
    make_workspace,
)

ALL_PACKAGE_RULES = list(PACKAGE_RULES)


def run(root: Path, cfg: Config, rules: list[str], package: str | None = None) -> list[Violation]:
    ctx = build_context(root, cfg)
    targets = [p for p in ctx.packages if not p.is_app]
    if package:
        targets = [p for p in targets if p.path.name == package]
    return lint(ctx, targets, rules)


def rules_hit(violations: list[Violation]) -> set[str]:
    return {v.rule for v in violations}


@pytest.fixture
def ws(tmp_path: Path) -> tuple[Path, Config]:
    cfg = make_workspace(tmp_path)
    add_package(tmp_path, cfg, "feature", "ac-notes")
    add_package(tmp_path, cfg, "base", "ac-core")
    add_app(tmp_path, "server", "agent_console_server")
    return tmp_path, cfg


def pkg(root: Path, name: str = "ac-notes") -> Path:
    return next(root.glob(f"packages/py/*/{name}"))


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new), encoding="utf-8")


@pytest.mark.parametrize("kind", ["base", "feature", "kit", "module", "link"])
def test_template_package_passes_every_package_rule(tmp_path: Path, kind: str) -> None:
    cfg = make_workspace(tmp_path)
    folder = {"module": "ac-mod-x", "link": "ac-link-x-y"}.get(kind, "ac-x")
    add_package(tmp_path, cfg, kind, folder)
    assert run(tmp_path, cfg, [*ALL_PACKAGE_RULES, "template-root-drift"]) == []


def test_layout(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    pkg(root).rename(root / "packages/py/ac-notes")
    root.joinpath("pyproject.toml").write_text(
        ROOT_PYPROJECT.replace('"packages/py/*/*"', '"packages/py/*/*", "packages/py/*"'),
        encoding="utf-8",
    )
    hits = run(root, cfg, ["layout"])
    assert [v.package for v in hits] == ["packages/py/ac-notes"]


def test_workspace_source(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    with (pkg(root) / "pyproject.toml").open("a", encoding="utf-8") as fh:
        fh.write("\n[tool.uv.sources]\nagent-console-contracts = { workspace = true }\n")
    hits = run(root, cfg, ["workspace-source"])
    assert len(hits) == 1
    assert "agent-console-contracts" in hits[0].message


def test_outside_path(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    edit(
        pkg(root) / "pyproject.toml",
        'files = ["src", "tests"]',
        'files = ["src", "tests", "../../x/src"]',
    )
    edit(
        pkg(root, "ac-core") / "pyproject.toml",
        'files = ["src", "tests"]',
        'files = ["src", "./tests/../src"]',
    )
    hits = run(root, cfg, ["outside-path"])
    assert [(v.package, v.rule) for v in hits] == [
        ("packages/py/features/ac-notes", "outside-path")
    ]


def test_find_root_lookups_levels() -> None:
    code = """
from pathlib import Path
A = Path(__file__).parent                      # 0
B = Path(__file__).resolve().parents[1]        # 1 (패키지 뿌리)
C = Path(__file__).resolve().parents[4]        # 4
D = Path(__file__).parent.parent.parent        # 2
E = some.parents[9]                            # 모름
"""
    hits = find_root_lookups(ast.parse(code), depth=1)
    assert [(line, up) for line, up in hits] == [(5, 4), (6, 2)]


def test_root_lookup(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    tests = pkg(root) / "tests"
    (tests / "test_ok.py").write_text(
        "from pathlib import Path\nDATA = Path(__file__).parent / 'data'\n"
        "SRC = Path(__file__).resolve().parents[1] / 'src'\n",
        encoding="utf-8",
    )
    assert run(root, cfg, ["root-lookup"]) == []
    (tests / "test_bad.py").write_text(
        "from pathlib import Path\nREPO = Path(__file__).resolve().parents[4]\n", encoding="utf-8"
    )
    hits = run(root, cfg, ["root-lookup"])
    assert [(v.path, v.line) for v in hits] == [("tests/test_bad.py", 2)]


def test_foreign_tests_import(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    (pkg(root, "ac-core") / "tests" / "agent_console_core_testkit.py").write_text(
        "X = 1\n", encoding="utf-8"
    )
    own = pkg(root, "ac-core") / "tests" / "test_own.py"
    own.write_text("from agent_console_core_testkit import X\n", encoding="utf-8")
    assert run(root, cfg, ["foreign-tests-import"]) == []
    bad = pkg(root) / "tests" / "test_uses_other.py"
    bad.write_text(
        "from agent_console_core_testkit import X\nimport agent_console_core.tests.helpers\n",
        encoding="utf-8",
    )
    hits = run(root, cfg, ["foreign-tests-import"])
    assert [(v.package, v.line) for v in hits] == [
        ("packages/py/features/ac-notes", 1),
        ("packages/py/features/ac-notes", 2),
    ]


def test_required_files(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    (pkg(root) / "CHANGELOG.md").unlink()
    (pkg(root) / "src/agent_console_notes/py.typed").unlink()
    hits = run(root, cfg, ["required-files"])
    assert sorted(v.path for v in hits) == ["CHANGELOG.md", "src/agent_console_notes/py.typed"]


def test_required_files_module_entry(tmp_path: Path) -> None:
    cfg = make_workspace(tmp_path)
    path = add_package(tmp_path, cfg, "module", "ac-mod-x")
    (path / "src/agent_console_mod_x/__main__.py").unlink()
    hits = run(tmp_path, cfg, ["required-files"])
    assert [v.path for v in hits] == ["src/agent_console_mod_x/__main__.py"]


def test_tool_config(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    path = pkg(root) / "pyproject.toml"
    edit(path, "strict = true", "strict = false\nextra_key = 1")
    edit(path, '    "mypy>=1.11",\n', "")
    edit(path, 'asyncio_mode = "auto"', 'asyncio_mode = "auto"\nmarkers = ["slow"]')
    msgs = [v.message for v in run(root, cfg, ["tool-config"])]
    assert any("tool.mypy.strict" in m for m in msgs)
    assert any("tool.mypy.extra_key" in m for m in msgs)
    assert any("mypy>=1.11" in m for m in msgs)
    assert not any("markers" in m for m in msgs), "pytest 표는 superset 허용"
    edit(pkg(root, "ac-core") / "pyproject.toml", "[tool.ruff.lint.isort]", "[tool.ruff.lint.x]")
    msgs = [v.message for v in run(root, cfg, ["tool-config"], package="ac-core")]
    assert any("isort" in m for m in msgs)


def test_internal_dep_range(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    edit(
        pkg(root) / "pyproject.toml",
        f'"agent-console-contracts{contracts_range()}"',
        '"agent-console-contracts"',
    )
    edit(pkg(root) / "pyproject.toml", '"ruff>=0.6",', '"ruff>=0.6",\n    "agent-console-core",')
    hits = run(root, cfg, ["internal-dep-range"])
    assert sorted(v.message.split()[2] for v in hits) == [
        "agent-console-contracts에",
        "agent-console-core에",
    ]


def test_readme_doctest(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    assert run(root, cfg, ["readme-doctest"]) == []
    (pkg(root) / "README.md").write_text("# x\n", encoding="utf-8")
    assert [v.package for v in run(root, cfg, ["readme-doctest"])] == [
        "packages/py/features/ac-notes"
    ]
    assert count_doctests("  >>> 1\n>>>2\n... x\n") == 1


def test_readme_doctest_counts_only_minimal_usage_section(ws: tuple[Path, Config]) -> None:
    """4R.18: "최소 사용" 절 밖의 >>>는 세지 않는다. 절이 없으면 그 사실을 알린다."""
    root, cfg = ws
    readme = pkg(root) / "README.md"
    readme.write_text(
        "# x\n\n## 최소 사용\n\n설명뿐\n\n## 공개 API\n\n```python\n>>> 1\n1\n```\n",
        encoding="utf-8",
    )
    [hit] = run(root, cfg, ["readme-doctest"])
    assert '"최소 사용" 절에 doctest' in hit.message
    readme.write_text("# x\n\n```python\n>>> 1\n1\n```\n", encoding="utf-8")
    [hit] = run(root, cfg, ["readme-doctest"])
    assert '"최소 사용" 절이 없습니다' in hit.message
    readme.write_text(
        "# x\n\n## 최소 사용\n\n### 하위 절\n\n"
        "```python\n# 코드 안 주석은 제목이 아니다\n>>> 1\n1\n```\n",
        encoding="utf-8",
    )
    assert run(root, cfg, ["readme-doctest"]) == []


def test_readme_section_boundaries() -> None:
    text = "# t\n## 최소 사용(단독)\na\n### 깊이\nb\n```\n# 아님\n```\n## 다음\nc\n"
    section = readme_section(text, "최소 사용")
    assert section is not None
    assert "a" in section
    assert "b" in section
    assert "# 아님" in section
    assert "c" not in section
    assert readme_section(text, "없음") is None


def test_template_root_drift(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    assert run(root, cfg, ["template-root-drift"]) == []
    root.joinpath("pyproject.toml").write_text(
        ROOT_PYPROJECT.replace("line-length = 100", "line-length = 120"), encoding="utf-8"
    )
    hits = run(root, cfg, ["template-root-drift"])
    assert len(hits) == 1
    assert "line-length" in hits[0].message


def test_root_source(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    msgs = sorted(v.message for v in run(root, cfg, ["root-source"]))
    assert len(msgs) == 3  # ac-core, ac-notes, 앱 server
    assert all("workspace = true }가 없습니다" in m for m in msgs)
    with (root / "pyproject.toml").open("a", encoding="utf-8") as fh:
        fh.write(
            "\n[tool.uv.sources]\n"
            "agent-console-core = { workspace = true }\n"
            "agent-console-notes = { workspace = true }\n"
            "agent-console-server = { workspace = true }\n"
            "agent-console-gone = { workspace = true }\n"
            'other = { path = "../other" }\n'
        )
    msgs = [v.message for v in run(root, cfg, ["root-source"])]
    assert msgs == ["[tool.uv.sources] agent-console-gone: 워크스페이스에 없는 사내 패키지입니다"]


def test_importlinter_drift(ws: tuple[Path, Config]) -> None:
    root, cfg = ws
    hits = run(root, cfg, ["importlinter-drift"])
    assert len(hits) == 1
    assert "--init" in hits[0].message
    (root / cfg.importlinter_rules).write_text('root_packages = ["@all"]\n', encoding="utf-8")
    hits = run(root, cfg, ["importlinter-drift"])
    assert hits
    assert "[tool.importlinter]가 없습니다" in hits[0].message
    with (root / "pyproject.toml").open("a", encoding="utf-8") as fh:
        fh.write(
            '\n[tool.importlinter]\nroot_packages = ["agent_console_core", '
            '"agent_console_notes", "agent_console_server"]\n'
        )
    assert run(root, cfg, ["importlinter-drift"]) == []
    add_package(root, cfg, "kit", "ac-modkit")
    msgs = [v.message for v in run(root, cfg, ["importlinter-drift"])]
    assert msgs == ["root_packages에 빠짐: agent_console_modkit"]


def test_enabled_rules_from_config() -> None:
    cfg = config()
    rules = enabled_rules(cfg)
    assert "readme-doctest" in rules  # 3R.6에서 켰다
    assert "layout" in rules
    assert set(rules) == set(PACKAGE_RULES) | set(REPO_RULES)
    assert enabled_rules(cfg, ["readme-doctest"]) == ["readme-doctest"]
    with pytest.raises(PkgkitError):
        enabled_rules(cfg, ["nope"])


def test_main_exit_codes_and_json(
    ws: tuple[Path, Config], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, cfg = ws
    import pkg_lint

    monkeypatch.setattr(pkg_lint, "load_config", lambda _path=None: cfg)
    assert main(["--root", str(root), "--package", "ac-notes"]) == 0
    (pkg(root) / "LICENSE").unlink()
    capsys.readouterr()
    assert main(["--root", str(root), "--package", "ac-notes", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert [d["rule"] for d in data] == ["required-files"]
    assert main(["--root", str(root), "--rule", "nope"]) == 2
