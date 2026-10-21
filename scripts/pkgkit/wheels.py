"""휠 모음 만들기(얇은 래퍼, design §3R.2.5 ``poe wheels``).

``uv build --all-packages --wheel -o <wheelhouse>``를 부른다. ``portability``가 저장소 밖 설치에서
사내 의존을 이 폴더에서만 찾는다.

사용::

    python scripts/pkgkit/wheels.py [--root .] [--out DIR] [--package NAME ...]
                                    [--clean] [--dry-run]
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from pkgkit_common import PkgkitError, load_config


def plan_wheels(out: Path, packages: Sequence[str] = ()) -> list[list[str]]:
    """실행할 명령 목록(순수). 패키지를 지정하지 않으면 워크스페이스 전체 한 번."""
    if not packages:
        return [["uv", "build", "--all-packages", "--wheel", "-o", str(out)]]
    return [["uv", "build", "--package", name, "--wheel", "-o", str(out)] for name in packages]


def stale_wheels(out: Path) -> list[Path]:
    """``--clean``이 지울 파일(휠 모음 폴더의 ``*.whl``·``*.tar.gz``만)."""
    if not out.is_dir():
        return []
    return sorted([*out.glob("*.whl"), *out.glob("*.tar.gz")])


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="워크스페이스 패키지 휠을 한 폴더에 만든다")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="저장소 루트(기본: 현재 폴더)")
    ap.add_argument("--config", type=Path, default=None, help="pkgkit_py.toml 경로")
    ap.add_argument("--out", type=Path, default=None, help="출력 폴더(기본: 설정 wheelhouse)")
    ap.add_argument("--package", action="append", default=[], help="이 배포 이름만(여러 번 가능)")
    ap.add_argument("--clean", action="store_true", help="먼저 출력 폴더의 휠·sdist를 지운다")
    ap.add_argument("--dry-run", action="store_true", help="명령만 출력")
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    try:
        cfg = load_config(args.config)
    except PkgkitError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    out: Path = args.out.resolve() if args.out else root / cfg.wheelhouse
    commands = plan_wheels(out, args.package)
    if args.dry_run:
        for c in commands:
            print(shlex.join(c))
        return 0
    if args.clean:
        for f in stale_wheels(out):
            f.unlink()
    for c in commands:
        print(f"$ {shlex.join(c)}", flush=True)
        code = subprocess.run(c, cwd=root, check=False).returncode
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
