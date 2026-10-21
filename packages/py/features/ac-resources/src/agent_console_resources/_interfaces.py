"""X14 리소스 종류 인터페이스와 주입 프로토콜(design §R12.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Issue, Resource, ResourceAttachment, ResourceTypeDescriptor

__all__ = [
    "Content",
    "ContentFiles",
    "ContributeContext",
    "Contribution",
    "FileContentLookup",
    "InMemoryResources",
    "ResourceLookup",
    "ResourceType",
]

type ContentFiles = Mapping[str, bytes]
"""여러 파일 본문(`ResourceContentSpec.multi_file` 종류): 본문 폴더 기준 상대 경로(`/`) → 내용."""

type Content = str | bytes | ContentFiles | None
"""리소스 본문. 단일 문서는 `str | bytes`, 여러 파일 종류는 `ContentFiles`(경로 → 바이트).
문서형이 아니거나 읽지 못했으면 `None`."""


@dataclass(frozen=True, slots=True)
class Contribution:
    """리소스 하나가 실행 묶음 칸 하나에 내는 값.

    - `slot`: 칸 이름(예: `instructions`). 문자열이며 목록은 코드에 없다.
    - `value`: 칸에 합칠 값. 목록 칸은 보통 원소 목록(`[항목]`)을 낸다.
    - `combine`: 선택. 이 기여에만 쓸 합치기 전략 이름. `None`이면 종류 디스크립터의 `combine`.
    - `fallback`: 선택. 실행 백엔드가 `slot`을 받지 않을 때(`accepted_slots`에 없음) 대신 쓸 기여
      (예: 경로 조건 지침 칸을 못 받는 백엔드에는 일반 지침 칸으로). 대체 칸도 받지 않으면 원래
      기여를 그대로 두고 `resource.slot_unsupported`로 알린다. 받는 칸을 모르면(`accepted_slots`
      없음) 쓰지 않는다.
    """

    slot: str
    value: Any
    combine: str | None = None
    fallback: Contribution | None = None


@dataclass(frozen=True, slots=True)
class ContributeContext:
    """`contribute`에 넘기는 맥락(읽기 전용).

    - `attachment`: 이 기여를 만든 첨부(설정 덮어쓰기는 이미 리소스 config에 반영돼 있다).
    - `layer`: 첨부가 들어온 설정 층 id(모르면 `None`).
    """

    attachment: ResourceAttachment
    layer: str | None = None


@runtime_checkable
class ResourceType(Protocol):
    """리소스 종류(X14). entry point `agent_console.resource_types` 또는 선언형 데이터로 등록한다.

    구현은 순수해야 한다: 파일 쓰기·네트워크·비밀 해석을 하지 않는다. 비밀은 `secret://` 참조
    문자열 그대로 묶음에 넣고, 실제 값은 실행 백엔드가 비밀 공급자로 푼다.
    """

    descriptor: ResourceTypeDescriptor

    def validate(self, resource: Resource) -> list[Issue]:
        """리소스 정의(설정 덮어쓰기 반영)를 검사한다. `error` 이슈가 있으면 묶음에서 빠진다."""
        ...

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """리소스 → 칸별 기여 목록. 순수 함수(파일 쓰기 없음)."""
        ...


@runtime_checkable
class FileContentLookup(Protocol):
    """선택 능력: 여러 파일 본문 읽기. `ResourceLookup` 구현이 함께 가지면 묶음 조립이
    `content.multi_file` 종류의 본문을 이것으로 읽는다(없으면 본문 없음 경고)."""

    def read_files(self, resource: Resource) -> ContentFiles | None:
        """리소스 본문 폴더의 파일 전부(경로 → 바이트). 없거나 읽지 못하면 `None`."""
        ...


@runtime_checkable
class ResourceLookup(Protocol):
    """리소스 정의·본문 조회(저장소가 구조적으로 구현한다)."""

    def get_resource(self, ref: str) -> Resource | None:
        """id로 정의를 찾는다. 없으면 `None`."""
        ...

    def read_content(self, resource: Resource) -> Content:
        """정의의 본문(`resource.content`)을 읽는다. 본문이 없거나 읽지 못하면 `None`."""
        ...


class InMemoryResources:
    """메모리 `ResourceLookup`·`FileContentLookup` 구현(테스트·스크립트용).

    Args:
        resources: 리소스 정의 목록.
        contents: 선택. `{리소스 id: 본문}`. 여러 파일 본문은 `{경로: 바이트}`로 준다.
    """

    def __init__(
        self,
        resources: list[Resource] | tuple[Resource, ...] = (),
        contents: Mapping[str, str | bytes | ContentFiles] | None = None,
    ) -> None:
        self._resources = {r.id: r for r in resources}
        self._contents = dict(contents or {})

    def get_resource(self, ref: str) -> Resource | None:
        """id로 정의를 찾는다."""
        return self._resources.get(ref)

    def read_content(self, resource: Resource) -> Content:
        """본문을 돌려준다(정의에 `content`가 없으면 `None`)."""
        if resource.content is None:
            return None
        found = self._contents.get(resource.id)
        if isinstance(found, Mapping):
            return found.get(resource.content.file)
        return found

    def read_files(self, resource: Resource) -> ContentFiles | None:
        """여러 파일 본문(`{경로: 바이트}`로 준 것). 단일 본문이면 `{content.file: 바이트}`."""
        found = self._contents.get(resource.id)
        if found is None:
            return None
        if isinstance(found, Mapping):
            return dict(found)
        if resource.content is None:
            return None
        data = found.encode("utf-8") if isinstance(found, str) else found
        return {resource.content.file: data}
