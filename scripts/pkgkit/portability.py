"""저장소 밖 이식 검사(design §3R.2.5 ``poe portability``, modularity §3.9.6).

패키지마다: 폴더를 임시 폴더(``$TMPDIR``)로 복사 → ``uv venv`` →
``uv sync``(사내 패키지는 휠 모음에서만, 외부는 캐시·인덱스) →
``ruff``·``mypy``·``pytest``(README doctest 포함) →
단독 실행 종류면 ``python -m <모듈> --check`` → 결과 표.

사내 패키지를 휠 모음에서만 가져오게 하려고, **복사본**의 pyproject 끝에
휠 모음을 가리키는 flat 인덱스를 덧붙인다(원본은 건드리지 않는다).
uv는 기본 인덱스(PyPI)를 가장 낮은 순위로 두고 처음 찾은 인덱스에서 멈추므로,
휠 모음에 있는 이름은 PyPI에서 찾지 않는다.
``--no-index``면 휠 모음만 쓴다(외부 의존 휠도 거기 있어야 한다).

``--wheels``는 휠 모음을 다시 만들고, 기본으로 이번 검사 전용 임시 ``UV_CACHE_DIR``을 쓴다
(버전을 올리지 않고 다시 만든 사내 휠을 uv 캐시가 옛 내용으로 재사용하지 않게, 4R.18).
``--reuse-uv-cache``면 환경의 캐시를 그대로 쓰고, ``--uv-cache-dir``로 위치를 정할 수 있다.
``--wheels`` 없이 돌릴 때 휠 모음의 휠이 패키지 소스(``pyproject.toml``·``README.md``·``src/``)보다
오래되었으면 경고한다.

계획 계산(:func:`plan_package`)은 순수 함수다. 실행기(:class:`Runner`)는 주입할 수 있다.

사용::

    python scripts/pkgkit/portability.py [--root .] [--package NAME ...] [--wheels] [--no-index]
                                         [--reuse-uv-cache | --uv-cache-dir DIR]
                                         [--keep] [--python 3.12] [--dry-run] [--timeout 900]
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import wheels as wheels_cmd
from pkgkit_common import (
    Config,
    KindSpec,
    PkgkitError,
    PyPackage,
    discover,
    import_name_of,
    load_config,
    load_kinds,
    requirement_name,
    select,
    templates_dir,
)

WHEELHOUSE_INDEX = "pkgkit-wheelhouse"
COPY_IGNORE = (
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "uv.lock",
    "*.egg-info",
)
# 임시 환경에 넘기지 않는 환경변수(공유 venv·워크스페이스를 가리키면 복사본 검사가 아니게 된다)
DROP_ENV = ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV", "UV_PROJECT", "PYTHONPATH", "MYPYPATH")
SETUP_STEPS = frozenset({"venv", "sync"})
# 휠에 들어가는 소스(낡은 휠 모음 판단 기준). 폴더는 재귀로 본다.
WHEEL_SOURCES = ("pyproject.toml", "README.md", "src")
STALE_LIST_LIMIT = 10


@dataclass(frozen=True)
class Step:
    """실행할 명령 하나. ``cwd``는 복사본 폴더."""

    name: str
    argv: tuple[str, ...]
    cwd: Path


@dataclass(frozen=True)
class PackagePlan:
    """패키지 하나의 검사 계획."""

    package: str
    source: Path
    workdir: Path
    steps: tuple[Step, ...]
    pyproject_suffix: str = ""
    missing_wheels: tuple[str, ...] = ()


@dataclass(frozen=True)
class StepResult:
    name: str
    ok: bool
    returncode: int
    output: str = ""


@dataclass
class PackageResult:
    package: str
    steps: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)


Runner = Callable[[Step, Mapping[str, str]], StepResult]
Copier = Callable[[Path, Path], None]


# ---------------------------------------------------------------- 계획(순수)


def wheelhouse_index_toml(wheelhouse: Path) -> str:
    """복사본 pyproject 끝에 붙일 flat 인덱스 선언."""
    return (
        "\n\n# --- pkgkit portability가 복사본에만 덧붙임(원본에는 없음)\n"
        "[[tool.uv.index]]\n"
        f'name = "{WHEELHOUSE_INDEX}"\n'
        f'url = "{wheelhouse.resolve().as_uri()}"\n'
        'format = "flat"\n'
    )


def internal_requirements(pkg: PyPackage, cfg: Config) -> list[str]:
    """패키지가 직접 쓰는 사내 의존 이름(본 의존 + dev 그룹, 정규화, 순서 유지)."""
    out: list[str] = []
    for req in pkg.dependencies() + pkg.dev_dependencies():
        name = requirement_name(req)
        if cfg.is_internal(name) and name not in out:
            out.append(name)
    return out


def missing_wheels(names: Sequence[str], wheel_files: Sequence[str]) -> list[str]:
    """휠 모음에 휠이 없는 사내 의존(휠 파일 이름 앞부분 = import 이름 형태)."""
    have = {f.split("-", 1)[0].lower() for f in wheel_files if f.endswith(".whl")}
    return [n for n in names if import_name_of(n) not in have]


def plan_package(
    pkg: PyPackage,
    *,
    cfg: Config,
    kinds: Mapping[str, KindSpec],
    wheelhouse: Path | None,
    wheel_files: Sequence[str],
    workdir: Path,
    no_index: bool = False,
    python: str | None = None,
) -> PackagePlan:
    """패키지 하나의 검사 단계를 계산한다(파일·프로세스를 건드리지 않는다).

    ``wheelhouse``가 ``None``이면(휠 모음 폴더가 없음) 찾기 경로를 넣지 않는다. 사내 의존이
    없는 패키지는 그대로 검사되고, 있으면 ``missing_wheels``에 남아 호출자가 안내한다.
    """
    venv = ["uv", "venv", "--quiet"] + (["--python", python] if python else [])
    sync = ["uv", "sync", "--quiet"]
    suffix = ""
    if wheelhouse is None:
        if no_index:
            raise PkgkitError("--no-index에는 휠 모음 폴더가 필요합니다")
    elif no_index:
        sync += ["--no-index", "--find-links", str(wheelhouse.resolve())]
    else:
        suffix = wheelhouse_index_toml(wheelhouse)
    run = ["uv", "run", "--no-sync"]
    steps = [
        Step("venv", tuple(venv), workdir),
        Step("sync", tuple(sync), workdir),
        Step("ruff", (*run, "ruff", "check", "."), workdir),
        Step("format", (*run, "ruff", "format", "--check", "."), workdir),
        Step("mypy", (*run, "mypy"), workdir),
        Step("pytest", (*run, "pytest", "-q"), workdir),
    ]
    kind = kinds.get(pkg.kind or "")
    if kind and kind.runnable and pkg.import_name:
        steps.append(Step("run-check", (*run, "python", "-m", pkg.import_name, "--check"), workdir))
    return PackagePlan(
        package=pkg.rel,
        source=pkg.path,
        workdir=workdir,
        steps=tuple(steps),
        pyproject_suffix=suffix,
        missing_wheels=tuple(missing_wheels(internal_requirements(pkg, cfg), wheel_files)),
    )


def portability_env(
    environ: Mapping[str, str], *, uv_cache_dir: Path | None = None
) -> dict[str, str]:
    """임시 환경용 환경변수(공유 venv·워크스페이스 지시를 뺀다).

    Args:
        environ: 원래 환경변수.
        uv_cache_dir: 주면 ``UV_CACHE_DIR``을 이 값으로 덮는다(``--wheels`` 기본 = 임시 폴더).
    """
    env = {k: v for k, v in environ.items() if k not in DROP_ENV}
    if uv_cache_dir is not None:
        env["UV_CACHE_DIR"] = str(uv_cache_dir)
    return env


def choose_uv_cache_dir(
    *, wheels: bool, reuse: bool, explicit: Path | None, session: Path
) -> Path | None:
    """복사본 검사에 쓸 ``UV_CACHE_DIR``(None = 환경 그대로).

    명시한 위치가 가장 먼저다. 그다음 ``--wheels``이고 ``--reuse-uv-cache``가 아니면 세션 임시 폴더.
    """
    if explicit is not None:
        return explicit
    if wheels and not reuse:
        return session / "uv-cache"
    return None


def wheel_stamps(wheel_files: Mapping[str, float]) -> dict[str, float]:
    """``{휠 파일 이름: 수정 시각}`` → ``{휠 이름 앞부분(소문자): 가장 최근 수정 시각}``."""
    out: dict[str, float] = {}
    for name, mtime in wheel_files.items():
        if name.endswith(".whl"):
            key = name.split("-", 1)[0].lower()
            out[key] = max(out.get(key, mtime), mtime)
    return out


def outdated_wheels(wheels: Mapping[str, float], sources: Mapping[str, float]) -> list[str]:
    """소스가 휠보다 새로운 패키지(순수, 이름 순).

    Args:
        wheels: ``{휠 이름 앞부분: 휠 수정 시각}`` (:func:`wheel_stamps`).
        sources: ``{휠 이름 앞부분: 소스 최신 수정 시각}``. 휠이 없는 이름은 보지 않는다.
    """
    return sorted(n for n, t in sources.items() if n in wheels and t > wheels[n])


def newest_source_mtime(path: Path, entries: Sequence[str] = WHEEL_SOURCES) -> float:
    """패키지 폴더에서 휠에 들어가는 파일의 가장 최근 수정 시각(캐시 폴더 제외, 없으면 0)."""
    newest = 0.0
    skip = {".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
    for entry in entries:
        target = path / entry
        if target.is_file():
            newest = max(newest, target.stat().st_mtime)
            continue
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [d for d in dirnames if d not in skip and not d.endswith(".egg-info")]
            for f in filenames:
                newest = max(newest, os.stat(os.path.join(dirpath, f)).st_mtime)
    return newest


def stale_wheelhouse_warning(
    wheelhouse: Path, packages: Sequence[PyPackage], *, limit: int = STALE_LIST_LIMIT
) -> str | None:
    """휠 모음의 휠이 패키지 소스보다 오래되었으면 안내 문구, 아니면 None."""
    if not wheelhouse.is_dir():
        return None
    stamps = wheel_stamps({p.name: p.stat().st_mtime for p in wheelhouse.glob("*.whl")})
    sources = {
        import_name_of(p.dist_name): newest_source_mtime(p.path)
        for p in packages
        if import_name_of(p.dist_name) in stamps
    }
    old = outdated_wheels(stamps, sources)
    if not old:
        return None
    shown = ", ".join(old[:limit]) + (f" 외 {len(old) - limit}개" if len(old) > limit else "")
    return (
        f"경고: 휠 모음({wheelhouse})이 소스보다 오래되었습니다({len(old)}개: {shown}). "
        "고친 내용이 검사에 반영되지 않을 수 있습니다. --wheels를 붙이거나 먼저 wheels.py를 돌린다"
    )


def format_table(results: Sequence[PackageResult]) -> str:
    """결과 표(행 = 패키지, 열 = 단계)."""
    names: list[str] = []
    for r in results:
        names.extend(s.name for s in r.steps if s.name not in names)
    header = ["package", *names, "result"]
    rows = [header]
    for r in results:
        by = {s.name: s for s in r.steps}
        cells = [r.package]
        for n in names:
            s = by.get(n)
            cells.append("-" if s is None else "ok" if s.ok else "FAIL")
        cells.append("PASS" if r.ok else "FAIL")
        rows.append(cells)
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    return "\n".join(
        "  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) for row in rows
    )


# ---------------------------------------------------------------- 실행


def subprocess_runner(timeout: float) -> Runner:
    """기본 실행기: 하위 프로세스로 돌리고 출력을 모은다."""

    def run(step: Step, env: Mapping[str, str]) -> StepResult:
        try:
            proc = subprocess.run(
                list(step.argv),
                cwd=step.cwd,
                env=dict(env),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            return StepResult(step.name, False, -1, f"{out}\n시간 초과({timeout}s)")
        except FileNotFoundError as exc:
            return StepResult(step.name, False, -1, str(exc))
        return StepResult(
            step.name, proc.returncode == 0, proc.returncode, proc.stdout + proc.stderr
        )

    return run


def copy_package(src: Path, dst: Path) -> None:
    """패키지 폴더를 복사한다(캐시·venv·빌드 산출물 제외)."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*COPY_IGNORE))


