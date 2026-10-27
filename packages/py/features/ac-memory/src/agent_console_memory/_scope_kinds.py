"""범위 종류(X29): 데이터(id 틀)·플러그인(계산) 범위 종류, 병합 목록, 범위 계산.

범위 종류 이름(예: 팀·프로젝트·공용)은 패키지 기본 데이터(`data/default_scope_kinds.yaml`)와 사용자
데이터에만 있고 코드는 모른다. 범위 id는 범위 종류의 id 틀을 접근 맥락(`MemoryAccessContext`)으로
푼 값이다. 틀 문법은 대응표와 같은 `{/포인터}`이고 포인터 첫 마디는 맥락 필드 이름이다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any, Final

from pydantic import ValidationError
from ruamel.yaml import YAML

from agent_console_conditions import MISSING, resolve_pointer
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.definitions import Issue
from agent_console_contracts.memory import (
    MEMORY_CONTEXT_FIELDS,
    MemoryAccessContext,
    MemoryScopeKindInfo,
    MemoryScopeKindList,
    MemoryScopeKindSpec,
    MemoryScopeRef,
    MemoryScopeSummary,
)

DEFAULT_SCOPE_KINDS_RESOURCE: Final = "data/default_scope_kinds.yaml"
"""패키지 기본 범위 종류 데이터 위치(패키지 안 상대 경로)."""

_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


def _check_kind_id(kind_id: object) -> str:
    """범위 종류 id 글자 규칙(계약 `MemoryScopeRef.kind`와 같음). 틀리면 `ValidationError`."""
    return MemoryScopeRef(kind=str(kind_id)).kind


type ScopeResolver = Callable[[MemoryAccessContext], str | None]
"""계산 범위 종류의 범위 id 계산(맥락 → 범위 id, 쓸 수 없으면 None)."""


class ScopeKindOrigins:
    """범위 종류 출처 값(`MemoryScopeKindInfo.origin`)."""

    DEFAULT: Final = "default"
    """패키지 기본 데이터."""
    USER: Final = "user"
    """사용자 설정."""
    PLUGIN_PREFIX: Final = "plugin:"
    """플러그인(`plugin:<배포 이름>`)."""


def template_problems(template: str) -> list[str]:
    """id 틀 문법 문제(사람이 읽는 문장 목록, 없으면 빈 목록).

    >>> template_problems("{/graph_id}/{/agent_id}")
    []
    >>> template_problems("{/nope}")
    ["맥락에 없는 필드를 가리킨다: 'nope'"]
    """
    problems: list[str] = []
    stripped = _PLACEHOLDER.sub("", template)
    if "{" in stripped or "}" in stripped:
        problems.append("중괄호 짝이 맞지 않는다")
    for pointer in _PLACEHOLDER.findall(template):
        if not pointer.startswith("/") or pointer == "/":
            problems.append(f"자리 표시는 '/'로 시작하는 맥락 경로여야 한다: {pointer!r}")
            continue
        head = pointer[1:].split("/", 1)[0]
        if head not in MEMORY_CONTEXT_FIELDS:
            problems.append(f"맥락에 없는 필드를 가리킨다: {head!r}")
    return problems


def template_context_fields(template: str) -> list[str]:
    """틀이 읽는 맥락 필드 이름(나온 순서, 중복 없음).

    >>> template_context_fields("{/graph_id}/{/agent_id}/{/graph_id}")
    ['graph_id', 'agent_id']
    """
    out: list[str] = []
    for pointer in _PLACEHOLDER.findall(template):
        head = pointer[1:].split("/", 1)[0] if pointer.startswith("/") else ""
        if head in MEMORY_CONTEXT_FIELDS and head not in out:
            out.append(head)
    return out


def _text(value: Any) -> str | None:
    if isinstance(value, bool) or value is MISSING or value is None:
        return None
    if isinstance(value, str | int | float):
        return str(value)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return "/".join(value)
    return None


def render_template(template: str, context: MemoryAccessContext) -> str | None:
    """id 틀을 맥락으로 푼다. 자리 표시 하나라도 빈 값이면 None(그 범위는 쓸 수 없음).

    >>> render_template("{/graph_id}", MemoryAccessContext(graph_id="g1"))
    'g1'
    >>> render_template("{/project_id}", MemoryAccessContext()) is None
    True
    >>> render_template("", MemoryAccessContext())
    ''
    """
    document = context.model_dump()
    empty = False

    def sub(match: re.Match[str]) -> str:
        nonlocal empty
        value = _text(resolve_pointer(document, match.group(1)))
        if not value:
            empty = True
            return ""
        return value

    rendered = _PLACEHOLDER.sub(sub, template)
    return None if empty else rendered


@dataclass(frozen=True, slots=True)
class MemoryScopeKind:
    """범위 종류 하나(병합 목록의 항목).

    Attributes:
        id: 범위 종류 id(Slug).
        label: 표시 이름.
        description: 설명.
        template: 범위 id 틀(데이터 범위 종류). 계산 범위 종류면 None.
        resolver: 계산 범위 종류의 범위 id 계산(플러그인). 틀이 있으면 쓰지 않는다.
        origin: 출처(`ScopeKindOrigins`).
        overrides: 같은 id의 앞 출처를 덮어썼으면 그 출처.
    """

    id: str
    label: str
    description: str = ""
    template: str | None = None
    resolver: ScopeResolver | None = field(default=None, compare=False)
    origin: str = ScopeKindOrigins.USER
    overrides: str | None = None

    def resolve(self, context: MemoryAccessContext) -> str | None:
        """맥락 → 범위 id(쓸 수 없으면 None). 계산 범위 종류의 예외도 None으로 본다."""
        if self.template is not None:
            return render_template(self.template, context)
        if self.resolver is None:
            return None
        try:
            value = self.resolver(context)
        except Exception:
            return None
        return value if isinstance(value, str) else None

    def info(self, *, disabled: bool = False) -> MemoryScopeKindInfo:
        """목록 항목(계약 모양)."""
        return MemoryScopeKindInfo(
            kind=self.id,
            label=self.label,
            description=self.description,
            id=self.template,
            origin=self.origin,
            overrides=self.overrides,
            disabled=disabled,
            context_fields=template_context_fields(self.template or ""),
        )

    @classmethod
    def from_spec(cls, kind_id: str, spec: MemoryScopeKindSpec, *, origin: str) -> MemoryScopeKind:
        """데이터 한 칸 → 범위 종류.

        Raises:
            ValueError: 범위 종류 id·틀이 규칙에 맞지 않을 때.
        """
        _check_kind_id(kind_id)
        problems = template_problems(spec.id)
        if problems:
            raise ValueError(f"범위 종류 {kind_id!r}의 id 틀: {'; '.join(problems)}")
        return cls(
            id=kind_id,
            label=spec.label,
            description=spec.description,
            template=spec.id,
            origin=origin,
        )


def resolve_scope(kind: MemoryScopeKind, context: MemoryAccessContext) -> MemoryScopeRef | None:
    """범위 종류 + 맥락 → 범위(쓸 수 없으면 None).

    >>> k = MemoryScopeKind(id="notes", label="노트", template="{/graph_id}")
    >>> resolve_scope(k, MemoryAccessContext(graph_id="g1"))
    MemoryScopeRef(kind='notes', id='g1')
    """
    scope_id = kind.resolve(context)
    return None if scope_id is None else MemoryScopeRef(kind=kind.id, id=scope_id)


def scope_kinds_from_mapping(data: Mapping[str, Any]) -> dict[str, MemoryScopeKindSpec]:
    """`{version, scope_kinds: {id: spec}}` 또는 `{id: spec}` → 범위 종류 데이터.

    Raises:
        ValueError: 형식이 틀렸을 때.
    """
    body = data.get("scope_kinds", data) if "version" in data or "scope_kinds" in data else data
    if not isinstance(body, Mapping):
        raise ValueError("scope_kinds는 {id: 범위 종류} 객체여야 한다")
    out: dict[str, MemoryScopeKindSpec] = {}
    for kind_id, spec in body.items():
        try:
            out[str(kind_id)] = MemoryScopeKindSpec.model_validate(spec)
        except ValidationError as exc:
            raise ValueError(f"범위 종류 {kind_id!r} 형식이 틀렸다: {exc}") from exc
    return out


def load_default_scope_kinds() -> dict[str, MemoryScopeKindSpec]:
    """패키지 기본 범위 종류 데이터(`data/default_scope_kinds.yaml`). 부를 때마다 새로 읽는다."""
    text = files("agent_console_memory").joinpath(DEFAULT_SCOPE_KINDS_RESOURCE).read_text("utf-8")
    data = YAML(typ="safe").load(text)
    if not isinstance(data, Mapping):
        raise ValueError("기본 범위 종류 데이터 형식이 틀렸다")
    return scope_kinds_from_mapping(data)


def check_scope_kinds(user: Mapping[str, Any]) -> list[Issue]:
    """사용자 `memory.scope_kinds` 검사. 경로는 섹션 기준(`/scope_kinds/<id>/...`).

    null 값(기본 끄기)은 문제가 아니다. 문제 코드는 `memory.settings_invalid`(error).
    """
    issues: list[Issue] = []
    for kind_id, raw in user.items():
        base = f"/scope_kinds/{str(kind_id).replace('~', '~0').replace('/', '~1')}"
        try:
            _check_kind_id(kind_id)
        except ValidationError:
            issues.append(_issue(base, f"범위 종류 id 형식이 틀렸다: {kind_id!r}"))
            continue
        if raw is None:
            continue
        try:
            spec = MemoryScopeKindSpec.model_validate(raw)
        except ValidationError as exc:
            issues.append(_issue(base, f"범위 종류 형식이 틀렸다: {exc.errors()[0]['msg']}"))
            continue
        issues.extend(_issue(f"{base}/id", problem) for problem in template_problems(spec.id))
    return issues


def _issue(path: str, message: str) -> Issue:
    return Issue(
        severity="error", code=KnownIssueCodes.MEMORY_SETTINGS_INVALID, message=message, path=path
    )


@dataclass(frozen=True, slots=True)
class ScopeKindCatalog:
    """병합된 범위 종류 목록(불변). `merge_scope_kinds`로 만든다.

    Attributes:
        kinds: 쓸 수 있는 범위 종류(병합 순서).
        disabled: 사용자가 null로 끈 종류(목록 표시용).
        include_defaults: 패키지 기본을 넣었는지.
    """

    kinds: tuple[MemoryScopeKind, ...] = ()
    disabled: tuple[MemoryScopeKind, ...] = ()
    include_defaults: bool = True

    def get(self, kind_id: str) -> MemoryScopeKind | None:
        """범위 종류 하나(없으면 None)."""
        return next((k for k in self.kinds if k.id == kind_id), None)

    def ids(self) -> list[str]:
        """범위 종류 id(병합 순서)."""
        return [k.id for k in self.kinds]

    def label(self, kind_id: str) -> str:
        """표시 이름(모르는 종류는 id 그대로)."""
        kind = self.get(kind_id)
        return kind.label if kind is not None else kind_id

    def resolve(self, kind_id: str, context: MemoryAccessContext) -> MemoryScopeRef | None:
        """범위 종류 id + 맥락 → 범위. 모르는 종류이거나 빈 값이면 None."""
        kind = self.get(kind_id)
        return None if kind is None else resolve_scope(kind, context)

    def listing(self, *, include_disabled: bool = True) -> MemoryScopeKindList:
        """`GET /memory/scope-kinds` 응답 모양."""
        infos = [k.info() for k in self.kinds]
        if include_disabled:
            infos.extend(k.info(disabled=True) for k in self.disabled)
        return MemoryScopeKindList(kinds=infos, include_defaults=self.include_defaults)

    def annotate(self, summaries: Iterable[MemoryScopeSummary]) -> list[MemoryScopeSummary]:
        """범위 요약의 `kind_known`을 이 목록으로 채운다."""
        known = set(self.ids())
        return [s.model_copy(update={"kind_known": s.scope.kind in known}) for s in summaries]


def merge_scope_kinds(
    *,
    defaults: Mapping[str, MemoryScopeKindSpec] | None = None,
    include_defaults: bool = True,
    plugins: Sequence[MemoryScopeKind] = (),
    user: Mapping[str, MemoryScopeKindSpec | Mapping[str, Any] | None] | None = None,
) -> ScopeKindCatalog:
    """패키지 기본 → 플러그인 → 사용자 순으로 병합한다(같은 id는 통째로 바꿈, 사용자 null = 끔).

    Args:
        defaults: 패키지 기본 데이터. None이면 `load_default_scope_kinds()`.
        include_defaults: false면 기본을 넣지 않는다(사용자 `include_default_scope_kinds`).
        plugins: 플러그인 범위 종류(X29, `origin`은 플러그인 쪽이 채운 값).
        user: 사용자 `memory.scope_kinds`(값 = 데이터 또는 null).

    Raises:
        ValueError: 사용자 데이터의 id·틀이 규칙에 맞지 않을 때(먼저 `check_scope_kinds`로 거른다).
    """
    merged: dict[str, MemoryScopeKind] = {}
    if include_defaults:
        source = load_default_scope_kinds() if defaults is None else defaults
        for kind_id, spec in source.items():
            merged[kind_id] = MemoryScopeKind.from_spec(
                kind_id, spec, origin=ScopeKindOrigins.DEFAULT
            )

    def put(kind: MemoryScopeKind) -> None:
        prior = merged.pop(kind.id, None)
        if prior is not None and kind.overrides is None:
            kind = MemoryScopeKind(
                id=kind.id,
                label=kind.label,
                description=kind.description,
                template=kind.template,
                resolver=kind.resolver,
                origin=kind.origin,
                overrides=prior.origin,
            )
        merged[kind.id] = kind

    for plugin_kind in plugins:
        put(plugin_kind)
    disabled: list[MemoryScopeKind] = []
    for kind_id, raw in (user or {}).items():
        if raw is None:
            removed = merged.pop(kind_id, None)
            if removed is not None:
                disabled.append(removed)
            continue
        spec = (
            raw if isinstance(raw, MemoryScopeKindSpec) else MemoryScopeKindSpec.model_validate(raw)
        )
        put(MemoryScopeKind.from_spec(kind_id, spec, origin=ScopeKindOrigins.USER))
    return ScopeKindCatalog(
        kinds=tuple(merged.values()), disabled=tuple(disabled), include_defaults=include_defaults
    )
