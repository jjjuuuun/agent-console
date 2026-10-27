from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path

import portability as pt
import pytest
import wheels
from pkgkit_common import PkgkitError, discover
from pkgkit_testkit import add_package, make_workspace
from pkgkit_testkit import kinds as kinds_of


def _plans(tmp_path: Path, **kw: object) -> dict[str, pt.PackagePlan]:
    cfg = make_workspace(tmp_path / "repo")
    root = tmp_path / "repo"
    add_package(
        root, cfg, "feature", "ac-notes", dev_dependencies=["agent-console-backend-fake-agent"]
    )
    add_package(root, cfg, "module", "ac-mod-notes", dependencies=["agent-console-notes"])
    kinds = kinds_of()
    kw.setdefault("wheelhouse", root / "dist/wheelhouse")
    out = {}
    for p in discover(root, cfg, kinds):
        out[p.path.name] = pt.plan_package(
            p,
            cfg=cfg,
            kinds=kinds,
            wheel_files=[
                "agent_console_contracts-0.4.0-py3-none-any.whl",
                "agent_console_notes-0.1.0.tar.gz",
            ],
            workdir=tmp_path / "tmp" / p.path.name,
            **kw,  # type: ignore[arg-type]
        )
    return out


def test_plan_steps_and_wheelhouse_index(tmp_path: Path) -> None:
    plans = _plans(tmp_path, python="3.12")
    lib, mod = plans["ac-notes"], plans["ac-mod-notes"]
    assert [s.name for s in lib.steps] == ["venv", "sync", "ruff", "format", "mypy", "pytest"]
    assert [s.name for s in mod.steps][-1] == "run-check"
    assert mod.steps[-1].argv[-3:] == ("-m", "agent_console_mod_notes", "--check")
    assert lib.steps[0].argv == ("uv", "venv", "--quiet", "--python", "3.12")
    assert all(s.cwd == tmp_path / "tmp" / "ac-notes" for s in lib.steps)
    assert "--no-index" not in lib.steps[1].argv
    index = tomllib.loads(lib.pyproject_suffix)["tool"]["uv"]["index"][0]
    assert index["format"] == "flat"
    assert index["url"].startswith("file://")
    assert "explicit" not in index, "명시 인덱스면 사내 간접 의존을 못 찾는다"
    assert lib.missing_wheels == ("agent-console-backend-fake-agent",)
    assert mod.missing_wheels == ("agent-console-modkit", "agent-console-notes")


def test_plan_no_index(tmp_path: Path) -> None:
    lib = _plans(tmp_path, no_index=True)["ac-notes"]
    assert lib.pyproject_suffix == ""
    assert "--no-index" in lib.steps[1].argv
    assert "--find-links" in lib.steps[1].argv


def test_portability_env_drops_shared_venv() -> None:
    env = pt.portability_env(
        {
            "UV_PROJECT_ENVIRONMENT": "/x",
            "VIRTUAL_ENV": "/y",
            "PYTHONPATH": "z",
            "MYPY_CACHE_DIR": "/repo/.mypy_cache",
            "UV_LINK_MODE": "copy",
            "HOME": "/h",
        }
    )
    assert env == {"UV_LINK_MODE": "copy", "HOME": "/h"}


def test_execute_with_fake_runner(tmp_path: Path) -> None:
    plans = _plans(tmp_path)
    plan = plans["ac-notes"]
    calls: list[str] = []

    def runner(step: pt.Step, env: Mapping[str, str]) -> pt.StepResult:
        calls.append(step.name)
        assert (step.cwd / "pyproject.toml").is_file()
        return pt.StepResult(step.name, step.name != "mypy", 0 if step.name != "mypy" else 1, "")

    result = pt.execute(plan, runner=runner, env={})
    assert calls == ["venv", "sync", "ruff", "format", "mypy", "pytest"], (
        "검사 단계 실패는 나머지를 계속"
    )
    assert not result.ok
    copied = (plan.workdir / "pyproject.toml").read_text(encoding="utf-8")
    assert "pkgkit-wheelhouse" in copied
    original = (plan.source / "pyproject.toml").read_text(encoding="utf-8")
    assert "pkgkit-wheelhouse" not in original, "원본은 건드리지 않는다"

    def failing_sync(step: pt.Step, env: Mapping[str, str]) -> pt.StepResult:
        return pt.StepResult(step.name, step.name != "sync", 1, "boom")

    result2 = pt.execute(plans["ac-mod-notes"], runner=failing_sync, env={})
    assert [s.name for s in result2.steps] == ["venv", "sync"], "준비 실패면 멈춘다"


def test_copy_ignores_caches(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / ".venv").mkdir(parents=True)
    (src / "a" / "__pycache__").mkdir(parents=True)
    (src / "a" / "m.py").write_text("", encoding="utf-8")
    pt.copy_package(src, tmp_path / "dst")
    assert (tmp_path / "dst/a/m.py").is_file()
    assert not (tmp_path / "dst/.venv").exists()
    assert not (tmp_path / "dst/a/__pycache__").exists()


def test_format_table() -> None:
    ok = pt.PackageResult("p1", [pt.StepResult("venv", True, 0), pt.StepResult("pytest", True, 0)])
    bad = pt.PackageResult("p2", [pt.StepResult("venv", False, 1)])
    lines = pt.format_table([ok, bad]).splitlines()
    assert lines[0].split() == ["package", "venv", "pytest", "result"]
    assert lines[1].split() == ["p1", "ok", "ok", "PASS"]
    assert lines[2].split() == ["p2", "FAIL", "-", "FAIL"]


