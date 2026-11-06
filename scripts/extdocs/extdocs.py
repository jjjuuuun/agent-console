"""extdocs 명령: 확장 지점 대조·문서 생성·드리프트 검사.

사용(저장소 루트에서, 워크스페이스 venv)::

    python scripts/extdocs/extdocs.py points [--allow-missing [CAT ...]]   # poe extpoints-check
    python scripts/extdocs/extdocs.py generate [--scaffold]                # poe extdocs
    python scripts/extdocs/extdocs.py docs [--allow-missing [CAT ...]]     # poe extdocs-check
    python scripts/extdocs/extdocs.py docs --report [GLOB ...]             # 공개 가능 린트를 경고로
    python scripts/extdocs/extdocs.py schema [--check]                     # declaration.schema.json

공통 옵션: ``--root``(기본 현재 폴더), ``--config``(기본 이 폴더의 ``extdocs.yaml``).
``--allow-missing``은 "아직 채우지 않음" 범주(declarations·examples·guides)를 경고로 낮춘다
(값 없이 주면 전부). 종료 코드: 0 통과, 1 위반, 2 설정·입력 오류.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from extdocs_common import (
    MISSING_CATEGORIES,
    TOOL_DIR,
    Collection,
    ExtdocsError,
    Finding,
    SymbolResolver,
    ToolData,
    collect,
    load_data,
    member_src_paths,
    report,
)
from extdocs_docs import BLOCKING_CODES, docs_present, expand_globs, public_lint, run_docs_checks
from extdocs_generate import Generator, write_plan
from extdocs_model import schema_text
from extdocs_points import SCHEMA_FILE, CodeFacts, check_points, code_points_summary

SKIP_MESSAGE = "문서 폴더 없음 — 건너뜀"


def _allowed(values: list[str] | None) -> list[str]:
    if values is None:
        return []
    if not values:
        return list(MISSING_CATEGORIES)
    bad = sorted(set(values) - set(MISSING_CATEGORIES))
    if bad:
        raise ExtdocsError(
            f"모르는 --allow-missing 범주: {', '.join(bad)}({', '.join(MISSING_CATEGORIES)})"
        )
    return values


def _prepare(root: Path, data: ToolData) -> tuple[Collection, SymbolResolver]:
    col = collect(root, data)
    return col, SymbolResolver(member_src_paths(col.members))


def run_points(
    root: Path, data: ToolData, tool_dir: Path, allowed: Sequence[str], *, quiet: bool = False
) -> tuple[int, list[Finding], CodeFacts]:
    """대조 검사. (종료 코드, 결과, 코드 사실)."""
    col, resolver = _prepare(root, data)
    findings, facts = check_points(root, col, data, resolver, tool_dir=tool_dir)
    print(f"extpoints-check: 선언 {len(col.declarations)}개, {code_points_summary(facts)}")
    return report(findings, allowed, quiet=quiet), findings, facts


def run_generate(root: Path, data: ToolData, tool_dir: Path, *, scaffold: bool) -> int:
    col, resolver = _prepare(root, data)
    findings, facts = check_points(root, col, data, resolver, tool_dir=tool_dir)
    blocking = [f for f in findings if f.code in BLOCKING_CODES]
    if blocking:
        report(blocking, [])
        print("선언 형식 오류가 있어 생성하지 않습니다")
        return 1
    planned = Generator(col, facts, data, resolver).plan(root, scaffold=scaffold)
    written = write_plan(root, planned)
    for key in written:
        print(f"생성: {key}")
    print(f"extdocs: {len(written)}개 파일을 썼습니다(검사 대상 {len(planned)}개)")
    return 0


def run_docs(
    root: Path, data: ToolData, tool_dir: Path, allowed: Sequence[str], *, quiet: bool = False
) -> int:
    if not docs_present(root, data):
        print(f"extdocs-check: {SKIP_MESSAGE} ({data.docs_dir})")
        return 0
    col, resolver = _prepare(root, data)
    findings = run_docs_checks(root, col, data, resolver, tool_dir=tool_dir)
    print(f"extdocs-check: 선언 {len(col.declarations)}개")
    return report(findings, allowed, quiet=quiet)


def run_report(root: Path, data: ToolData, patterns: Sequence[str]) -> int:
    files = expand_globs(root, patterns or data.s("report_globs") or [])
    findings = public_lint(root, files, data.lint_rules, warning=True)
    print(f"extdocs-check --report: 파일 {len(files)}개")
    report(findings, [])
    return 0


def run_schema(tool_dir: Path, *, check: bool) -> int:
    path = tool_dir / SCHEMA_FILE
    text = schema_text()
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    if check:
        if current != text:
            print(f"{SCHEMA_FILE}가 모델과 다릅니다 — `python scripts/extdocs/extdocs.py schema`")
            return 1
        return 0
    if current != text:
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"생성: {SCHEMA_FILE}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="확장 지점 대조·문서 생성·드리프트 검사")
    ap.add_argument("--root", type=Path, default=Path("."), help="저장소 루트(기본 현재 폴더)")
    ap.add_argument("--config", type=Path, default=None, help="설정 파일(기본 extdocs.yaml)")
    ap.add_argument(
        "--tool-dir", type=Path, default=TOOL_DIR, help="데이터 파일 폴더(기본 이 폴더)"
    )
    ap.add_argument("--quiet", action="store_true", help="경고는 규칙별 건수만")
    sub = ap.add_subparsers(dest="command", required=True)
    allow_help = f"아직 채우지 않음 범주를 경고로({', '.join(MISSING_CATEGORIES)}; 값 없으면 전부)"
    p_points = sub.add_parser("points", help="코드 ↔ 선언 대조(poe extpoints-check)")
    p_points.add_argument("--allow-missing", nargs="*", metavar="CAT", help=allow_help)
    p_gen = sub.add_parser("generate", help="문서 생성(poe extdocs)")
    p_gen.add_argument(
        "--scaffold", action="store_true", help="없는 가이드 절 틀을 만든다(extdocs:todo)"
    )
    p_docs = sub.add_parser("docs", help="드리프트 검사(poe extdocs-check)")
    p_docs.add_argument("--allow-missing", nargs="*", metavar="CAT", help=allow_help)
    p_docs.add_argument(
        "--report", nargs="*", metavar="GLOB", help="공개 가능 린트만 경고로(기본 report_globs)"
    )
    p_schema = sub.add_parser("schema", help="declaration.schema.json 생성")
    p_schema.add_argument("--check", action="store_true", help="다르면 1")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "schema":
            return run_schema(args.tool_dir, check=args.check)
        data = load_data(args.tool_dir, args.config)
        if args.command == "points":
            return run_points(
                root, data, args.tool_dir, _allowed(args.allow_missing), quiet=args.quiet
            )[0]
        if args.command == "generate":
            return run_generate(root, data, args.tool_dir, scaffold=args.scaffold)
        if args.report is not None:
            return run_report(root, data, args.report)
        return run_docs(root, data, args.tool_dir, _allowed(args.allow_missing), quiet=args.quiet)
    except ExtdocsError as exc:
        print(f"extdocs: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
