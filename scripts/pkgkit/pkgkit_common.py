"""pkgkit(Python) 공용.

설정 읽기, 워크스페이스 패키지 찾기, 종류(kind) 템플릿 정보, 간단한 TOML 쓰기.

이 파일은 표준 라이브러리만 쓴다. 저장소 경로는 항상 인자(``root``)로 받는다.
설계: specs/agent-console/design.md §3R.2, modularity-design.md §3.9.
"""

from __future__ import annotations

import dataclasses
import glob
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILE = "pkgkit_py.toml"
KIND_FILE = "kind.toml"
FROM_PACKAGE = "from-package"
"""``internal_ranges`` 값: 워크스페이스에 있는 그 패키지의 지금 버전에서 범위를 만든다
(:func:`compatible_range`, :func:`resolve_ranges`). 버전을 올려도 설정이 낡지 않는다."""

TomlTable = dict[str, Any]


class PkgkitError(Exception):
    """설정·템플릿·입력이 잘못됐을 때 내는 예외(명령은 메시지를 출력하고 2로 끝난다)."""


# ---------------------------------------------------------------- 설정


@dataclass(frozen=True)
class Config:
    """``pkgkit_py.toml`` 내용. 경로는 저장소 루트 기준 상대 경로 그대로 둔다."""

    dist_prefix: str
    import_prefix: str
    folder_prefix: str
    package_root: str
    app_root: str
    templates: str
    wheelhouse: str
    initial_version: str
    license: str
    internal_ranges: Mapping[str, str]
    importlinter_rules: str
    importlinter_target: str
    lint_rules: Mapping[str, bool]
    tool_sections: Mapping[str, str]
    drift_ignore_keys: Mapping[str, list[str]]
    template_values: Mapping[str, str] = field(default_factory=dict)
    readme_doctest_heading: str = "최소 사용"

    @property
    def template_vars(self) -> dict[str, str]:
        """템플릿 자리표시자 기본값(접두사·라이선스 + ``[python.template_values]``)."""
        return {
            "dist_prefix": self.dist_prefix,
            "import_prefix": self.import_prefix,
            "license": self.license,
            **self.template_values,
        }

    def range_for(self, dist_name: str) -> str:
        """사내 의존 ``dist_name``에 쓸 버전 범위(E-7).

        Raises:
            PkgkitError: 값이 ``from-package``인데 :func:`resolve_ranges`로 풀지 못했을 때.
        """
        value = self.internal_ranges.get(normalize_dist(dist_name), self.internal_ranges["default"])
        if value == FROM_PACKAGE:
            raise PkgkitError(
                f"{dist_name}의 버전 범위({FROM_PACKAGE})를 풀 수 없습니다: "
                "워크스페이스에서 그 패키지를 찾지 못했습니다"
            )
        return value

    def is_internal(self, dist_name: str) -> bool:
        """배포 이름이 사내 패키지인지."""
        return normalize_dist(dist_name).startswith(normalize_dist(self.dist_prefix))


def default_config_path() -> Path:
    """이 스크립트 옆의 기본 설정 파일 경로."""
    return Path(__file__).resolve().with_name(CONFIG_FILE)


