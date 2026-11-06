"""확장 지점 선언 모델(Pydantic). 공용 JSON Schema(``declaration.schema.json``)의 단일 소스다.

선언 자리:

- Python 패키지: ``pyproject.toml``의 ``[tool.agent-console.extension-points.<slug>]``
  (같은 표의 ``internal-ports``·``internal-groups``, 예제 패키지는 ``[tool.agent-console.example]``)
- TS 패키지·앱: ``package.json``의 ``"agentConsole": {"extensionPoints": {"<slug>": {...}}}``
  (예제는 ``"agentConsole": {"example": {"points": [...]}}``)

두 곳 모두 같은 모델로 검증한다. 키 이름은 선언 표의 키(``design_id`` 등) 그대로다.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
"""지점 id(slug) 형식: 소문자·숫자·하이픈(문서 앵커와 같다)."""

GUIDE_PATTERN = r"^[^#\s]+\.md(?:#[^\s#]+)?$"
"""``guide`` 형식: 문서 폴더 기준 ``파일.md#절``(절을 생략하면 slug)."""

EXAMPLE_KINDS = ("package", "reference", "contract-tests", "snippet")


class Registration(BaseModel):
    """등록 방법. ``kind``는 열린 문자열이다(생성기가 모르는 값은 원문 그대로 표에 나온다).

    생성기가 아는 ``kind``와 쓰는 필드:
    ``entry-point``(``group`` = 그룹 상수 기호 ``모듈:이름`` 또는 그룹 문자열),
    ``port``(``port`` = ``PortKey`` 기호, ``multi``), ``data``(``path``·``settings``·``disable``),
    ``injection``, ``annotation``·``descriptor``·``registry``(``name``), ``props``(``export``).
    모르는 kind가 쓰는 필드를 위해 그 밖의 키도 받는다.
    """

    model_config = ConfigDict(extra="allow")

    kind: str = Field(min_length=1, description="등록 종류(열린 문자열)")
    group: str | None = Field(default=None, description="entry point 그룹 상수 기호 또는 그룹 이름")
    port: str | None = Field(default=None, description="포트 기호(모듈:이름)")
    multi: bool | None = Field(default=None, description="다중 포트 여부(생략하면 코드에서 읽음)")
    path: str | None = Field(default=None, description="패키지 데이터 파일(패키지 폴더 기준)")
    settings: list[str] = Field(default_factory=list, description="덮어쓰는 설정 키")
    disable: list[str] = Field(default_factory=list, description="끄는 설정 키")
    export: str | None = Field(default=None, description="TS export(@pkg#이름)")
    name: str | None = Field(default=None, description="주석 키·서술자 필드·레지스트리 이름")

    @field_validator("settings", "disable", mode="before")
    @classmethod
    def _one_or_many(cls, value: Any) -> Any:
        return [value] if isinstance(value, str) else value


class Example(BaseModel):
    """지점을 보이는 예제 하나.

    ``package``(설치형 예제 폴더 ``path``), ``reference``(저장소 안 참조 구현 ``path``),
    ``contract-tests``(계약 테스트 묶음·대역 기호 ``symbols``), ``snippet``(가이드 절 안의
    검증되는 조각 — 절은 지점의 ``guide``).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["package", "reference", "contract-tests", "snippet"]
    path: str | None = Field(default=None, description="저장소 루트 기준 폴더")
    symbols: list[str] = Field(default_factory=list, description="계약 테스트·대역 기호")
    note: str | None = Field(default=None, description="한 줄 설명(선택)")

    @model_validator(mode="after")
    def _required_fields(self) -> Example:
        if self.kind in ("package", "reference") and not self.path:
            raise ValueError(f"예제 종류 {self.kind}에는 path가 필요합니다")
        if self.kind == "contract-tests" and not self.symbols:
            raise ValueError("예제 종류 contract-tests에는 symbols가 필요합니다")
        return self


class ExtensionPoint(BaseModel):
    """확장 지점 선언 하나(표 키 = slug)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, description="사람이 읽는 이름")
    area: str = Field(min_length=1, description="문서 영역 id(areas.yaml)")
    summary: str = Field(min_length=1, description="한 줄 설명")
    design_id: str | None = Field(default=None, description="내부 설계 번호(문서에 내지 않음)")
    registration: Registration
    interface: list[str] = Field(
        default_factory=list, description="공개 기호(모듈:이름, @pkg#이름)"
    )
    settings: list[str] = Field(default_factory=list, description="관련 설정 키")
    builtin: str | None = Field(
        default=None, description="기본 구현 목록을 모으는 방법(entry-points·providers·none)"
    )
    example: list[Example] = Field(default_factory=list, description="예제(하나 이상이어야 완성)")
    guide: str | None = Field(default=None, pattern=GUIDE_PATTERN, description="가이드 파일#절")

    @field_validator("example", mode="before")
    @classmethod
    def _example_one_or_many(cls, value: Any) -> Any:
        return [value] if isinstance(value, dict) else value

    @field_validator("interface", "settings", mode="before")
    @classmethod
    def _str_one_or_many(cls, value: Any) -> Any:
        return [value] if isinstance(value, str) else value


