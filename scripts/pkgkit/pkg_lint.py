"""Python 패키지 이식성 정적 검사(design §3R.2.5 ``poe pkg-lint``, modularity §3.9.6).

"패키지 폴더 하나를 저장소 밖으로 가져가도 설치·테스트·실행된다"를 막는 것을 찾는다.
규칙은 :data:`PACKAGE_RULES`·:data:`REPO_RULES`에 등록돼 있고, 켜고 끄기는 ``pkgkit_py.toml``
``[pkg_lint.rules]``에서 한다. 각 규칙은 (문맥, 패키지) → 위반 목록인 순수 함수다.

사용::

    python scripts/pkgkit/pkg_lint.py [--root .] [--package NAME ...] [--path DIR ...]
                                      [--rule RULE ...] [--json] [--list-rules]

위반이 있으면 1, 설정 오류는 2로 끝난다.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import importlinter_sync
from pkgkit_common import (
    CommonSpec,
    Config,
    KindSpec,
    PkgkitError,
    PyPackage,
    discover,
    get_path,
    load_common,
    load_config,
    load_kinds,
    load_package,
    normalize_dist,
    read_toml,
    render,
    requirement_name,
    requirement_specifier,
    resolve_ranges,
    select,
    templates_dir,
    workspace_versions,
)
from pkgkit_template import read_templates, required_paths

REPO = "<repo>"


@dataclass(frozen=True)
class Violation:
    """위반 하나. ``package``는 패키지 상대 경로(저장소 전체 규칙이면 ``<repo>``)."""

    rule: str
    package: str
    message: str
    path: str = ""
    line: int | None = None

    def format(self) -> str:
        loc = self.package
        if self.path:
            loc = f"{loc}/{self.path}" if self.package != REPO else self.path
            if self.line:
                loc = f"{loc}:{self.line}"
        return f"{loc}: [{self.rule}] {self.message}"


@dataclass
class LintContext:
    """규칙이 공유하는 읽기 전용 정보."""

    root: Path
    cfg: Config
    kinds: Mapping[str, KindSpec]
    common: CommonSpec
    packages: Sequence[PyPackage]
    templates: Mapping[str, str] = field(default_factory=dict)

    @cached_property
    def root_pyproject(self) -> dict[str, Any]:
        return read_toml(self.root / "pyproject.toml")

    def template_pyproject(self, pkg: PyPackage) -> dict[str, Any]:
        """패키지 이름으로 렌더링한 템플릿 pyproject(도구 설정 비교용)."""
        text = self.templates["pyproject.toml"]
        values = {
            **self.cfg.template_vars,
            "year": "",
            "dist_name": pkg.dist_name,
            "import_name": pkg.import_name or "",
            "folder": pkg.path.name,
            "kind": pkg.kind or "",
            "version": "0.0.0",
            "description": "",
            "module_id": "",
            "dependencies_block": "dependencies = []",
            "dev_block": "dev = []",
            "entry_points_block": "",
        }
        return tomllib.loads(render(text, values))

    @cached_property
    def foreign_test_modules(self) -> dict[str, str]:
        """다른 패키지 ``tests/``의 도우미 모듈 이름 → 그 패키지 경로.

        ``test_*``·``conftest``는 뺀다.
        """
        out: dict[str, str] = {}
        for p in self.packages:
            for f in _py_files(p.path / "tests"):
                stem = f.stem
                if stem.startswith("test_") or stem == "conftest" or stem == "__init__":
                    continue
                out.setdefault(stem, p.rel)
        return out


PackageRule = Callable[[LintContext, PyPackage], list[Violation]]
RepoRule = Callable[[LintContext], list[Violation]]


def _py_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------- 패키지 규칙


def rule_layout(ctx: LintContext, pkg: PyPackage) -> list[Violation]:
    """패키지는 종류 폴더(``packages/py/<종류>/<패키지>``) 아래에 있어야 한다."""
    if pkg.kind is None:
        folders = ", ".join(sorted(k.folder for k in ctx.kinds.values()))
        return [Violation("layout", pkg.rel, f"종류 폴더 밖에 있습니다(종류 폴더: {folders})")]
    if pkg.kind not in ctx.kinds:
        return [Violation("layout", pkg.rel, f"모르는 종류 폴더입니다: {pkg.kind}")]
    return []


def rule_workspace_source(ctx: LintContext, pkg: PyPackage) -> list[Violation]:
    """패키지 파일에 ``[tool.uv.sources]``(workspace·path 등 저장소 전용 연결)가 없어야 한다(P1)."""
    sources = get_path(pkg.pyproject, "tool.uv.sources") or {}
    out = []
    for name, spec in sources.items():
        kind = ", ".join(sorted(spec)) if isinstance(spec, Mapping) else str(spec)
        out.append(
            Violation(
                "workspace-source",
                pkg.rel,
                f"[tool.uv.sources] {name} = {{{kind}}} — 소스 선언은 루트 pyproject.toml에만 둔다",
                "pyproject.toml",
            )
        )
    return out


def _strings(value: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, Mapping):
        for k, v in value.items():
            yield from _strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, f"{path}[{i}]")


def rule_outside_path(ctx: LintContext, pkg: PyPackage) -> list[Violation]:
    """pyproject 값의 상대 경로가 패키지 폴더 밖을 가리키면 안 된다(P2·P8)."""
    out = []
    base = pkg.path.resolve()
    for key, value in _strings(pkg.pyproject):
        candidates = [v for v in value.replace(",", " ").split() if ".." in v]
        for c in candidates:
            if not (c.startswith("..") or "/../" in c or c.startswith("./..")):
                continue
            target = (base / c).resolve()
            if target != base and base not in target.parents:
                out.append(
                    Violation(
                        "outside-path",
                        pkg.rel,
                        f"{key} = {c!r}가 패키지 밖을 가리킵니다",
                        "pyproject.toml",
                    )
                )
    return out


def _file_path_levels(node: ast.AST) -> int | None:
    """``Path(__file__)`` 기반 식이 파일 폴더에서 몇 단계 위인지(-1 = 파일 자체). 모르면 None."""
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("resolve", "absolute")
            and not node.args
        ):
            return _file_path_levels(func.value)
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else ""
        )
        if (
            name in ("Path", "PurePath")
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "__file__"
        ):
            return -1
        return None
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        inner = _file_path_levels(node.value)
        return None if inner is None else inner + 1
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "parents"
    ):
        inner = _file_path_levels(node.value.value)
        idx = node.slice
        if inner is None or not isinstance(idx, ast.Constant) or not isinstance(idx.value, int):
            return None
        return inner + 1 + idx.value
    return None


def find_root_lookups(tree: ast.AST, depth: int) -> list[tuple[int, int]]:
    """``Path(__file__)``에서 패키지 뿌리보다 위로 올라가는 식의 (줄, 단계) 목록.

    ``depth``는 파일 폴더가 패키지 뿌리에서 몇 단계 아래인지(``tests/x.py`` → 1).
    단계 ``u``는 파일 폴더 기준 위로 간 횟수이고, ``u > depth``면 패키지 밖이다.
    """
    hits: list[tuple[int, int]] = []
    seen: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute | ast.Subscript):
            continue
        u = _file_path_levels(node)
        if u is None or u <= depth:
            continue
        line = getattr(node, "lineno", 0)
        if line in seen:
            continue
        seen.add(line)
        hits.append((line, u))
    return sorted(hits)


def rule_root_lookup(ctx: LintContext, pkg: PyPackage) -> list[Violation]:
    """``Path(__file__).parents[N]``로 패키지 밖(저장소 루트)을 찾으면 안 된다(P5)."""
    out = []
    for f in _py_files(pkg.path / "src") + _py_files(pkg.path / "tests"):
        tree = _parse(f)
        if tree is None:
            continue
        rel = f.relative_to(pkg.path)
        for line, up in find_root_lookups(tree, len(rel.parts) - 1):
            out.append(
                Violation(
                    "root-lookup",
                    pkg.rel,
                    f"__file__에서 {up}단계 위로 올라가 패키지 밖을 봅니다",
                    rel.as_posix(),
                    line,
                )
            )
    return out


def imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    """(줄, 모듈 이름) 목록. 상대 import는 뺀다."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((node.lineno, a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append((node.lineno, node.module))
    return out