def parse_config(data: Mapping[str, Any]) -> Config:
    """TOML 표에서 :class:`Config`를 만든다. 필수 키가 없으면 :class:`PkgkitError`."""
    try:
        py = data["python"]
        ranges = dict(py.get("internal_ranges", {}))
        if "default" not in ranges:
            raise PkgkitError("python.internal_ranges.default가 필요합니다")
        il = data.get("importlinter", {})
        lint = data.get("pkg_lint", {})
        return Config(
            dist_prefix=py["dist_prefix"],
            import_prefix=py["import_prefix"],
            folder_prefix=py.get("folder_prefix", ""),
            package_root=py["package_root"],
            app_root=py.get("app_root", "apps"),
            templates=py["templates"],
            wheelhouse=py["wheelhouse"],
            initial_version=py["initial_version"],
            license=py["license"],
            internal_ranges={
                (k if k == "default" else normalize_dist(k)): str(v) for k, v in ranges.items()
            },
            importlinter_rules=il.get("rules", "importlinter.rules.toml"),
            importlinter_target=il.get("target", "pyproject.toml"),
            lint_rules=dict(lint.get("rules", {})),
            tool_sections=dict(lint.get("tool_sections", {})),
            drift_ignore_keys={k: list(v) for k, v in lint.get("drift_ignore_keys", {}).items()},
            template_values={str(k): str(v) for k, v in py.get("template_values", {}).items()},
            readme_doctest_heading=str(lint.get("readme_doctest_heading", "최소 사용")),
        )
    except KeyError as exc:
        raise PkgkitError(f"pkgkit 설정에 키가 없습니다: {exc}") from exc


def compatible_range(version: str) -> str:
    """버전에서 호환 범위(E-7): ``0.5.2`` → ``>=0.5,<0.6``, ``1.2.0`` → ``>=1.2,<2``.

    Raises:
        PkgkitError: ``주.부`` 숫자로 시작하지 않는 버전.
    """
    m = re.match(r"^(\d+)\.(\d+)", version.strip())
    if not m:
        raise PkgkitError(f"버전 형식을 알 수 없습니다: {version!r}")
    major, minor = int(m.group(1)), int(m.group(2))
    upper = f"{major}.{minor + 1}" if major == 0 else f"{major + 1}"
    return f">={major}.{minor},<{upper}"


def resolve_ranges(cfg: Config, versions: Mapping[str, str]) -> Config:
    """``from-package`` 범위를 ``versions``(배포 이름 → 지금 버전)로 푼 설정 사본.

    ``versions``에 없는 이름은 그대로 둔다(:meth:`Config.range_for`가 오류를 낸다).
    """
    found = {normalize_dist(k): v for k, v in versions.items()}
    ranges = dict(cfg.internal_ranges)
    for name, value in cfg.internal_ranges.items():
        if value == FROM_PACKAGE and name in found:
            ranges[name] = compatible_range(found[name])
    return dataclasses.replace(cfg, internal_ranges=ranges)


def workspace_versions(root: Path) -> dict[str, str]:
    """루트 워크스페이스 members의 배포 이름 → ``project.version``(버전 없는 것은 뺀다)."""
    root_pyproject = root / "pyproject.toml"
    if not root_pyproject.is_file():
        return {}
    members, exclude = workspace_members(read_toml(root_pyproject))
    out: dict[str, str] = {}
    for path in expand_members(root, members, exclude):
        data = read_toml(path / "pyproject.toml")
        name, version = get_path(data, "project.name"), get_path(data, "project.version")
        if isinstance(name, str) and isinstance(version, str):
            out[normalize_dist(name)] = version
    return out


def load_config(path: Path | None = None) -> Config:
    """설정 파일을 읽는다(기본: 스크립트 옆 ``pkgkit_py.toml``)."""
    return parse_config(read_toml(path or default_config_path()))


def read_toml(path: Path) -> TomlTable:
    """TOML 파일을 읽는다. 문법 오류는 :class:`PkgkitError`."""
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise PkgkitError(f"{path}: TOML 문법 오류: {exc}") from exc


def get_path(table: Mapping[str, Any], dotted: str) -> Any:
    """``"tool.ruff.lint"`` 같은 점 경로로 중첩 표 값을 꺼낸다. 없으면 ``None``."""
    cur: Any = table
    for part in dotted.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


# ---------------------------------------------------------------- 이름


