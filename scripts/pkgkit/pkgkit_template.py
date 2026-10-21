"""Python 패키지 템플릿 렌더링(순수 함수). 파일을 쓰지 않고 ``{상대 경로: 내용}``만 계산한다.

템플릿 배치(``templates/python``):
- ``common.toml``: 공통 필수 파일·dev 도구
- ``common/**.tmpl``: 모든 종류에 들어가는 파일
- ``kinds/<kind>/kind.toml`` + ``kinds/<kind>/files/**.tmpl``: 종류별 데이터와 덧붙일 파일

파일 내용과 경로의 ``{{key}}``를 바꾸고 ``.tmpl``을 뗀다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pkgkit_common import (
    CommonSpec,
    Config,
    KindSpec,
    Names,
    PkgkitError,
    normalize_dist,
    render,
    requirement_name,
    requirement_specifier,
    toml_key,
    toml_list_block,
    toml_value,
)

TEMPLATE_SUFFIX = ".tmpl"


@dataclass(frozen=True)
class TemplateInput:
    """템플릿 하나를 렌더링하는 데 필요한 값."""

    names: Names
    kind: KindSpec
    common: CommonSpec
    description: str
    version: str
    license: str
    module_id: str
    year: str
    dependencies: tuple[str, ...] = ()
    dev_dependencies: tuple[str, ...] = ()


def module_id_for(names: Names, kind: KindSpec, cfg: Config) -> str:
    """폴더 이름에서 모듈 id를 정한다(폴더 접두사·종류 id 접두사를 뗀다)."""
    stem = names.folder
    if cfg.folder_prefix and stem.startswith(cfg.folder_prefix):
        stem = stem[len(cfg.folder_prefix) :]
    if kind.id_prefix and stem.startswith(kind.id_prefix):
        stem = stem[len(kind.id_prefix) :]
    return stem


def with_range(req: str, cfg: Config) -> str:
    """사내 의존에 범위가 없으면 설정 범위를 붙인다(extra ``[x]``는 유지). 외부 의존은 그대로."""
    name = requirement_name(req)
    if cfg.is_internal(name) and not requirement_specifier(req):
        extras = re.match(r"^\s*[A-Za-z0-9][A-Za-z0-9._-]*\s*(\[[^\]]*\])?", req)
        extra = extras.group(1) if extras and extras.group(1) else ""
        return f"{name}{extra.replace(' ', '')}{cfg.range_for(name)}"
    return req


def merge_requirements(*groups: Iterable[str]) -> list[str]:
    """의존 목록을 합친다. 같은 이름은 먼저 나온 것을 쓴다(순서 유지)."""
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for req in group:
            name = requirement_name(req)
            if name in seen:
                continue
            seen.add(name)
            out.append(req)
    return out


def template_values(inp: TemplateInput, cfg: Config) -> dict[str, str]:
    """자리표시자 값 표를 만든다(pyproject 블록 포함)."""
    base = {
        **cfg.template_vars,
        "year": inp.year,
        "dist_name": inp.names.dist_name,
        "import_name": inp.names.import_name,
        "folder": inp.names.folder,
        "kind": inp.kind.name,
        "version": inp.version,
        "license": inp.license,
        "description": inp.description.replace('"', "'"),
        "module_id": inp.module_id,
    }
    deps = [with_range(r, cfg) for r in merge_requirements(inp.kind.dependencies, inp.dependencies)]
    dev = [
        with_range(r, cfg)
        for r in merge_requirements(
            inp.common.dev_dependencies, inp.kind.dev_dependencies, inp.dev_dependencies
        )
    ]
    base["dependencies_block"] = (
        toml_list_block("dependencies", deps) if deps else "dependencies = []"
    )
    base["dev_block"] = toml_list_block("dev", dev)
    eps: list[str] = []
    for group, entries in inp.kind.entry_points.items():
        eps.append(f"\n[project.entry-points.{toml_value(group)}]")
        for key, value in entries.items():
            eps.append(f"{toml_key(render(key, base))} = {toml_value(render(value, base))}")
    base["entry_points_block"] = "\n".join(eps) + ("\n" if eps else "")
    return base


def template_files(tdir: Path, kind: str) -> dict[str, Path]:
    """렌더링할 템플릿 파일 목록 ``{상대 경로(.tmpl 뗌): 원본}``. 종류 파일이 공통을 덮는다."""
    sources = [tdir / "common", tdir / "kinds" / kind / "files"]
    out: dict[str, Path] = {}
    for src in sources:
        if not src.is_dir():
            continue
        for f in sorted(src.rglob(f"*{TEMPLATE_SUFFIX}")):
            rel = f.relative_to(src).as_posix()[: -len(TEMPLATE_SUFFIX)]
            out[rel] = f
    if not out:
        raise PkgkitError(f"템플릿 파일이 없습니다: {tdir}")
    return out


def render_tree(files: Mapping[str, str], values: Mapping[str, str]) -> dict[str, str]:
    """``{템플릿 경로: 템플릿 내용}`` → ``{결과 경로: 결과 내용}``."""
    return {render(rel, values): render(text, values) for rel, text in files.items()}


def read_templates(tdir: Path, kind: str) -> dict[str, str]:
    """템플릿 파일 내용을 읽는다(UTF-8)."""
    return {rel: p.read_text(encoding="utf-8") for rel, p in template_files(tdir, kind).items()}


def required_paths(common: CommonSpec, kind: KindSpec | None, import_name: str) -> list[str]:
    """pkg-lint가 확인할 필수 파일 경로(패키지 상대)."""
    values = {"import_name": import_name}
    items = list(common.required_files) + (list(kind.required_files) if kind else [])
    return [render(i, values) for i in items]


def default_description(kind: KindSpec, dist_name: str) -> str:
    return f"{kind.description} ({normalize_dist(dist_name)})"
