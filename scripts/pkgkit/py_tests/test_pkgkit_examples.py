"""예제 자동 찾기(``poe examples``)와 ``portability``의 예제 대상 시험."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import examples_check as ex
import portability as pt
import pytest
from pkgkit_common import (
    EXAMPLE_KIND,
    Config,
    PkgkitError,
    discover,
    discover_examples,
    example_folders,
    parse_config,
    read_toml,
)
from pkgkit_testkit import PKGKIT_DIR, REPO_ROOT, add_package, make_workspace
from pkgkit_testkit import kinds as kinds_of


def _example(root: Path, name: str, *, pyproject: bool = True) -> Path:
    path = root / "examples" / "extensions" / name
    (path / "src" / name.replace("-", "_")).mkdir(parents=True)
    (path / "src" / name.replace("-", "_") / "__init__.py").write_text("", encoding="utf-8")
    if pyproject:
        (path / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
            'dependencies = ["agent-console-contracts>=0.1"]\n',
            encoding="utf-8",
        )
    return path


def _repo(tmp_path: Path) -> tuple[Path, Config]:
    """임시 워크스페이스(패키지 ``ac-x``) + 예제 설정(기본 전체 실행에는 예제를 넣지 않음)."""
    root = tmp_path / "repo"
    cfg = make_workspace(root)
    add_package(root, cfg, "base", "ac-x")
    cfg = dataclasses.replace(
        cfg,
        example_roots=("examples/extensions/*",),
        example_steps=(("mypy",), ("pytest", "-q")),
        portability_examples=False,
    )
    return root, cfg


def test_repo_config_finds_every_example_folder() -> None:
    """저장소 설정 glob이 실제 예제 폴더를 빠짐없이 찾는다(손 목록 없음, 8R 검토 F-4)."""
    cfg = parse_config(read_toml(PKGKIT_DIR / "pkgkit_py.toml"))
    on_disk = sorted(
        p.name
        for p in (REPO_ROOT / "examples" / "extensions").iterdir()
        if (p / "pyproject.toml").is_file()
    )
    found = [p.path.name for p in discover_examples(REPO_ROOT, cfg)]
    assert found == on_disk
    assert len(found) >= 1
    assert example_folders(REPO_ROOT, cfg)[1] == [], "pyproject 없는 예제 폴더가 있다"
    assert cfg.example_steps, "예제 단계가 비었다"
    assert cfg.portability_examples, "TS portability처럼 기본 전체 실행에 예제를 넣는다"


def test_parse_config_examples_table() -> None:
    data = read_toml(PKGKIT_DIR / "pkgkit_py.toml")
    data["examples"] = {"roots": ["ex/*"], "steps": [["a", "b"]], "portability_default": True}
    cfg = parse_config(data)
    assert cfg.example_roots == ("ex/*",)
    assert cfg.example_steps == (("a", "b"),)
    assert cfg.portability_examples is True
    data["examples"] = {"steps": ["mypy"]}
    with pytest.raises(PkgkitError, match=r"examples\.steps"):
        parse_config(data)
    del data["examples"]
    empty = parse_config(data)
    assert (empty.example_roots, empty.example_steps, empty.portability_examples) == ((), (), False)


def test_discover_examples_new_folder_is_picked_up(tmp_path: Path) -> None:
    root, cfg = _repo(tmp_path)
    _example(root, "agent-console-example-b")
    _example(root, "agent-console-example-a")
    _example(root, "half-made", pyproject=False)
    (root / "examples" / "extensions" / "README.md").write_text("x", encoding="utf-8")
    (root / "examples" / "extensions" / ".hidden").mkdir()
    found = discover_examples(root, cfg)
    assert [p.path.name for p in found] == ["agent-console-example-a", "agent-console-example-b"]
    assert all(p.kind == EXAMPLE_KIND and not p.is_app for p in found)
    assert found[0].rel == "examples/extensions/agent-console-example-a"
    assert found[0].import_name == "agent_console_example_a"
    assert [p.name for p in example_folders(root, cfg)[1]] == ["half-made"]
    assert all(p.kind != EXAMPLE_KIND for p in discover(root, cfg, kinds_of())), (
        "워크스페이스 찾기에는 섞이지 않는다"
    )


def test_plan_examples_and_step_names(tmp_path: Path) -> None:
    root, cfg = _repo(tmp_path)
    a = _example(root, "agent-console-example-a")
    [(pkg, steps)] = ex.plan_examples(discover_examples(root, cfg), cfg.example_steps)
    assert pkg.path == a.resolve()
    assert [(s.name, s.argv, s.cwd) for s in steps] == [
        ("mypy", ("mypy",), a.resolve()),
        ("pytest", ("pytest", "-q"), a.resolve()),
    ]
    assert ex.step_names([["mypy"], ["mypy", "--strict"], ["mypy"]]) == ["mypy", "mypy#2", "mypy#3"]


def _main(
    root: Path, cfg: Config, monkeypatch: pytest.MonkeyPatch, *args: str
) -> tuple[int, list[tuple[str, str]]]:
    calls: list[tuple[str, str]] = []

    def runner(step: pt.Step) -> pt.StepResult:
        calls.append((step.cwd.name, step.name))
        ok = not (step.cwd.name.endswith("-b") and step.name == "mypy")
        return pt.StepResult(step.name, ok, 0 if ok else 1)

    monkeypatch.setattr(ex, "load_config", lambda _p=None: cfg)
    return ex.main(["--root", str(root), *args], runner=runner), calls


def test_main_runs_all_and_reports_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, cfg = _repo(tmp_path)
    _example(root, "agent-console-example-a")
    _example(root, "agent-console-example-b")
    code, calls = _main(root, cfg, monkeypatch)
    assert code == 1
    assert calls == [
        ("agent-console-example-a", "mypy"),
        ("agent-console-example-a", "pytest"),
        ("agent-console-example-b", "mypy"),
        ("agent-console-example-b", "pytest"),
    ], "실패해도 나머지를 계속 돌린다"
    table = capsys.readouterr().out.splitlines()[-2:]
    assert table[0].split() == ["examples/extensions/agent-console-example-a", "ok", "ok", "PASS"]
    assert table[1].split()[-1] == "FAIL"
    code, calls = _main(root, cfg, monkeypatch, "--package", "agent-console-example-a")
    assert (code, len(calls)) == (0, 2)


def test_main_flags_folder_without_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, cfg = _repo(tmp_path)
    _example(root, "agent-console-example-a")
    _example(root, "half-made", pyproject=False)
    code, calls = _main(root, cfg, monkeypatch)
    assert code == 1
    assert len(calls) == 2, "있는 예제는 그대로 돈다"
    assert "examples/extensions/half-made" in capsys.readouterr().err
    code, _ = _main(root, cfg, monkeypatch, "--list")
    assert code == 1
    assert capsys.readouterr().out.split() == ["examples/extensions/agent-console-example-a"]


def test_main_without_examples_and_unknown_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, cfg = _repo(tmp_path)
    code, calls = _main(root, cfg, monkeypatch)
    assert (code, calls) == (0, [])
    assert "예제 없음" in capsys.readouterr().out
    code, _ = _main(root, cfg, monkeypatch, "--package", "nope")
    assert code == 2
    code, _ = _main(root, dataclasses.replace(cfg, example_steps=()), monkeypatch)
    assert code == 2


def test_main_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, cfg = _repo(tmp_path)
    _example(root, "agent-console-example-a")
    code, calls = _main(root, cfg, monkeypatch, "--dry-run")
    assert (code, calls) == (0, [])
    assert capsys.readouterr().out.splitlines() == [
        "[examples/extensions/agent-console-example-a] mypy",
        "[examples/extensions/agent-console-example-a] pytest -q",
    ]


# ---------------------------------------------------------------- portability 대상(8R 검토 F-5)


def test_choose_targets_examples(tmp_path: Path) -> None:
    root, cfg = _repo(tmp_path)
    _example(root, "agent-console-example-a")
    packages = [p for p in discover(root, cfg, kinds_of()) if not p.is_app]
    examples = discover_examples(root, cfg)

    def names(**kw: object) -> list[str]:
        return [p.path.name for p in pt.choose_targets(packages, examples, **kw)]  # type: ignore[arg-type]

    assert names(names=[], with_examples=False) == ["ac-x"]
    assert names(names=[], with_examples=True) == ["ac-x", "agent-console-example-a"]
    assert names(names=["agent-console-example-a"], with_examples=False) == [
        "agent-console-example-a"
    ]
    both = ["examples/extensions/agent-console-example-a", "ac-x"]
    assert names(names=both, with_examples=False) == ["agent-console-example-a", "ac-x"]
    with pytest.raises(PkgkitError, match="nope"):
        names(names=["nope"], with_examples=True)


def test_plan_example_has_no_run_check(tmp_path: Path) -> None:
    root, cfg = _repo(tmp_path)
    _example(root, "agent-console-example-a")
    [pkg] = discover_examples(root, cfg)
    plan = pt.plan_package(
        pkg,
        cfg=cfg,
        kinds=kinds_of(),
        wheelhouse=root / "dist/wheelhouse",
        wheel_files=[],
        workdir=tmp_path / "tmp" / pkg.path.name,
    )
    assert [s.name for s in plan.steps] == ["venv", "sync", "ruff", "format", "mypy", "pytest"]
    assert plan.missing_wheels == ("agent-console-contracts",)
    assert plan.package == "examples/extensions/agent-console-example-a"


def test_portability_main_dry_run_with_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, cfg = _repo(tmp_path)
    _example(root, "agent-console-example-a")
    monkeypatch.setattr(pt, "load_config", lambda _p=None: cfg)
    args = ["--root", str(root), "--tmp", str(tmp_path / "t"), "--dry-run"]
    assert pt.main(args) == 0
    out = capsys.readouterr().out
    assert "# packages/py/base/ac-x" in out
    assert "agent-console-example-a" not in out, "설정이 끄면 기본 전체 실행에 예제가 없다"
    assert pt.main([*args, "--examples"]) == 0
    assert "# examples/extensions/agent-console-example-a" in capsys.readouterr().out
    assert pt.main([*args, "--package", "agent-console-example-a"]) == 0
    out = capsys.readouterr().out
    assert "# examples/extensions/agent-console-example-a" in out
    assert "ac-x" not in out
    on = dataclasses.replace(cfg, portability_examples=True)
    monkeypatch.setattr(pt, "load_config", lambda _p=None: on)
    assert pt.main(args) == 0
    out = capsys.readouterr().out
    assert "# packages/py/base/ac-x" in out
    assert "# examples/extensions/agent-console-example-a" in out
    assert pt.main([*args, "--no-examples"]) == 0
    assert "agent-console-example-a" not in capsys.readouterr().out