def rule_foreign_tests_import(ctx: LintContext, pkg: PyPackage) -> list[Violation]:
    """다른 패키지 ``tests/``의 모듈을 import하면 안 된다(공개 ``testing`` 하위 모듈을 쓴다, P2)."""
    own = {f.stem for f in _py_files(pkg.path / "tests")}
    foreign = ctx.foreign_test_modules
    out = []
    for f in _py_files(pkg.path / "src") + _py_files(pkg.path / "tests"):
        tree = _parse(f)
        if tree is None:
            continue
        for line, mod in imported_modules(tree):
            parts = mod.split(".")
            head = parts[0]
            owner = foreign.get(head)
            reason = None
            if owner and owner != pkg.rel and head not in own:
                reason = f"{owner}/tests의 {head}"
            elif head == "tests" or (len(parts) > 1 and parts[1] == "tests"):
                reason = f"{mod}(tests는 배포되지 않는다)"
            if reason:
                out.append(
                    Violation(
                        "foreign-tests-import",
                        pkg.rel,
                        f"{reason}를 import합니다 — 그 패키지의 공개 testing 모듈로 옮긴다",
                        f.relative_to(pkg.path).as_posix(),
                        line,
                    )
                )
    return out


def rule_required_files(ctx: LintContext, pkg: PyPackage) -> list[Violation]:
    """템플릿이 정한 필수 파일(README·CHANGELOG·LICENSE·py.typed·tests 등)이 있어야 한다."""
    if not pkg.import_name:
        return [Violation("required-files", pkg.rel, "src/<import 이름>/__init__.py가 없습니다")]
    kind = ctx.kinds.get(pkg.kind or "")
    return [
        Violation("required-files", pkg.rel, "필수 파일이 없습니다", rel)
        for rel in required_paths(ctx.common, kind, pkg.import_name)
        if not (pkg.path / rel).exists()
    ]


