"""extdocs 공용: 설정·데이터 읽기, 선언 수집, 기호 풀기, 서술자 읽기, 검사 결과.

저장소 경로는 항상 인자(``root``)로 받는다. 도구가 아는 값은 ``extdocs.yaml``과 데이터 파일
(``areas.yaml``·``readme_sections.yaml``·``public_lint.yaml``·``templates/``)에 있다.
"""

from __future__ import annotations

import ast
import glob
import importlib
import json
import re
import sys
import time
import tomllib
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from extdocs_model import (
    ExampleMarker,
    ExtensionPoint,
    InternalGroup,
    InternalPort,
    PackageJsonTable,
    ToolTable,
)
from pydantic import ValidationError
from ruamel.yaml import YAML

TOOL_DIR = Path(__file__).resolve().parent
CONFIG_FILE = "extdocs.yaml"

MISSING_CATEGORIES = ("declarations", "examples", "guides")
"""``--allow-missing``로 경고로 낮출 수 있는 "아직 채우지 않음" 범주(단계적 적용).

- ``declarations``: 코드에 있는데 선언이 없는 그룹·포트, 예제가 가리키는데 선언이 없는 지점
- ``examples``: 예제가 하나도 없는 지점
- ``guides``: 가이드 절이 없거나 손글이 빈(``extdocs:todo``) 지점
"""


class ExtdocsError(Exception):
    """설정·입력이 잘못됐을 때(명령은 메시지를 출력하고 2로 끝난다)."""


# ---------------------------------------------------------------- 검사 결과


@dataclass(frozen=True)
class Finding:
    """검사 결과 하나.

    Args:
        code: 규칙 이름(예: ``group-undeclared``).
        where: 위치(저장소 상대 경로, 기호, slug 등).
        message: 사람이 읽는 설명.
        missing: "아직 채우지 않음" 범주(``MISSING_CATEGORIES``). ``--allow-missing``이 이 범주를
            허용하면 경고, 아니면 오류. None이면 늘 오류.
        warning: 늘 경고(실패하지 않음).
    """

    code: str
    where: str
    message: str
    missing: str | None = None
    warning: bool = False

    def is_error(self, allowed: Iterable[str]) -> bool:
        if self.warning:
            return False
        return not (self.missing is not None and self.missing in set(allowed))

    def render(self, allowed: Iterable[str]) -> str:
        level = "오류" if self.is_error(allowed) else "경고"
        return f"{level} [{self.code}] {self.where}: {self.message}"


def report(
    findings: Sequence[Finding], allowed: Iterable[str], out: Any = None, *, quiet: bool = False
) -> int:
    """결과를 출력하고 종료 코드(오류가 있으면 1)를 돌려준다.

    ``quiet``이면 경고는 줄마다 내지 않고 규칙별 건수만 낸다(오류는 늘 줄마다).
    """
    stream = out if out is not None else sys.stdout
    allowed_set = set(allowed)
    ordered = sorted(findings, key=lambda f: (f.is_error(allowed_set) is False, f.code, f.where))
    counts: dict[str, int] = {}
    for finding in ordered:
        if quiet and not finding.is_error(allowed_set):
            counts[finding.code] = counts.get(finding.code, 0) + 1
            continue
        print(finding.render(allowed_set), file=stream)
    for code, count in sorted(counts.items()):
        print(f"경고 [{code}] {count}건(줄마다 보려면 --quiet 없이)", file=stream)
    errors = sum(1 for f in findings if f.is_error(allowed_set))
    warnings = len(findings) - errors
    print(f"오류 {errors}건, 경고 {warnings}건", file=stream)
    return 1 if errors else 0


# ---------------------------------------------------------------- 설정·데이터


def _yaml() -> YAML:
    return YAML(typ="safe", pure=True)


def read_yaml(path: Path) -> Any:
    """YAML 파일 하나(safe). 없거나 형식이 틀리면 ExtdocsError."""
    try:
        with path.open(encoding="utf-8") as fh:
            return _yaml().load(fh)
    except FileNotFoundError as exc:
        raise ExtdocsError(f"파일이 없습니다: {path}") from exc
    except Exception as exc:
        raise ExtdocsError(f"YAML을 읽지 못했습니다: {path}: {exc}") from exc


@dataclass(frozen=True)
class Area:
    id: str
    title: str
    file: str


@dataclass(frozen=True)
class ReadmeSection:
    id: str
    title: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class LintRule:
    id: str
    message: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class ExampleRoot:
    glob: str
    language: str
    install: str
    remove: str