def execute(
    plan: PackagePlan, *, runner: Runner, env: Mapping[str, str], copier: Copier = copy_package
) -> PackageResult:
    """계획 하나를 실행한다. 준비 단계(venv·sync)가 실패하면 나머지는 건너뛴다."""
    result = PackageResult(plan.package)
    copier(plan.source, plan.workdir)
    if plan.pyproject_suffix:
        pyproject = plan.workdir / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8") + plan.pyproject_suffix, encoding="utf-8"
        )
    for step in plan.steps:
        r = runner(step, env)
        result.steps.append(r)
        if not r.ok and step.name in SETUP_STEPS:
            break
    return result


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="패키지 폴더를 저장소 밖에서 설치·검사한다")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="저장소 루트(기본: 현재 폴더)")
    ap.add_argument("--config", type=Path, default=None, help="pkgkit_py.toml 경로")
    ap.add_argument("--package", action="append", default=[], help="이 패키지만(여러 번 가능)")
    ap.add_argument("--wheelhouse", type=Path, default=None, help="휠 모음(기본: 설정 wheelhouse)")
    ap.add_argument(
        "--wheels", action="store_true", help="먼저 휠 모음을 다시 만든다(wheels --clean)"
    )
    ap.add_argument("--no-index", action="store_true", help="인덱스를 쓰지 않고 휠 모음만")
    ap.add_argument(
        "--reuse-uv-cache",
        action="store_true",
        help="--wheels에서도 임시 UV_CACHE_DIR 대신 환경의 uv 캐시를 쓴다",
    )
    ap.add_argument("--uv-cache-dir", type=Path, default=None, help="복사본 검사의 UV_CACHE_DIR")
    ap.add_argument("--python", default=None, help="uv venv --python 값")
    ap.add_argument("--tmp", type=Path, default=None, help="임시 폴더 위치(기본: $TMPDIR)")
    ap.add_argument("--keep", action="store_true", help="임시 폴더를 지우지 않는다")
    ap.add_argument("--timeout", type=float, default=900.0, help="단계마다 제한 시간(초)")
    ap.add_argument("--dry-run", action="store_true", help="계획만 출력")
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    try:
        cfg = load_config(args.config)
        kinds = load_kinds(templates_dir(root, cfg), cfg.template_vars)
        discovered = discover(root, cfg, kinds)
        packages = [p for p in discovered if not p.is_app]
        targets = select(packages, args.package)
    except PkgkitError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    wheelhouse: Path = args.wheelhouse.resolve() if args.wheelhouse else root / cfg.wheelhouse
    if args.wheels and not args.dry_run:
        code = wheels_cmd.main(["--root", str(root), "--out", str(wheelhouse), "--clean"])
        if code != 0:
            return code
    has_wheelhouse = wheelhouse.is_dir() or (args.wheels and args.dry_run)
    if not has_wheelhouse:
        if args.no_index:
            print(
                f"오류: 휠 모음 폴더가 없습니다: {wheelhouse}\n"
                "먼저 `python scripts/pkgkit/wheels.py`를 돌리거나 --wheels를 붙인다",
                file=sys.stderr,
            )
            return 2
        print(
            f"안내: 휠 모음 폴더가 없어({wheelhouse}) 사내 의존 찾기 경로 없이 검사합니다. "
            "사내 의존이 있는 패키지는 --wheels를 붙이거나 먼저 wheels.py를 돌린다"
        )
    if not args.wheels:
        warning = stale_wheelhouse_warning(wheelhouse, discovered)
        if warning:
            print(warning, file=sys.stderr)
    wheel_files = sorted(p.name for p in wheelhouse.glob("*.whl")) if wheelhouse.is_dir() else []
    tmp_base = args.tmp or Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
    tmp_base.mkdir(parents=True, exist_ok=True)
    session = Path(tempfile.mkdtemp(prefix="agent-console-portability-", dir=tmp_base))
    plans = [
        plan_package(
            p,
            cfg=cfg,
            kinds=kinds,
            wheelhouse=wheelhouse if has_wheelhouse else None,
            wheel_files=wheel_files,
            workdir=session / p.path.name,
            no_index=args.no_index,
            python=args.python,
        )
        for p in targets
    ]
    if args.dry_run:
        for plan in plans:
            print(f"# {plan.package} → {plan.workdir}")
            if plan.missing_wheels:
                print(f"#   휠 모음에 없는 사내 의존: {', '.join(plan.missing_wheels)}")
            for s in plan.steps:
                print(f"  [{s.name}] {shlex.join(s.argv)}")
        shutil.rmtree(session, ignore_errors=True)
        return 0
    uv_cache = choose_uv_cache_dir(
        wheels=args.wheels,
        reuse=args.reuse_uv_cache,
        explicit=args.uv_cache_dir.resolve() if args.uv_cache_dir else None,
        session=session,
    )
    if uv_cache is not None:
        print(f"UV_CACHE_DIR: {uv_cache}", flush=True)
    env = portability_env(os.environ, uv_cache_dir=uv_cache)
    runner = subprocess_runner(args.timeout)
    results: list[PackageResult] = []
    try:
        for plan in plans:
            if plan.missing_wheels:
                missing = ", ".join(plan.missing_wheels)
                print(f"경고 {plan.package}: 휠 모음에 없는 사내 의존 {missing}")
            print(f"검사: {plan.package}", flush=True)
            r = execute(plan, runner=runner, env=env)
            results.append(r)
            for sr in r.steps:
                if not sr.ok:
                    tail = "\n".join(sr.output.strip().splitlines()[-40:])
                    print(f"--- {plan.package} [{sr.name}] 실패(exit {sr.returncode})\n{tail}")
    finally:
        if args.keep:
            print(f"임시 폴더 유지: {session}")
        else:
            shutil.rmtree(session, ignore_errors=True)
    print(format_table(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