def compare_section(expected: Any, actual: Any, mode: str, prefix: str) -> list[str]:
    """도구 설정 비교. ``exact``는 키 집합까지 같아야 하고, ``superset``은 추가 키를 허용한다."""
    if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
        return [] if expected == actual else [f"{prefix}: 기대 {expected!r}, 실제 {actual!r}"]
    out: list[str] = []
    for key, ev in expected.items():
        path = f"{prefix}.{key}"
        if key not in actual:
            out.append(f"{path}: 없음(기대 {ev!r})")
        else:
            out.extend(compare_section(ev, actual[key], mode, path))
    if mode == "exact":
        out.extend(f"{prefix}.{k}: 템플릿에 없는 키" for k in actual if k not in expected)
    return out


def rule_tool_config(ctx: LintContext, pkg: PyPackage) -> list[Violation]:
    """패키지 도구 설정(pytest·mypy·ruff)과 dev 그룹이 템플릿과 같아야 한다(P2·P3·P4)."""
    tmpl = ctx.template_pyproject(pkg)
    out = []
    for section, mode in ctx.cfg.tool_sections.items():
        expected = get_path(tmpl, section)
        actual = get_path(pkg.pyproject, section)
        if actual is None:
            out.append(
                Violation("tool-config", pkg.rel, f"[{section}]가 없습니다", "pyproject.toml")
            )
            continue
        out.extend(
            Violation("tool-config", pkg.rel, msg, "pyproject.toml")
            for msg in compare_section(expected, actual, mode, section)
        )
    dev = {requirement_name(r) for r in (get_path(pkg.pyproject, "dependency-groups.dev") or [])}
    for req in ctx.common.dev_dependencies:
        if requirement_name(req) not in dev:
            out.append(
                Violation(
                    "tool-config",
                    pkg.rel,
                    f"[dependency-groups] dev에 {req}가 없습니다",
                    "pyproject.toml",
                )
            )
    return out


def _range_example(cfg: Config, name: str) -> str:
    """위반 문구의 범위 예(풀 수 없는 ``from-package``면 예 없이)."""
    try:
        return f"(예: {name}{cfg.range_for(name)})"
    except PkgkitError:
        return ""


def rule_internal_dep_range(ctx: LintContext, pkg: PyPackage) -> list[Violation]:
    """사내 의존은 이름과 버전 범위로 선언한다(E-7)."""
    out = []
    for req in pkg.dependencies() + pkg.dev_dependencies():
        name = requirement_name(req)
        if ctx.cfg.is_internal(name) and not requirement_specifier(req):
            out.append(
                Violation(
                    "internal-dep-range",
                    pkg.rel,
                    f"사내 의존 {name}에 버전 범위가 없습니다{_range_example(ctx.cfg, name)}",
                    "pyproject.toml",
                )
            )
    return out


def count_doctests(text: str) -> int:
    """README 텍스트의 doctest 예(``>>>`` 줄) 수."""
    return sum(1 for ln in text.splitlines() if ln.lstrip().startswith(">>> "))


