"""i18n 도구 공용: 설정(``i18n.yaml``), 대상 패키지, 패키지 문구 묶음, 결과(Finding).

서버·HTTP를 모른다. 묶음 형식은 ``agent_console_i18n``(design §I18N.3)을 그대로 쓴다.
"""

from __future__ import annotations

import fnmatch
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from ruamel.yaml import YAML

from agent_console_i18n import (
    LOCALES_DIR,
    MESSAGE_CATALOGS_GROUP,
    Catalog,
    CatalogIssue,
    load_catalog_folder,
)

TOOL_DIR: Final = Path(__file__).resolve().parent
DEFAULT_CONFIG: Final = TOOL_DIR / "i18n.yaml"

RULES: Final = (
    "missing_text",
    "untranslated_text",
    "dynamic_text",
    "unowned_text",
    "missing_code",
    "untranslated_code",
    "unowned_code",
    "stale_code",
    "placeholder_mismatch",
    "unknown_placeholder",
    "catalog_unregistered",
    "catalog_invalid",
)
"""결과 규칙 이름(``severity`` 키). 뜻은 README "규칙"."""

SEVERITIES: Final = ("error", "warning")


class I18nToolError(Exception):
    """설정·입력 오류(종료 코드 2)."""


# ---------------------------------------------------------------- 설정


@dataclass(frozen=True, slots=True)
class Group:
    """요약 표의 묶음(패키지 폴더 glob, 저장소 루트 기준)."""

    name: str
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParamSource:
    """경로 변수 값: 고정 ``values`` 또는 GET 경로 ``source``의 응답에서 ``select``로 고른 값."""

    values: tuple[str, ...] = ()
    source: str | None = None
    select: str = ""


@dataclass(frozen=True, slots=True)
class Seed:
    """훑기 전에 보낼 요청 하나."""

    method: str
    path: str
    body: Any = None
    if_match: ParamSource | None = None
    """``If-Match`` 값을 얻을 GET 경로(``source``)와 ``select``.

    버전이 필요한 저장(예: 리소스 본문)에 쓴다."""


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """S1 서버 훑기 설정."""

    openapi: str = "/api/v1/openapi.json"
    env: Mapping[str, str] = field(default_factory=dict)
    options: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    seeds: tuple[Seed, ...] = ()
    params: Mapping[str, ParamSource] = field(default_factory=dict)
    query_params: Mapping[str, ParamSource] = field(default_factory=dict)
    """질의 변수 값. 경로가 OpenAPI에 그 질의 변수를 선언했으면 값마다 한 번 더 읽는다."""
    max_param_values: int = 50
    skip_paths: tuple[str, ...] = ()
    dirs: tuple[str, ...] = ()
    """씨앗 전에 만들 폴더(값의 ``{tmp}`` = 임시 폴더) — 예: 등록할 프로젝트 폴더."""


@dataclass(frozen=True, slots=True)
class SchemaDiscover:
    """웹 소스에서 화면이 그리는 계약 모델 이름을 찾는 규칙(``static.schemas[].discover``)."""

    files: tuple[str, ...]
    """저장소 루트 기준 glob."""
    pattern: re.Pattern[str]
    """첫 묶음이 모델 이름인 정규식."""
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SchemaSource:
    """정적 S1 출처: JSON Schema 문서 하나에서 화면이 그리는 모델들(``$ref`` 따라감)."""

    document: str
    """저장소 루트 기준 경로."""
    defs: str = "$defs"
    models: tuple[str, ...] = ()
    discover: SchemaDiscover | None = None


@dataclass(frozen=True, slots=True)
class DataSource:
    """정적 S1 출처: 패키지 데이터 파일에서 화면에 가는 값(``select`` 경로, 없으면 전부)."""

    files: tuple[str, ...]
    """저장소 루트 기준 glob."""
    select: tuple[str, ...] = ()
    pointer_slots: bool = False
    """참이면 값의 ``{/포인터}``·``{/포인터|방식}`` 자리 표시를 이름 자리 표시(``{이름}``)로
    바꾼 틀을 모은다(출처가 응답 ``text_templates``에 싣는 틀과 같은 규칙 —
    ``i18n_static.pointer_key``)."""


