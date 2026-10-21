"""선언형 리소스 종류(코드 없이 YAML 데이터로 만드는 X14 구현, design §R12.2).

파일 형식(`<workspace>/resource-types/*.yaml`):

```yaml
id: prompt-fragment
title: 프롬프트 조각
config_schema: {type: object, properties: {title: {type: string}}}
content: {media_types: [text/markdown], editor: markdown}   # 선택(문서형)
slot_key: title                                              # 선택
combine: append                                              # 선택(기본 append)
contributes:
  - slot: instructions
    template: "## {title}\\n{content}"     # 문자열 → 칸에 [결과] 한 항목
  - slot: mcp_servers
    value: {name: "{name}", type: stdio, command: "{command}"}   # 구조 값 → 칸에 [값] 한 항목
    combine: append                        # 선택(이 기여만)
  - slot: env_map
    value: {A: "{a}"}
    raw: true                              # 감싸지 않고 값 그대로(객체 칸을 merge로 합칠 때)
    combine: merge
```

치환 변수: `id`·`name`·`description`·`title`(기본 = 이름)·`content`(본문, 없으면 빈 문자열)
+ config의 최상위 키(같은 이름이면 config가 이긴다).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from ruamel.yaml import YAML

from agent_console_contracts import (
    Issue,
    Resource,
    ResourceContentSpec,
    ResourceTypeDescriptor,
    UiHints,
)
from agent_console_registry import LoadReport, Registry

from ._base import SchemaResourceType, content_text
from ._interfaces import Content, ContributeContext, Contribution, ResourceType
from ._schema import InvalidConfigSchemaError, check_config_schema
from ._template import fill_value, render_template

__all__ = [
    "DECLARATIVE_SUFFIXES",
    "ContributionSpec",
    "DeclarativeResourceType",
    "DeclarativeTypeError",
    "DeclarativeTypeSpec",
    "declarative_type_from_data",
    "load_declarative_types",
]

DECLARATIVE_SUFFIXES = (".yaml", ".yml")
"""선언형 종류 파일 확장자."""


class DeclarativeTypeError(ValueError):
    """선언형 종류 데이터가 잘못됐다(형식 오류·잘못된 config_schema)."""


class ContributionSpec(BaseModel):
    """선언형 종류의 기여 하나. `template`(문자열)과 `value`(구조 값) 중 하나만 둔다.

    결과는 칸 항목 하나(`[결과]`)로 들어간다. `raw=True`면 감싸지 않고 결과 그대로 합친다.
    """

    model_config = ConfigDict(extra="forbid")

    slot: str = Field(min_length=1)
    template: str | None = None
    value: Any = None
    combine: str | None = None
    raw: bool = False

    @model_validator(mode="after")
    def _one_of(self) -> ContributionSpec:
        if (self.template is None) == (self.value is None):
            raise ValueError("contributes 항목에는 template과 value 중 하나만 둡니다")
        return self


class DeclarativeTypeSpec(BaseModel):
    """선언형 종류 파일의 형식."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    version: int = 1
    title: str = Field(min_length=1)
    description: str = ""
    config_schema: dict[str, Any] = Field(default_factory=dict)
    ui_schema: dict[str, Any] = Field(default_factory=dict)
    content: ResourceContentSpec | None = None
    slot_key: str | None = None
    combine: str = "append"
    contributes: list[ContributionSpec] = Field(min_length=1)
    ui_hints: UiHints | None = None


