"""패키지 소스에서 원문 문구·코드를 모은다(AST·데이터 파일, design §I18N.10 S1·S2).

- 원문 문구: 문자열 상수(독스트링은 ``inspect.cleandoc``한 꼴과 첫 줄도 — Pydantic 설명이 앞의 꼴,
  요약만 내는 표가 뒤의 꼴이다)와
  데이터 파일(YAML·JSON) 안 문자열. 서버 응답의 문구가 어느 패키지 것인지 정하는 데 쓴다.
- 문구 틀: 원문 문자가 든 f-string과 ``{이름}`` 자리가 있는 상수. 값이 섞인 문구(정적 키가 될 수
  없는 것)를 찾는 데 쓴다.
- 코드: ``*Codes`` 클래스의 문자열 상수(정의), ``code=`` 인자(문자열·상수 참조)와 ``"code": "..."``
  사전 항목(사용). 같은 호출의 ``details=`` 사전 글자의 키는 그 코드의 예시 ``details`` 키다.
"""

from __future__ import annotations

import ast
import fnmatch
import inspect
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from i18n_common import Config, Package
from ruamel.yaml import YAML

from agent_console_i18n import LOCALES_DIR

_FIELD: Final = re.compile(r"\{[A-Za-z_][\w.]*(?:\s*,[^{}]*)?\}")


@dataclass(frozen=True, slots=True)
class CodeSite:
    """코드가 나온 곳 하나."""

    code: str
    package: str
    where: str
    definition: bool
    details: frozenset[str] | None = None
    """같은 호출의 ``details=`` 사전 글자 키(모르면 None)."""


@dataclass(frozen=True, slots=True)
class Template:
    """값이 섞이는 문구 틀(f-string·``{이름}`` 상수)."""

    pattern: re.Pattern[str]
    package: str
    where: str


@dataclass(slots=True)
class SourceScan:
    """대상 패키지 전체를 훑은 결과."""

    texts: dict[str, dict[str, str]] = field(default_factory=dict)
    """원문 문구 → {패키지: 처음 나온 곳}."""
    templates: list[Template] = field(default_factory=list)
    codes: list[CodeSite] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    """읽지 못한 파일(문법 오류 등) — 건너뛰고 적는다."""

    def add_text(self, text: str, package: str, where: str) -> None:
        self.texts.setdefault(text, {}).setdefault(package, where)

    def owners(self, text: str) -> Mapping[str, str]:
        """그 문구를 가진 패키지 → 위치."""
        return self.texts.get(text, {})

    def template_for(self, text: str) -> Template | None:
        """그 문구에 맞는 첫 틀."""
        for template in self.templates:
            if template.pattern.fullmatch(text):
                return template
        return None


def _matches(rel: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(rel, p) for p in patterns)


def package_files(pkg: Package, globs: Sequence[str], exclude: Sequence[str]) -> Iterator[Path]:
    """패키지 폴더 기준 glob에 맞는 파일(``locales/``·``exclude`` 제외, 경로 순)."""
    seen: set[Path] = set()
    for pattern in globs:
        for path in sorted(pkg.root.glob(pattern)):
            if path in seen or not path.is_file():
                continue
            rel = path.relative_to(pkg.root).as_posix()
            if f"/{LOCALES_DIR}/" in f"/{rel}" or _matches(rel, exclude):
                continue
            if "__pycache__" in path.parts:
                continue
            seen.add(path)
            yield path


def _template_regex(parts: Sequence[str | None]) -> re.Pattern[str]:
    """상수 조각과 값 자리(None) → 전체 일치 정규식."""
    return re.compile("".join(".+?" if p is None else re.escape(p) for p in parts), re.DOTALL)


def _format_parts(text: str) -> list[str | None]:
    parts: list[str | None] = []
    last = 0
    for m in _FIELD.finditer(text):
        parts.append(text[last : m.start()])
        parts.append(None)
        last = m.end()
    parts.append(text[last:])
    return parts


