"""i18n 명령: 서버 문구 검사(``poe i18n-check``)와 빠진 항목 뽑기(``poe i18n-extract``).

사용(저장소 루트에서, 워크스페이스 venv)::

    python scripts/i18n/i18n_tool.py check [--package NAME ...] [--strict] [--no-server]
                                           [--list] [--by-package] [--quiet]
    python scripts/i18n/i18n_tool.py extract --lang CODE [--package NAME ...] [--no-server]
                                             [--dry-run]

검사(design §I18N.10):

- S1: 조립 서버(fake, 빈 작업 공간 + ``i18n.yaml`` 씨앗)의 OpenAPI GET 응답과 정적 출처
  (``static`` — 웹이 그리는 계약 스키마 모델·패키지 데이터 값, 서버 없이 읽음)에 나온 원문 문구가
  원문 언어가 아닌 묶음 ``text``에 있는지.
- S2: 소스의 오류·이슈 코드(``*Codes`` 클래스·``code=``·이슈 사전)와 응답에서 본 코드가 모든 언어
  묶음 ``codes``에 있는지.
- S3: 패키지 묶음끼리 코드 틀 자리표시자가 같은지, 틀의 자리표시자가 그 코드의 ``details`` 키
  (소스의 ``details=`` 사전 글자·응답 예시) 안에 있는지.

뽑기는 빠진 항목을 빈 값으로 맡을 패키지의 ``src/<import>/locales/<lang>.json``에 더한다(있는 값은
건드리지 않음). 묶음 entry point가 없으면 ``pyproject.toml``에 더한다.

공통 옵션: ``--root``(기본 현재 폴더), ``--config``(기본 이 폴더의 ``i18n.yaml``).
종료 코드: 0 통과(경고만), 1 오류 규칙 위반, 2 설정·입력 오류.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from i18n_common import (
    DEFAULT_CONFIG,
    CatalogIndex,
    Config,
    Finding,
    I18nToolError,
    Package,
    PackageCatalogs,
    discover_packages,
    group_of,
    load_config,
    read_package_catalogs,
    select_packages,
    severity_of,
)
from i18n_crawl import CrawlResult, crawl_server
from i18n_scan import SourceScan, scan_packages
from i18n_static import StaticResult, collect_static

from agent_console_i18n import (
    CODES,
    MESSAGE_CATALOGS_GROUP,
    NS,
    TEXT,
    check_details,
    compare_catalogs,
)

type CrawlFn = Callable[[Config], CrawlResult]


@dataclass(slots=True)
class Analysis:
    """검사 한 번의 결과."""

    config: Config
    packages: list[Package]
    scan: SourceScan
    crawl: CrawlResult | None
    static: StaticResult = field(default_factory=StaticResult)
    findings: list[Finding] = field(default_factory=list)
    codes: dict[str, tuple[str | None, str]] = field(default_factory=dict)
    """찾은 코드 → (맡을 패키지, 위치)."""
    languages: tuple[str, ...] = ()

    def package(self, name: str | None) -> Package | None:
        return next((p for p in self.packages if p.name == name), None)


def _pick(owners: Mapping[str, str], prefer: Sequence[str]) -> str:
    for name in prefer:
        if name in owners:
            return name
    return sorted(owners)[0]


def _short(text: str, limit: int = 80) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def analyze(
    repo: Path,
    config: Config,
    *,
    crawl_fn: CrawlFn | None = crawl_server,
    languages: Sequence[str] | None = None,
) -> Analysis:
    """대상 패키지를 훑고(필요하면 서버도) 규칙 결과를 만든다.

    Args:
        repo: 저장소 루트.
        config: 설정.
        crawl_fn: S1 훑기 함수(None이면 S1을 하지 않는다 — ``--no-server``).
        languages: 볼 언어(기본 ``config.languages``).
    """
    langs = tuple(languages or config.languages)
    packages = discover_packages(repo, config.targets)
    scan = scan_packages(packages, config)
    crawl = crawl_fn(config) if crawl_fn is not None else None
    static = collect_static(repo, config)
    result = Analysis(config, packages, scan, crawl, static, languages=langs)
    out = result.findings

    # ---- 묶음 읽기·등록
    index = CatalogIndex()
    catalogs: list[PackageCatalogs] = []
    for pkg in packages:
        found = read_package_catalogs(pkg)
        if found is None:
            continue
        catalogs.append(found)
        for issue in found.issues:
            out.append(
                Finding(
                    "catalog_invalid",
                    issue.path or pkg.name,
                    pkg.name,
                    issue.language,
                    issue.path or "",
                    f"{issue.code}: {issue.message}",
                )
            )
        for catalog in found.by_language.values():
            index.add(pkg.name, catalog)
        name = pkg.import_name
        if name is not None and not pkg.is_registered(name):
            out.append(
                Finding(
                    "catalog_unregistered",
                    name,
                    pkg.name,
                    None,
                    f"{pkg.rel}/pyproject.toml",
                    f"locales/ exists but no '{MESSAGE_CATALOGS_GROUP}' entry point "
                    f"points to {name}",
                )
            )

    # ---- S1 원문 문구
    text_langs = [lang for lang in langs if lang != config.source_language]
    seen_texts: dict[str, list[str]] = {}
    for source in ([crawl] if crawl is not None else []) + [static.result]:
        for text, routes in source.texts.items():
            where_list = seen_texts.setdefault(text, [])
            where_list.extend(r for r in routes if r not in where_list)
    if seen_texts:
        for text, routes in seen_texts.items():
            where = routes[0]
            states = {lang: index.state(lang, TEXT, text) for lang in text_langs}
            missing_langs = [lang for lang, (state, _) in states.items() if state == "missing"]
            for lang, (state, pkg_name) in states.items():
                if state == "empty":
                    out.append(
                        Finding(
                            "untranslated_text",
                            text,
                            pkg_name,
                            lang,
                            where,
                            "empty value (not translated yet)",
                        )
                    )
            if not missing_langs:
                continue
            owners = scan.owners(text)
            if owners:
                owner = _pick(owners, config.prefer_owners)
                for lang in missing_langs:
                    out.append(
                        Finding(
                            "missing_text",
                            text,
                            owner,
                            lang,
                            f"{where}; {owners[owner]}",
                            "no translation",
                        )
                    )
                continue
            template = scan.template_for(text)
            if template is not None:
                out.append(
                    Finding(
                        "dynamic_text",
                        text,
                        template.package,
                        None,
                        f"{where}; {template.where}",
                        "built from values: give it a code + details or a fixed text",
                    )
                )
            else:
                out.append(
                    Finding(
                        "unowned_text",
                        text,
                        None,
                        None,
                        where,
                        "not found in any target package source",
                    )
                )

    # ---- S2 코드
    codes = result.codes
    for site in sorted(scan.codes, key=lambda s: (not s.definition, s.package, s.where)):
        codes.setdefault(site.code, (site.package, site.where))
    if crawl is not None:
        for seen in crawl.issues:
            if config.is_code(seen.code):
                codes.setdefault(seen.code, (None, seen.where))
    for code, (code_owner, code_where) in sorted(codes.items()):
        if code_owner is None:
            if any(index.state(lang, CODES, code)[0] == "missing" for lang in langs):
                out.append(
                    Finding(
                        "unowned_code",
                        code,
                        None,
                        None,
                        code_where,
                        "seen in a response but not found in any target source",
                    )
                )
            continue
        for lang in langs:
            state, pkg_name = index.state(lang, CODES, code)
            if state == "empty":
                out.append(
                    Finding(
                        "untranslated_code",
                        code,
                        pkg_name,
                        lang,
                        code_where,
                        "empty value (not translated yet)",
                    )
                )
            elif state == "missing":
                out.append(
                    Finding("missing_code", code, code_owner, lang, code_where, "no message")
                )
    for lang in langs:
        for code, pkg_name in sorted(index.keys(lang, CODES).items()):
            if code not in codes:
                out.append(
                    Finding(
                        "stale_code",
                        code,
                        pkg_name,
                        lang,
                        "",
                        "catalog has a code that no target source produces",
                    )
                )

    # ---- S3 자리표시자
    examples: dict[str, set[str]] = {}
    sites = [(s.code, s.details) for s in scan.codes]
    if crawl is not None:
        sites.extend((s.code, s.details) for s in crawl.issues)
    for code, keys in sites:
        if keys is None:
            continue
        examples[code] = set(keys) if code not in examples else examples[code] & keys
    for found in catalogs:
        present = [found.by_language[lang] for lang in langs if lang in found.by_language]
        if not present:
            continue
        base = present[0]
        for other in present[1:]:
            for issue in compare_catalogs(base, other, sections=(CODES,)):
                if issue.code == "i18n.placeholder_mismatch":
                    out.append(
                        Finding(
                            "placeholder_mismatch",
                            issue.key or "",
                            found.package.name,
                            other.language,
                            "",
                            issue.message,
                        )
                    )
        for catalog in present:
            for issue in check_details(catalog, {k: sorted(v) for k, v in examples.items()}):
                out.append(
                    Finding(
                        "unknown_placeholder",
                        issue.key or "",
                        found.package.name,
                        catalog.language,
                        codes.get(issue.key or "", (None, ""))[1],
                        issue.message,
                    )
                )
    return result


# ---------------------------------------------------------------- 보고

_HEADS = {
    "missing_text": "text",
    "untranslated_text": "text-empty",
    "dynamic_text": "dynamic",
    "unowned_text": "unowned",
    "missing_code": "code",
    "untranslated_code": "code-empty",
    "unowned_code": "code-unowned",
}


def _filter(findings: Sequence[Finding], chosen: Sequence[Package] | None) -> list[Finding]:
    if chosen is None:
        return list(findings)
    names = {p.name for p in chosen}
    return [f for f in findings if f.package in names]


def report(
    analysis: Analysis,
    findings: Sequence[Finding],
    *,
    strict: bool,
    show_list: bool,
    by_package: bool,
    quiet: bool,
    stream: TextIO,
) -> int:
    """요약(언어·묶음별 건수)과 선택한 목록을 쓰고 종료 코드를 돌려준다."""
    config = analysis.config
    crawl = analysis.crawl

    def p(line: str = "") -> None:
        print(line, file=stream)

    if crawl is not None:
        p(
            f"S1 server crawl: {len(crawl.visited)} GET routes read, {len(crawl.skipped)} skipped, "
            f"{len(crawl.texts)} source-language strings in responses"
        )
        for failure in crawl.seed_failures:
            p(f"  seed failed: {failure}")
    else:
        p("S1 server crawl: skipped (--no-server)")
    static = analysis.static
    if static.models or static.files or static.python_files or static.unknown_models:
        python = f"{len(static.python_files)} python files, " if static.python_files else ""
        p(
            f"S1 static sources: {len(static.models)} schema models, {len(static.files)} data "
            f"files, {python}{len(static.result.texts)} source-language strings"
        )
        if static.unknown_models and not quiet:
            p(f"  models not in the schema document: {', '.join(static.unknown_models)}")
    if analysis.scan.errors:
        p(f"source scan: {len(analysis.scan.errors)} unreadable files")
        if not quiet:
            for error in analysis.scan.errors:
                p(f"  {error}")
    p(f"S2 codes: {len(analysis.codes)} codes found")

    counts = Counter((f.rule, f.language) for f in findings)
    columns = (
        [
            (rule, lang)
            for rule in ("missing_text", "untranslated_text")
            for lang in analysis.languages
            if lang != config.source_language
        ]
        + [(rule, None) for rule in ("dynamic_text", "unowned_text")]
        + [
            (rule, lang)
            for rule in ("missing_code", "untranslated_code")
            for lang in analysis.languages
        ]
        + [(rule, None) for rule in ("unowned_code",)]
    )
    p("totals:")
    for rule, lang in columns:
        p(f"  {rule}{'[' + lang + ']' if lang else ''}: {counts[(rule, lang)]}")
    for rule in (
        "stale_code",
        "placeholder_mismatch",
        "unknown_placeholder",
        "catalog_unregistered",
        "catalog_invalid",
    ):
        total = sum(n for (r, _), n in counts.items() if r == rule)
        p(f"  {rule}: {total}")

    def table(title: str, key: Callable[[Finding], str]) -> None:
        rows: dict[str, Counter[tuple[str, str | None]]] = {}
        for f in findings:
            rows.setdefault(key(f), Counter())[(f.rule, f.language)] += 1
        shown = [c for c in columns if any(r[c] for r in rows.values())]
        if not shown:
            return
        heads = [f"{_HEADS.get(r, r)}{'/' + lang if lang else ''}" for r, lang in shown]
        width = max([len(title), *map(len, rows)])
        p(f"{title:<{width}}  " + "  ".join(f"{h:>12}" for h in heads))
        for name in sorted(rows):
            p(f"{name:<{width}}  " + "  ".join(f"{rows[name][c]:>12}" for c in shown))

    groups = config.groups
    table("group", lambda f: group_of(analysis.package(f.package), groups))
    if by_package:
        table("package", lambda f: f.package or "(unowned)")

    errors = 0
    warnings = 0
    for f in findings:
        if severity_of(f, config, strict=strict) == "error":
            errors += 1
        else:
            warnings += 1
    if show_list:
        for f in sorted(findings, key=lambda f: (f.rule, f.package or "", f.language or "", f.key)):
            level = severity_of(f, config, strict=strict)
            lang = f"[{f.language}]" if f.language else ""
            p(
                f"{level} {f.rule}{lang} {f.package or '-'}: {_short(f.key)!r} — {f.message}"
                f"{' (' + f.where + ')' if f.where else ''}"
            )
    elif errors and not quiet:
        p("errors (use --list for all findings):")
        for f in findings:
            if severity_of(f, config, strict=strict) == "error":
                p(f"  {f.rule} {f.package or '-'}: {_short(f.key)!r} — {f.message}")
    p(f"{errors} errors, {warnings} warnings")
    return 1 if errors else 0


# ---------------------------------------------------------------- 뽑기


def _catalog_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise I18nToolError(f"cannot read catalog {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise I18nToolError(f"catalog {path} must be a JSON object")
    return data


def add_entries(path: Path, section: str, keys: Sequence[str]) -> int:
    """묶음 파일 구역에 빈 값 항목을 더한다(있는 키는 그대로). 더한 수를 돌려준다."""
    data = _catalog_document(path)
    entries = data.get(section)
    if entries is None:
        entries = {}
        ordered: dict[str, Any] = {}
        for name in (TEXT, CODES, NS):
            if name in data:
                ordered[name] = data[name]
            elif name == section:
                ordered[name] = entries
        ordered.update({k: v for k, v in data.items() if k not in ordered})
        data = ordered
    if not isinstance(entries, dict):
        raise I18nToolError(f"catalog {path}: '{section}' must be an object")
    added = 0
    for key in keys:
        if key not in entries:
            entries[key] = ""
            added += 1
    if added:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


_TABLE = re.compile(r"^\[", re.MULTILINE)


def _before_comments(text: str, pos: int) -> int:
    """``pos``(표 머리) 바로 위에 붙은 주석 줄들의 시작(그 주석은 그 표의 설명이다)."""
    while pos > 0:
        prev = text.rfind("\n", 0, pos - 1) + 1
        if not text[prev:pos].lstrip().startswith("#"):
            break
        pos = prev
    return pos


def register_catalog(pyproject: Path, name: str, module: str) -> bool:
    """``[project.entry-points."agent_console.message_catalogs"]``에 ``name = "module"``을 더한다.

    이미 그 모듈을 가리키는 항목이 있으면 아무것도 하지 않는다(False). 표가 없으면 첫 ``[tool.``·
    ``[dependency-groups]``·``[build-system]`` 표 앞에(그 표 바로 위 주석 줄보다 앞, 없으면 끝에)
    만든다.

    Raises:
        I18nToolError: 고친 결과가 TOML로 읽히지 않을 때(파일은 바꾸지 않는다).
    """
    text = pyproject.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    eps = data.get("project", {}).get("entry-points", {}).get(MESSAGE_CATALOGS_GROUP, {})
    if any(str(v).split(":", 1)[0] == module for v in eps.values()):
        return False
    line = f'{name} = "{module}"\n'
    header = f'[project.entry-points."{MESSAGE_CATALOGS_GROUP}"]'
    if header in text:
        start = text.index(header) + len(header)
        nl = text.index("\n", start) + 1 if "\n" in text[start:] else len(text)
        new = text[:nl] + line + text[nl:]
    else:
        block = f"{header}\n{line}\n"
        anchor = None
        for m in _TABLE.finditer(text):
            rest = text[m.start() :]
            if rest.startswith(("[dependency-groups]", "[build-system]", "[tool.")):
                anchor = _before_comments(text, m.start())
                break
        new = (
            text[:anchor] + block + text[anchor:]
            if anchor is not None
            else text.rstrip("\n") + "\n\n" + block
        )
    try:
        tomllib.loads(new)
    except tomllib.TOMLDecodeError as exc:
        raise I18nToolError(f"cannot add entry point to {pyproject}: {exc}") from exc
    pyproject.write_text(new, encoding="utf-8")
    return True


@dataclass(frozen=True, slots=True)
class ExtractPlan:
    """뽑기 결과(패키지 → 구역 → 키)."""

    entries: Mapping[str, Mapping[str, Sequence[str]]]
    skipped: Mapping[str, int]
    """뽑지 못한 규칙 → 수(값이 섞인 문구·맡을 패키지 모름)."""


def plan_extract(analysis: Analysis, lang: str, chosen: Sequence[Package] | None) -> ExtractPlan:
    """빠진 항목(``missing_text``·``missing_code``)을 맡을 패키지별로 모은다."""
    names = None if chosen is None else {p.name for p in chosen}
    entries: dict[str, dict[str, list[str]]] = {}
    skipped: Counter[str] = Counter()
    for f in analysis.findings:
        if names is not None and f.package not in names:
            continue
        if f.rule in ("dynamic_text", "unowned_text", "unowned_code"):
            skipped[f.rule] += 1
            continue
        if f.language != lang or f.package is None:
            continue
        section = {"missing_text": TEXT, "missing_code": CODES}.get(f.rule)
        if section is None:
            continue
        keys = entries.setdefault(f.package, {}).setdefault(section, [])
        if f.key not in keys:
            keys.append(f.key)
    return ExtractPlan(entries, dict(skipped))


def apply_extract(
    analysis: Analysis, plan: ExtractPlan, lang: str, *, dry_run: bool, stream: TextIO
) -> None:
    """계획대로 묶음 파일에 빈 값을 더하고, 묶음 entry point가 없으면 등록한다."""
    total = 0
    registered: list[str] = []
    for name in sorted(plan.entries):
        pkg = analysis.package(name)
        if pkg is None or pkg.import_name is None:
            print(f"  {name}: no import package under src/ — skipped", file=stream)
            continue
        folder = pkg.locales_dir()
        assert folder is not None
        path = folder / f"{lang}.json"
        sections = plan.entries[name]
        count = sum(len(keys) for keys in sections.values())
        if not dry_run:
            count = sum(add_entries(path, sec, keys) for sec, keys in sections.items())
            if register_catalog(pkg.root / "pyproject.toml", pkg.name, pkg.import_name):
                registered.append(pkg.name)
        total += count
        rel = f"{pkg.rel}/{path.relative_to(pkg.root).as_posix()}"
        detail = ", ".join(f"{sec} {len(keys)}" for sec, keys in sections.items())
        print(f"  {rel}: +{count} ({detail})", file=stream)
    verb = "would add" if dry_run else "added"
    print(f"{verb} {total} empty entries for '{lang}'", file=stream)
    for rule, n in sorted(plan.skipped.items()):
        print(f"not extracted: {rule} {n} (see `check --list`)", file=stream)
    if registered:
        print(
            f"registered catalog entry points in: {', '.join(registered)} "
            "(run `uv sync --all-packages` so the server sees them)",
            file=stream,
        )


# ---------------------------------------------------------------- CLI


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="i18n_tool", description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="i18n.yaml path")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="find missing server translations (S1~S3)")
    extract = sub.add_parser("extract", help="add missing entries as empty values")
    for cmd in (check, extract):
        cmd.add_argument(
            "--package",
            action="append",
            default=[],
            help="target package folder or distribution name (glob, repeatable)",
        )
        cmd.add_argument(
            "--no-server",
            action="store_true",
            help="skip S1 (no server assembly): codes and placeholders only",
        )
    check.add_argument("--strict", action="store_true", help="treat every finding as an error")
    check.add_argument("--list", action="store_true", help="print every finding")
    check.add_argument("--by-package", action="store_true", help="add a per-package table")
    check.add_argument("--quiet", action="store_true", help="summary only")
    extract.add_argument("--lang", required=True, help="language code of the catalog to fill")
    extract.add_argument("--dry-run", action="store_true", help="show what would be added")
    return parser


def main(argv: Sequence[str] | None = None, *, crawl_fn: CrawlFn | None = crawl_server) -> int:
    """명령 진입점(테스트는 ``crawl_fn``에 가짜 훑기를 넘긴다)."""
    args = _parser().parse_args(argv)
    root: Path = args.root.resolve()
    try:
        config = load_config(args.config)
        fn = None if args.no_server else crawl_fn
        if args.command == "extract":
            lang = str(args.lang)
            analysis = analyze(root, config, crawl_fn=fn, languages=[lang])
            chosen = select_packages(analysis.packages, args.package) if args.package else None
            plan = plan_extract(analysis, lang, chosen)
            apply_extract(analysis, plan, lang, dry_run=args.dry_run, stream=sys.stdout)
            return 0
        analysis = analyze(root, config, crawl_fn=fn)
        chosen = select_packages(analysis.packages, args.package) if args.package else None
        findings = _filter(analysis.findings, chosen)
        return report(
            analysis,
            findings,
            strict=args.strict,
            show_list=args.list,
            by_package=args.by_package,
            quiet=args.quiet,
            stream=sys.stdout,
        )
    except I18nToolError as exc:
        print(f"i18n: {exc}", file=sys.stderr)
        return 2


__all__ = [
    "Analysis",
    "ExtractPlan",
    "add_entries",
    "analyze",
    "apply_extract",
    "main",
    "plan_extract",
    "register_catalog",
    "report",
]

if __name__ == "__main__":
    sys.exit(main())
