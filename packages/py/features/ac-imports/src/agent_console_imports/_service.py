"""`ImportService`: 출처 목록 → 미리보기(후보 스캔) → 고른 항목 가져오기(복사)."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any

from agent_console_contracts import (
    AppliedItemInfo,
    ConflictPolicy,
    ImportPreview,
    ImportRequest,
    ImportResult,
    ImportSourceDescriptor,
)

from ._interfaces import DefinitionWriter, ImportItem, ImportSource

_log = logging.getLogger(__name__)

_ID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
MAX_RENAME_ATTEMPTS = 1000

SCOPE_FIELD = "project"
"""정의 범위 필드(계약 0.8.0 `Agent`·`Resource.project`). 요청 `ImportRequest.project`를 만든 정의의
이 필드에 찍는다(design §UX-P.2 — 생략 = 공용)."""


def request_stamp(request: ImportRequest, stamp: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """가져온 정의에 찍을 최상위 필드: 요청 `project`(있으면) + `stamp`(뒤가 이김).

    값이 `None`인 필드는 문서에서 뺀다(`apply` 참고).
    """
    out: dict[str, Any] = {SCOPE_FIELD: request.project} if request.project else {}
    out.update(stamp or {})
    out.pop("id", None)
    return out


class ImportServiceError(LookupError):
    """가져오기 오류의 베이스. `code`는 계약 오류 코드."""

    code = "bad_request"


class UnknownImportSourceError(ImportServiceError):
    """출처 id가 등록되어 있지 않다."""

    code = "not_found"


class ImportService:
    """외부 출처에서 정의를 **복사해** 가져온다. 원본은 출처가 읽기만 한다.

    Args:
        sources: 출처 목록(id는 디스크립터 `id`, 겹치면 앞의 것).
        store: 쓸 정의 저장소(`DefinitionWriter`).
        message: 저장 이력 메시지.
    """

    def __init__(
        self,
        sources: Iterable[ImportSource],
        store: DefinitionWriter,
        *,
        message: str = "가져오기",
    ) -> None:
        self._sources: dict[str, ImportSource] = {}
        for source in sources:
            self._sources.setdefault(source.descriptor.id, source)
        self._store = store
        self._message = message

    def descriptors(self) -> list[ImportSourceDescriptor]:
        """출처 디스크립터(등록 순서)."""
        return [s.descriptor for s in self._sources.values()]

    def _source(self, source_id: str) -> ImportSource:
        source = self._sources.get(source_id)
        if source is None:
            raise UnknownImportSourceError(f"가져오기 출처가 없습니다: {source_id}")
        return source

    def _exists(self, kind: str, id: str, cache: dict[str, set[str]]) -> bool:
        if kind not in cache:
            try:
                cache[kind] = set(self._store.list_ids(kind))
            except Exception:  # 모르는 종류 등: 충돌 없음으로 본다(쓰기에서 실패한다)
                cache[kind] = set()
        return id in cache[kind]

    def preview(self, source_id: str) -> ImportPreview:
        """후보를 스캔한다(원본·워크스페이스 모두 쓰지 않는다).

        Raises:
            UnknownImportSourceError: 출처가 없을 때.
        """
        scan = self._source(source_id).scan()
        cache: dict[str, set[str]] = {}
        candidates = [
            item.candidate.model_copy(
                update={
                    "conflict": self._exists(
                        item.candidate.kind, item.candidate.suggested_id, cache
                    )
                }
            )
            for item in scan.items
        ]
        return ImportPreview(
            source=source_id, root=scan.root, candidates=candidates, warnings=scan.warnings
        )

    def apply(
        self, request: ImportRequest, *, stamp: Mapping[str, Any] | None = None
    ) -> ImportResult:
        """고른 후보를 워크스페이스에 쓴다. 후보는 다시 스캔해 확인한다.

        항목 하나의 실패는 그 항목만 `failed`로 보고하고 나머지는 계속한다.
        요청 `project`가 있으면 쓴 정의(만듦·덮어씀·이름 바꿈)에 그 범위를 찍는다(`request_stamp`).
        `stamp`는 그 밖에 찍을 최상위 필드다(값 `None` = 필드 빼기, `id`는 무시).

        Raises:
            UnknownImportSourceError: 출처가 없을 때.
        """
        scan = self._source(request.source).scan()
        by_id = {item.candidate.id: item for item in scan.items}
        cache: dict[str, set[str]] = {}
        results: list[AppliedItemInfo] = []
        fields = request_stamp(request, stamp)
        for selection in request.items:
            item = by_id.get(selection.candidate_id)
            if item is None:
                results.append(
                    AppliedItemInfo(
                        source=selection.candidate_id,
                        kind="unknown",
                        id=selection.candidate_id,
                        action="failed",
                        error="후보를 찾을 수 없습니다(원본이 바뀌었을 수 있음)",
                    )
                )
                continue
            target = selection.target_id or item.candidate.suggested_id
            results.append(self._write(item, target, selection.on_conflict, cache, fields))
        return ImportResult(source=request.source, items=results)

    # ------------------------------------------------------------ 내부

    def _write(
        self,
        item: ImportItem,
        target: str,
        policy: ConflictPolicy,
        cache: dict[str, set[str]],
        fields: Mapping[str, Any],
    ) -> AppliedItemInfo:
        c = item.candidate
        info: dict[str, Any] = {"source": c.path, "kind": c.kind, "id": c.suggested_id}
        if not _ID_OK.match(target):
            return AppliedItemInfo(**info, action="failed", error="id 형식이 잘못됐습니다")
        try:
            action = "created"
            if self._exists(c.kind, target, cache):
                if policy == "skip":
                    return AppliedItemInfo(**info, target_id=target, action="skipped")
                if policy == "rename":
                    target = self._free_id(c.kind, target, cache)
                    action = "renamed"
                else:
                    action = "overwritten"
            document = {**item.document, "id": target}
            for name, value in fields.items():
                if value is None:
                    document.pop(name, None)
                else:
                    document[name] = value
            if action == "overwritten":
                current = self._store.get(c.kind, target)
                stored = self._store.save(
                    c.kind,
                    document,
                    expected_version=current.version_hash,
                    message=self._message,
                )
            else:
                stored = self._store.create(c.kind, document, message=self._message)
            if item.content is not None:
                stored = self._store.write_content(
                    c.kind,
                    target,
                    item.content,
                    expected_version=stored.version_hash,
                    message=self._message,
                )
            if item.files is not None:
                changes: dict[str, bytes | None] = dict(item.files)
                if action == "overwritten":  # 덮어쓰면 원본에 없는 옛 파일은 지운다
                    for old in self._store.list_files(c.kind, target):
                        changes.setdefault(old.path, None)
                self._store.write_files(
                    c.kind,
                    target,
                    changes,
                    expected_version=stored.version_hash,
                    message=self._message,
                )
            cache.setdefault(c.kind, set()).add(target)
        except Exception as exc:
            _log.warning("가져오기 실패: %s/%s (%s)", c.kind, target, type(exc).__name__)
            return AppliedItemInfo(
                **info, target_id=target, action="failed", error=type(exc).__name__
            )
        return AppliedItemInfo(**info, target_id=target, action=action)  # type: ignore[arg-type]

    def _free_id(self, kind: str, base: str, cache: dict[str, set[str]]) -> str:
        for n in range(2, MAX_RENAME_ATTEMPTS):
            suffix = f"-{n}"
            candidate = base[: 128 - len(suffix)] + suffix
            if not self._exists(kind, candidate, cache):
                return candidate
        raise ImportServiceError("빈 id를 찾지 못했습니다")