class _Visitor(ast.NodeVisitor):
    """파일 하나: 원문 문구·틀·코드 정의·코드 사용(참조는 나중에 풀이)."""

    def __init__(self, config: Config, package: str, rel: str) -> None:
        self.config = config
        self.package = package
        self.rel = rel
        self.texts: list[tuple[str, int]] = []
        self.templates: list[tuple[list[str | None], int]] = []
        self.class_consts: dict[tuple[str, str], str] = {}
        self.module_consts: dict[str, str] = {}
        self.code_defs: list[tuple[str, int]] = []
        self.code_uses: list[tuple[str | ast.expr, int, frozenset[str] | None]] = []
        self._class: list[str] = []
        self._fstring_parts: set[int] = set()

    # -- 문자열
    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and id(node) not in self._fstring_parts:
            value = node.value
            if self.config.is_source_text(value):
                self.texts.append((value, node.lineno))
                cleaned = inspect.cleandoc(value)
                if cleaned != value:
                    self.texts.append((cleaned, node.lineno))
                summary = cleaned.split("\n", 1)[0]
                if summary != cleaned and self.config.is_source_text(summary):
                    # 독스트링 첫 줄(요약)만 설명으로 내는 곳이 있다(예: 병합 전략 표).
                    self.texts.append((summary, node.lineno))
                if _FIELD.search(value):
                    self.templates.append((_format_parts(value), node.lineno))

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        parts: list[str | None] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                self._fstring_parts.add(id(value))
                parts.append(value.value)
            else:
                parts.append(None)
        if any(p is not None and self.config.is_source_text(p) for p in parts):
            self.templates.append((parts, node.lineno))
        self.generic_visit(node)

    # -- 코드 정의
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class.append(node.name)
        is_codes = bool(self.config.code_class_pattern.search(node.name))
        for stmt in node.body:
            target, value = _assigned(stmt)
            if target is None or not isinstance(value, ast.Constant):
                continue
            if isinstance(value.value, str) and self.config.is_code(value.value):
                self.class_consts[(node.name, target)] = value.value
                if is_codes:
                    self.code_defs.append((value.value, stmt.lineno))
        self.generic_visit(node)
        self._class.pop()

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            target, value = _assigned(stmt)
            if (
                target is not None
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and self.config.is_code(value.value)
            ):
                self.module_consts[target] = value.value
        self.generic_visit(node)

    # -- 코드 사용
    def visit_Call(self, node: ast.Call) -> None:
        code_kw = next((kw for kw in node.keywords if kw.arg == "code"), None)
        if code_kw is not None:
            spread = any(kw.arg is None for kw in node.keywords)
            details_kw = next((kw for kw in node.keywords if kw.arg == "details"), None)
            keys: frozenset[str] | None = None
            if details_kw is not None and not spread:
                keys = _dict_keys(details_kw.value)
            value = code_kw.value
            if isinstance(value, ast.Constant):
                if isinstance(value.value, str) and self.config.is_code(value.value):
                    self.code_uses.append((value.value, node.lineno, keys))
            elif isinstance(value, ast.Name | ast.Attribute):
                self.code_uses.append((value, node.lineno, keys))
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        shape = self.config.issue
        entries = {
            k.value: v
            for k, v in zip(node.keys, node.values, strict=True)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        code = entries.get(shape.code)
        if code is not None and shape.message in entries:
            spread = any(k is None for k in node.keys)
            details_node = entries.get(shape.details)
            keys = _dict_keys(details_node) if details_node is not None and not spread else None
            if isinstance(code, ast.Constant):
                if isinstance(code.value, str) and self.config.is_code(code.value):
                    self.code_uses.append((code.value, node.lineno, keys))
            elif isinstance(code, ast.Name | ast.Attribute):
                self.code_uses.append((code, node.lineno, keys))
        self.generic_visit(node)


def _assigned(stmt: ast.stmt) -> tuple[str | None, ast.expr | None]:
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        target = stmt.targets[0]
        if isinstance(target, ast.Name):
            return target.id, stmt.value
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return stmt.target.id, stmt.value
    return None, None


def _dict_keys(node: ast.expr) -> frozenset[str] | None:
    """사전 글자의 문자열 키(``**`` 펼침·문자열 아닌 키가 있으면 None)."""
    if not isinstance(node, ast.Dict):
        return None
    keys: list[str] = []
    for key in node.keys:
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            return None
        keys.append(key.value)
    return frozenset(keys)


def _data_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _data_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _data_strings(item)


def _load_data(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return YAML(typ="safe", pure=True).load(text)


def scan_packages(packages: Sequence[Package], config: Config) -> SourceScan:
    """대상 패키지의 소스·데이터 파일을 훑는다(읽기 실패는 ``errors``에 적고 건너뜀)."""
    scan = SourceScan()
    visitors: list[_Visitor] = []
    for pkg in packages:
        for path in package_files(pkg, config.python_globs, config.exclude_globs):
            rel = f"{pkg.rel}/{path.relative_to(pkg.root).as_posix()}"
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as exc:
                scan.errors.append(f"{rel}: {type(exc).__name__}: {exc}")
                continue
            visitor = _Visitor(config, pkg.name, rel)
            visitor.visit(tree)
            visitors.append(visitor)
        for path in package_files(pkg, config.data_globs, config.exclude_globs):
            rel = f"{pkg.rel}/{path.relative_to(pkg.root).as_posix()}"
            try:
                data = _load_data(path)
            except Exception as exc:  # 데이터 파일 하나가 깨져도 나머지는 본다
                scan.errors.append(f"{rel}: {type(exc).__name__}: {exc}")
                continue
            for text in _data_strings(data):
                if config.is_source_text(text):
                    scan.add_text(text, pkg.name, rel)
                    if _FIELD.search(text):
                        scan.templates.append(
                            Template(_template_regex(_format_parts(text)), pkg.name, rel)
                        )

    class_consts: dict[tuple[str, str], str] = {}
    module_consts: dict[str, set[str]] = {}
    for v in visitors:
        class_consts.update(v.class_consts)
        for name, value in v.module_consts.items():
            module_consts.setdefault(name, set()).add(value)

    for v in visitors:
        for text, line in v.texts:
            scan.add_text(text, v.package, f"{v.rel}:{line}")
        for parts, line in v.templates:
            scan.templates.append(Template(_template_regex(parts), v.package, f"{v.rel}:{line}"))
        for code, line in v.code_defs:
            scan.codes.append(CodeSite(code, v.package, f"{v.rel}:{line}", definition=True))
        for ref, line, keys in v.code_uses:
            for code in _resolve(ref, v, class_consts, module_consts):
                scan.codes.append(
                    CodeSite(code, v.package, f"{v.rel}:{line}", definition=False, details=keys)
                )
    return scan


def _resolve(
    ref: str | ast.expr,
    visitor: _Visitor,
    class_consts: Mapping[tuple[str, str], str],
    module_consts: Mapping[str, set[str]],
) -> list[str]:
    """``code=`` 값 → 코드(문자열 그대로, ``Class.ATTR``, 같은 파일·다른 파일의 모듈 상수)."""
    if isinstance(ref, str):
        return [ref]
    if isinstance(ref, ast.Attribute) and isinstance(ref.value, ast.Name):
        found = class_consts.get((ref.value.id, ref.attr))
        return [found] if found is not None else []
    if isinstance(ref, ast.Name):
        if ref.id in visitor.module_consts:
            return [visitor.module_consts[ref.id]]
        return sorted(module_consts.get(ref.id, ()))
    return []


__all__ = ["CodeSite", "SourceScan", "Template", "package_files", "scan_packages"]
