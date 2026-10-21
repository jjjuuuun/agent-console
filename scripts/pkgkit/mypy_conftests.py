"""패키지 ``tests/conftest.py``를 하나씩 mypy로 검사한다(집계 ``poe typecheck``의 둘째 단계).

왜: 패키지 테스트 폴더에는 ``__init__.py``가 없어(pytest ``--import-mode=importlib``) mypy가
모든 ``conftest.py``를 같은 모듈 이름 ``conftest``로 본다. 집계 실행 한 번에 둘 이상을 넣으면
``Duplicate module named "conftest"``로 실패하므로, 루트 ``[tool.mypy] exclude``가 집계 실행에서
``conftest.py``를 빼고 이 스크립트가 파일마다 따로 mypy를 돌린다(루트 설정의 strict 그대로).
패키지 단독 검사(``poe portability``·패키지 폴더의 ``mypy``)는 conftest가 하나뿐이라 영향이 없다.

사용::

    python scripts/pkgkit/mypy_conftests.py [--root .] [--dry-run]
"""

from __future__ import annotations

import argparse
import glob
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Sequence
from pathlib import Path

CONFTEST = "conftest.py"


def mypy_paths(root: Path) -> list[str]:
    """루트 ``pyproject.toml``의 ``[tool.mypy] files``(glob 그대로)."""
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    files = data.get("tool", {}).get("mypy", {}).get("files", [])
    return [str(f) for f in files]


def find_conftests(root: Path, patterns: Iterable[str]) -> list[Path]:
    """``patterns``(루트 기준 glob)가 가리키는 폴더·파일 아래의 ``conftest.py``(정렬, 중복 없음).

    ``node_modules``·``.venv`` 등 점 폴더 아래는 건너뛴다.
    """
    found: set[Path] = set()
    for pattern in patterns:
        for hit in glob.glob(str(root / pattern)):
            p = Path(hit)
            candidates = [p] if p.is_file() else p.rglob(CONFTEST)
            for c in candidates:
                rel = c.relative_to(root)
                if c.name != CONFTEST or any(
                    part.startswith(".") or part == "node_modules" for part in rel.parts
                ):
                    continue
                found.add(rel)
    return sorted(found)


def plan(conftests: Sequence[Path]) -> list[list[str]]:
    """실행할 명령(순수). 파일마다 한 번(같은 이름 모듈이 한 실행에 둘 들어가지 않게)."""
    return [[sys.executable, "-m", "mypy", str(c)] for c in conftests]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="conftest.py를 파일마다 mypy로 검사")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="저장소 루트(기본: 현재 폴더)")
    ap.add_argument("--dry-run", action="store_true", help="명령만 출력")
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    commands = plan(find_conftests(root, mypy_paths(root)))
    failed = 0
    for cmd in commands:
        print("$", " ".join(cmd[1:]), flush=True)
        if args.dry_run:
            continue
        if subprocess.run(cmd, cwd=root, check=False).returncode != 0:
            failed += 1
    print(f"conftest {len(commands)}개 검사, 실패 {failed}개")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