_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize_dist(name: str) -> str:
    """PEP 503 정규화(소문자, ``_``·``.`` → ``-``)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(req: str) -> str:
    """의존 문자열에서 배포 이름만(정규화)."""
    m = _REQ_NAME.match(req)
    if not m:
        raise PkgkitError(f"의존 문자열을 읽을 수 없습니다: {req!r}")
    return normalize_dist(m.group(1))


def requirement_specifier(req: str) -> str:
    """의존 문자열에서 이름 뒤 버전 범위 부분(마커 제외, 공백 제거). 없으면 빈 문자열."""
    m = _REQ_NAME.match(req)
    rest = req[m.end() :] if m else req
    rest = rest.split(";", 1)[0]
    rest = re.sub(r"^\s*\[[^\]]*\]", "", rest)
    return rest.strip()


def import_name_of(dist_name: str) -> str:
    """배포 이름 → import 이름(``agent-console-chat`` → ``agent_console_chat``)."""
    return normalize_dist(dist_name).replace("-", "_")


@dataclass(frozen=True)
class Names:
    """새 패키지 하나의 이름 세트."""

    folder: str
    dist_name: str
    import_name: str


def names_for(folder_name: str, cfg: Config) -> Names:
    """폴더 이름(``ac-chat``)에서 배포·import 이름을 정한다.

    폴더 접두사(``ac-``)가 있으면 떼고 배포 접두사(``agent-console-``)를 붙인다.
    """
    if not re.fullmatch(r"[a-z][a-z0-9]*(-[a-z0-9]+)*", folder_name):
        raise PkgkitError(f"패키지 폴더 이름은 소문자·숫자·하이픈만 씁니다: {folder_name!r}")
    stem = folder_name
    if cfg.folder_prefix and stem.startswith(cfg.folder_prefix):
        stem = stem[len(cfg.folder_prefix) :]
    if not stem:
        raise PkgkitError(f"접두사만 있는 이름입니다: {folder_name!r}")
    dist = normalize_dist(cfg.dist_prefix + stem)
    return Names(folder=folder_name, dist_name=dist, import_name=import_name_of(dist))


# ---------------------------------------------------------------- 종류(kind)


@dataclass(frozen=True)
class KindSpec:
    """``templates/python/kinds/<kind>/kind.toml`` 내용.

    - ``folder``: 패키지가 놓일 종류 폴더(``packages/py/<folder>/``)
    - ``dependencies``·``dev_dependencies``: 템플릿이 넣는 의존(사내 의존은 이름만, 범위는 설정에서)
    - ``required_files``: 공통 필수 파일에 더해 이 종류에 필요한 파일
      (``{{import_name}}`` 자리표시자 가능)
    - ``runnable``: ``python -m <import> --check`` 단독 실행 진입점이 있는지(portability가 실행)
    """

    name: str
    folder: str
    description: str
    dependencies: tuple[str, ...] = ()
    dev_dependencies: tuple[str, ...] = ()
    required_files: tuple[str, ...] = ()
    runnable: bool = False
    id_prefix: str = ""
    entry_points: Mapping[str, Mapping[str, str]] = field(default_factory=dict)


def templates_dir(root: Path, cfg: Config) -> Path:
    return root / cfg.templates


def load_kinds(tdir: Path, values: Mapping[str, str]) -> dict[str, KindSpec]:
    """템플릿 폴더의 ``kinds/*/kind.toml``을 모두 읽는다. 종류 목록은 이 폴더가 정한다.

    문자열 값의 ``{{키}}`` 중 ``values``에 있는 것(설정의 접두사·제품 이름 등)은 여기서 바꾸고,
    패키지마다 다른 것(``{{import_name}}``·``{{module_id}}``)은 그대로 남긴다.
    """
    kinds: dict[str, KindSpec] = {}
    kinds_dir = tdir / "kinds"
    if not kinds_dir.is_dir():
        raise PkgkitError(f"종류 템플릿 폴더가 없습니다: {kinds_dir}")
    for kind_file in sorted(kinds_dir.glob(f"*/{KIND_FILE}")):
        data = _render_partial(read_toml(kind_file), values)
        name = kind_file.parent.name
        kinds[name] = KindSpec(
            name=name,
            folder=data.get("folder", name),
            description=data.get("description", ""),
            dependencies=tuple(data.get("dependencies", [])),
            dev_dependencies=tuple(data.get("dev_dependencies", [])),
            required_files=tuple(data.get("required_files", [])),
            runnable=bool(data.get("runnable", False)),
            id_prefix=str(data.get("id_prefix", "")),
            entry_points={k: dict(v) for k, v in data.get("entry_points", {}).items()},
        )
    return kinds


