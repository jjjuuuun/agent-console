"""정의 버전 두 개 비교 → 계약 ``DefinitionDiff`` (design §2R.9, §1.1 B-4).

버전 경로를 가진 모듈(``mod-versions``의 정의 컬렉션, ``mod-sdd``의 문서 틀)이 같은 계산을 쓴다.
문서 비교는 ``agent_console_settings.diff_documents``(JSON Pointer, 비밀 위치 가림), 본문 파일은
버전 본문 스냅샷의 sha256만 비교한다. 비밀 위치를 정하는 규칙(검사 이슈·의심 규칙)은 호출자가
함수로 넘긴다 — 이 모듈은 어떤 값이 비밀인지 모른다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol

from agent_console_contracts import (
    ContentChange,
    DefinitionDiff,
    DefinitionVersion,
    DiffChange,
    ResourceFile,
)
from agent_console_settings import MISSING, diff_digests, diff_documents

from .errors import NotFound
from .interfaces import StoredDefinition

SECRET_MASK = "***"
"""비교 결과에서 비밀 위치 값 대신 쓰는 기본 문자열(계약 ``DiffChange.secret``)."""

type SecretPaths = Callable[[Mapping[str, Any]], Iterable[str]]
"""정의 문서 → 그 문서의 비밀 위치(문서 기준 JSON Pointer) 목록."""


class VersionDiffSource(Protocol):
    """비교에 필요한 저장소 능력(``DefinitionStore``가 만족한다)."""

    def get(self, kind: str, id: str) -> StoredDefinition: ...

    def get_version(self, kind: str, id: str, version_hash: str) -> DefinitionVersion: ...

    def list_version_files(self, kind: str, id: str, version_hash: str) -> list[ResourceFile]: ...


def _no_secrets(_document: Mapping[str, Any]) -> Iterable[str]:
    return ()


def _file_digests(
    store: VersionDiffSource, kind: str, item_id: str, version_hash: str
) -> dict[str, str] | None:
    try:
        files = store.list_version_files(kind, item_id, version_hash)
    except NotFound:  # 본문 스냅샷이 없는 버전(본문 없는 종류, 0003 이전 버전)
        return None
    return {f.path: f.sha256 for f in files}


def _diff_change(op: Any, path: str, before: Any, after: Any, secret: bool) -> DiffChange:
    values: dict[str, Any] = {}
    if before is not MISSING:
        values["before"] = before
    if after is not MISSING:
        values["after"] = after
    return DiffChange(op=op, path=path, secret=secret, **values)


def diff_versions(
    store: VersionDiffSource,
    kind: str,
    item_id: str,
    from_hash: str,
    to_hash: str | None = None,
    *,
    secret_paths: SecretPaths = _no_secrets,
    mask: str = SECRET_MASK,
) -> DefinitionDiff:
    """정의 ``kind/item_id``의 두 버전을 비교한다.

    Args:
        store: 버전을 읽을 저장소.
        kind: 정의 종류.
        item_id: 정의 id.
        from_hash: 이전 버전 해시.
        to_hash: 이후 버전 해시. None이면 현재 버전.
        secret_paths: 문서 → 비밀 위치(JSON Pointer). 두 버전 문서 각각에 부른다. 기본 = 없음.
        mask: 비밀 위치 값 대신 쓸 문자열.

    Returns:
        ``DefinitionDiff``. ``changes[].path``는 ``remove``·``replace`` = 이전 문서 기준,
        ``add`` = 이후 문서 기준. 한쪽 버전에 본문 스냅샷이 없으면 ``content_changes``는 빈 목록.

    Raises:
        NotFound: 버전이 없거나, ``to_hash``가 None인데 정의가 지워졌다.

    >>> from agent_console_store import DefinitionKind, InMemoryDefinitionStore
    >>> store = InMemoryDefinitionStore([DefinitionKind("note", "notes")])
    >>> a = store.create("note", {"id": "n", "name": "old", "token": "x1"}).version_hash
    >>> _ = store.save("note", {"id": "n", "name": "new", "token": "x2"}, expected_version=a)
    >>> diff = diff_versions(store, "note", "n", a, secret_paths=lambda doc: ["/token"])
    >>> [(c.path, c.before, c.after, c.secret) for c in diff.changes]
    [('/name', 'old', 'new', False), ('/token', '***', '***', True)]
    """
    old = store.get_version(kind, item_id, from_hash)
    target = to_hash or store.get(kind, item_id).version_hash
    new = store.get_version(kind, item_id, target)
    before, after = old.content or {}, new.content or {}
    changes = diff_documents(
        before,
        after,
        before_secrets=secret_paths(before),
        after_secrets=secret_paths(after),
        mask=mask,
    )
    old_files = _file_digests(store, kind, item_id, from_hash)
    new_files = _file_digests(store, kind, item_id, target)
    content: list[ContentChange] = []
    if old_files is not None and new_files is not None:
        content = [
            ContentChange(path=c.path, before_hash=c.before, after_hash=c.after)
            for c in diff_digests(old_files, new_files)
        ]
    return DefinitionDiff(
        kind=kind,
        id=item_id,
        from_hash=from_hash,
        to_hash=target,
        changes=[_diff_change(c.op, c.path, c.before, c.after, c.secret) for c in changes],
        content_changes=content,
    )


__all__ = ["SECRET_MASK", "SecretPaths", "VersionDiffSource", "diff_versions"]