class ExtensionPointTable(RootModel[dict[str, ExtensionPoint]]):
    """선언 표 전체: slug → 선언. 공용 JSON Schema의 최상위."""

    @field_validator("root")
    @classmethod
    def _slugs(cls, value: dict[str, ExtensionPoint]) -> dict[str, ExtensionPoint]:
        bad = [slug for slug in value if not re.fullmatch(SLUG_PATTERN, slug)]
        if bad:
            raise ValueError(f"slug 형식이 아닙니다(소문자·숫자·하이픈): {', '.join(sorted(bad))}")
        return value


class InternalPort(BaseModel):
    """확장 지점이 아닌 포트(모듈끼리 쓰는 내부 포트)와 그 사유."""

    model_config = ConfigDict(extra="forbid")

    port: str = Field(min_length=1, description="포트 이름 또는 포트 기호(모듈:이름)")
    reason: str = Field(min_length=1, description="확장 지점이 아닌 이유")


class InternalGroup(BaseModel):
    """확장 지점이 아닌 entry point 그룹과 그 사유."""

    model_config = ConfigDict(extra="forbid")

    group: str = Field(min_length=1, description="그룹 이름 또는 그룹 상수 기호")
    reason: str = Field(min_length=1)


class ExampleMarker(BaseModel):
    """예제 패키지가 자기가 보이는 지점을 알리는 표."""

    model_config = ConfigDict(extra="forbid")

    points: list[str] = Field(min_length=1, description="이 예제가 보이는 지점 slug")


class ToolTable(BaseModel):
    """``[tool.agent-console]`` 표(Python). 이 도구가 모르는 키는 무시한다."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    extension_points: ExtensionPointTable = Field(
        default_factory=lambda: ExtensionPointTable({}), alias="extension-points"
    )
    internal_ports: list[InternalPort] = Field(default_factory=list, alias="internal-ports")
    internal_groups: list[InternalGroup] = Field(default_factory=list, alias="internal-groups")
    example: ExampleMarker | None = None


class PackageJsonTable(BaseModel):
    """``package.json``의 ``agentConsole`` 표(TS). 이 도구가 모르는 키(``kind`` 등)는 무시한다."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    extension_points: ExtensionPointTable = Field(
        default_factory=lambda: ExtensionPointTable({}), alias="extensionPoints"
    )
    example: ExampleMarker | None = None


_ONE_OR_MANY = {
    "ExtensionPoint": ("example", "interface", "settings"),
    "Registration": ("settings", "disable"),
}


def declaration_json_schema() -> dict[str, Any]:
    """공용 JSON Schema(선언 표 slug → 선언, ``$defs``에 예제 표·내부 포트).

    TS 쪽(``pnpm extdocs-check``)이 같은 파일로 ``agentConsole.extensionPoints``를 검사한다.
    """
    schema = ExtensionPointTable.model_json_schema()
    schema["propertyNames"] = {"pattern": SLUG_PATTERN}
    defs = schema.setdefault("$defs", {})
    # 모델은 "값 하나 또는 목록"을 받는다(TOML 인라인 표·문자열 하나). 스키마도 같게 적는다.
    for model_name, fields in _ONE_OR_MANY.items():
        props = defs.get(model_name, {}).get("properties", {})
        for name in fields:
            prop = props.get(name)
            if prop and prop.get("type") == "array":
                meta = {k: prop.pop(k) for k in ("title", "description", "default") if k in prop}
                props[name] = {"anyOf": [prop["items"], prop], **meta}
    for model in (ExampleMarker, InternalPort, InternalGroup):
        sub = model.model_json_schema()
        defs.update(sub.pop("$defs", {}))
        defs[model.__name__] = sub
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Agent Console extension point declarations"
    return schema


def schema_text() -> str:
    """``declaration.schema.json``에 쓸 결정적 텍스트(키 정렬, LF, 끝 줄바꿈)."""
    return (
        json.dumps(declaration_json_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


__all__ = [
    "EXAMPLE_KINDS",
    "GUIDE_PATTERN",
    "SLUG_PATTERN",
    "Example",
    "ExampleMarker",
    "ExtensionPoint",
    "ExtensionPointTable",
    "InternalGroup",
    "InternalPort",
    "PackageJsonTable",
    "Registration",
    "ToolTable",
    "declaration_json_schema",
    "schema_text",
]