@dataclass(frozen=True)
class CommonSpec:
    """``templates/python/common.toml``: 모든 종류에 공통인 필수 파일과 dev 도구."""

    required_files: tuple[str, ...]
    dev_dependencies: tuple[str, ...]


def load_common(tdir: Path) -> CommonSpec:
    """공통 템플릿 정보를 읽는다."""
    data = read_toml(tdir / "common.toml")
    return CommonSpec(
        required_files=tuple(data.get("required_files", [])),
        dev_dependencies=tuple(data.get("dev_dependencies", [])),
    )


# ---------------------------------------------------------------- 워크스페이스 패키지


@dataclass(frozen=True)
class PyPackage:
    """워크스페이스의 Python 프로젝트 하나.

    ``kind``는 종류 폴더에서 정한다(``packages/py/features/ac-chat`` → ``feature``).
    종류 폴더 없이 바로 놓인 옛 배치(``packages/py/ac-chat``)는 ``None``, 앱은 ``"app"``.
    """

    path: Path
    rel: str
    dist_name: str
    import_name: str | None
    kind: str | None
    is_app: bool
    pyproject: TomlTable

    @property
    def version(self) -> str | None:
        v = get_path(self.pyproject, "project.version")
        return v if isinstance(v, str) else None

    def dependencies(self) -> list[str]:
        deps = get_path(self.pyproject, "project.dependencies")
        return list(deps) if isinstance(deps, list) else []

    def dev_dependencies(self) -> list[str]:
        groups = get_path(self.pyproject, "dependency-groups") or {}
        out: list[str] = []
        for items in groups.values():
            out.extend(x for x in items if isinstance(x, str))
        return out


def find_import_name(pkg_dir: Path) -> str | None:
    """``src/`` 아래 ``__init__.py``가 있는 첫 폴더 이름(없으면 ``None``)."""
    src = pkg_dir / "src"
    if not src.is_dir():
        return None
    names = sorted(p.parent.name for p in src.glob("*/__init__.py"))
    return names[0] if names else None


