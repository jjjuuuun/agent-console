"""정의 저장소 공통 로직: 검증, 해시, If-Match, 버전 스냅샷.

실제 문서 입출력(파일, 메모리)만 하위 클래스가 구현한다. 그래서 `FileDefinitionStore`와
`InMemoryDefinitionStore`가 같은 규칙을 따른다.
"""

import copy
import hashlib
import json
import logging
import mimetypes
import re
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Iterable, Mapping
from typing import Any

from pydantic import BaseModel

from agent_console_contracts import DefinitionVersion, ResourceFile, VersionConflictDetails

from .content_path import check_content_path
from .errors import (
    AlreadyExists,
    ContentTooLarge,
    DefinitionCorrupt,
    InvalidContentPath,
    InvalidIdentifier,
    NotFound,
    VersionConflict,
    VersionRequired,
)
from .hashing import HashFn, default_hash
from .interfaces import DefinitionSummary, StoredDefinition, VersionRepository
from .kinds import DEFAULT_KINDS, DefinitionKind, kinds_by_name
from .memory import InMemoryVersionRepository

_log = logging.getLogger(__name__)
DEFAULT_MAX_CONTENT_BYTES = 10 * 1024 * 1024
"""정의 하나의 본문 총량 기본 한도(10MiB). 서버는 정의 모듈의 `max_content_bytes`를 넘긴다."""
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def _json_copy(document: Mapping[str, Any]) -> dict[str, Any]:
    """JSON 호환 깊은 복사(직렬화 불가능한 값은 `TypeError`)."""
    result = json.loads(json.dumps(document, ensure_ascii=False))
    assert isinstance(result, dict)
    return result


def _resource_file(path: str, size: int, sha256: str) -> ResourceFile:
    return ResourceFile(
        path=path, media_type=mimetypes.guess_type(path)[0], size=size, sha256=sha256
    )


