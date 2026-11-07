"""드리프트 검사(``poe extdocs-check``): 생성 문서·가이드 절·링크·공개 가능 린트·문서 조각.

문서 폴더가 없으면(공개본) 호출하는 쪽이 건너뛴다(:func:`docs_present`).
"""

from __future__ import annotations

import doctest
import glob
import json
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from extdocs_common import (
    Collection,
    Finding,
    LintRule,
    SymbolError,
    SymbolResolver,
    ToolData,
)
from extdocs_generate import Generator
from extdocs_md import (
    FACTS_RE,
    TODO_MARK,
    anchors,
    fences,
    hand_text,
    lines,
    links,
    section_text,
)
from extdocs_points import check_points
from pydantic import BaseModel, ValidationError
from ruamel.yaml import YAML

VALIDATE_KEY = "extdocs:validate="
BLOCKING_CODES = ("schema-invalid", "slug-duplicate")
"""선언 형식 오류: 생성·문서 검사도 이 결과를 함께 낸다(생성 결과를 믿을 수 없다)."""


def docs_present(root: Path, data: ToolData) -> bool:
    return (root / data.docs_dir).is_dir()


def expand_globs(root: Path, patterns: Iterable[str]) -> list[Path]:
    out: set[Path] = set()
    for pattern in patterns:
        for hit in glob.glob(str(root / pattern), recursive=True):
            p = Path(hit)
            if p.is_file() and "node_modules" not in p.parts:
                out.add(p)
    return sorted(out)


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


# ---------------------------------------------------------------- 생성 문서 낡음


def check_drift(root: Path, planned: Mapping[str, str]) -> list[Finding]:
    out = []
    for key, content in planned.items():
        path = root / key
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current != content:
            out.append(
                Finding(
                    "generated-stale",
                    key,
                    "생성 문서 낡음 — `uv run poe extdocs`로 다시 만든다"
                    + ("(파일 없음)" if current is None else ""),
                )
            )
    return out


# ---------------------------------------------------------------- 가이드 절