@dataclass(frozen=True)
class ToolData:
    """설정 + 데이터 파일 전부(도구가 아는 값)."""

    settings: Mapping[str, Any]
    areas: tuple[Area, ...]
    readme_sections: tuple[ReadmeSection, ...]
    lint_rules: tuple[LintRule, ...]
    registration_templates: Mapping[str, Mapping[str, str]]
    text: Mapping[str, Any]

    def s(self, key: str) -> Any:
        try:
            return self.settings[key]
        except KeyError as exc:
            raise ExtdocsError(f"설정 {key}가 없습니다({CONFIG_FILE})") from exc

    @property
    def docs_dir(self) -> str:
        return str(self.s("docs_dir"))

    @property
    def area_ids(self) -> set[str]:
        return {a.id for a in self.areas}

    @property
    def example_roots(self) -> tuple[ExampleRoot, ...]:
        return tuple(
            ExampleRoot(
                glob=str(r["glob"]),
                language=str(r.get("language", "")),
                install=str(r.get("install", "")),
                remove=str(r.get("remove", "")),
            )
            for r in self.s("example_roots") or []
        )

    def code(self, key: str) -> str:
        return str(self.s("code")[key])


def load_data(tool_dir: Path = TOOL_DIR, config: Path | None = None) -> ToolData:
    """``extdocs.yaml``과 데이터 파일을 읽는다(데이터 파일은 ``tool_dir`` 기준).

    Raises:
        ExtdocsError: 파일이 없거나 형식이 틀렸다.
    """
    settings = read_yaml(config or tool_dir / CONFIG_FILE) or {}
    areas_raw = (read_yaml(tool_dir / "areas.yaml") or {}).get("areas") or []
    sections_raw = (read_yaml(tool_dir / "readme_sections.yaml") or {}).get("sections") or []
    lint_raw = (read_yaml(tool_dir / "public_lint.yaml") or {}).get("rules") or []
    templates = (read_yaml(tool_dir / "templates" / "registration.yaml") or {}).get("kinds") or {}
    text = read_yaml(tool_dir / "templates" / "text.yaml") or {}
    try:
        areas = tuple(Area(str(a["id"]), str(a["title"]), str(a["file"])) for a in areas_raw)
        sections = tuple(
            ReadmeSection(str(s["id"]), str(s.get("title", s["id"])), tuple(s["aliases"]))
            for s in sections_raw
        )
        rules = tuple(
            LintRule(str(r["id"]), str(r["message"]), re.compile(str(r["pattern"])))
            for r in lint_raw
        )
    except (KeyError, TypeError, re.error) as exc:
        raise ExtdocsError(f"데이터 파일 형식 오류: {exc}") from exc
    if "_default" not in templates:
        raise ExtdocsError("templates/registration.yaml에 _default가 없습니다")
    return ToolData(
        settings=settings,
        areas=areas,
        readme_sections=sections,
        lint_rules=rules,
        registration_templates=templates,
        text=text,
    )


# ---------------------------------------------------------------- 워크스페이스


def read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ExtdocsError(f"TOML을 읽지 못했습니다: {path}: {exc}") from exc