class BaseDefinitionStore(ABC):
    """`DefinitionStore` 공통 구현. 하위 클래스는 원시 문서 입출력 다섯 개만 채운다."""

    def __init__(
        self,
        kinds: Iterable[DefinitionKind] = DEFAULT_KINDS,
        *,
        versions: VersionRepository | None = None,
        hash_fn: HashFn = default_hash,
        clock: Callable[[], float] = time.time,
        max_content_bytes: int | None = DEFAULT_MAX_CONTENT_BYTES,
        max_versions: int | None = None,
    ) -> None:
        self._kinds = kinds_by_name(kinds)
        self._max_content_bytes = max_content_bytes
        self._max_versions = max_versions
        self.versions: VersionRepository = versions or InMemoryVersionRepository()
        self._hash_fn = hash_fn
        self._clock = clock
        self._lock = threading.RLock()

    # ---- 하위 클래스가 구현 -------------------------------------------------
    @abstractmethod
    def _read(self, kind: DefinitionKind, id: str) -> dict[str, Any] | None:
        """현재 문서(JSON 호환 dict). 없으면 None. 읽을 수 없으면 `DefinitionCorrupt`."""

    @abstractmethod
    def _write(self, kind: DefinitionKind, id: str, document: dict[str, Any]) -> None: ...

    @abstractmethod
    def _remove(self, kind: DefinitionKind, id: str) -> bool: ...

    @abstractmethod
    def _ids(self, kind: DefinitionKind) -> list[str]: ...

    def _modified_at(self, kind: DefinitionKind, id: str) -> float | None:
        """문서의 마지막 수정 시각(알면). 외부에서 바뀐 문서의 `saved_at` 근사값."""
        return None

    # 본문 파일 훅: `kind.content_field`가 있는 종류만 호출된다. `file`은 이미 경로 검사를 통과했다.
    def _read_body(self, kind: DefinitionKind, id: str, file: str) -> bytes | None:
        """본문 파일 내용. 없으면 None."""
        raise NotImplementedError(f"{type(self).__name__} does not store content files")

    def _write_body(self, kind: DefinitionKind, id: str, file: str, data: bytes) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not store content files")

    def _remove_body(self, kind: DefinitionKind, id: str, file: str) -> None:
        """본문 파일을 지운다(없어도 오류 아님). 비게 된 정의 폴더도 정리한다."""
        raise NotImplementedError(f"{type(self).__name__} does not store content files")

    def _body_stat(self, kind: DefinitionKind, id: str, file: str) -> tuple[int, str] | None:
        """본문의 (바이트 수, sha256 16진수). 없으면 None. 큰 본문을 목록마다 읽지 않도록
        재정의할 수 있다."""
        data = self._read_body(kind, id, file)
        return None if data is None else (len(data), hashlib.sha256(data).hexdigest())

    def _body_digest(self, kind: DefinitionKind, id: str, file: str) -> str | None:
        stat = self._body_stat(kind, id, file)
        return None if stat is None else stat[1]

    def _list_body(self, kind: DefinitionKind, id: str) -> list[str]:
        """본문 폴더의 유효한 파일 경로들(정렬). 링크·규칙에 어긋난 이름은 뺀다."""
        raise NotImplementedError(f"{type(self).__name__} does not store content files")

    def _body_ids(self, kind: DefinitionKind) -> list[str]:
        """본문 폴더가 있는 정의 id들(정의 문서 유무와 무관)."""
        raise NotImplementedError(f"{type(self).__name__} does not store content files")

    # ---- 공개 API -----------------------------------------------------------
    def kinds(self) -> list[str]:
        return list(self._kinds)

    def register_kind(self, kind: DefinitionKind) -> None:
        """종류를 추가한다. 이름이 이미 있으면 `ValueError`."""
        if kind.name in self._kinds:
            raise ValueError(f"duplicate definition kind: {kind.name}")
        self._kinds[kind.name] = kind

    def list_ids(self, kind: str) -> list[str]:
        k = self._kind(kind)
        with self._lock:
            return sorted(self._ids(k))

    def get(self, kind: str, id: str) -> StoredDefinition:
        k = self._kind(kind)
        self._check_id(id, k)
        with self._lock:
            current = self._current(k, id)
        if current is None:
            raise NotFound(f"{kind}/{id}")
        return current

    def create(
        self, kind: str, document: Mapping[str, Any] | BaseModel, *, message: str = ""
    ) -> StoredDefinition:
        k = self._kind(kind)
        doc = self._prepare(k, document)
        id = self._id_of(k, doc)
        with self._lock:
            if self._read(k, id) is not None:
                raise AlreadyExists(f"{kind}/{id}")
            return self._store(k, id, doc, message)

    def save(
        self,
        kind: str,
        document: Mapping[str, Any] | BaseModel,
        *,
        expected_version: str | None = None,
        message: str = "",
    ) -> StoredDefinition:
        k = self._kind(kind)
        doc = self._prepare(k, document)
        id = self._id_of(k, doc)
        with self._lock:
            if k.require_version and expected_version is None:
                raise VersionRequired(f"{kind}/{id}: expected_version is required")
            current = self._current(k, id)
            self._check_version(k, id, current, expected_version)
            return self._store(k, id, doc, message)

    def delete(self, kind: str, id: str, *, expected_version: str | None = None) -> None:
        """삭제(본문 포함). ``expected_version``을 주면 지금 버전과 같아야 한다(다르면
        ``VersionConflict``, 없으면 ``NotFound``). 버전 이력은 남는다."""
        k = self._kind(kind)
        self._check_id(id, k)
        with self._lock:
            if expected_version is not None:
                current = self._current(k, id)
                if current is None:
                    raise NotFound(f"{kind}/{id}")
                if current.version_hash != expected_version:
                    raise VersionConflict(self._conflict_details(k, current))
            try:
                files = self._body_files(k, id)
            except (DefinitionCorrupt, InvalidContentPath):
                files = []
            if not self._remove(k, id):
                raise NotFound(f"{kind}/{id}")
            for file in files:
                self._remove_body(k, id, file)

    def read_content(self, kind: str, id: str) -> bytes | None:
        k = self._kind(kind)
        self._check_id(id, k)
        with self._lock:
            current = self._current(k, id)
            if current is None:
                raise NotFound(f"{kind}/{id}")
            file = self._ref_or_corrupt(k, id, current.document)
            return None if file is None else self._read_body(k, id, file)

    def write_content(
        self,
        kind: str,
        id: str,
        data: bytes,
        *,
        file: str | None = None,
        media_type: str | None = None,
        expected_version: str | None = None,
        message: str = "본문 수정",
    ) -> StoredDefinition:
        k = self._kind(kind)
        self._check_id(id, k)
        field = k.content_field
        if field is None:
            raise ValueError(f"definition kind {kind!r} has no content files")
        with self._lock:
            current = self._current(k, id)
            if current is None:
                raise NotFound(f"{kind}/{id}")
            self._check_version(k, id, current, expected_version)
            doc = copy.deepcopy(current.document)
            old_file = self._content_ref(k, doc)
            new_file = old_file if file is None else check_content_path(file)
            if new_file is None:
                raise InvalidContentPath(f"{kind}/{id}: no content file name is set")
            ref = doc.get(field)
            ref = dict(ref) if isinstance(ref, dict) else {}
            ref["file"] = new_file
            if media_type is not None:
                ref["media_type"] = media_type
            doc[field] = ref
            if k.model is not None:
                k.model.model_validate(doc)
            return self._store(
                k,
                id,
                doc,
                message,
                put={new_file: data},
                drop=[old_file] if old_file not in (None, new_file) else [],
            )

    def summaries(self, kind: str) -> list[DefinitionSummary]:
        k = self._kind(kind)
        result: list[DefinitionSummary] = []
        with self._lock:
            for id in sorted(self._ids(k)):
                try:
                    stored = self._current(k, id)
                except DefinitionCorrupt as exc:
                    _log.warning("skip unreadable definition %s/%s: %s", kind, id, exc)
                    continue
                if stored is not None:
                    result.append(self._summarize(k, stored))
        return result

    def list_versions(self, kind: str, id: str) -> list[DefinitionVersion]:
        self._check_id(id, self._kind(kind))
        return self.versions.list(kind, id)

    def get_version(self, kind: str, id: str, version_hash: str) -> DefinitionVersion:
        self._check_id(id, self._kind(kind))
        found = self.versions.get(kind, id, version_hash)
        if found is None:
            raise NotFound(f"{kind}/{id}@{version_hash}")
        return found

    # ---- 여러 파일 본문 ------------------------------------------------------
    def list_files(self, kind: str, id: str) -> list[ResourceFile]:
        k = self._multi_kind(kind)
        self._check_id(id, k)
        with self._lock:
            if self._read(k, id) is None:
                raise NotFound(f"{kind}/{id}")
            result: list[ResourceFile] = []
            for path in self._list_body_checked(k, id):
                stat = self._body_stat(k, id, path)
                if stat is not None:
                    result.append(_resource_file(path, stat[0], stat[1]))
            return result

    def read_file(self, kind: str, id: str, path: str) -> bytes:
        k = self._multi_kind(kind)
        self._check_id(id, k)
        safe = check_content_path(path)
        with self._lock:
            if self._read(k, id) is None:
                raise NotFound(f"{kind}/{id}")
            data = self._read_body(k, id, safe)
        if data is None:
            raise NotFound(f"{kind}/{id}/{safe}")
        return data

    def write_file(
        self,
        kind: str,
        id: str,
        path: str,
        data: bytes,
        *,
        expected_version: str | None = None,
        message: str = "파일 수정",
    ) -> StoredDefinition:
        return self.write_files(
            kind, id, {path: data}, expected_version=expected_version, message=message
        )

    def delete_file(
        self,
        kind: str,
        id: str,
        path: str,
        *,
        expected_version: str | None = None,
        message: str = "파일 삭제",
    ) -> StoredDefinition:
        k = self._multi_kind(kind)
        self._check_id(id, k)
        safe = check_content_path(path)
        with self._lock:
            if safe not in self._list_body_checked(k, id):
                if self._read(k, id) is None:
                    raise NotFound(f"{kind}/{id}")
                raise NotFound(f"{kind}/{id}/{safe}")
            return self.write_files(
                kind, id, {safe: None}, expected_version=expected_version, message=message
            )

    def write_files(
        self,
        kind: str,
        id: str,
        changes: Mapping[str, bytes | None],
        *,
        expected_version: str | None = None,
        message: str = "파일 수정",
    ) -> StoredDefinition:
        k = self._multi_kind(kind)
        self._check_id(id, k)
        put: dict[str, bytes] = {}
        drop: list[str] = []
        for raw, data in changes.items():
            path = check_content_path(raw)
            if path in put or path in drop:
                raise InvalidContentPath(f"duplicate path in one change: {path!r}")
            if data is None:
                drop.append(path)
            else:
                put[path] = bytes(data)
        with self._lock:
            current = self._current(k, id)
            if current is None:
                raise NotFound(f"{kind}/{id}")
            self._check_version(k, id, current, expected_version)
            return self._store(k, id, copy.deepcopy(current.document), message, put=put, drop=drop)

    def list_version_files(self, kind: str, id: str, version_hash: str) -> list[ResourceFile]:
        self._check_id(id, self._kind(kind))
        snapshot = self.versions.files(kind, id, version_hash)
        if snapshot is None:
            raise NotFound(f"{kind}/{id}@{version_hash} has no content snapshot")
        return [
            _resource_file(path, self.versions.blob_size(sha) or 0, sha)
            for path, sha in sorted(snapshot.items())
        ]

    def read_version_file(self, kind: str, id: str, version_hash: str, path: str) -> bytes:
        self._check_id(id, self._kind(kind))
        snapshot = self.versions.files(kind, id, version_hash)
        sha = None if snapshot is None else snapshot.get(path)
        data = None if sha is None else self.versions.read_blob(sha)
        if data is None:
            raise NotFound(f"{kind}/{id}@{version_hash}/{path}")
        return data

    def restore_version(
        self,
        kind: str,
        id: str,
        version_hash: str,
        *,
        expected_version: str | None = None,
        message: str = "",
    ) -> StoredDefinition:
        k = self._kind(kind)
        self._check_id(id, k)
        with self._lock:
            version = self.get_version(kind, id, version_hash)
            doc = copy.deepcopy(version.content or {})
            current = self._current(k, id)
            if current is not None:
                self._check_version(k, id, current, expected_version)
            self._content_ref(k, doc)
            if k.model is not None:
                k.model.model_validate(doc)
            snapshot = self.versions.files(kind, id, version_hash) if k.content_field else None
            put: dict[str, bytes] = {}
            drop: list[str] = []
            if snapshot is not None:
                for path, sha in snapshot.items():
                    blob = self.versions.read_blob(sha)
                    if blob is None:
                        raise NotFound(f"{kind}/{id}@{version_hash}/{path}: blob is gone")
                    put[path] = blob
                drop = [p for p in self._body_files(k, id) if p not in snapshot]
            return self._store(
                k, id, doc, message or f"버전 {version_hash[:8]} 복원", put=put, drop=drop
            )

    def prune_blobs(self) -> int:
        return self.versions.prune_blobs()

    def orphan_bodies(self, kind: str) -> list[str]:
        k = self._kind(kind)
        if k.content_field is None:
            return []
        with self._lock:
            return sorted(
                i for i in self._body_ids(k) if _ID_RE.fullmatch(i) and not self._has_document(k, i)
            )

    def prune_orphan_bodies(self, kind: str) -> list[str]:
        k = self._kind(kind)
        removed: list[str] = []
        with self._lock:
            for id in self.orphan_bodies(kind):
                try:
                    files = self._list_body(k, id)
                except (DefinitionCorrupt, InvalidContentPath):
                    continue  # 링크가 낀 폴더는 건드리지 않는다
                for file in files:
                    self._remove_body(k, id, file)
                removed.append(id)
        return removed

    # ---- 내부 ---------------------------------------------------------------
    def _kind(self, name: str) -> DefinitionKind:
        try:
            return self._kinds[name]
        except KeyError:
            raise NotFound(f"unknown definition kind: {name}") from None

    def _check_id(self, id: str, kind: DefinitionKind | None = None) -> None:
        if kind is not None and kind.is_singleton and id != kind.name:
            raise NotFound(f"{kind.name}/{id}")
        if not _ID_RE.fullmatch(id):
            raise InvalidIdentifier(f"invalid id: {id!r}")

    def _check_version(
        self,
        kind: DefinitionKind,
        id: str,
        current: StoredDefinition | None,
        expected_version: str | None,
    ) -> None:
        """If-Match 규칙: 필수 종류는 `VersionRequired`, 다르면 `VersionConflict`.
        기존 문서가 없으면(싱글턴 제외) `NotFound`."""
        if kind.require_version and expected_version is None:
            raise VersionRequired(f"{kind.name}/{id}: expected_version is required")
        if current is None and not kind.is_singleton:
            raise NotFound(f"{kind.name}/{id}")
        if expected_version is not None and (
            current is None or current.version_hash != expected_version
        ):
            if current is None:
                raise NotFound(f"{kind.name}/{id}")
            raise VersionConflict(self._conflict_details(kind, current))

    def _hash(
        self,
        kind: DefinitionKind,
        document: Mapping[str, Any],
        body: str | dict[str, str] | None = None,
    ) -> str:
        """버전 해시. 본문이 있으면 그 sha256이 해시 입력에 들어간다(본문만 바뀌어도 새 버전).

        `body`가 문자열이면 본문 파일 하나의 sha256(`$content_sha256`, 0003 이전과 같은 값),
        dict면 여러 파일의 경로 -> sha256(`$content_files`)이다.
        """
        fn = kind.hash_fn or self._hash_fn
        if body is None:
            return fn(document)
        key = "$content_sha256" if isinstance(body, str) else "$content_files"
        return fn({**document, key: body})

    def _prepare(
        self, kind: DefinitionKind, document: Mapping[str, Any] | BaseModel
    ) -> dict[str, Any]:
        """검증을 거친 **사용자가 쓴 그대로의** JSON 호환 dict를 만든다.

        "생략 = 상속": 모델 기본값을 채워 넣지 않는다. 모델 인스턴스는 `exclude_unset`으로,
        dict는 원본 그대로 보존한다. 검증은 하되 검증 결과(기본값이 채워진 모델)는 버린다.
        그래서 생략, null, 빈 목록이 저장 후에도 구분된다. 모르는 필드도 보존된다.
        """
        if isinstance(document, BaseModel):
            plain = _json_copy(document.model_dump(mode="json", exclude_unset=True))
        else:
            plain = _json_copy(document)
        self._content_ref(kind, plain)  # 본문 경로 검사(모델 검증보다 먼저: 오류 종류를 일정하게)
        if kind.model is not None:
            kind.model.model_validate(plain)
        return plain

    def _content_ref(self, kind: DefinitionKind, document: Mapping[str, Any]) -> str | None:
        """문서가 가리키는 본문 파일(검사한 상대 경로). 쓰지 않거나 가리키지 않으면 None.

        Raises:
            InvalidContentPath: 경로 형식이 틀렸거나 정의 폴더 밖이다.
        """
        if kind.content_field is None:
            return None
        ref = document.get(kind.content_field)
        if ref is None:
            return None
        if not isinstance(ref, Mapping):
            raise InvalidContentPath(f"{kind.content_field} must be a mapping with 'file'")
        return check_content_path(ref.get("file"))

    def _ref_or_corrupt(
        self, kind: DefinitionKind, id: str, document: Mapping[str, Any]
    ) -> str | None:
        """저장된 문서의 본문 참조. 손으로 고친 문서의 나쁜 경로는 `DefinitionCorrupt`로 바꾼다."""
        try:
            return self._content_ref(kind, document)
        except InvalidContentPath as exc:
            raise DefinitionCorrupt(f"{kind.name}/{id}: {exc}") from exc

    def _multi_kind(self, name: str) -> DefinitionKind:
        kind = self._kind(name)
        if not kind.multi_file:
            raise ValueError(f"definition kind {name!r} does not store multiple content files")
        return kind

    def _has_document(self, kind: DefinitionKind, id: str) -> bool:
        try:
            return self._read(kind, id) is not None
        except DefinitionCorrupt:
            return True  # 깨졌어도 정의는 있다. 본문을 고아로 취급하지 않는다

    def _list_body_checked(self, kind: DefinitionKind, id: str) -> list[str]:
        try:
            return self._list_body(kind, id)
        except InvalidContentPath as exc:
            raise DefinitionCorrupt(f"{kind.name}/{id}: {exc}") from exc

    def _body_files(self, kind: DefinitionKind, id: str) -> list[str]:
        """정의의 본문 파일들. 여러 파일 종류는 폴더의 모든 파일, 아니면 `content.file` 하나."""
        if kind.content_field is None:
            return []
        if kind.multi_file:
            return self._list_body_checked(kind, id)
        document = self._read(kind, id)
        if document is None:
            return []
        file = self._ref_or_corrupt(kind, id, document)
        return [] if file is None else [file]

    def _content_part(
        self, kind: DefinitionKind, id: str, document: Mapping[str, Any]
    ) -> str | dict[str, str] | None:
        """버전 해시에 넣을 본문 요약(`_hash`의 `body`)."""
        if kind.content_field is None:
            return None
        ref = self._ref_or_corrupt(kind, id, document)
        try:
            if not kind.multi_file:
                return None if ref is None else self._body_digest(kind, id, ref)
            digests: dict[str, str] = {}
            for path in self._list_body_checked(kind, id):
                digest = self._body_digest(kind, id, path)
                if digest is not None:
                    digests[path] = digest
        except InvalidContentPath as exc:
            raise DefinitionCorrupt(f"{kind.name}/{id}: {exc}") from exc
        if not digests:
            return None
        if len(digests) == 1 and ref in digests:
            return digests[ref]  # 단일 파일 본문은 예전과 같은 해시
        return digests

    def _snapshot_files(
        self, kind: DefinitionKind, id: str, document: Mapping[str, Any]
    ) -> dict[str, bytes] | None:
        """버전에 남길 본문(경로 -> 내용). 본문을 쓰지 않는 종류는 None."""
        if kind.content_field is None:
            return None
        files: dict[str, bytes] = {}
        for path in self._body_files(kind, id):
            data = self._read_body(kind, id, path)
            if data is not None:
                files[path] = data
        return files

    def _record_version(
        self,
        kind: DefinitionKind,
        id: str,
        version_hash: str,
        document: Mapping[str, Any],
        *,
        saved_at: float,
        message: str,
    ) -> None:
        """스냅샷(문서 + 본문)을 남기고 보존 개수를 적용한다."""
        self.versions.record(
            kind.name,
            id,
            version_hash,
            document,
            saved_at=saved_at,
            message=message,
            files=self._snapshot_files(kind, id, document),
        )
        trimmed = self._max_versions is not None and self.versions.trim(
            kind.name, id, keep=self._max_versions, protect=(version_hash,)
        )
        if trimmed:
            self.versions.prune_blobs()

    def _check_body_change(
        self,
        kind: DefinitionKind,
        id: str,
        put: Mapping[str, bytes],
        drop: Collection[str],
    ) -> None:
        """본문을 쓰기 전 검사: 파일/폴더 이름 충돌, 대소문자만 다른 이름, 총량 한도."""
        existing = {p: None for p in self._body_files(kind, id)}
        final = {p for p in existing if p not in drop} | set(put)
        if kind.multi_file:
            for path in put:
                self._check_layout(path, final)
        if self._max_content_bytes is None:
            return
        total = sum(len(d) for d in put.values())
        for path in final - set(put):
            stat = self._body_stat(kind, id, path)
            total += 0 if stat is None else stat[0]
        if total > self._max_content_bytes:
            raise ContentTooLarge(
                f"{kind.name}/{id}: content is {total} bytes, limit is {self._max_content_bytes}"
            )

    @staticmethod
    def _check_layout(path: str, final: Collection[str]) -> None:
        folded = path.casefold()
        for other in final:
            if other == path:
                continue
            if other.casefold() == folded:
                raise InvalidContentPath(f"{path!r} differs from {other!r} only by case")
            if path.startswith(other + "/") or other.startswith(path + "/"):
                raise InvalidContentPath(f"{path!r} conflicts with {other!r} (file vs folder)")

    def _id_of(self, kind: DefinitionKind, document: Mapping[str, Any]) -> str:
        if kind.is_singleton:
            return kind.name
        id = document.get("id")
        if not isinstance(id, str):
            raise InvalidIdentifier(f"{kind.name}: document has no string 'id'")
        self._check_id(id)
        return id

    def _current(self, kind: DefinitionKind, id: str) -> StoredDefinition | None:
        document = self._read(kind, id)
        if document is None:
            return None
        version_hash = self._hash(kind, document, self._content_part(kind, id, document))
        saved_at = self.versions.saved_at(kind.name, id, version_hash)
        if saved_at is None:
            # 파일을 사람이 직접 만들거나 고친 경우: 해시를 내보내기 전에 스냅샷을 남겨
            # Run의 graph_version 같은 참조가 항상 조회되게 한다.
            saved_at = self._modified_at(kind, id) or self._clock()
            self._record_version(
                kind, id, version_hash, document, saved_at=saved_at, message="외부 변경 감지"
            )
        return StoredDefinition(kind.name, id, document, version_hash, saved_at)

    def _store(
        self,
        kind: DefinitionKind,
        id: str,
        document: dict[str, Any],
        message: str,
        *,
        put: Mapping[str, bytes] | None = None,
        drop: Collection[str] = (),
    ) -> StoredDefinition:
        """문서(와 바뀐 본문)를 쓰고 버전을 남긴다. 검사를 마친 뒤 본문을 먼저 쓰고 문서를 쓴다."""
        put = put or {}
        if put or drop:
            self._check_body_change(kind, id, put, drop)
        for path, data in put.items():
            self._write_body(kind, id, path, data)
        self._write(kind, id, document)
        for path in drop:
            if path not in put:
                self._remove_body(kind, id, path)
        version_hash = self._hash(kind, document, self._content_part(kind, id, document))
        saved_at = self._clock()
        self._record_version(kind, id, version_hash, document, saved_at=saved_at, message=message)
        return StoredDefinition(kind.name, id, copy.deepcopy(document), version_hash, saved_at)

    def _counts(self, kind: DefinitionKind, document: Mapping[str, Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for name in kind.count_fields:
            value = document.get(name)
            counts[name] = len(value) if isinstance(value, list) else 0
        return counts

    def _summarize(self, kind: DefinitionKind, stored: StoredDefinition) -> DefinitionSummary:
        doc = stored.document
        name = doc.get("name")
        description = doc.get("description")
        labels = doc.get("labels")
        attributes = doc.get("attributes")
        return DefinitionSummary(
            kind=kind.name,
            id=stored.id,
            name=name if isinstance(name, str) else stored.id,
            description=description if isinstance(description, str) else "",
            labels=[x for x in labels if isinstance(x, str)] if isinstance(labels, list) else [],
            version_hash=stored.version_hash,
            saved_at=stored.saved_at,
            counts=self._counts(kind, doc),
            has_content=kind.content_field is not None and doc.get(kind.content_field) is not None,
            extra={f: doc[f] for f in kind.summary_fields if isinstance(doc.get(f), str)},
            attributes=copy.deepcopy(attributes) if isinstance(attributes, dict) else {},
        )

    def _conflict_details(
        self, kind: DefinitionKind, current: StoredDefinition
    ) -> VersionConflictDetails:
        counts = self._counts(kind, current.document)
        return VersionConflictDetails(
            current_version_hash=current.version_hash,
            saved_at=current.saved_at,
            node_count=counts.get("nodes"),
            edge_count=counts.get("edges"),
        )


class InMemoryDefinitionStore(BaseDefinitionStore):
    """메모리에만 두는 정의 저장소(테스트·임시 실행용). 규칙은 파일 저장소와 같다."""

    def __init__(
        self,
        kinds: Iterable[DefinitionKind] = DEFAULT_KINDS,
        *,
        versions: VersionRepository | None = None,
        hash_fn: HashFn = default_hash,
        clock: Callable[[], float] = time.time,
        max_content_bytes: int | None = DEFAULT_MAX_CONTENT_BYTES,
        max_versions: int | None = None,
    ) -> None:
        super().__init__(
            kinds,
            versions=versions,
            hash_fn=hash_fn,
            clock=clock,
            max_content_bytes=max_content_bytes,
            max_versions=max_versions,
        )
        self._docs: dict[tuple[str, str], dict[str, Any]] = {}
        self._bodies: dict[tuple[str, str, str], bytes] = {}

    def _read(self, kind: DefinitionKind, id: str) -> dict[str, Any] | None:
        doc = self._docs.get((kind.name, id))
        return None if doc is None else copy.deepcopy(doc)

    def _write(self, kind: DefinitionKind, id: str, document: dict[str, Any]) -> None:
        self._docs[(kind.name, id)] = copy.deepcopy(document)

    def _remove(self, kind: DefinitionKind, id: str) -> bool:
        return self._docs.pop((kind.name, id), None) is not None

    def _ids(self, kind: DefinitionKind) -> list[str]:
        return [i for (k, i) in self._docs if k == kind.name]

    def _read_body(self, kind: DefinitionKind, id: str, file: str) -> bytes | None:
        return self._bodies.get((kind.name, id, file))

    def _write_body(self, kind: DefinitionKind, id: str, file: str, data: bytes) -> None:
        self._bodies[(kind.name, id, file)] = bytes(data)

    def _remove_body(self, kind: DefinitionKind, id: str, file: str) -> None:
        self._bodies.pop((kind.name, id, file), None)

    def _list_body(self, kind: DefinitionKind, id: str) -> list[str]:
        return sorted(f for (k, i, f) in self._bodies if k == kind.name and i == id)

    def _body_ids(self, kind: DefinitionKind) -> list[str]:
        return sorted({i for (k, i, _) in self._bodies if k == kind.name})
