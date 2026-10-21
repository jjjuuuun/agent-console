"""import-linter 계약의 패키지 목록을 패키지 폴더에서 생성한다(modularity §3.7, design §3R.2.5).

규칙은 데이터 파일(기본 ``importlinter.rules.toml``)에 두고, 목록 자리에는 그룹을 쓴다::

    root_packages = ["@all"]

    [options]                       # [tool.importlinter]에 그대로 들어가는 다른 키
    include_external_packages = true

    [groups]                        # 사용자 그룹(다른 그룹·빼기 사용 가능)
    libraries = ["@feature", "!agent_console_store"]

    [[contracts]]
    name = "기능 모듈은 서로 독립"
    type = "independence"
    modules = ["@module"]

목록 항목: ``@그룹``(펼침), ``@그룹.하위``(그룹의 각 패키지 + ``.하위``, 예: ``@module.ports``),
``!이름``·``!@그룹``(빼기), 그 밖은 이름 그대로.
import 식 목록(기본 ``ignore_imports``)의 ``A -> B``는 양쪽의 ``@그룹[.하위]``를 펼친 모든 조합이
된다(예: ``"** -> @module.ports"``).
기본 그룹: ``@all``(패키지+앱), ``@packages``(앱 제외), ``@app``,
종류마다 ``@<kind>``(템플릿 ``kinds/`` 폴더 이름).
``forbidden`` 계약은 ``forbidden_modules``에서 ``source_modules``를 자동으로 뺀다.
펼친 목록이 비는 계약(독립 계약은 2개 미만)은 건너뛰고 알린다
(아직 없는 종류를 미리 적어 둘 수 있다).

결과는 대상 ``pyproject.toml``의 ``[tool.importlinter]`` 영역(표식 줄 사이, 표식이 없으면 기존
``[tool.importlinter*]`` 표들)을 바꾼다. ``--check``는 쓰지 않고 내용(의미) 차이만 보고한다.

사용::

    python scripts/pkgkit/importlinter_sync.py [--root .] [--check] [--init [--force]]
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pkgkit_common import (
    Config,
    PkgkitError,
    PyPackage,
    discover,
    get_path,
    load_config,
    load_kinds,
    read_toml,
    templates_dir,
    toml_key,
    toml_list_block,
    toml_value,
)

BEGIN_MARK = "# >>> pkgkit:importlinter"
END_MARK = "# <<< pkgkit:importlinter"
HEADER_NOTE = (
    "# 이 영역은 scripts/pkgkit/importlinter_sync.py가 {rules}에서 생성한다. 직접 고치지 않는다."
)
DEFAULT_EXPAND_KEYS = ("source_modules", "forbidden_modules", "modules")
DEFAULT_EXPAND_IMPORT_KEYS = ("ignore_imports",)
IMPORT_ARROW = "->"


@dataclass(frozen=True)
class SyncResult:
    """생성 결과: ``[tool.importlinter]`` 표(의미)와 건너뛴 계약 이름."""

    table: dict[str, Any]
    skipped: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 그룹


def builtin_groups(packages: Iterable[PyPackage], kinds: Iterable[str]) -> dict[str, list[str]]:
    """패키지 목록에서 기본 그룹(``all``·``packages``·``app``·종류별)을 만든다. import 이름 정렬."""
    groups: dict[str, list[str]] = {"all": [], "packages": [], "app": []}
    for k in kinds:
        groups.setdefault(k, [])
    for p in packages:
        if not p.import_name:
            continue
        groups["all"].append(p.import_name)
        if p.is_app:
            groups["app"].append(p.import_name)
        else:
            groups["packages"].append(p.import_name)
            if p.kind:
                groups.setdefault(p.kind, []).append(p.import_name)
    return {k: sorted(set(v)) for k, v in groups.items()}


def expand(
    items: Sequence[str],
    groups: Mapping[str, Sequence[str]],
    user_groups: Mapping[str, Sequence[str]],
    _stack: tuple[str, ...] = (),
) -> list[str]:
    """목록 항목을 펼친다(순서 유지·중복 제거). 모르는 그룹·순환은 :class:`PkgkitError`."""
    out: list[str] = []

    def resolve(ref: str) -> list[str]:
        name, _, suffix = ref[1:].partition(".")
        if name in _stack:
            raise PkgkitError(f"그룹 순환: {' -> '.join((*_stack, name))}")
        if name in user_groups:
            found = expand(user_groups[name], groups, user_groups, (*_stack, name))
        elif name in groups:
            found = list(groups[name])
        else:
            raise PkgkitError(f"모르는 그룹: {ref}")
        return [f"{m}.{suffix}" for m in found] if suffix else found

    for raw in items:
        if not isinstance(raw, str):
            raise PkgkitError(f"목록 항목은 문자열이어야 합니다: {raw!r}")
        if raw.startswith("!"):
            target = raw[1:]
            drop = set(resolve(target)) if target.startswith("@") else {target}
            out = [x for x in out if x not in drop]
        elif raw.startswith("@"):
            out.extend(x for x in resolve(raw) if x not in out)
        elif raw not in out:
            out.append(raw)
    return out


def expand_imports(
    items: Sequence[str],
    groups: Mapping[str, Sequence[str]],
    user_groups: Mapping[str, Sequence[str]],
) -> list[str]:
    """import 식 목록(``A -> B``)을 펼친다. 양쪽의 ``@그룹[.하위]``는 모든 조합이 된다."""
    out: list[str] = []
    for raw in items:
        if not isinstance(raw, str):
            raise PkgkitError(f"목록 항목은 문자열이어야 합니다: {raw!r}")
        left, arrow, right = raw.partition(IMPORT_ARROW)
        if not arrow:
            raise PkgkitError(f"import 식에는 {IMPORT_ARROW!r}가 필요합니다: {raw!r}")
        sides = [
            expand([side.strip()], groups, user_groups)
            if side.strip().startswith("@")
            else [side.strip()]
            for side in (left, right)
        ]
        for a in sides[0]:
            for b in sides[1]:
                item = f"{a} {IMPORT_ARROW} {b}"
                if item not in out:
                    out.append(item)
    return out


# ---------------------------------------------------------------- 생성(순수)


def build_table(rules: Mapping[str, Any], groups: Mapping[str, Sequence[str]]) -> SyncResult:
    """규칙 데이터 + 그룹 → ``[tool.importlinter]`` 표."""
    user_groups = rules.get("groups", {})
    clash = set(user_groups) & set(groups)
    if clash:
        raise PkgkitError(f"사용자 그룹 이름이 기본 그룹과 겹칩니다: {sorted(clash)}")
    expand_keys = tuple(get_path(rules, "sync.expand_keys") or DEFAULT_EXPAND_KEYS)
    import_keys = tuple(get_path(rules, "sync.expand_import_keys") or DEFAULT_EXPAND_IMPORT_KEYS)
    table: dict[str, Any] = {
        "root_packages": expand(rules.get("root_packages", ["@all"]), groups, user_groups)
    }
    table.update(rules.get("options", {}))
    contracts: list[dict[str, Any]] = []
    skipped: list[str] = []
    for raw in rules.get("contracts", []):
        if "name" not in raw or "type" not in raw:
            raise PkgkitError(f"계약에는 name·type이 필요합니다: {raw!r}")
        c: dict[str, Any] = {}
        for key, value in raw.items():
            if key in expand_keys and isinstance(value, list):
                c[key] = expand(value, groups, user_groups)
            elif key in import_keys and isinstance(value, list):
                c[key] = expand_imports(value, groups, user_groups)
            else:
                c[key] = value
        if c["type"] == "forbidden" and "source_modules" in c and "forbidden_modules" in c:
            src = set(c["source_modules"])
            c["forbidden_modules"] = [m for m in c["forbidden_modules"] if m not in src]
        if _is_empty(c, expand_keys):
            skipped.append(c["name"])
            continue
        contracts.append(c)
    table["contracts"] = contracts
    return SyncResult(table=table, skipped=skipped)


def _is_empty(contract: Mapping[str, Any], expand_keys: Iterable[str]) -> bool:
    for key in expand_keys:
        value = contract.get(key)
        if not isinstance(value, list):
            continue
        minimum = 2 if contract["type"] == "independence" and key == "modules" else 1
        if len(value) < minimum:
            return True
    return False


def render_table(table: Mapping[str, Any], rules_name: str) -> str:
    """표 → TOML 텍스트(표식 줄 포함)."""
    lines = [BEGIN_MARK, HEADER_NOTE.format(rules=rules_name), "[tool.importlinter]"]
    for key, value in table.items():
        if key == "contracts":
            continue
        lines.append(_kv(key, value))
    for c in table.get("contracts", []):
        lines.append("")
        lines.append("[[tool.importlinter.contracts]]")
        lines.extend(_kv(k, v) for k, v in c.items())
    lines.append(END_MARK)
    return "\n".join(lines) + "\n"


def _kv(key: str, value: Any) -> str:
    if isinstance(value, list) and len(value) > 3:
        return toml_list_block(key, value)
    return f"{toml_key(key)} = {toml_value(value)}"


def find_region(text: str) -> tuple[int, int] | None:
    """대상 텍스트에서 바꿀 줄 범위 ``[시작, 끝)``.

    표식이 있으면 표식 사이(포함), 없으면 ``[tool.importlinter*]`` 표들.
    """
    lines = text.splitlines(keepends=True)
    begin = next((i for i, ln in enumerate(lines) if ln.strip() == BEGIN_MARK), None)
    if begin is not None:
        end = next((i for i in range(begin, len(lines)) if lines[i].strip() == END_MARK), None)
        if end is None:
            raise PkgkitError(f"시작 표식만 있고 끝 표식({END_MARK})이 없습니다")
        return begin, end + 1
    start = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("[") and "tool.importlinter" in s.split("]")[0]:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        s = lines[i].strip()
        if s.startswith("[") and "tool.importlinter" not in s.split("]")[0]:
            end = i
            break
    # 다음 표 앞의 주석·빈 줄은 다음 표 몫으로 남긴다.
    while end > start + 1 and (
        not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")
    ):
        end -= 1
    return start, end


def replace_region(text: str, block: str) -> str:
    """대상 텍스트의 importlinter 영역을 ``block``으로 바꾼다(없으면 끝에 덧붙인다)."""
    region = find_region(text)
    lines = text.splitlines(keepends=True)
    if region is None:
        sep = "" if text.endswith("\n") or not text else "\n"
        return f"{text}{sep}\n{block}"
    start, end = region
    return "".join(lines[:start]) + block + "".join(lines[end:])


def diff_tables(expected: Mapping[str, Any], actual: Mapping[str, Any] | None) -> list[str]:
    """두 ``[tool.importlinter]`` 표의 의미 차이(사람이 읽는 문장 목록). 같으면 빈 목록."""
    if actual is None:
        return ["대상에 [tool.importlinter]가 없습니다"]
    out: list[str] = []
    exp_root = set(expected.get("root_packages", []))
    act_root = set(actual.get("root_packages", []))
    for m in sorted(exp_root - act_root):
        out.append(f"root_packages에 빠짐: {m}")
    for m in sorted(act_root - exp_root):
        out.append(f"root_packages에 남는 것: {m}")
    for key in sorted((set(expected) | set(actual)) - {"root_packages", "contracts"}):
        if expected.get(key) != actual.get(key):
            out.append(f"옵션 {key}: 기대 {expected.get(key)!r}, 실제 {actual.get(key)!r}")
    exp_c = {c["name"]: c for c in expected.get("contracts", [])}
    act_c = {c.get("name"): c for c in actual.get("contracts", [])}
    for name in exp_c.keys() - act_c.keys():
        out.append(f"계약 빠짐: {name}")
    for name in act_c.keys() - exp_c.keys():
        out.append(f"규칙에 없는 계약: {name}")
    for name in sorted(exp_c.keys() & act_c.keys(), key=str):
        e, a = exp_c[name], act_c[name]
        for key in sorted(set(e) | set(a)):
            ev, av = e.get(key), a.get(key)
            if isinstance(ev, list) and isinstance(av, list) and key != "layers":
                missing, extra = (
                    set(map(str, ev)) - set(map(str, av)),
                    set(map(str, av)) - set(map(str, ev)),
                )
                if missing or extra:
                    out.append(f"계약 {name!r}.{key}: 빠짐 {sorted(missing)}, 남음 {sorted(extra)}")
            elif ev != av:
                out.append(f"계약 {name!r}.{key}: 기대 {ev!r}, 실제 {av!r}")
    return out


def init_rules(actual: Mapping[str, Any], groups: Mapping[str, Sequence[str]]) -> str:
    """기존 ``[tool.importlinter]``을 규칙 파일 텍스트로 옮긴다.

    목록은 그대로 두고, root_packages가 ``@all``과 같으면 ``["@all"]``로 쓴다.
    """
    lines = [
        "# import-linter 규칙(그룹 사용 가능).",
        "# scripts/pkgkit/importlinter_sync.py가 pyproject.toml로 펼친다.",
        "# 그룹: @all @packages @app @<kind>, 빼기: !이름 / !@그룹.",
        "# 자세한 문법은 importlinter_sync.py 머리말.",
    ]
    roots = list(actual.get("root_packages", []))
    lines.append(
        _kv("root_packages", ["@all"] if set(roots) == set(groups.get("all", [])) else roots)
    )
    options = {k: v for k, v in actual.items() if k not in ("root_packages", "contracts")}
    if options:
        lines.append("")
        lines.append("[options]")
        lines.extend(_kv(k, v) for k, v in options.items())
    for c in actual.get("contracts", []):
        lines.append("")
        lines.append("[[contracts]]")
        lines.extend(_kv(k, v) for k, v in c.items())
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 실행


def generate(root: Path, cfg: Config) -> tuple[SyncResult, Path, Path]:
    """저장소에서 규칙·패키지를 읽어 생성한다. (결과, 규칙 경로, 대상 경로)."""
    rules_path = root / cfg.importlinter_rules
    target = root / cfg.importlinter_target
    if not rules_path.is_file():
        raise PkgkitError(
            f"import-linter 규칙 파일이 없습니다: {rules_path} (처음이면 --init으로 만든다)"
        )
    kinds = load_kinds(templates_dir(root, cfg), cfg.template_vars)
    groups = builtin_groups(discover(root, cfg, kinds), kinds)
    return build_table(read_toml(rules_path), groups), rules_path, target


def check(root: Path, cfg: Config) -> list[str]:
    """드리프트 목록(없으면 빈 목록). pkg-lint가 부른다."""
    result, _, target = generate(root, cfg)
    actual = get_path(read_toml(target), "tool.importlinter")
    return diff_tables(result.table, actual)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="저장소 루트(기본: 현재 폴더)")
    ap.add_argument("--config", type=Path, default=None, help="pkgkit_py.toml 경로")
    ap.add_argument("--check", action="store_true", help="쓰지 않고 차이만 보고(있으면 exit 1)")
    ap.add_argument(
        "--init", action="store_true", help="기존 [tool.importlinter]로 규칙 파일을 만든다"
    )
    ap.add_argument("--force", action="store_true", help="--init이 기존 규칙 파일을 덮어쓴다")
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    try:
        cfg = load_config(args.config)
        if args.init:
            rules_path = root / cfg.importlinter_rules
            if rules_path.exists() and not args.force:
                raise PkgkitError(f"규칙 파일이 이미 있습니다: {rules_path} (--force)")
            kinds = load_kinds(templates_dir(root, cfg), cfg.template_vars)
            groups = builtin_groups(discover(root, cfg, kinds), kinds)
            actual = get_path(read_toml(root / cfg.importlinter_target), "tool.importlinter") or {}
            rules_path.write_text(init_rules(actual, groups), encoding="utf-8")
            print(f"규칙 파일을 만들었습니다: {rules_path}")
            return 0
        result, rules_path, target = generate(root, cfg)
        for name in result.skipped:
            print(f"건너뜀(펼친 목록이 비어 있음): {name}")
        if args.check:
            problems = diff_tables(result.table, get_path(read_toml(target), "tool.importlinter"))
            for p in problems:
                print(f"importlinter-drift: {p}")
            return 1 if problems else 0
        block = render_table(result.table, rules_path.relative_to(root).as_posix())
        text = target.read_text(encoding="utf-8")
        new_text = replace_region(text, block)
        tomllib.loads(new_text)  # 결과가 TOML로 읽히는지 확인한 뒤에만 쓴다
        if new_text != text:
            target.write_text(new_text, encoding="utf-8")
            print(f"갱신: {target}")
        else:
            print("변경 없음")
        return 0
    except PkgkitError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