class DeclarativeResourceType(SchemaResourceType):
    """선언형 데이터로 만든 리소스 종류. `declarative_type_from_data`로 만든다."""

    def __init__(self, spec: DeclarativeTypeSpec) -> None:
        self.spec = spec
        slots = list(dict.fromkeys(c.slot for c in spec.contributes))
        self.descriptor = ResourceTypeDescriptor(
            id=spec.id,
            version=spec.version,
            title=spec.title,
            description=spec.description,
            config_schema=spec.config_schema,
            ui_schema=spec.ui_schema,
            content=spec.content,
            slot_key=spec.slot_key,
            combine=spec.combine,
            contributes=slots,
            declarative=True,
            ui_hints=spec.ui_hints,
        )

    def extra_issues(self, resource: Resource) -> list[Issue]:
        """문서형 종류인데 본문 참조가 없으면 경고."""
        if self.spec.content is not None and resource.content is None:
            return [
                Issue(
                    severity="warning",
                    code="resource.content_missing",
                    message="본문이 없습니다",
                    details={"resource": resource.id, "resource_type": resource.type},
                )
            ]
        return []

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """기여 항목마다 템플릿을 치환한다."""
        values: dict[str, Any] = {
            "id": resource.id,
            "name": resource.name,
            "title": resource.name,
            "description": resource.description,
            "content": content_text(content) or "",
        }
        values.update(resource.config)
        out: list[Contribution] = []
        for spec in self.spec.contributes:
            if spec.template is not None:
                value: Any = render_template(spec.template, values)
            else:
                value = fill_value(spec.value, values)
            if not spec.raw:
                value = [value]
            out.append(Contribution(spec.slot, value, spec.combine))
        return out


def declarative_type_from_data(data: Mapping[str, Any]) -> DeclarativeResourceType:
    """선언형 종류 데이터(파싱된 YAML) → `DeclarativeResourceType`.

    Raises:
        DeclarativeTypeError: 형식이 틀렸거나 config_schema가 잘못됐을 때.
    """
    try:
        spec = DeclarativeTypeSpec.model_validate(dict(data))
        check_config_schema(spec.config_schema)
    except ValidationError as exc:
        raise DeclarativeTypeError(str(exc)) from exc
    except InvalidConfigSchemaError as exc:
        raise DeclarativeTypeError(f"config_schema가 잘못됐습니다: {exc}") from exc
    return DeclarativeResourceType(spec)


def _read_yaml(path: Path) -> Any:
    return YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))


def load_declarative_types(
    directory: Path | str,
    registry: Registry[ResourceType],
    *,
    read: Callable[[Path], Any] = _read_yaml,
    files: Iterable[Path] | None = None,
) -> list[LoadReport]:
    """폴더의 선언형 종류 파일(`*.yaml`·`*.yml`)을 읽어 `registry`에 등록한다.

    Args:
        directory: 선언형 종류 폴더(예: `<workspace>/resource-types`). 없으면 빈 결과.
        registry: 등록 대상.
        read: 파일 → 파싱된 데이터(기본 ruamel.yaml safe). 테스트에서 바꿀 수 있다.
        files: 선택. 폴더를 훑는 대신 읽을 파일 목록.

    Returns:
        파일별 `LoadReport`(파일 이름 순). 형식 오류·중복 id(entry point 종류와 겹침 포함)는
        예외 대신 `failed`로 담긴다. 레지스트리 key = 데이터의 `id`.
    """
    base = Path(directory)
    if files is None:
        if not base.is_dir():
            return []
        paths = sorted(p for p in base.iterdir() if p.suffix in DECLARATIVE_SUFFIXES)
    else:
        paths = sorted(Path(p) for p in files)
    reports: list[LoadReport] = []
    for path in paths:
        source = f"declarative {path.name}"
        key: str | None = None
        try:
            data = read(path)
            if not isinstance(data, Mapping):
                raise DeclarativeTypeError("최상위 값이 객체가 아닙니다")
            raw_id = data.get("id")
            key = raw_id if isinstance(raw_id, str) else None
            item = declarative_type_from_data(data)
            key = item.descriptor.id
            registry.register(key, item, version=item.descriptor.version, source=source)
        except Exception as exc:
            reports.append(
                LoadReport(
                    source=source, status="failed", key=key, error=f"{type(exc).__name__}: {exc}"
                )
            )
            continue
        reports.append(
            LoadReport(source=source, status="loaded", key=key, version=item.descriptor.version)
        )
    return reports
