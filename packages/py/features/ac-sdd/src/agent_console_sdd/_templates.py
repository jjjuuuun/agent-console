"""문서 틀 ↔ 스펙 변환(`instantiate`·`spec_to_template`)과 정의 종류 만들기(design §6R.1.1·§6R.1.2,
§6R.18 Q8).

둘 다 복사다. 결과 문서에 원본(틀·스펙) id·버전 같은 출처 메타를 쓰지 않는다(K33-17) — 출처는
호출자가
버전 기록 메시지에만 남긴다. 종류 이름·폴더 이름은 호출자 데이터(`mod-sdd` 설치자 옵션)다.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any

from pydantic import BaseModel
from ruamel.yaml import YAML

from agent_console_contracts.sdd import SpecDefinition, SpecDocument, SpecTemplate
from agent_console_store import DefinitionKind

__all__ = [
    "BLANK_SPEC_RESOURCE",
    "CONTENT_FIELD",
    "SpecDraft",
    "blank_documents",
    "definition_kinds",
    "instantiate",
    "spec_to_template",
]

BLANK_SPEC_RESOURCE = "data/blank_spec.yaml"
"""틀 없이 만든 스펙의 문서 목록(패키지 기본 데이터)."""

CONTENT_FIELD = "content"
"""스펙·틀 정의의 본문 참조 필드(`SpecContentRef`)."""

# 복사하는 최상위 키. 그 밖의 최상위 키(손으로 더한 것)는 원본 쪽 데이터라 옮기지 않는다.
_COPIED = ("description", "documents", "rules", "labels", "attributes")
_STATE_KEYS = ("state", "state_changed")


@dataclass(slots=True)
class SpecDraft:
    """저장 전 정의 문서(JSON 호환 dict)와 본문 파일(본문 폴더 기준 경로 → 내용)."""

    document: dict[str, Any]
    files: dict[str, bytes] = field(default_factory=dict)

    def spec(self) -> SpecDefinition:
        """스펙 모델로 검증한 것."""
        return SpecDefinition.model_validate(self.document)

    def template(self) -> SpecTemplate:
        """문서 틀 모델로 검증한 것."""
        return SpecTemplate.model_validate(self.document)


def _raw(source: SpecTemplate | SpecDefinition | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, BaseModel):
        dumped: dict[str, Any] = source.model_dump(mode="json", by_alias=True, exclude_none=True)
        return dumped
    return copy.deepcopy(dict(source))


@cache
def _blank() -> tuple[dict[str, Any], ...]:
    text = (resources.files("agent_console_sdd") / BLANK_SPEC_RESOURCE).read_text(encoding="utf-8")
    data = YAML(typ="safe").load(text) or {}
    docs = data.get("documents") if isinstance(data, dict) else None
    return tuple(dict(d) for d in docs or ())


def blank_documents() -> list[SpecDocument]:
    """틀 없이 만든 스펙의 문서 목록(패키지 기본 데이터 `data/blank_spec.yaml`, 새 사본)."""
    return [SpecDocument.model_validate(d) for d in _blank()]


def _documents(
    raw_docs: Any, *, keep_state: bool, initial_state: str | None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for doc in raw_docs if isinstance(raw_docs, list) else ():
        if not isinstance(doc, Mapping):
            continue
        item = copy.deepcopy(dict(doc))
        if not keep_state:
            for key in _STATE_KEYS:
                item.pop(key, None)
            if initial_state is not None:
                item["state"] = initial_state
        out.append(item)
    return out


def _assemble(
    raw: Mapping[str, Any],
    *,
    kind: str,
    id: str,
    name: str,
    description: str | None,
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    doc: dict[str, Any] = {"kind": kind, "id": id, "name": name}
    for key in _COPIED:
        if key in raw:
            doc[key] = copy.deepcopy(raw[key])
    doc["documents"] = documents
    if description is not None:
        doc["description"] = description
    if documents:
        doc[CONTENT_FIELD] = {"file": documents[0]["file"]}
    return doc


def _initial_state(raw: Mapping[str, Any]) -> str | None:
    rules = raw.get("rules")
    value = rules.get("initial_document_state") if isinstance(rules, Mapping) else None
    return value if isinstance(value, str) and value else None


def instantiate(
    template: SpecTemplate | Mapping[str, Any],
    files: Mapping[str, bytes],
    *,
    kind: str,
    id: str,
    name: str,
    description: str | None = None,
) -> SpecDraft:
    """문서 틀 → 새 스펙(복사, 이후 틀과 독립).

    틀의 문서 목록·규칙·설명·라벨·속성과 본문 파일을 그대로 복사한다. 문서 상태는 비우고 규칙에
    처음 문서 상태(`initial_document_state`)가 있으면 그 값으로 둔다. 틀에 본문이 없는 문서는 빈
    파일로 만든다. 틀 id·버전은 결과에 쓰지 않는다.

    Args:
        template: 문서 틀(모델 또는 저장된 문서 dict — 모르는 키 보존).
        files: 틀 본문 파일(본문 폴더 기준 경로 → 내용).
        kind: 스펙 정의 종류 이름(호출자 데이터).
        id: 새 스펙 id.
        name: 새 스펙 이름.
        description: 주면 틀 설명 대신 쓴다.

    Raises:
        pydantic.ValidationError: 결과가 스펙 모양이 아니다(틀이 깨졌을 때).
    """
    raw = _raw(template)
    docs = _documents(raw.get("documents"), keep_state=False, initial_state=_initial_state(raw))
    document = _assemble(raw, kind=kind, id=id, name=name, description=description, documents=docs)
    out = {path: bytes(data) for path, data in files.items()}
    for d in docs:
        out.setdefault(d["file"], b"")
    draft = SpecDraft(document=document, files=out)
    draft.spec()
    return draft


def spec_to_template(
    spec: SpecDefinition | Mapping[str, Any],
    files: Mapping[str, bytes | None],
    *,
    kind: str,
    id: str,
    name: str,
    include_content: bool = False,
    description: str | None = None,
) -> SpecDraft:
    """스펙 → 새 문서 틀(틀로 저장, §6R.18 Q8).

    문서 목록·규칙을 복사하고 문서 상태 값·상태 바꾼 기록은 뺀다. `include_content`가 거짓이면 문서
    본문 파일은 빈 파일이다(제목 줄도 남기지 않는다). 참이면 본문 폴더의 파일을 모두 복사한다.
    프로필의
    팀 구성은 복사하지 않는다(틀은 그래프 id만 가진다). 스펙 id는 결과에 쓰지 않는다.

    Args:
        spec: 스펙(모델 또는 저장된 문서 dict).
        files: 스펙 본문 파일(경로 → 내용, None = 없음).
        kind: 문서 틀 정의 종류 이름(호출자 데이터).
        id: 새 틀 id.
        name: 새 틀 이름.
        include_content: 본문도 복사한다.
        description: 주면 스펙 설명 대신 쓴다.
    """
    raw = _raw(spec)
    docs = _documents(raw.get("documents"), keep_state=False, initial_state=None)
    document = _assemble(raw, kind=kind, id=id, name=name, description=description, documents=docs)
    out: dict[str, bytes] = {}
    if include_content:
        out = {path: bytes(data) for path, data in files.items() if data is not None}
    for d in docs:
        if include_content:
            out.setdefault(d["file"], b"")
        else:
            out[d["file"]] = b""
    draft = SpecDraft(document=document, files=out)
    draft.template()
    return draft


def definition_kinds(
    *,
    spec_kind: str,
    spec_directory: str,
    template_kind: str,
    template_directory: str,
    summary_fields: Sequence[str] = (),
) -> tuple[DefinitionKind, DefinitionKind]:
    """스펙·문서 틀 정의 종류(`ac-store` `DefinitionKind`)를 만든다. 이름·폴더는 호출자 데이터.

    둘 다 여러 파일 본문(`multi_file`, 본문 폴더 = 문서 파일들), 저장은 `If-Match` 필수, 옮길 수
    있음.
    스펙은 `library=False`(프로젝트·단독 공간에만, design §6R.3 X36), 문서 틀은 라이브러리에도 둔다.

    Returns:
        (스펙 종류, 문서 틀 종류).
    """
    common: dict[str, Any] = {
        "require_version": True,
        "content_field": CONTENT_FIELD,
        "multi_file": True,
        "summary_fields": tuple(summary_fields),
    }
    spec = DefinitionKind(
        name=spec_kind, directory=spec_directory, model=SpecDefinition, library=False, **common
    )
    template = DefinitionKind(
        name=template_kind, directory=template_directory, model=SpecTemplate, **common
    )
    return spec, template
