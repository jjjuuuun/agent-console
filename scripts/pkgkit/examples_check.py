"""확장 예제 검사(``poe examples``).

``pkgkit_py.toml`` ``[examples] roots`` glob에 걸린 폴더 가운데 ``pyproject.toml``이 있는 것을 모두
예제로 보고, 폴더마다 ``[examples] steps`` 명령(기본 ``mypy``·``pytest -q``)을 그 폴더를 작업 폴더로
돌린다. 예제를 설치하지 않고 폴더 자기 설정(mypy ``files``, pytest ``pythonpath``)으로 검사한다.
예제 목록을 손으로 적지 않으므로 새 예제 폴더는 저절로 검사 대상이 된다. glob에 걸렸는데
``pyproject.toml``이 없는 폴더는 실패로 알린다(반쯤 만든 예제가 조용히 빠지지 않게).

계획 계산(:func:`plan_examples`)은 순수 함수다. 실행기(:data:`Runner`)는 주입할 수 있다.

사용::

    python scripts/pkgkit/examples_check.py [--root .] [--config PATH] [--package NAME ...]
                                      [--list] [--dry-run]
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pkgkit_common import PkgkitError, PyPackage, discover_examples, example_folders, load_config
from pkgkit_common import select as select_packages
from portability import PackageResult, Step, StepResult, format_table

Runner = Callable[[Step], StepResult]


def step_names(steps: Sequence[Sequence[str]]) -> list[str]:
    """단계 이름 = 명령 첫 낱말. 같은 이름이 또 나오면 ``#2``·``#3``을 붙인다."""
    out: list[str] = []
    for argv in steps:
        base = argv[0]
        name, n = base, 1
        while name in out:
            n += 1
            name = f"{base}#{n}"
        out.append(name)
    return out


def plan_examples(
    examples: Sequence[PyPackage], steps: Sequence[Sequence[str]]
) -> list[tuple[PyPackage, list[Step]]]:
    """예제마다 실행할 단계(파일·프로세스를 건드리지 않는다)."""
    names = step_names(steps)
    return [
        (ex, [Step(n, tuple(argv), ex.path) for n, argv in zip(names, steps, strict=True)])
        for ex in examples
    ]


def streaming_runner(step: Step) -> StepResult:
    """기본 실행기: 출력을 그대로 흘려 보내고 종료 코드만 모은다(환경은 현재 그대로)."""
    try:
        code = subprocess.run(list(step.argv), cwd=step.cwd, check=False).returncode
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return StepResult(step.name, False, -1, str(exc))
    return StepResult(step.name, code == 0, code)


def run_examples(
    plans: Sequence[tuple[PyPackage, Sequence[Step]]], *, runner: Runner = streaming_runner
) -> list[PackageResult]:
    """계획을 차례로 실행한다. 한 단계가 실패해도 나머지 단계·예제를 계속 돌린다."""
    results: list[PackageResult] = []
    for ex, steps in plans:
        result = PackageResult(ex.rel)
        for step in steps:
            print(f"$ (cd {ex.rel} && {shlex.join(step.argv)})", flush=True)
            result.steps.append(runner(step))
        results.append(result)
    return results


def main(argv: Sequence[str] | None = None, *, runner: Runner = streaming_runner) -> int:
    ap = argparse.ArgumentParser(description="확장 예제 폴더마다 mypy·pytest(설정 [examples])")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="저장소 루트(기본: 현재 폴더)")
    ap.add_argument("--config", type=Path, default=None, help="pkgkit_py.toml 경로")
    ap.add_argument("--package", action="append", default=[], help="이 예제만(여러 번 가능)")
    ap.add_argument("--list", action="store_true", help="찾은 예제 폴더만 출력")
    ap.add_argument("--dry-run", action="store_true", help="명령만 출력")
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    try:
        cfg = load_config(args.config)
        found = discover_examples(root, cfg)
        _, without_project = example_folders(root, cfg)
        targets = select_packages(found, args.package)
    except PkgkitError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    if not cfg.example_steps and not args.list:
        print("오류: 설정 [examples] steps가 비었습니다", file=sys.stderr)
        return 2
    problems = [] if args.package else without_project
    for path in problems:
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        print(f"오류: 예제 폴더에 pyproject.toml이 없습니다: {rel}", file=sys.stderr)
    if args.list:
        for ex in targets:
            print(ex.rel)
        return 1 if problems else 0
    if not targets:
        print(f"예제 없음({', '.join(cfg.example_roots) or '[examples] roots 비어 있음'})")
        return 1 if problems else 0
    plans = plan_examples(targets, cfg.example_steps)
    if args.dry_run:
        for ex, steps in plans:
            for step in steps:
                print(f"[{ex.rel}] {shlex.join(step.argv)}")
        return 1 if problems else 0
    results = run_examples(plans, runner=runner)
    print(format_table(results))
    return 0 if all(r.ok for r in results) and not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