def normalize_dist(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def rel(root: Path, path: Path) -> str:
    """저장소 상대 POSIX 경로(결정적 출력용)."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


@dataclass(frozen=True)
class Member:
    """워크스페이스 멤버 배포 하나."""

    name: str
    dir: Path
    pyproject: Mapping[str, Any]

    @property
    def src(self) -> Path:
        return self.dir / "src"

    def entry_points(self) -> dict[str, dict[str, str]]:
        eps = self.pyproject.get("project", {}).get("entry-points", {})
        return {str(g): {str(k): str(v) for k, v in t.items()} for g, t in eps.items()}


def workspace_members(root: Path) -> list[Member]:
    """루트 ``[tool.uv.workspace] members`` 중 ``[tool.uv.sources]``에서 ``workspace = true``로
    이은 배포만(이름 순). 루트 pyproject가 없으면 빈 목록."""
    root_py = root / "pyproject.toml"
    if not root_py.is_file():
        return []
    data = read_toml(root_py)
    uv = data.get("tool", {}).get("uv", {})
    sources = {
        normalize_dist(name)
        for name, spec in (uv.get("sources") or {}).items()
        if isinstance(spec, Mapping) and spec.get("workspace") is True
    }
    workspace = uv.get("workspace") or {}
    excluded = {
        p.resolve()
        for pattern in workspace.get("exclude") or []
        for p in (root.glob(pattern) if pattern else [])
    }
    found: dict[str, Member] = {}
    for pattern in workspace.get("members") or []:
        for candidate in sorted(root.glob(pattern)):
            pyproject = candidate / "pyproject.toml"
            if candidate.resolve() in excluded or not pyproject.is_file():
                continue
            table = read_toml(pyproject)
            name = normalize_dist(str(table.get("project", {}).get("name", "")))
            if name and name in sources:
                found[name] = Member(name=name, dir=candidate, pyproject=table)
    return [found[k] for k in sorted(found)]


# ---------------------------------------------------------------- 선언 수집


@dataclass(frozen=True)
class Declared:
    """선언 하나와 그 출처."""

    slug: str
    point: ExtensionPoint
    package: str
    file: str
    language: str  # "python" | "ts"


@dataclass(frozen=True)
class ExampleDir:
    """예제 폴더 하나."""

    path: str  # 저장소 상대
    name: str  # 배포·패키지 이름
    language: str
    marker: ExampleMarker | None
    install: str
    remove: str


@dataclass
class Collection:
    """선언·예제·내부 목록 수집 결과."""

    members: list[Member] = field(default_factory=list)
    declarations: list[Declared] = field(default_factory=list)
    internal_ports: list[tuple[InternalPort, str]] = field(default_factory=list)
    internal_groups: list[tuple[InternalGroup, str]] = field(default_factory=list)
    examples: list[ExampleDir] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def by_slug(self) -> dict[str, Declared]:
        return {d.slug: d for d in self.declarations}


def _schema_finding(where: str, exc: ValidationError) -> Finding:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"])
        parts.append(f"{loc}: {err['msg']}" if loc else str(err["msg"]))
    return Finding("schema-invalid", where, "; ".join(parts))


def _read_package_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExtdocsError(f"package.json을 읽지 못했습니다: {path}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def _glob_dirs(root: Path, patterns: Iterable[str]) -> list[Path]:
    out: set[Path] = set()
    for pattern in patterns:
        for hit in glob.glob(str(root / pattern)):
            p = Path(hit)
            if p.is_dir() and "node_modules" not in p.parts:
                out.add(p)
    return sorted(out)


def collect(root: Path, data: ToolData) -> Collection:
    """워크스페이스 멤버 pyproject·TS package.json·예제 폴더에서 선언을 모은다.

    형식 오류는 예외가 아니라 ``schema-invalid`` 결과로 담는다.
    """
    col = Collection(members=workspace_members(root))
    table_key = str(data.s("pyproject_tool_table"))
    for member in col.members:
        where = rel(root, member.dir / "pyproject.toml")
        raw = member.pyproject.get("tool", {}).get(table_key)
        if raw is None:
            continue
        try:
            table = ToolTable.model_validate(raw)
        except ValidationError as exc:
            col.findings.append(_schema_finding(where, exc))
            continue
        for slug, point in sorted(table.extension_points.root.items()):
            col.declarations.append(Declared(slug, point, member.name, where, "python"))
        col.internal_ports.extend((p, member.name) for p in table.internal_ports)
        col.internal_groups.extend((g, member.name) for g in table.internal_groups)

    ts_key = str(data.s("ts_table"))
    for pkg_dir in _glob_dirs(root, data.s("ts_package_globs") or []):
        pj = pkg_dir / "package.json"
        if not pj.is_file():
            continue
        pkg = _read_package_json(pj)
        raw = pkg.get(ts_key)
        if not isinstance(raw, dict) or "extensionPoints" not in raw:
            continue
        where = rel(root, pj)
        try:
            ts_table = PackageJsonTable.model_validate(raw)
        except ValidationError as exc:
            col.findings.append(_schema_finding(where, exc))
            continue
        name = str(pkg.get("name", pkg_dir.name))
        for slug, point in sorted(ts_table.extension_points.root.items()):
            col.declarations.append(Declared(slug, point, name, where, "ts"))

    for ex_root in data.example_roots:
        for ex_dir in _glob_dirs(root, [ex_root.glob]):
            example = _read_example(root, ex_dir, ex_root, data, col)
            if example is not None:
                col.examples.append(example)
    col.examples.sort(key=lambda e: e.path)
    col.declarations.sort(key=lambda d: (d.slug, d.file))
    return col


def _read_example(
    root: Path, ex_dir: Path, ex_root: ExampleRoot, data: ToolData, col: Collection
) -> ExampleDir | None:
    marker_raw: Any = None
    if (ex_dir / "pyproject.toml").is_file():
        table = read_toml(ex_dir / "pyproject.toml")
        name = str(table.get("project", {}).get("name", ex_dir.name))
        where = rel(root, ex_dir / "pyproject.toml")
        marker_raw = (
            table.get("tool", {}).get(str(data.s("pyproject_tool_table")), {}).get("example")
        )
    elif (ex_dir / "package.json").is_file():
        pkg = _read_package_json(ex_dir / "package.json")
        name = str(pkg.get("name", ex_dir.name))
        where = rel(root, ex_dir / "package.json")
        raw = pkg.get(str(data.s("ts_table")))
        marker_raw = raw.get("example") if isinstance(raw, dict) else None
    else:
        return None
    marker: ExampleMarker | None = None
    if marker_raw is not None:
        try:
            marker = ExampleMarker.model_validate(marker_raw)
        except ValidationError as exc:
            col.findings.append(_schema_finding(where, exc))
    path = rel(root, ex_dir)
    return ExampleDir(
        path=path,
        name=name,
        language=ex_root.language,
        marker=marker,
        install=ex_root.install.format(path=path, name=name),
        remove=ex_root.remove.format(path=path, name=name),
    )


# ---------------------------------------------------------------- 코드 쪽: 그룹 상수


@dataclass(frozen=True)
class GroupConstant:
    symbol: str  # 정의 모듈:이름
    value: str
    package: str


def _module_name(src: Path, path: Path) -> str:
    parts = list(path.relative_to(src).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def scan_group_constants(members: Sequence[Member], data: ToolData) -> list[GroupConstant]:
    """멤버 ``src`` 아래 모듈 수준 문자열 상수 중 이름·값 패턴이 맞는 것(정렬)."""
    name_re = re.compile(data.code("group_constant_name"))
    value_re = re.compile(data.code("group_value"))
    found: list[GroupConstant] = []
    for member in members:
        if not member.src.is_dir():
            continue
        for path in sorted(member.src.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError):
                continue
            module = _module_name(member.src, path)
            for node in tree.body:
                target: ast.expr | None = None
                value: ast.expr | None = None
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target, value = node.targets[0], node.value
                elif isinstance(node, ast.AnnAssign):
                    target, value = node.target, node.value
                if not isinstance(target, ast.Name) or not isinstance(value, ast.Constant):
                    continue
                if not isinstance(value.value, str):
                    continue
                if name_re.search(target.id) and value_re.search(value.value):
                    found.append(GroupConstant(f"{module}:{target.id}", value.value, member.name))
    return sorted(found, key=lambda g: (g.value, g.symbol))


@dataclass(frozen=True)
class EntryPointRef:
    group: str
    name: str
    value: str
    package: str


def entry_point_refs(members: Sequence[Member], pattern: str | None = None) -> list[EntryPointRef]:
    """멤버 pyproject ``[project.entry-points]``의 항목(그룹 패턴이 주어지면 맞는 것만)."""
    group_re = re.compile(pattern) if pattern else None
    out = [
        EntryPointRef(group, name, value, member.name)
        for member in members
        for group, table in member.entry_points().items()
        if group_re is None or group_re.search(group)
        for name, value in table.items()
    ]
    return sorted(out, key=lambda e: (e.group, e.name, e.package))


# ---------------------------------------------------------------- 기호 풀기

PY_SYMBOL = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_][\w.]*$")


def is_python_symbol(symbol: str) -> bool:
    return bool(PY_SYMBOL.match(symbol))


class SymbolError(Exception):
    """기호를 import하지 못했다."""


class SymbolResolver:
    """``모듈:이름`` 기호를 import해 객체를 돌려준다(결과 캐시).

    Args:
        extra_paths: import 경로 뒤에 덧붙일 폴더(워크스페이스 멤버 ``src`` — 설치본이 우선).
    """

    def __init__(self, extra_paths: Sequence[Path] = ()) -> None:
        self._extra = [str(p) for p in extra_paths]
        self._cache: dict[str, Any] = {}

    @contextmanager
    def paths(self) -> Iterator[None]:
        """이 구간 동안 덧붙인 import 경로를 쓴다(늦은 import가 있는 객체를 다룰 때)."""
        added = [p for p in self._extra if p not in sys.path]
        sys.path.extend(added)
        try:
            yield
        finally:
            for p in added:
                if p in sys.path:
                    sys.path.remove(p)

    def resolve(self, symbol: str) -> Any:
        """Raises: SymbolError — 형식이 틀렸거나 import·속성 찾기에 실패."""
        if symbol in self._cache:
            return self._cache[symbol]
        if not is_python_symbol(symbol):
            raise SymbolError(f"기호 형식이 아닙니다(모듈:이름): {symbol}")
        module_name, attr = symbol.split(":", 1)
        with self.paths():
            try:
                obj: Any = importlib.import_module(module_name)
                for part in attr.split("."):
                    obj = getattr(obj, part)
            except Exception as exc:
                raise SymbolError(f"{symbol}: {type(exc).__name__}: {exc}") from exc
        self._cache[symbol] = obj
        return obj


def first_doc_line(obj: Any) -> str:
    doc = getattr(obj, "__doc__", None)
    if not isinstance(doc, str) or isinstance(obj, (str, int, float, tuple, dict, list)):
        return ""
    for line in doc.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


# ---------------------------------------------------------------- 서버 모듈 서술자


@dataclass(frozen=True)
class PortInfo:
    name: str
    multi: bool


@dataclass(frozen=True)
class ModuleInfo:
    """서술자에서 읽은 것(build하지 않는다)."""

    entry: str
    package: str
    id: str
    kind: str
    web_roles: tuple[str, ...]
    contracts: tuple[tuple[str, str], ...]
    migrations: tuple[tuple[str, tuple[str, ...]], ...]
    provides: tuple[PortInfo, ...]
    requires: tuple[PortInfo, ...]
    optional: tuple[PortInfo, ...]


@dataclass
class ModuleScan:
    modules: list[ModuleInfo]
    findings: list[Finding]
    seconds: float


def _ports(value: Any) -> tuple[PortInfo, ...]:
    return tuple(
        PortInfo(str(getattr(p, "name", p)), bool(getattr(p, "multi", False))) for p in value or ()
    )


def load_modules(members: Sequence[Member], data: ToolData, resolver: SymbolResolver) -> ModuleScan:
    """멤버 pyproject의 서버 모듈 entry point에서 ``descriptor``만 읽는다."""
    group = data.code("modules_group")
    started = time.perf_counter()
    modules: list[ModuleInfo] = []
    findings: list[Finding] = []
    for ref in entry_point_refs(members):
        if ref.group != group:
            continue
        try:
            with resolver.paths():
                obj = resolver.resolve(ref.value.replace(" ", ""))
                module = obj() if isinstance(obj, type) else obj
                desc = module.descriptor
            modules.append(
                ModuleInfo(
                    entry=ref.name,
                    package=ref.package,
                    id=str(desc.id),
                    kind=str(desc.kind),
                    web_roles=tuple(str(r) for r in getattr(desc, "web_roles", ()) or ()),
                    contracts=tuple(sorted((getattr(desc, "contracts", None) or {}).items())),
                    migrations=tuple(
                        (str(m.name), tuple(str(s) for s in getattr(m, "scopes", ()) or ()))
                        for m in getattr(desc, "migrations", ()) or ()
                    ),
                    provides=_ports(desc.provides),
                    requires=_ports(desc.requires),
                    optional=_ports(desc.optional),
                )
            )
        except Exception as exc:
            findings.append(
                Finding(
                    "descriptor-load-failed",
                    f"{ref.package}:{ref.name}",
                    f"서술자를 읽지 못했습니다: {type(exc).__name__}: {exc}",
                )
            )
    modules.sort(key=lambda m: m.id)
    return ModuleScan(modules, findings, time.perf_counter() - started)


def member_src_paths(members: Sequence[Member]) -> list[Path]:
    return [m.src for m in members if m.src.is_dir()]


__all__ = [
    "MISSING_CATEGORIES",
    "TOOL_DIR",
    "Area",
    "Collection",
    "Declared",
    "EntryPointRef",
    "ExampleDir",
    "ExampleRoot",
    "ExtdocsError",
    "Finding",
    "GroupConstant",
    "LintRule",
    "Member",
    "ModuleInfo",
    "ModuleScan",
    "PortInfo",
    "ReadmeSection",
    "SymbolError",
    "SymbolResolver",
    "ToolData",
    "collect",
    "entry_point_refs",
    "first_doc_line",
    "is_python_symbol",
    "load_data",
    "load_modules",
    "member_src_paths",
    "normalize_dist",
    "read_toml",
    "read_yaml",
    "rel",
    "report",
    "scan_group_constants",
    "workspace_members",
]