_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def readme_section(text: str, heading: str) -> str | None:
    """마크다운에서 제목이 ``heading``으로 시작하는 절의 본문.

    하위 절을 포함하고, 같은 수준 이상의 다음 제목 전까지다.

    코드 울타리(```` ``` ````·``~~~``) 안의 ``#`` 줄은 제목으로 보지 않는다. 절이 없으면 None.
    """
    lines = text.splitlines()
    level: int | None = None
    body: list[str] = []
    fence: str | None = None
    for line in lines:
        m_fence = _FENCE.match(line)
        if m_fence:
            mark = m_fence.group(1)
            fence = None if fence == mark else (fence or mark)
        m = _HEADING.match(line) if fence is None and not m_fence else None
        if m:
            depth = len(m.group(1))
            if level is not None and depth <= level:
                break
            if level is None and m.group(2).strip().startswith(heading):
                level = depth
                continue
        if level is not None:
            body.append(line)
    return "\n".join(body) if level is not None else None


def rule_readme_doctest(ctx: LintContext, pkg: PyPackage) -> list[Violation]:
    """README "최소 사용"(설정 ``pkg_lint.readme_doctest_heading``) 절 안에 doctest가 하나 이상
    있어야 한다(E-9, 3R.6부터 기본 켬, 4R.18부터 그 절만 센다)."""
    readme = pkg.path / "README.md"
    if not readme.is_file():
        return []
    heading = ctx.cfg.readme_doctest_heading
    section = readme_section(readme.read_text(encoding="utf-8"), heading)
    if section is None:
        message = f'README에 "{heading}" 절이 없습니다(doctest로 실행되는 최소 사용 예를 둔다)'
    elif count_doctests(section) == 0:
        message = (
            f'README "{heading}" 절에 doctest(>>>)가 없습니다'
            "(최소 사용 예를 testing 가짜로 실행되게 쓴다)"
        )
    else:
        return []
    return [Violation("readme-doctest", pkg.rel, message, "README.md")]


# ---------------------------------------------------------------- 저장소 규칙


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {prefix: value}
    out: dict[str, Any] = {}
    for k, v in value.items():
        out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    return out


def rule_template_root_drift(ctx: LintContext) -> list[Violation]:
    """템플릿 도구 설정과 루트 도구 설정이 어긋나지 않아야 한다(집계 실행 전용 키 제외)."""
    out = []
    any_pkg = PyPackage(
        path=ctx.root,
        rel=REPO,
        dist_name="x",
        import_name="x",
        kind=None,
        is_app=False,
        pyproject={},
    )
    tmpl = ctx.template_pyproject(any_pkg)
    for section in ctx.cfg.tool_sections:
        root_sec = get_path(ctx.root_pyproject, section)
        if root_sec is None:
            continue
        ignore = set(ctx.cfg.drift_ignore_keys.get(section, []))
        exp = {k: v for k, v in _flatten(get_path(tmpl, section) or {}).items() if k not in ignore}
        act = {k: v for k, v in _flatten(root_sec).items() if k not in ignore}
        for key in sorted(set(exp) | set(act)):
            if exp.get(key) != act.get(key):
                out.append(
                    Violation(
                        "template-root-drift",
                        REPO,
                        f"[{section}] {key}: 템플릿 {exp.get(key)!r}, 루트 {act.get(key)!r}",
                        "pyproject.toml",
                    )
                )
    return out


def rule_root_source(ctx: LintContext) -> list[Violation]:
    """루트 ``[tool.uv.sources]``가 워크스페이스의 사내 프로젝트를 모두 workspace로 잇는다(P1)."""
    sources = get_path(ctx.root_pyproject, "tool.uv.sources") or {}
    declared = {normalize_dist(k): v for k, v in sources.items()}
    members = {p.dist_name for p in ctx.packages if ctx.cfg.is_internal(p.dist_name)}
    out = [
        Violation(
            "root-source",
            REPO,
            f"[tool.uv.sources]에 {name} = {{ workspace = true }}가 없습니다",
            "pyproject.toml",
        )
        for name in sorted(members)
        if not (isinstance(declared.get(name), Mapping) and declared[name].get("workspace") is True)
    ]
    out.extend(
        Violation(
            "root-source",
            REPO,
            f"[tool.uv.sources] {name}: 워크스페이스에 없는 사내 패키지입니다",
            "pyproject.toml",
        )
        for name in sorted(declared)
        if ctx.cfg.is_internal(name)
        and name not in members
        and isinstance(declared[name], Mapping)
        and declared[name].get("workspace") is True
    )
    return out


def rule_importlinter_drift(ctx: LintContext) -> list[Violation]:
    """import-linter 계약 목록이 패키지 폴더에서 생성한 것과 같아야 한다(importlinter_sync)."""
    if not (ctx.root / ctx.cfg.importlinter_rules).is_file():
        return [
            Violation(
                "importlinter-drift",
                REPO,
                "규칙 파일이 없습니다 — importlinter_sync.py --init으로 만든다",
                ctx.cfg.importlinter_rules,
            )
        ]
    return [
        Violation("importlinter-drift", REPO, msg, ctx.cfg.importlinter_target)
        for msg in importlinter_sync.check(ctx.root, ctx.cfg)
    ]


