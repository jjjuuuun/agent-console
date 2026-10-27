"""맥락 구성 표지 `agent.context_prepared`(design §5.5R.1 C1).

에이전트 노드가 백엔드 요청을 만들 때 붙은 리소스의 **표지만** 모은다: id·종류·바이트 수·sha256과
프롬프트 조각 수. 본문(프롬프트·리소스 내용)은 payload에 넣지 않는다 — 크기와 해시를 계산하려고
본문을 읽을 뿐이다. 리소스 종류 이름·칸 이름은 이 모듈에 없다(묶음 출처 `BundleSource`를 따른다).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from agent_console_contracts import (
    AgentContextPreparedPayload,
    ContextResourceRef,
    ResourceBundle,
)
from agent_console_registry import Registry, UnknownExtensionError
from agent_console_resources import FileContentLookup, ResourceLookup, ResourceType

__all__ = ["CONTEXT_PREPARED_EVENT", "content_digest", "context_prepared_payload"]

CONTEXT_PREPARED_EVENT = "agent.context_prepared"
"""에이전트 노드가 백엔드 요청 맥락을 만들었음을 알리는 이벤트 형식(계약 `runs` 1.4.0)."""


def content_digest(content: Any) -> tuple[int, str] | None:
    """본문 → (바이트 수, sha256 16진). 모르는 모양이면 None.

    - `str`: UTF-8 바이트 기준. `bytes`: 그대로.
    - 여러 파일(`{경로: 바이트}`): 바이트 수 = 파일 합, 해시 = 경로 순으로 `경로\\0파일 sha256\\n`을
      이은 것의 sha256(경로·내용 어느 쪽이 바뀌어도 바뀐다).
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    if isinstance(content, bytes | bytearray):
        return len(content), hashlib.sha256(content).hexdigest()
    if isinstance(content, Mapping):
        total = 0
        outer = hashlib.sha256()
        for path in sorted(str(k) for k in content):
            value = content[path]
            if isinstance(value, str):
                value = value.encode("utf-8")
            if not isinstance(value, bytes | bytearray):
                return None
            total += len(value)
            outer.update(f"{path}\0{hashlib.sha256(value).hexdigest()}\n".encode())
        return total, outer.hexdigest()
    return None


def _read(
    ref: str, resources: ResourceLookup, resource_types: Registry[ResourceType] | None
) -> Any:
    try:
        resource = resources.get_resource(ref)
    except LookupError:
        return None
    if resource is None:
        return None
    multi = False
    if resource_types is not None:
        try:
            spec = resource_types.get(resource.type).descriptor.content
        except UnknownExtensionError:
            spec = None
        multi = bool(spec is not None and spec.multi_file)
    if multi:
        return resources.read_files(resource) if isinstance(resources, FileContentLookup) else None
    if resource.content is None:
        return None
    return resources.read_content(resource)


def context_prepared_payload(
    bundle: ResourceBundle | None,
    resources: ResourceLookup | None = None,
    *,
    resource_types: Registry[ResourceType] | None = None,
    fragments: int | None = None,
) -> AgentContextPreparedPayload:
    """실행 묶음 → `agent.context_prepared` payload(본문 없음).

    Args:
        bundle: 백엔드 요청에 붙은 실행 묶음(없으면 리소스 없음). 칸별 출처(`sources`) 순서대로,
            같은 리소스 id는 처음 한 번만 싣는다.
        resources: 선택. 본문 조회(바이트 수·해시 계산용). 없거나 본문이 없는 리소스는 둘 다 null.
        resource_types: 선택. 종류 레지스트리(여러 파일 본문 종류를 `read_files`로 읽는다).
        fragments: 프롬프트를 이룬 조각 수(모르면 None).

    Returns:
        `AgentContextPreparedPayload`. 종류 = 출처의 리소스 종류 id(없으면 칸 이름).
        본문을 읽다 실패하면 그 리소스의 크기·해시만 null이다(예외를 올리지 않는다).
    """
    refs: list[ContextResourceRef] = []
    seen: set[str] = set()
    for slot, sources in (bundle.sources if bundle is not None else {}).items():
        for source in sources:
            if source.ref in seen:
                continue
            seen.add(source.ref)
            digest: tuple[int, str] | None = None
            if resources is not None:
                try:
                    digest = content_digest(_read(source.ref, resources, resource_types))
                except Exception:  # 조회 구현(사용자 플러그인) 실패가 실행을 막지 않게
                    digest = None
            refs.append(
                ContextResourceRef(
                    id=source.ref,
                    kind=source.resource_type or slot,
                    bytes=digest[0] if digest is not None else None,
                    sha256=digest[1] if digest is not None else None,
                )
            )
    return AgentContextPreparedPayload(resources=refs, fragments=fragments)
