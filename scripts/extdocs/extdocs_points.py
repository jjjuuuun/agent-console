"""대조 검사(``poe extpoints-check``): 코드의 확장 지점과 패키지 선언을 맞춘다. 문서 없이 돈다.

검사 항목:

1. 그룹: 멤버 ``src``의 그룹 상수(이름·값 패턴은 ``extdocs.yaml`` ``code``) + 멤버 pyproject
   entry point 그룹 = 선언 ``registration.group`` + ``internal-groups``
2. 포트: 멤버 서버 모듈 서술자(``descriptor``만)의 provides·requires·optional = 선언
   ``registration.port`` + ``internal-ports``(사유 필수)
3. 선언의 Python 기호가 import된다(TS 기호 ``@pkg#이름``은 ``pnpm extdocs-check``가 본다)
4. 예제 경로가 있다, 예제 패키지의 ``points``와 선언이 서로 맞다, 예제가 하나 이상
5. 예제 README 필수 절(``readme_sections.yaml``)
6. slug 중복 없음, ``area``가 ``areas.yaml``에 있음
7. ``declaration.schema.json``이 모델과 같다
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from extdocs_common import (
    Collection,
    Declared,
    ExampleDir,
    Finding,
    GroupConstant,
    ModuleScan,
    SymbolError,
    SymbolResolver,
    ToolData,
    entry_point_refs,
    is_python_symbol,
    load_modules,
    scan_group_constants,
)
from extdocs_md import headings
from extdocs_model import schema_text

SCHEMA_FILE = "declaration.schema.json"


@dataclass
class CodeFacts:
    """대조·생성이 함께 쓰는 코드 쪽 사실."""

    constants: list[GroupConstant]
    ep_groups: dict[str, list[tuple[str, str]]]  # 그룹 → [(등록 이름, 배포)]
    modules: ModuleScan
    declared_groups: dict[str, str] = field(default_factory=dict)  # slug → 그룹 문자열
    declared_ports: dict[str, tuple[str, bool | None]] = field(
        default_factory=dict
    )  # slug → (이름, multi)

    @property
    def ports(self) -> dict[str, dict[str, Any]]:
        """포트 이름 → provides·requires·optional 모듈 id 목록·multi."""
        table: dict[str, dict[str, Any]] = {}
        for mod in self.modules.modules:
            for role, ports in (
                ("provides", mod.provides),
                ("requires", mod.requires),
                ("optional", mod.optional),
            ):
                for port in ports:
                    entry = table.setdefault(
                        port.name, {"provides": [], "requires": [], "optional": [], "multi": False}
                    )
                    entry[role].append(mod.id)
                    entry["multi"] = entry["multi"] or port.multi
        for entry in table.values():
            for role in ("provides", "requires", "optional"):
                entry[role] = sorted(set(entry[role]))
        return dict(sorted(table.items()))


def gather_code_facts(
    col: Collection, data: ToolData, resolver: SymbolResolver, findings: list[Finding]
) -> CodeFacts:
    """그룹 상수·entry point·서술자를 읽고 선언의 그룹·포트 기호를 푼다(문제는 ``findings``에)."""
    ep_pattern = data.code("entry_point_group")
    ep_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ref in entry_point_refs(col.members, ep_pattern):
        ep_groups[ref.group].append((ref.name, ref.package))
    facts = CodeFacts(
        constants=scan_group_constants(col.members, data),
        ep_groups={g: sorted(v) for g, v in sorted(ep_groups.items())},
        modules=load_modules(col.members, data, resolver),
    )
    findings.extend(facts.modules.findings)
    for decl in col.declarations:
        reg = decl.point.registration
        if reg.group:
            value = _group_value(reg.group, resolver, decl, findings)
            if value is not None:
                facts.declared_groups[decl.slug] = value
        if reg.port:
            port = _port_value(reg.port, resolver, decl, findings)
            if port is not None:
                facts.declared_ports[decl.slug] = (
                    port[0],
                    reg.multi if reg.multi is not None else port[1],
                )
    return facts


def _group_value(
    group: str, resolver: SymbolResolver, decl: Declared, findings: list[Finding]
) -> str | None:
    if not is_python_symbol(group):
        return group  # 그룹 문자열을 그대로 쓴 선언(바깥 플러그인 등)
    try:
        value = resolver.resolve(group)
    except SymbolError as exc:
        findings.append(Finding("symbol-unresolved", f"{decl.file} [{decl.slug}]", str(exc)))
        return None
    if not isinstance(value, str):
        findings.append(
            Finding("symbol-invalid", f"{decl.file} [{decl.slug}]", f"{group}는 문자열이 아닙니다")
        )
        return None
    return value


def _port_value(
    port: str, resolver: SymbolResolver, decl: Declared, findings: list[Finding]
) -> tuple[str, bool] | None:
    if not is_python_symbol(port):
        return port, False
    try:
        obj = resolver.resolve(port)
    except SymbolError as exc:
        findings.append(Finding("symbol-unresolved", f"{decl.file} [{decl.slug}]", str(exc)))
        return None
    name = getattr(obj, "name", None)
    if not isinstance(name, str):
        findings.append(
            Finding(
                "symbol-invalid", f"{decl.file} [{decl.slug}]", f"{port}는 포트(name)가 아닙니다"
            )
        )
        return None
    return name, bool(getattr(obj, "multi", False))


def _internal_value(value: str, resolver: SymbolResolver, attr: str | None) -> str:
    if not is_python_symbol(value):
        return value
    try:
        obj = resolver.resolve(value)
    except SymbolError:
        return value
    if attr is None:
        return obj if isinstance(obj, str) else value
    name = getattr(obj, attr, None)
    return name if isinstance(name, str) else value


# ---------------------------------------------------------------- 검사


def check_points(
    root: Path,
    col: Collection,
    data: ToolData,
    resolver: SymbolResolver,
    *,
    tool_dir: Path,
) -> tuple[list[Finding], CodeFacts]:
    """대조 검사 전체. (결과, 코드 사실)을 돌려준다."""
    findings: list[Finding] = list(col.findings)
    facts = gather_code_facts(col, data, resolver, findings)
    findings.extend(_check_schema_file(tool_dir))
    findings.extend(_check_slugs(col, data))
    findings.extend(_check_symbols(col, resolver))
    findings.extend(_check_groups(col, facts, resolver))
    findings.extend(_check_ports(col, facts, resolver))
    limit = float(data.s("descriptor_time_limit_seconds"))
    if facts.modules.seconds > limit:
        findings.append(
            Finding(
                "descriptor-slow",
                "server modules",
                f"서술자 대조가 {facts.modules.seconds:.1f}초 걸렸습니다(상한 {limit:g}초)",
            )
        )
    findings.extend(_check_examples(root, col, data))
    return findings, facts


def _check_schema_file(tool_dir: Path) -> list[Finding]:
    path = tool_dir / SCHEMA_FILE
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    if current != schema_text():
        return [
            Finding(
                "schema-drift",
                SCHEMA_FILE,
                "공용 JSON Schema가 모델과 다릅니다 — `python scripts/extdocs/extdocs.py schema`",
            )
        ]
    return []


def _check_slugs(col: Collection, data: ToolData) -> list[Finding]:
    out: list[Finding] = []
    seen: dict[str, list[str]] = defaultdict(list)
    for decl in col.declarations:
        seen[decl.slug].append(decl.file)
        if decl.point.area not in data.area_ids:
            out.append(
                Finding(
                    "area-unknown",
                    f"{decl.file} [{decl.slug}]",
                    f"영역 {decl.point.area}가 areas.yaml에 없습니다",
                )
            )
    for slug, files in sorted(seen.items()):
        if len(files) > 1:
            out.append(
                Finding("slug-duplicate", slug, f"여러 곳에서 선언: {', '.join(sorted(files))}")
            )
    return out


def _decl_symbols(decl: Declared) -> list[str]:
    symbols = list(decl.point.interface)
    for ex in decl.point.example:
        symbols.extend(ex.symbols)
    return symbols


def _check_symbols(col: Collection, resolver: SymbolResolver) -> list[Finding]:
    out: list[Finding] = []
    for decl in col.declarations:
        for symbol in _decl_symbols(decl):
            if "#" in symbol or decl.language == "ts":
                continue  # TS 기호는 pnpm extdocs-check가 본다
            try:
                resolver.resolve(symbol)
            except SymbolError as exc:
                out.append(Finding("symbol-unresolved", f"{decl.file} [{decl.slug}]", str(exc)))
    return out


def _check_groups(col: Collection, facts: CodeFacts, resolver: SymbolResolver) -> list[Finding]:
    out: list[Finding] = []
    code_groups: dict[str, str] = {}
    for const in facts.constants:
        code_groups.setdefault(const.value, f"상수 {const.symbol}({const.package})")
    for group, regs in facts.ep_groups.items():
        code_groups.setdefault(group, f"entry point({', '.join(sorted({p for _, p in regs}))})")
    declared = set(facts.declared_groups.values())
    internal: dict[str, str] = {}
    for item, package in col.internal_groups:
        value = _internal_value(item.group, resolver, None)
        internal[value] = package
        if value not in code_groups:
            out.append(
                Finding(
                    "internal-group-stale", package, f"내부 그룹 {item.group}가 코드에 없습니다"
                )
            )
    for group, where in sorted(code_groups.items()):
        if group in declared or group in internal:
            continue
        out.append(
            Finding(
                "group-undeclared",
                group,
                f"선언 없는 확장 지점(entry point 그룹, {where}) — 정의한 패키지에 "
                "[tool.agent-console.extension-points.<slug>]를 더하거나 "
                "internal-groups에 사유를 적는다",
                missing="declarations",
            )
        )
    return out


def _check_ports(col: Collection, facts: CodeFacts, resolver: SymbolResolver) -> list[Finding]:
    out: list[Finding] = []
    code_ports = facts.ports
    declared = {name for name, _ in facts.declared_ports.values()}
    internal: dict[str, str] = {}
    for item, package in col.internal_ports:
        name = _internal_value(item.port, resolver, "name")
        if name in internal:
            continue
        internal[name] = package
        if name not in code_ports:
            out.append(
                Finding(
                    "internal-port-stale", package, f"내부 포트 {item.port}가 서술자에 없습니다"
                )
            )
        if name in declared:
            out.append(
                Finding(
                    "internal-port-declared",
                    package,
                    f"포트 {name}가 확장 지점이자 내부 포트입니다",
                )
            )
    for slug, (name, _) in sorted(facts.declared_ports.items()):
        if name not in code_ports:
            out.append(Finding("port-unknown", slug, f"포트 {name}를 쓰는 서버 모듈이 없습니다"))
    for name, roles in code_ports.items():
        if name in declared or name in internal:
            continue
        users = ", ".join(sorted({*roles["provides"], *roles["requires"], *roles["optional"]}))
        out.append(
            Finding(
                "port-undeclared",
                name,
                f"선언 없는 확장 지점(포트, 모듈 {users}) — 선언하거나 [tool.agent-console] "
                "internal-ports에 사유를 적는다",
                missing="declarations",
            )
        )
    return out


def readme_missing_sections(readme: str, data: ToolData) -> list[str]:
    """README에 없는 필수 절 제목 목록(``readme_sections.yaml`` 순서)."""
    titles = [h.text for h in headings(readme) if h.level in (2, 3)]
    missing = []
    for section in data.readme_sections:
        if not any(alias in title for title in titles for alias in section.aliases):
            missing.append(section.title)
    return missing


def _check_examples(root: Path, col: Collection, data: ToolData) -> list[Finding]:
    out: list[Finding] = []
    by_path: dict[str, ExampleDir] = {e.path: e for e in col.examples}
    slugs = col.by_slug()
    shown: dict[str, set[str]] = defaultdict(set)  # 예제 경로 → 선언이 가리키는 slug
    for decl in col.declarations:
        where = f"{decl.file} [{decl.slug}]"
        if not decl.point.example:
            out.append(
                Finding(
                    "example-missing",
                    where,
                    "예제가 없습니다(예제 종류 4가지 중 하나 이상)",
                    "examples",
                )
            )
        for ex in decl.point.example:
            if ex.kind not in ("package", "reference") or not ex.path:
                continue
            target = root / ex.path
            if not target.exists():
                out.append(
                    Finding("example-path-missing", where, f"예제 경로가 없습니다: {ex.path}")
                )
                continue
            if ex.kind == "package":
                norm = Path(ex.path).as_posix().rstrip("/")
                if norm not in by_path:
                    out.append(
                        Finding(
                            "example-not-package",
                            where,
                            f"{ex.path}는 예제 폴더(example_roots)의 패키지가 아닙니다",
                        )
                    )
                    continue
                shown[norm].add(decl.slug)
    for example in col.examples:
        marker_points = set(example.marker.points) if example.marker else set()
        where = example.path
        for slug in sorted(marker_points - set(slugs)):
            out.append(
                Finding(
                    "example-point-undeclared",
                    where,
                    f"예제가 보이는 지점 {slug}의 선언이 없습니다",
                    missing="declarations",
                )
            )
        for slug in sorted(shown.get(example.path, set()) - marker_points):
            out.append(
                Finding(
                    "example-points-mismatch",
                    where,
                    f"지점 {slug} 선언이 이 예제를 가리키는데 "
                    "예제 [tool.agent-console.example] points에 없습니다",
                )
            )
        for slug in sorted((marker_points & set(slugs)) - shown.get(example.path, set())):
            out.append(
                Finding(
                    "example-points-mismatch",
                    where,
                    f'예제 points의 {slug} 선언에 이 예제(kind = "package", path)가 없습니다',
                )
            )
        if example.path in shown or (marker_points & set(slugs)):
            readme = root / example.path / "README.md"
            if not readme.is_file():
                out.append(Finding("readme-missing", where, "README.md가 없습니다"))
                continue
            missing = readme_missing_sections(readme.read_text(encoding="utf-8"), data)
            if missing:
                out.append(
                    Finding(
                        "readme-section-missing",
                        f"{where}/README.md",
                        f"필수 절 없음: {', '.join(missing)}",
                    )
                )
    return out


def code_points_summary(facts: CodeFacts) -> str:
    """사람이 읽는 한 줄 요약."""
    groups = {c.value for c in facts.constants} | set(facts.ep_groups)
    return (
        f"그룹 {len(groups)}개, 서버 모듈 {len(facts.modules.modules)}개, "
        f"포트 {len(facts.ports)}개(서술자 {facts.modules.seconds:.2f}초)"
    )


__all__ = [
    "SCHEMA_FILE",
    "CodeFacts",
    "check_points",
    "code_points_summary",
    "gather_code_facts",
    "readme_missing_sections",
]
