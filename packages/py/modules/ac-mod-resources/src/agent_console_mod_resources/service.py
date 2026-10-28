"""리소스 경로의 동작(종류 검사·요약·본문·여러 파일). FastAPI를 모른다."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from agent_console_contracts import (
    DefinitionReference,
    Issue,
    MergeStrategyInfo,
    Resource,
    ResourceSummary,
    ResourceTypeDescriptor,
)
from agent_console_registry import Registry, UnknownExtensionError
from agent_console_resources import (
    ResourceType,
    list_descriptors,
    resource_strategies,
    validate_resource,
)
from agent_console_store import RESOURCE_KIND, SCOPE_FIELD, StoredDefinition

from .errors import NOT_MULTI_FILE, RESERVED_FILE_NAME, ResourceRejectedError
from .ports import DefinitionCheck, DefinitionUsages, ResourceStore

_log = logging.getLogger("agent_console_mod_resources")

RESOURCE_CONFIG_POINTER = "/config"
"""리소스 문서에서 config의 위치(종류 검사 이슈 path의 기준)."""


def resource_document_path(path: str | None) -> str:
    """config 기준 JSON Pointer → 리소스 문서 기준(``/env/A`` → ``/config/env/A``)."""
    if not path:
        return RESOURCE_CONFIG_POINTER
    return RESOURCE_CONFIG_POINTER + (path if path.startswith("/") else "/" + path)


def resource_issues(resource: Resource, types: Registry[ResourceType]) -> list[Issue]:
    """리소스 종류 검사(``validate_resource``) 이슈. path는 리소스 문서 기준."""
    return [
        i.model_copy(update={"path": resource_document_path(i.path)})
        for i in validate_resource(resource, types)
    ]


def merge_strategies() -> list[MergeStrategyInfo]:
    """설정 ``settings_merge``에 쓸 수 있는 병합 전략 이름(유효 설정 계산과 같은 전략 표)."""
    table = resource_strategies()
    out: list[MergeStrategyInfo] = []
    for name in table:
        doc = (getattr(table[name], "__doc__", None) or "").strip().splitlines()
        out.append(MergeStrategyInfo(id=name, description=doc[0] if doc else ""))
    return out


class ResourceService:
    """리소스 경로의 동작 묶음.

    Args:
        store: 정의 저장소.
        types: 리소스 종류 레지스트리.
        usages: 붙은 곳 제공자(부를 때마다, 없으면 None → ``usage_count`` null).
        content_files: 본문 형식 → 처음 저장할 본문 파일 이름.
        default_content_file: 표에 없는 형식의 본문 파일 이름.
        reserved_file_names: 여러 파일 본문 경로에 있으면 경고할 이름(대소문자 무시).
        checks: 지금 저장 전 정의 검사 목록(``definitions.checks``, 부를 때마다 — 늦게 켜진
            제공자도 보인다). 없으면 종류 검사만 한다.
    """

    def __init__(
        self,
        store: ResourceStore,
        types: Registry[ResourceType],
        *,
        usages: Callable[[], DefinitionUsages | None] = lambda: None,
        content_files: Mapping[str, str] | None = None,
        default_content_file: str = "content.txt",
        kind: str = RESOURCE_KIND.name,
        reserved_file_names: Iterable[str] = (),
        checks: Callable[[], Sequence[DefinitionCheck]] = lambda: (),
    ) -> None:
        self.store = store
        self._checks = checks
        self.types = types
        self.kind = kind
        self._usages = usages
        self._content_files = dict(content_files or {})
        self._default_content_file = default_content_file
        self._reserved = {n.casefold(): n for n in reserved_file_names if n}

    # ------------------------------------------------------------ 검사

    def issues(self, resource: Resource) -> list[Issue]:
        """종류 검사 이슈 + 저장 전 정의 검사(``definitions.checks``) 이슈(path = 문서 기준).

        같은 코드·path의 이슈는 한 번만 낸다(종류 검사를 저장 전 검사로도 주는 연동이 있다).
        검사 하나가 예외를 내면 기록하고 그 검사만 건너뛴다(제공 모듈의 오류 타입을 모른다).
        """
        found = resource_issues(resource, self.types)
        checks = self._checks()
        if not checks:
            return found
        seen = {(i.code, i.path) for i in found}
        document = resource.model_dump(mode="json", exclude_unset=True)
        for check in checks:
            try:
                extra = list(check.issues(self.kind, document))
            except Exception:
                _log.exception("저장 전 정의 검사 실패(리소스): %s", type(check).__name__)
                continue
            for issue in extra:
                key = (issue.code, issue.path)
                if key in seen:
                    continue
                seen.add(key)
                found.append(issue)
        return found

    def check(self, resource: Resource) -> list[Issue]:
        """검사에 error가 있으면 ``ResourceRejectedError``(422). 아니면 저장은 하되 보일 이슈
        (warning·info — 예: 등록되지 않은 종류, 메모리 리소스의 모르는 범위 종류)를 돌려준다."""
        issues = self.issues(resource)
        if any(i.severity == "error" for i in issues):
            raise ResourceRejectedError(issues, "리소스 설정에 오류가 있어 저장하지 않았습니다")
        return issues

    def is_multi_file(self, type_id: str) -> bool:
        """종류 디스크립터가 여러 파일 본문(``content.multi_file``)이면 참. 모르는 종류는 거짓."""
        try:
            descriptor = self.types.get(type_id).descriptor
        except UnknownExtensionError:
            return False
        return descriptor.content is not None and descriptor.content.multi_file

    def require_multi_file(self, stored: StoredDefinition) -> None:
        type_id = stored.document.get("type")
        if isinstance(type_id, str) and self.is_multi_file(type_id):
            return
        raise ResourceRejectedError(
            [
                Issue(
                    severity="error",
                    code=NOT_MULTI_FILE,
                    message=(
                        "이 리소스 종류는 여러 파일 본문을 쓰지 않습니다(본문은 /content로 저장)"
                    ),
                    details={"resource_type": type_id if isinstance(type_id, str) else None},
                )
            ],
            "여러 파일 본문을 쓸 수 없는 리소스입니다",
        )

    def file_path_issues(self, file_path: str) -> list[Issue]:
        """여러 파일 본문 경로의 경고(저장은 막지 않는다). 예약 이름 칸마다 warning 하나.

        메시지에는 파일 경로와 예약 이름만 담고 파일 내용은 담지 않는다.
        ``details`` = ``{path, name}``, ``path``(이슈 위치) = JSON Pointer ``/files/<파일 경로>``
        (파일 경로의 ``/``는 ``~1``) — 저장 경고 배너가 위치를 보이도록(5R.19, 4R.19 QA).
        """
        pointer = "/files/" + file_path.replace("~", "~0").replace("/", "~1")
        issues: list[Issue] = []
        for part in file_path.split("/"):
            reserved = self._reserved.get(part.casefold())
            if reserved is None:
                continue
            issues.append(
                Issue(
                    severity="warning",
                    code=RESERVED_FILE_NAME,
                    message=(
                        f"파일 '{file_path}' 경로에 예약 이름 '{reserved}'이(가) 있습니다. "
                        "저장했지만 실행 폴더·버전 관리와 겹칠 수 있으니 다른 이름을 권장합니다"
                    ),
                    path=pointer,
                    details={"path": file_path, "name": reserved},
                )
            )
        return issues

    # ------------------------------------------------------------ 조회

    def references(self, resource_id: str) -> list[DefinitionReference] | None:
        """붙은 곳(제공자가 없으면 None)."""
        usages = self._usages()
        return None if usages is None else list(usages.references(self.kind, resource_id))

    def summaries(self, type_filter: str | None = None) -> list[ResourceSummary]:
        """요약(id 순). ``type_filter``로 종류를 거른다. ``usage_count`` = 붙은 곳 수(또는 null)."""
        usages = self._usages()
        out: list[ResourceSummary] = []
        for s in self.store.summaries(self.kind):
            if type_filter is not None and s.extra.get("type") != type_filter:
                continue
            count = None if usages is None else len(usages.references(self.kind, s.id))
            out.append(
                ResourceSummary(
                    id=s.id,
                    type=s.extra.get("type") or "unknown",
                    name=s.name,
                    description=s.description,
                    labels=s.labels,
                    version_hash=s.version_hash,
                    saved_at=s.saved_at,
                    has_content=s.has_content,
                    usage_count=count,
                    project=s.extra.get(SCOPE_FIELD),
                    attributes=s.attributes,
                )
            )
        return out

    def descriptors(self) -> list[ResourceTypeDescriptor]:
        return list_descriptors(self.types)

    # ------------------------------------------------------------ 본문

    def content_file_for(self, media_type: str | None, current: Mapping[str, Any]) -> str | None:
        """처음 저장할 본문 파일 이름(이미 파일이 있으면 None — 그대로 쓴다)."""
        content = current.get("content")
        if isinstance(content, dict) and isinstance(content.get("file"), str):
            return None
        return self._content_files.get(media_type or "", self._default_content_file)


__all__ = [
    "RESOURCE_CONFIG_POINTER",
    "ResourceService",
    "merge_strategies",
    "resource_document_path",
    "resource_issues",
]