PACKAGE_RULES: dict[str, PackageRule] = {
    "layout": rule_layout,
    "workspace-source": rule_workspace_source,
    "outside-path": rule_outside_path,
    "root-lookup": rule_root_lookup,
    "foreign-tests-import": rule_foreign_tests_import,
    "required-files": rule_required_files,
    "tool-config": rule_tool_config,
    "internal-dep-range": rule_internal_dep_range,
    "readme-doctest": rule_readme_doctest,
}
REPO_RULES: dict[str, RepoRule] = {
    "template-root-drift": rule_template_root_drift,
    "root-source": rule_root_source,
    "importlinter-drift": rule_importlinter_drift,
}


def enabled_rules(cfg: Config, only: Sequence[str] = ()) -> list[str]:
    """실행할 규칙 이름. ``only``가 있으면 설정과 상관없이 그것만(모르는 이름은 오류)."""
    known = [*PACKAGE_RULES, *REPO_RULES]
    if only:
        unknown = [r for r in only if r not in known]
        if unknown:
            raise PkgkitError(f"모르는 규칙: {unknown} (알려진 규칙: {known})")
        return list(only)
    unknown = [r for r in cfg.lint_rules if r not in known]
    if unknown:
        raise PkgkitError(f"설정에 모르는 규칙: {unknown}")
    return [r for r in known if cfg.lint_rules.get(r, True)]


def lint(ctx: LintContext, targets: Sequence[PyPackage], rules: Sequence[str]) -> list[Violation]:
    """대상 패키지에 규칙을 돌린다(저장소 규칙은 한 번)."""
    out: list[Violation] = []
    for name in rules:
        if name in REPO_RULES:
            out.extend(REPO_RULES[name](ctx))
    for pkg in targets:
        for name in rules:
            if name in PACKAGE_RULES:
                out.extend(PACKAGE_RULES[name](ctx, pkg))
    return out


def build_context(root: Path, cfg: Config) -> LintContext:
    tdir = templates_dir(root, cfg)
    kinds = load_kinds(tdir, cfg.template_vars)
    packages = discover(root, cfg, kinds)
    templates = read_templates(tdir, next(iter(kinds)) if kinds else "")
    return LintContext(
        root=root,
        cfg=cfg,
        kinds=kinds,
        common=load_common(tdir),
        packages=packages,
        templates=templates,
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Python 패키지 이식성 정적 검사")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="저장소 루트(기본: 현재 폴더)")
    ap.add_argument("--config", type=Path, default=None, help="pkgkit_py.toml 경로")
    ap.add_argument("--package", action="append", default=[], help="이 패키지만(여러 번 가능)")
    ap.add_argument(
        "--path", action="append", type=Path, default=[], help="워크스페이스 밖 폴더도 검사"
    )
    ap.add_argument("--rule", action="append", default=[], help="이 규칙만(설정 무시)")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    ap.add_argument("--list-rules", action="store_true", help="규칙 목록과 켜짐 여부")
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    try:
        cfg = resolve_ranges(load_config(args.config), workspace_versions(root))
        if args.list_rules:
            on = set(enabled_rules(cfg))
            for name, fn in [*PACKAGE_RULES.items(), *REPO_RULES.items()]:
                doc = (fn.__doc__ or "").strip().splitlines()[0]
                print(f"{'on ' if name in on else 'off'}  {name:22} {doc}")
            return 0
        ctx = build_context(root, cfg)
        targets = [p for p in ctx.packages if not p.is_app]
        if args.package or args.path:
            targets = select(targets, args.package) if args.package else []
            kind_folders = {k.folder: k.name for k in ctx.kinds.values()}
            targets += [load_package(p.resolve(), root, cfg, kind_folders) for p in args.path]
        rules = enabled_rules(cfg, args.rule)
        if args.package or args.path:
            rules = [r for r in rules if r in PACKAGE_RULES] if not args.rule else rules
        violations = lint(ctx, targets, rules)
    except PkgkitError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([asdict(v) for v in violations], ensure_ascii=False, indent=2))
    else:
        for v in violations:
            print(v.format())
        print(f"pkg-lint: 패키지 {len(targets)}개, 규칙 {len(rules)}개, 위반 {len(violations)}건")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