@dataclass(frozen=True, slots=True)
class PythonSource:
    """정적 S1 출처: 파이썬 소스에서 화면에 가는 글자(정한 호출의 키워드 인자·사전 키 값).

    값 식 안의 문자열 상수(조건식·``or`` 양쪽 포함)를 모으고, f-string은 값 자리를 ``{…}``로 둔
    꼴로 모은다(묶음 키가 될 수 없어 ``dynamic_text``가 된다 — 틀 + 값으로 바꾸라는 뜻).
    """

    files: tuple[str, ...]
    """저장소 루트 기준 glob."""
    calls: tuple[str, ...] = ()
    """호출 이름(``Name``이나 속성 이름, 예: ``LogEventDraft``·``update``)."""
    keywords: tuple[str, ...] = ()
    """그 호출에서 볼 키워드 인자 이름."""
    dict_keys: tuple[str, ...] = ()
    """사전 글자(``{"title": ...}``)에서 볼 키."""


@dataclass(frozen=True, slots=True)
class StaticConfig:
    """서버 응답 밖에서 화면에 가는 원문(웹이 서버 묶음으로 번역하는 것)."""

    schemas: tuple[SchemaSource, ...] = ()
    data: tuple[DataSource, ...] = ()
    python: tuple[PythonSource, ...] = ()


@dataclass(frozen=True, slots=True)
class IssueShape:
    """응답 안 오류·이슈 객체의 키 이름."""

    code: str = "code"
    message: str = "message"
    details: str = "details"


@dataclass(frozen=True, slots=True)
class Config:
    """``i18n.yaml`` 전체."""

    targets: tuple[str, ...]
    groups: tuple[Group, ...]
    source_language: str
    source_pattern: re.Pattern[str]
    languages: tuple[str, ...]
    python_globs: tuple[str, ...]
    data_globs: tuple[str, ...]
    exclude_globs: tuple[str, ...]
    code_pattern: re.Pattern[str]
    code_class_pattern: re.Pattern[str]
    exclude_codes: tuple[re.Pattern[str], ...]
    exclude_texts: tuple[re.Pattern[str], ...]
    skip_keys: tuple[str, ...]
    keep_keys_in: Mapping[str, tuple[str, ...]]
    """``skip_keys``의 키라도 이 부모 키 안에서는 모은다(부모 → 키, 예: ``x-ui`` → ``example``)."""
    name_maps: tuple[str, ...]
    """값이 ``이름 → 스키마`` 표인 키(``properties`` 등).

    그 안의 키는 이름이라 ``skip_keys``로 보지 않는다."""
    prefer_owners: tuple[str, ...]
    templates_key: str
    """값이 섞인 칸의 원문 틀 + 값 표 키.

    계약 ``text_templates``: JSON Pointer → ``[{template, params}]``.

    이 키가 있는 객체는 틀(중첩 포함)을 원문으로 모으고, 틀이 덮은 칸 값은 모으지 않는다."""
    issue: IssueShape
    severity: Mapping[str, str]
    server: ServerConfig
    static: StaticConfig = field(default_factory=StaticConfig)

    def is_code(self, value: str) -> bool:
        """코드 모양이고 제외 목록에 없는지."""
        return bool(self.code_pattern.match(value)) and not any(
            p.fullmatch(value) for p in self.exclude_codes
        )

    def is_source_text(self, value: str) -> bool:
        """원문 문자가 있고 제외 목록에 없는지."""
        return bool(self.source_pattern.search(value)) and not any(
            p.search(value) for p in self.exclude_texts
        )