def test_missing_wheels_matches_normalized_names() -> None:
    files = ["agent_console_contracts-0.4.0-py3-none-any.whl"]
    assert pt.missing_wheels(["agent-console-contracts", "agent-console-x"], files) == [
        "agent-console-x"
    ]


def test_wheels_plan_and_clean(tmp_path: Path) -> None:
    out = tmp_path / "wh"
    assert wheels.plan_wheels(out) == [["uv", "build", "--all-packages", "--wheel", "-o", str(out)]]
    assert wheels.plan_wheels(out, ["a"]) == [
        ["uv", "build", "--package", "a", "--wheel", "-o", str(out)]
    ]
    out.mkdir()
    for name in ("a-0.1.0-py3-none-any.whl", "a-0.1.0.tar.gz", "keep.txt"):
        (out / name).write_text("", encoding="utf-8")
    assert [p.name for p in wheels.stale_wheels(out)] == [
        "a-0.1.0-py3-none-any.whl",
        "a-0.1.0.tar.gz",
    ]
    assert wheels.stale_wheels(tmp_path / "none") == []


def test_plan_without_wheelhouse(tmp_path: Path) -> None:
    plans = _plans(tmp_path, wheelhouse=None)
    lib = plans["ac-notes"]
    assert lib.pyproject_suffix == ""
    assert lib.steps[1].argv == ("uv", "sync", "--quiet")
    with pytest.raises(PkgkitError, match="휠 모음"):
        _plans(tmp_path / "b", wheelhouse=None, no_index=True)


def test_main_without_wheelhouse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    cfg = make_workspace(root)
    add_package(root, cfg, "base", "ac-x")
    monkeypatch.setattr(pt, "load_config", lambda _p=None: cfg)
    args = ["--root", str(root), "--tmp", str(tmp_path / "t")]
    assert pt.main([*args, "--no-index", "--dry-run"]) == 2
    assert "wheels.py" in capsys.readouterr().err
    assert pt.main([*args, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "안내: 휠 모음 폴더가 없어" in out
    assert "--find-links" not in out


def test_portability_env_sets_uv_cache_dir(tmp_path: Path) -> None:
    env = pt.portability_env({"UV_CACHE_DIR": "/shared", "HOME": "/h"}, uv_cache_dir=tmp_path)
    assert env == {"UV_CACHE_DIR": str(tmp_path), "HOME": "/h"}
    assert pt.portability_env({"UV_CACHE_DIR": "/shared"}) == {"UV_CACHE_DIR": "/shared"}


def test_choose_uv_cache_dir_defaults_to_session_temp_with_wheels(tmp_path: Path) -> None:
    """4R.18: --wheels는 기본으로 임시 UV_CACHE_DIR(같은 버전 휠 재빌드 시 캐시 재사용 방지)."""
    s = tmp_path / "session"
    assert pt.choose_uv_cache_dir(wheels=True, reuse=False, explicit=None, session=s) == (
        s / "uv-cache"
    )
    assert pt.choose_uv_cache_dir(wheels=True, reuse=True, explicit=None, session=s) is None
    assert pt.choose_uv_cache_dir(wheels=False, reuse=False, explicit=None, session=s) is None
    mine = tmp_path / "mine"
    assert pt.choose_uv_cache_dir(wheels=False, reuse=True, explicit=mine, session=s) == mine


def test_outdated_wheels_is_pure() -> None:
    stamps = pt.wheel_stamps(
        {
            "agent_console_a-0.1.0-py3-none-any.whl": 10.0,
            "agent_console_b-0.1.0-py3-none-any.whl": 10.0,
            "agent_console_b-0.0.9-py3-none-any.whl": 5.0,
            "agent_console_c-0.1.0.tar.gz": 1.0,
        }
    )
    assert stamps == {"agent_console_a": 10.0, "agent_console_b": 10.0}
    sources = {"agent_console_a": 11.0, "agent_console_b": 9.0, "agent_console_c": 99.0}
    assert pt.outdated_wheels(stamps, sources) == ["agent_console_a"]


def test_stale_wheelhouse_warning(tmp_path: Path) -> None:
    import os

    root = tmp_path / "repo"
    cfg = make_workspace(root)
    add_package(root, cfg, "base", "ac-x")
    [pkg] = [p for p in discover(root, cfg, kinds_of()) if p.path.name == "ac-x"]
    house = root / "dist" / "wheelhouse"
    house.mkdir(parents=True)
    wheel = house / "agent_console_x-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"")
    newest = pt.newest_source_mtime(pkg.path)
    assert newest > 0
    os.utime(wheel, (newest + 100, newest + 100))
    assert pt.stale_wheelhouse_warning(house, [pkg]) is None
    os.utime(wheel, (newest - 100, newest - 100))
    warning = pt.stale_wheelhouse_warning(house, [pkg])
    assert warning is not None
    assert "agent_console_x" in warning
    assert "--wheels" in warning
    assert pt.stale_wheelhouse_warning(tmp_path / "none", [pkg]) is None


def test_main_warns_on_stale_wheelhouse_without_wheels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import os

    root = tmp_path / "repo"
    cfg = make_workspace(root)
    add_package(root, cfg, "base", "ac-x")
    house = root / cfg.wheelhouse
    house.mkdir(parents=True)
    wheel = house / "agent_console_x-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"")
    os.utime(wheel, (1.0, 1.0))
    monkeypatch.setattr(pt, "load_config", lambda _p=None: cfg)
    args = ["--root", str(root), "--tmp", str(tmp_path / "t"), "--dry-run"]
    assert pt.main(args) == 0
    assert "휠 모음" in capsys.readouterr().err
    assert pt.main([*args, "--wheels"]) == 0  # 다시 만들 것이므로 경고하지 않는다
    assert "오래되었습니다" not in capsys.readouterr().err