def check_guides(root: Path, col: Collection, data: ToolData) -> list[Finding]:
    """선언마다 가이드 절이 있고 손글이 있고 생성 구간이 있는지, ``extdocs:todo``가 없는지."""
    out: list[Finding] = []
    docs = root / data.docs_dir
    texts: dict[str, str] = {}
    for path in sorted(docs.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        texts[path.relative_to(docs).as_posix()] = text
        for ln in lines(text):
            if TODO_MARK in ln.text:
                out.append(
                    Finding(
                        "guide-todo",
                        f"{_rel(root, path)}:{ln.number}",
                        "손글이 아직 없습니다(extdocs:todo 표지를 지우고 설명을 쓴다)",
                        missing="guides",
                    )
                )
    declared = {d.slug for d in col.declarations}
    for key, text in texts.items():
        for m in FACTS_RE.finditer(text):
            if m.group("slug") not in declared:
                out.append(
                    Finding(
                        "facts-orphan",
                        f"{data.docs_dir}/{key}",
                        f"선언 없는 지점 {m.group('slug')}의 생성 구간",
                    )
                )
    for decl in col.declarations:
        where = f"{decl.file} [{decl.slug}]"
        guide = decl.point.guide
        if not guide:
            out.append(Finding("guide-missing", where, "guide가 없습니다", missing="guides"))
            continue
        file_part, _, anchor = guide.partition("#")
        anchor = anchor or decl.slug
        page = texts.get(file_part)
        if page is None:
            out.append(
                Finding(
                    "guide-missing", where, f"가이드 파일이 없습니다: {file_part}", missing="guides"
                )
            )
            continue
        section = section_text(page, anchor)
        if section is None:
            out.append(
                Finding(
                    "guide-missing",
                    where,
                    f"가이드 절이 없습니다: {guide} — `uv run poe extdocs --scaffold`",
                    missing="guides",
                )
            )
            continue
        if not hand_text(section):
            out.append(
                Finding(
                    "guide-empty", where, f"가이드 절에 손글이 없습니다: {guide}", missing="guides"
                )
            )
        if decl.slug not in {m.group("slug") for m in FACTS_RE.finditer(section)}:
            out.append(
                Finding(
                    "facts-missing",
                    where,
                    f"가이드 절에 생성 구간이 없습니다: {guide} — `uv run poe extdocs --scaffold`",
                    missing="guides",
                )
            )
        if any(ex.kind == "snippet" for ex in decl.point.example) and not _has_checked_snippet(
            section
        ):
            out.append(
                Finding(
                    "snippet-missing",
                    where,
                    "예제 종류 snippet인데 절에 검증되는 조각"
                    "(>>> 또는 extdocs:validate)이 없습니다",
                    missing="examples",
                )
            )
    return out


def _has_checked_snippet(section: str) -> bool:
    return any(VALIDATE_KEY in f.info or ">>>" in f.body for f in fences(section))


# ---------------------------------------------------------------- 링크·앵커


def check_links(
    root: Path, files: Sequence[Path], *, pending: Iterable[Path] = ()
) -> list[Finding]:
    """문서 안 상대 링크·앵커를 푼다.

    ``pending``: 아직 쓰지 않았을 수 있는 영역 페이지 경로(``areas.yaml``의 파일). 그 파일로 가는
    링크가 깨지면 "아직 채우지 않음"(``guides``)으로 본다 — 지도·공통 가이드가 영역 페이지보다 먼저
    생겨도 ``--allow-missing guides``에서 경고로 낮아진다. 그 밖의 깨진 링크는 늘 오류다.
    """
    out: list[Finding] = []
    later = {p.resolve() for p in pending}
    anchor_cache: dict[Path, set[str]] = {}

    def anchors_of(path: Path) -> set[str]:
        if path not in anchor_cache:
            anchor_cache[path] = anchors(path.read_text(encoding="utf-8"))
        return anchor_cache[path]

    for path in files:
        text = path.read_text(encoding="utf-8")
        for link in links(text):
            target = link.target
            if ":" in target.split("#", 1)[0] and not target.startswith("#"):
                continue  # http:, mailto: 등 바깥 링크
            file_part, _, anchor = target.partition("#")
            dest = path if not file_part else (path.parent / file_part)
            where = f"{_rel(root, path)}:{link.line}"
            if not dest.exists():
                missing = "guides" if dest.resolve() in later else None
                note = " — 아직 쓰지 않은 영역 페이지" if missing else ""
                out.append(
                    Finding(
                        "link-broken", where, f"대상이 없습니다: {target}{note}", missing=missing
                    )
                )
                continue
            if (
                anchor
                and dest.is_file()
                and dest.suffix == ".md"
                and anchor not in anchors_of(dest)
            ):
                out.append(Finding("anchor-broken", where, f"앵커가 없습니다: {target}"))
    return out


# ---------------------------------------------------------------- 공개 가능 린트


def public_lint(
    root: Path, files: Sequence[Path], rules: Sequence[LintRule], *, warning: bool
) -> list[Finding]:
    out: list[Finding] = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
            for rule in rules:
                m = rule.pattern.search(line)
                if m:
                    out.append(
                        Finding(
                            f"public-{rule.id}",
                            f"{_rel(root, path)}:{number}",
                            f"{rule.message}: {m.group(0)!r}",
                            warning=warning,
                        )
                    )
    return out


# ---------------------------------------------------------------- 문서 조각


def run_doctests(root: Path, files: Sequence[Path], resolver: SymbolResolver) -> list[Finding]:
    """``>>>``가 든 코드 펜스를 파일마다 같은 이름 공간으로 doctest한다."""
    out: list[Finding] = []
    parser = doctest.DocTestParser()
    flags = doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE
    for path in files:
        blocks = [f for f in fences(path.read_text(encoding="utf-8")) if ">>>" in f.body]
        if not blocks:
            continue
        globs: dict[str, Any] = {"__name__": "__extdocs__"}
        for block in blocks:
            name = f"{_rel(root, path)}:{block.line}"
            test = parser.get_doctest(block.body, globs, name, str(path), block.line)
            runner = doctest.DocTestRunner(optionflags=flags, verbose=False)
            messages: list[str] = []
            with resolver.paths():
                runner.run(test, out=messages.append, clear_globs=False)
            # DocTest는 globs를 복사해 쓴다. 다음 블록이 앞 블록의 이름을 보게 되돌려 담는다.
            globs.update(test.globs)
            if runner.failures:
                detail = "".join(messages).strip().splitlines()
                out.append(
                    Finding(
                        "doctest-failed",
                        name,
                        f"doctest 실패 {runner.failures}건: " + " / ".join(detail[-6:]),
                    )
                )
    return out


def _parse_snippet(info: str, body: str) -> Any:
    lang = info.split()[0].lower() if info.split() else ""
    if lang in ("json", "jsonc"):
        return json.loads(body)
    if lang == "toml":
        return tomllib.loads(body)
    return YAML(typ="safe", pure=True).load(body)


def _extras(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, BaseModel):
        for key in sorted((value.model_extra or {}).keys()):
            found.append(f"{path}{key}")
        for name in type(value).model_fields:
            found.extend(_extras(getattr(value, name), f"{path}{name}."))
    elif isinstance(value, Mapping):
        for k, v in value.items():
            found.extend(_extras(v, f"{path}{k}."))
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            found.extend(_extras(v, f"{path}{i}."))
    return found


def validate_snippets(root: Path, files: Sequence[Path], resolver: SymbolResolver) -> list[Finding]:
    """`` ```yaml extdocs:validate=모듈:모델 `` 조각을 그 모델로 검증한다(모르는 키도 실패)."""
    out: list[Finding] = []
    for path in files:
        for block in fences(path.read_text(encoding="utf-8")):
            token = next((t for t in block.info.split() if t.startswith(VALIDATE_KEY)), None)
            if token is None:
                continue
            where = f"{_rel(root, path)}:{block.line}"
            symbol = token[len(VALIDATE_KEY) :]
            try:
                model = resolver.resolve(symbol)
            except SymbolError as exc:
                out.append(Finding("snippet-model-unresolved", where, str(exc)))
                continue
            if not (isinstance(model, type) and issubclass(model, BaseModel)):
                out.append(
                    Finding("snippet-model-invalid", where, f"{symbol}는 Pydantic 모델이 아닙니다")
                )
                continue
            try:
                parsed = _parse_snippet(block.info, block.body)
                instance = model.model_validate(parsed)
            except ValidationError as exc:
                msgs = "; ".join(
                    f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()
                )
                out.append(Finding("snippet-invalid", where, msgs))
                continue
            except Exception as exc:
                out.append(Finding("snippet-invalid", where, f"조각을 읽지 못했습니다: {exc}"))
                continue
            extras = _extras(instance)
            if extras:
                out.append(
                    Finding("snippet-unknown-keys", where, f"모르는 키: {', '.join(extras)}")
                )
    return out


def run_docs_checks(
    root: Path, col: Collection, data: ToolData, resolver: SymbolResolver, *, tool_dir: Path
) -> list[Finding]:
    """문서 폴더가 있을 때의 검사 전부(생성 낡음·가이드 절·링크·공개 가능 린트·조각)."""
    point_findings, facts = check_points(root, col, data, resolver, tool_dir=tool_dir)
    findings = [f for f in point_findings if f.code in BLOCKING_CODES]
    planned = Generator(col, facts, data, resolver).plan(root)
    findings += check_drift(root, planned)
    findings += check_guides(root, col, data)
    doc_files = expand_globs(root, data.s("docs_globs") or [])
    area_pages = [root / data.docs_dir / a.file for a in data.areas]
    findings += check_links(root, doc_files, pending=area_pages)
    lint_files = expand_globs(root, data.s("public_lint_globs") or [])
    findings += public_lint(root, lint_files, data.lint_rules, warning=False)
    findings += run_doctests(root, doc_files, resolver)
    findings += validate_snippets(root, doc_files, resolver)
    return findings


__all__ = [
    "BLOCKING_CODES",
    "VALIDATE_KEY",
    "check_drift",
    "check_guides",
    "check_links",
    "docs_present",
    "expand_globs",
    "public_lint",
    "run_docs_checks",
    "run_doctests",
    "validate_snippets",
]
