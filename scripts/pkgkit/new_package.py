"""템플릿으로 새 Python 패키지를 만든다(design §3R.2.5 ``poe new-package``).

``packages/py/<종류 폴더>/<NAME>``에 템플릿을 렌더링해 쓰고, 루트 workspace ``members``에
경로가 들어 있지 않으면 추가하고, 루트 ``[tool.uv.sources]``에
``<배포 이름> = { workspace = true }``가 없으면 추가하며(P1: 소스 선언은 루트에만),
import-linter 규칙 파일이 있으면 ``importlinter_sync``로 목록을 갱신한다.
종류(kind)는 ``templates/python/kinds/`` 폴더 이름이다.

사용::

    python scripts/pkgkit/new_package.py --kind feature ac-notes [--description TEXT]
        [--dep agent-console-registry ...] [--dev-dep NAME ...] [--id MODULE_ID] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
import tomllib
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

import importlinter_sync
from pkgkit_common import (
    CommonSpec,
    Config,
    KindSpec,
    PkgkitError,
    get_path,
    load_common,
    load_config,
    load_kinds,
    names_for,
    normalize_dist,
    read_toml,
    resolve_ranges,
    templates_dir,
    toml_value,
    workspace_members,
    workspace_versions,
)
from pkgkit_template import (
    TemplateInput,
    default_description,
    module_id_for,
    read_templates,
    render_tree,
    template_values,
)


@dataclass(frozen=True)
class NewPackagePlan:
    """만들 패키지: 위치(루트 상대), 파일 내용, 추가할 workspace member·루트 소스(없으면 None)."""

    rel: str
    files: Mapping[str, str]
    add_member: str | None
    add_source: str | None = None


def member_matches(rel: str, pattern: str) -> bool:
    """workspace members glob 한 개가 경로와 같은 깊이로 맞는지(``packages/py/*/*``)."""
    parts, pats = PurePosixPath(rel).parts, PurePosixPath(pattern).parts
    return len(parts) == len(pats) and all(
        fnmatchcase(a, b) for a, b in zip(parts, pats, strict=True)
    )


def plan_new_package(
    *,
    cfg: Config,
    kind: KindSpec,
    common: CommonSpec,
    templates: Mapping[str, str],
    folder_name: str,
    members: Sequence[str],
    description: str | None = None,
    dependencies: Sequence[str] = (),
    dev_dependencies: Sequence[str] = (),
    module_id: str | None = None,
    year: str,
    sources: Collection[str] = (),
) -> NewPackagePlan:
    """새 패키지 계획(순수). 파일은 쓰지 않는다.

    ``sources``는 루트 ``[tool.uv.sources]``에 이미 있는 배포 이름들이다(없으면 ``add_source``).
    """
    names = names_for(folder_name, cfg)
    rel = f"{cfg.package_root}/{kind.folder}/{names.folder}"
    inp = TemplateInput(
        names=names,
        kind=kind,
        common=common,
        description=description or default_description(kind, names.dist_name),
        version=cfg.initial_version,
        license=cfg.license,
        module_id=module_id or module_id_for(names, kind, cfg),
        dependencies=tuple(dependencies),
        dev_dependencies=tuple(dev_dependencies),
        year=year,
    )
    files = render_tree(templates, template_values(inp, cfg))
    tomllib.loads(files["pyproject.toml"])  # 렌더 결과가 TOML인지 확인
    add = None if any(member_matches(rel, m) for m in members) else rel
    have = {normalize_dist(s) for s in sources}
    src = None if names.dist_name in have else names.dist_name
    return NewPackagePlan(rel=rel, files=files, add_member=add, add_source=src)


_MEMBERS = re.compile(r"(?ms)^(\[tool\.uv\.workspace\][^\[]*?^members\s*=\s*\[)(.*?)(\])")


def add_workspace_member(pyproject_text: str, member: str) -> str:
    """루트 pyproject 텍스트의 ``[tool.uv.workspace] members``에 경로를 덧붙인다."""
    m = _MEMBERS.search(pyproject_text)
    if not m:
        raise PkgkitError("루트 pyproject.toml에서 [tool.uv.workspace] members를 찾지 못했습니다")
    body = m.group(2).rstrip()
    if body and not body.endswith(","):
        body += ","
    sep = " " if "\n" not in body else "\n    "
    new_body = f"{body}{sep}{toml_value(member)}" if body else toml_value(member)
    if "\n" in body:
        new_body += ",\n"
    return pyproject_text[: m.start(2)] + new_body + pyproject_text[m.end(2) :]


_TABLE = re.compile(r"(?m)^\s*\[")


def add_root_source(pyproject_text: str, dist_name: str) -> str:
    """루트 pyproject 텍스트의 ``[tool.uv.sources]``에 ``<dist> = { workspace = true }``를 더한다.

    표가 없으면 끝에 새로 만든다. 이미 있으면 그대로 돌려준다.
    """
    entry = f"{dist_name} = {{ workspace = true }}\n"
    header = re.search(r"(?m)^\[tool\.uv\.sources\][ \t]*\n", pyproject_text)
    if header is None:
        sep = "" if pyproject_text.endswith("\n") or not pyproject_text else "\n"
        return f"{pyproject_text}{sep}\n[tool.uv.sources]\n{entry}"
    nxt = _TABLE.search(pyproject_text, header.end())
    end = nxt.start() if nxt else len(pyproject_text)
    body = pyproject_text[header.end() : end]
    if re.search(rf"(?m)^\s*\"?{re.escape(dist_name)}\"?\s*=", body):
        return pyproject_text
    # 표의 마지막 값 줄 바로 뒤(뒤따르는 빈 줄·주석은 다음 표 몫으로 남긴다)
    lines = body.splitlines(keepends=True)
    keep = len(lines)
    while keep > 0 and (not lines[keep - 1].strip() or lines[keep - 1].lstrip().startswith("#")):
        keep -= 1
    head = "".join(lines[:keep])
    if head and not head.endswith("\n"):
        head += "\n"
    new_body = head + entry + "".join(lines[keep:])
    return pyproject_text[: header.end()] + new_body + pyproject_text[end:]


def write_plan(root: Path, plan: NewPackagePlan) -> list[Path]:
    """계획대로 파일을 쓴다. 대상 폴더가 이미 있으면 :class:`PkgkitError`."""
    target = root / plan.rel
    if target.exists():
        raise PkgkitError(f"이미 있습니다: {target}")
    written = []
    for rel, text in sorted(plan.files.items()):
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="템플릿으로 새 Python 패키지를 만든다")
    ap.add_argument("name", help="패키지 폴더 이름(예: ac-notes, ac-mod-notes)")
    ap.add_argument("--kind", required=True, help="종류(templates/python/kinds의 폴더 이름)")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="저장소 루트(기본: 현재 폴더)")
    ap.add_argument("--config", type=Path, default=None, help="pkgkit_py.toml 경로")
    ap.add_argument("--description", default=None, help="한 줄 설명")
    ap.add_argument(
        "--dep", action="append", default=[], help="추가 의존(사내는 이름만 쓰면 범위가 붙는다)"
    )
    ap.add_argument(
        "--dev-dep",
        action="append",
        default=[],
        help="추가 dev 의존(N3: 테스트에서 쓰는 사내 패키지)",
    )
    ap.add_argument(
        "--id", dest="module_id", default=None, help="모듈 id(모듈·연동 종류, 기본: 폴더 이름에서)"
    )
    ap.add_argument("--no-sync", action="store_true", help="import-linter 목록을 갱신하지 않는다")
    ap.add_argument("--dry-run", action="store_true", help="만들 파일만 출력")
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    try:
        cfg = resolve_ranges(load_config(args.config), workspace_versions(root))
        tdir = templates_dir(root, cfg)
        kinds = load_kinds(tdir, cfg.template_vars)
        if args.kind not in kinds:
            raise PkgkitError(f"모르는 종류: {args.kind} (가능: {', '.join(sorted(kinds))})")
        root_pyproject = root / "pyproject.toml"
        root_data = read_toml(root_pyproject)
        members, _ = workspace_members(root_data)
        sources = list(get_path(root_data, "tool.uv.sources") or {})
        plan = plan_new_package(
            cfg=cfg,
            kind=kinds[args.kind],
            common=load_common(tdir),
            templates=read_templates(tdir, args.kind),
            folder_name=args.name,
            members=members,
            description=args.description,
            dependencies=args.dep,
            dev_dependencies=args.dev_dep,
            module_id=args.module_id,
            year=str(datetime.date.today().year),
            sources=sources,
        )
        if args.dry_run:
            print(f"# {plan.rel}")
            for rel in sorted(plan.files):
                print(f"  {rel}")
            if plan.add_member:
                print(f"# workspace members에 추가: {plan.add_member}")
            if plan.add_source:
                print(f"# [tool.uv.sources]에 추가: {plan.add_source}")
            return 0
        for path in write_plan(root, plan):
            print(f"생성: {path.relative_to(root).as_posix()}")
        if plan.add_member:
            text = root_pyproject.read_text(encoding="utf-8")
            new_text = add_workspace_member(text, plan.add_member)
            tomllib.loads(new_text)
            root_pyproject.write_text(new_text, encoding="utf-8")
            print(f"workspace members에 추가: {plan.add_member}")
        if plan.add_source:
            text = root_pyproject.read_text(encoding="utf-8")
            new_text = add_root_source(text, plan.add_source)
            tomllib.loads(new_text)
            root_pyproject.write_text(new_text, encoding="utf-8")
            print(f"[tool.uv.sources]에 추가: {plan.add_source}")
        if not args.no_sync:
            if (root / cfg.importlinter_rules).is_file():
                code = importlinter_sync.main(
                    ["--root", str(root)] + (["--config", str(args.config)] if args.config else [])
                )
                if code != 0:
                    return code
            else:
                print(
                    f"참고: {cfg.importlinter_rules}가 없어 "
                    "import-linter 목록은 갱신하지 않았습니다"
                )
    except PkgkitError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