def workspace_members(root_pyproject: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """루트 ``[tool.uv.workspace]``의 ``members``·``exclude`` glob."""
    ws = get_path(root_pyproject, "tool.uv.workspace") or {}
    return list(ws.get("members", [])), list(ws.get("exclude", []))


def expand_members(root: Path, members: Iterable[str], exclude: Iterable[str]) -> list[Path]:
    """members glob을 펼쳐 ``pyproject.toml``이 있는 폴더만 돌려준다(정렬, 중복 제거)."""
    excluded: set[Path] = set()
    for pattern in exclude:
        excluded.update(Path(p).resolve() for p in glob.glob(str(root / pattern)))
    found: dict[Path, None] = {}
    for pattern in members:
        for p in sorted(glob.glob(str(root / pattern))):
            path = Path(p).resolve()
            if path in excluded or not (path / "pyproject.toml").is_file():
                continue
            found[path] = None
    return list(found)


def classify(rel: str, cfg: Config, kind_folders: Mapping[str, str]) -> tuple[str | None, bool]:
    """루트 기준 경로로 (종류, 앱 여부)를 정한다. ``kind_folders``는 종류 폴더 → 종류 이름."""
    parts = Path(rel).parts
    app_parts = Path(cfg.app_root).parts
    if parts[: len(app_parts)] == app_parts:
        return "app", True
    pkg_parts = Path(cfg.package_root).parts
    if parts[: len(pkg_parts)] == pkg_parts:
        rest = parts[len(pkg_parts) :]
        if len(rest) >= 2:
            return kind_folders.get(rest[0], rest[0]), False
        return None, False
    return None, False


def load_package(path: Path, root: Path, cfg: Config, kind_folders: Mapping[str, str]) -> PyPackage:
    """폴더 하나를 :class:`PyPackage`로 읽는다."""
    data = read_toml(path / "pyproject.toml")
    name = get_path(data, "project.name")
    if not isinstance(name, str):
        raise PkgkitError(f"{path}/pyproject.toml에 project.name이 없습니다")
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    kind, is_app = classify(rel, cfg, kind_folders)
    return PyPackage(
        path=path,
        rel=rel,
        dist_name=normalize_dist(name),
        import_name=find_import_name(path),
        kind=kind,
        is_app=is_app,
        pyproject=data,
    )


def discover(
    root: Path, cfg: Config, kinds: Mapping[str, KindSpec] | None = None
) -> list[PyPackage]:
    """루트 워크스페이스 members에 있는 Python 프로젝트를 모두 찾는다(앱 포함, 경로 순)."""
    root_data = read_toml(root / "pyproject.toml")
    members, exclude = workspace_members(root_data)
    kind_folders = {k.folder: k.name for k in (kinds or {}).values()}
    return [
        load_package(p, root, cfg, kind_folders) for p in expand_members(root, members, exclude)
    ]


def select(packages: Iterable[PyPackage], names: Iterable[str]) -> list[PyPackage]:
    """``--package`` 값(폴더 이름·배포 이름·import 이름 아무거나)으로 고른다. 없는 이름은 오류."""
    pkgs = list(packages)
    wanted = list(names)
    if not wanted:
        return pkgs
    out: list[PyPackage] = []
    for w in wanted:
        hits = [
            p
            for p in pkgs
            if w in (p.path.name, p.dist_name, p.import_name, p.rel)
            or normalize_dist(w) == p.dist_name
        ]
        if not hits:
            raise PkgkitError(f"패키지를 찾을 수 없습니다: {w}")
        out.extend(h for h in hits if h not in out)
    return out


# ---------------------------------------------------------------- 템플릿 자리표시자

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def render(text: str, values: Mapping[str, str]) -> str:
    """``{{key}}``를 값으로 바꾼다. 모르는 자리표시자는 :class:`PkgkitError`."""

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            raise PkgkitError(f"템플릿 자리표시자 값이 없습니다: {key}")
        return values[key]

    return _PLACEHOLDER.sub(sub, text)


def render_known(text: str, values: Mapping[str, str]) -> str:
    """``values``에 있는 자리표시자만 바꾸고 나머지는 남긴다."""
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def _render_partial(value: Any, values: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return render_known(value, values)
    if isinstance(value, list):
        return [_render_partial(v, values) for v in value]
    if isinstance(value, Mapping):
        return {render_known(k, values): _render_partial(v, values) for k, v in value.items()}
    return value


# ------------------------------------------------ TOML 쓰기(문자열·숫자·불·목록·표만)


def toml_value(value: Any) -> str:
    """단순 값을 TOML 표현으로."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(value, list | tuple):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, Mapping):
        return "{ " + ", ".join(f"{toml_key(k)} = {toml_value(v)}" for k, v in value.items()) + " }"
    raise PkgkitError(f"TOML로 쓸 수 없는 값: {value!r}")


def toml_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else toml_value(key)


def toml_list_block(key: str, items: Iterable[Any], indent: str = "    ") -> str:
    """여러 줄 목록 ``key = [\\n    "a",\\n]``."""
    lines = [f"{toml_key(key)} = ["]
    lines.extend(f"{indent}{toml_value(v)}," for v in items)
    lines.append("]")
    return "\n".join(lines)