def read_yaml(path: Path) -> Any:
    """YAML 파일 하나(safe). 없거나 형식이 틀리면 ``I18nToolError``."""
    try:
        with path.open(encoding="utf-8") as fh:
            return YAML(typ="safe", pure=True).load(fh)
    except FileNotFoundError as exc:
        raise I18nToolError(f"file not found: {path}") from exc
    except Exception as exc:
        raise I18nToolError(f"cannot read YAML {path}: {exc}") from exc


def _strs(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise I18nToolError(f"{where} must be a list of strings")
    return tuple(value)


def _regex(value: str, where: str) -> re.Pattern[str]:
    try:
        return re.compile(value)
    except re.error as exc:
        raise I18nToolError(f"{where}: invalid regular expression ({exc})") from exc


def _map(value: Any, where: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise I18nToolError(f"{where} must be a mapping")
    return value


def parse_config(data: Any) -> Config:
    """YAML 값 → ``Config``. 모르는 심각도·규칙 이름은 ``I18nToolError``."""
    top = _map(data, "config")
    groups = tuple(
        Group(str(g["name"]), _strs(g.get("paths"), f"groups.{g.get('name')}.paths"))
        for g in top.get("groups") or []
    )
    sources = _map(top.get("sources"), "sources")
    codes = _map(top.get("codes"), "codes")
    texts = _map(top.get("texts"), "texts")
    issue = _map(top.get("issue"), "issue")
    severity = {str(k): str(v) for k, v in _map(top.get("severity"), "severity").items()}
    unknown = sorted(set(severity) - set(RULES))
    if unknown:
        raise I18nToolError(f"severity: unknown rules {unknown} (known: {', '.join(RULES)})")
    bad = sorted(k for k, v in severity.items() if v not in SEVERITIES)
    if bad:
        raise I18nToolError(f"severity: {bad} must be one of {SEVERITIES}")
    srv = _map(top.get("server"), "server")

    def param_sources(key: str) -> dict[str, ParamSource]:
        out: dict[str, ParamSource] = {}
        for name, spec in _map(srv.get(key), f"server.{key}").items():
            spec_map = _map(spec, f"server.{key}.{name}")
            out[str(name)] = ParamSource(
                values=tuple(str(v) for v in spec_map.get("values") or []),
                source=spec_map.get("from"),
                select=str(spec_map.get("select", "")),
            )
        return out

    params = param_sources("params")

    def seed(raw: Any, i: int) -> Seed:
        spec = _map(raw, f"server.seeds[{i}]")
        match = spec.get("if_match")
        if_match = None
        if match is not None:
            m = _map(match, f"server.seeds[{i}].if_match")
            if not isinstance(m.get("from"), str):
                raise I18nToolError(f"server.seeds[{i}].if_match.from must be a GET path")
            if_match = ParamSource(source=m["from"], select=str(m.get("select", "")))
        return Seed(str(spec["method"]).upper(), str(spec["path"]), spec.get("body"), if_match)

    seeds = tuple(seed(s, i) for i, s in enumerate(srv.get("seeds") or []))
    keep_in = {
        str(parent): _strs(keys, f"texts.keep_keys_in.{parent}")
        for parent, keys in _map(texts.get("keep_keys_in"), "texts.keep_keys_in").items()
    }
    languages = _strs(top.get("languages"), "languages")
    if not languages:
        raise I18nToolError("languages must not be empty")
    return Config(
        targets=_strs(top.get("targets"), "targets"),
        groups=groups,
        source_language=str(top.get("source_language", "ko")),
        source_pattern=_regex(str(top.get("source_pattern", "")), "source_pattern"),
        languages=languages,
        python_globs=_strs(sources.get("python"), "sources.python") or ("src/**/*.py",),
        data_globs=_strs(sources.get("data"), "sources.data"),
        exclude_globs=_strs(sources.get("exclude"), "sources.exclude"),
        code_pattern=_regex(str(codes.get("pattern", r"^[a-z][a-z0-9_.]*$")), "codes.pattern"),
        code_class_pattern=_regex(str(codes.get("class_pattern", "Codes$")), "codes.class_pattern"),
        exclude_codes=tuple(
            _regex(p, "codes.exclude") for p in _strs(codes.get("exclude"), "codes.exclude")
        ),
        exclude_texts=tuple(
            _regex(p, "texts.exclude") for p in _strs(texts.get("exclude"), "texts.exclude")
        ),
        skip_keys=_strs(texts.get("skip_keys"), "texts.skip_keys"),
        keep_keys_in=keep_in,
        name_maps=_strs(texts.get("name_maps"), "texts.name_maps"),
        prefer_owners=_strs(texts.get("prefer_owners"), "texts.prefer_owners"),
        templates_key=str(texts.get("templates_key", "text_templates")),
        issue=IssueShape(
            code=str(issue.get("code", "code")),
            message=str(issue.get("message", "message")),
            details=str(issue.get("details", "details")),
        ),
        severity=severity,
        server=ServerConfig(
            openapi=str(srv.get("openapi", "/api/v1/openapi.json")),
            env={str(k): str(v) for k, v in _map(srv.get("env"), "server.env").items()},
            options={
                str(k): dict(_map(v, f"server.options.{k}"))
                for k, v in _map(srv.get("options"), "server.options").items()
            },
            seeds=seeds,
            params=params,
            query_params=param_sources("query_params"),
            max_param_values=int(srv.get("max_param_values", 50)),
            skip_paths=_strs(srv.get("skip_paths"), "server.skip_paths"),
            dirs=_strs(srv.get("dirs"), "server.dirs"),
        ),
        static=_static(_map(top.get("static"), "static")),
    )


def _static(top: Mapping[str, Any]) -> StaticConfig:
    schemas: list[SchemaSource] = []
    for i, raw in enumerate(top.get("schemas") or []):
        where = f"static.schemas[{i}]"
        spec = _map(raw, where)
        if not isinstance(spec.get("document"), str):
            raise I18nToolError(f"{where}.document must be a string")
        disc = spec.get("discover")
        discover = None
        if disc is not None:
            d = _map(disc, f"{where}.discover")
            pattern = _regex(str(d.get("pattern", "")), f"{where}.discover.pattern")
            if pattern.groups < 1:
                raise I18nToolError(f"{where}.discover.pattern needs a group for the model name")
            discover = SchemaDiscover(
                files=_strs(d.get("files"), f"{where}.discover.files"),
                pattern=pattern,
                exclude=_strs(d.get("exclude"), f"{where}.discover.exclude"),
            )
        schemas.append(
            SchemaSource(
                document=spec["document"],
                defs=str(spec.get("defs", "$defs")),
                models=_strs(spec.get("models"), f"{where}.models"),
                discover=discover,
            )
        )
    data: list[DataSource] = []
    for i, raw in enumerate(top.get("data") or []):
        where = f"static.data[{i}]"
        spec = _map(raw, where)
        slots = spec.get("pointer_slots", False)
        if not isinstance(slots, bool):
            raise I18nToolError(f"{where}.pointer_slots must be true or false")
        data.append(
            DataSource(
                files=_strs(spec.get("files"), f"{where}.files"),
                select=_strs(spec.get("select"), f"{where}.select"),
                pointer_slots=slots,
            )
        )
    python: list[PythonSource] = []
    for i, raw in enumerate(top.get("python") or []):
        where = f"static.python[{i}]"
        spec = _map(raw, where)
        source = PythonSource(
            files=_strs(spec.get("files"), f"{where}.files"),
            calls=_strs(spec.get("calls"), f"{where}.calls"),
            keywords=_strs(spec.get("keywords"), f"{where}.keywords"),
            dict_keys=_strs(spec.get("dict_keys"), f"{where}.dict_keys"),
        )
        if not source.files:
            raise I18nToolError(f"{where}.files must not be empty")
        if not ((source.calls and source.keywords) or source.dict_keys):
            raise I18nToolError(f"{where} needs calls + keywords or dict_keys")
        python.append(source)
    return StaticConfig(tuple(schemas), tuple(data), tuple(python))


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    """설정 파일을 읽는다."""
    return parse_config(read_yaml(path))


# ---------------------------------------------------------------- 대상 패키지


@dataclass(frozen=True, slots=True)
class Package:
    """검사 대상 패키지 폴더 하나.

    Attributes:
        name: 폴더 이름(``--package``·entry point 이름).
        dist: 배포 이름(``[project].name``).
        root: 패키지 폴더.
        rel: 저장소 루트 기준 경로(``/`` 구분).
        imports: ``src/`` 아래 import 패키지 이름(이름 순).
        entry_points: ``agent_console.message_catalogs`` 그룹 값(이름 → 모듈).
    """

    name: str
    dist: str
    root: Path
    rel: str
    imports: tuple[str, ...]
    entry_points: Mapping[str, str]

    @property
    def import_name(self) -> str | None:
        """묶음을 둘 import 패키지(첫째). 없으면 None."""
        return self.imports[0] if self.imports else None

    def locales_dir(self, import_name: str | None = None) -> Path | None:
        """``src/<import>/locales``. import 패키지가 없으면 None."""
        name = import_name or self.import_name
        return None if name is None else self.root / "src" / name / LOCALES_DIR

    def is_registered(self, import_name: str) -> bool:
        """entry point 값이 그 import 패키지를 가리키는지."""
        return any(v.split(":", 1)[0] == import_name for v in self.entry_points.values())


def read_package(root: Path, repo: Path) -> Package | None:
    """``pyproject.toml``이 있는 폴더를 패키지로 읽는다(없으면 None)."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise I18nToolError(f"cannot read {pyproject}: {exc}") from exc
    project = data.get("project", {})
    eps = project.get("entry-points", {}).get(MESSAGE_CATALOGS_GROUP, {})
    src = root / "src"
    imports = (
        tuple(sorted(p.name for p in src.iterdir() if (p / "__init__.py").is_file()))
        if src.is_dir()
        else ()
    )
    return Package(
        name=root.name,
        dist=str(project.get("name", root.name)),
        root=root,
        rel=root.relative_to(repo).as_posix(),
        imports=imports,
        entry_points={str(k): str(v) for k, v in eps.items()},
    )


def discover_packages(repo: Path, targets: Iterable[str]) -> list[Package]:
    """대상 glob에 맞는 패키지 폴더(경로 순, 중복 없음)."""
    seen: dict[Path, Package] = {}
    for pattern in targets:
        for root in sorted(repo.glob(pattern)):
            if root.is_dir() and root not in seen:
                pkg = read_package(root, repo)
                if pkg is not None:
                    seen[root] = pkg
    return sorted(seen.values(), key=lambda p: p.rel)


def select_packages(packages: Sequence[Package], patterns: Sequence[str]) -> list[Package]:
    """``--package`` 값(폴더 이름·배포 이름 glob)에 맞는 것. 값이 없으면 전부.

    Raises:
        I18nToolError: 어느 패키지에도 맞지 않는 값이 있을 때.
    """
    if not patterns:
        return list(packages)
    chosen: list[Package] = []
    for pattern in patterns:
        hit = [
            p
            for p in packages
            if fnmatch.fnmatchcase(p.name, pattern) or fnmatch.fnmatchcase(p.dist, pattern)
        ]
        if not hit:
            raise I18nToolError(f"--package {pattern}: no target package matches")
        chosen.extend(p for p in hit if p not in chosen)
    return chosen


def group_of(pkg: Package | None, groups: Sequence[Group]) -> str:
    """패키지가 든 첫 묶음 이름(없으면 ``other``, 패키지가 없으면 ``unowned``)."""
    if pkg is None:
        return "unowned"
    for group in groups:
        if any(fnmatch.fnmatchcase(pkg.rel, pattern) for pattern in group.paths):
            return group.name
    return "other"


# ---------------------------------------------------------------- 묶음


@dataclass(frozen=True, slots=True)
class PackageCatalogs:
    """패키지 하나의 언어별 묶음과 읽기 문제."""

    package: Package
    by_language: Mapping[str, Catalog]
    issues: tuple[CatalogIssue, ...] = ()


def read_package_catalogs(pkg: Package) -> PackageCatalogs | None:
    """``src/<import>/locales``(설치 entry point가 아니라 소스에서 바로). 폴더가 없으면 None."""
    folder = pkg.locales_dir()
    if folder is None or not folder.is_dir():
        return None
    load = load_catalog_folder(folder, source=pkg.name, origin="package")
    return PackageCatalogs(pkg, {c.language: c for c in load.catalogs}, load.issues)


@dataclass(slots=True)
class CatalogIndex:
    """언어별로 모든 패키지 묶음을 합쳐 본 것(어느 패키지든 값이 있으면 번역된 것)."""

    filled: dict[tuple[str, str, str], str] = field(default_factory=dict)
    """(언어, 구역, 키) → 값을 준 패키지(빈 값 아님)."""
    empty: dict[tuple[str, str, str], str] = field(default_factory=dict)
    """(언어, 구역, 키) → 빈 값으로만 가진 패키지(뽑기가 더했고 아직 번역 안 함)."""

    def add(self, pkg: str, catalog: Catalog) -> None:
        for section, entries in (("text", catalog.text), ("codes", catalog.codes)):
            for key, value in entries.items():
                slot = (catalog.language, section, str(key))
                if value:
                    self.filled.setdefault(slot, pkg)
                else:
                    self.empty.setdefault(slot, pkg)

    def state(self, language: str, section: str, key: str) -> tuple[str, str | None]:
        """``("filled"|"empty"|"missing", 패키지)``."""
        slot = (language, section, key)
        if slot in self.filled:
            return "filled", self.filled[slot]
        if slot in self.empty:
            return "empty", self.empty[slot]
        return "missing", None

    def keys(self, language: str, section: str) -> dict[str, str]:
        """그 언어·구역의 모든 키 → 패키지."""
        out: dict[str, str] = {}
        for (lang, sec, key), pkg in [*self.filled.items(), *self.empty.items()]:
            if lang == language and sec == section:
                out.setdefault(key, pkg)
        return out


# ---------------------------------------------------------------- 결과


@dataclass(frozen=True, slots=True)
class Finding:
    """검사 결과 하나.

    Attributes:
        rule: ``RULES`` 중 하나.
        key: 문구(원문) 또는 코드.
        package: 맡을 패키지 폴더 이름(모르면 None).
        language: 언어(해당 없으면 None).
        where: 근거 위치(경로 틀·``파일:줄``).
        message: 터미널용 한 줄(영어).
    """

    rule: str
    key: str
    package: str | None = None
    language: str | None = None
    where: str = ""
    message: str = ""


def severity_of(finding: Finding, config: Config, *, strict: bool) -> str:
    """규칙 심각도. ``strict``면 모두 error. 설정에 없는 규칙은 error."""
    if strict:
        return "error"
    return config.severity.get(finding.rule, "error")


__all__ = [
    "DEFAULT_CONFIG",
    "RULES",
    "SEVERITIES",
    "TOOL_DIR",
    "CatalogIndex",
    "Config",
    "DataSource",
    "Finding",
    "Group",
    "I18nToolError",
    "IssueShape",
    "Package",
    "PackageCatalogs",
    "ParamSource",
    "PythonSource",
    "SchemaDiscover",
    "SchemaSource",
    "Seed",
    "ServerConfig",
    "StaticConfig",
    "discover_packages",
    "group_of",
    "load_config",
    "parse_config",
    "read_package",
    "read_package_catalogs",
    "read_yaml",
    "select_packages",
    "severity_of",
]
