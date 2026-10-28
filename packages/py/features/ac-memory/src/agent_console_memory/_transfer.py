"""마크다운 zip 내보내기·가져오기(design §5.7R.6·§5.7R.8).

형식: zip 항목 하나 = 메모리 항목 하나, 경로 `<범위 종류>/<범위 id>/<키>.md`.

- 범위 id는 경로 마디 하나로 퍼센트 인코딩한다. 빈 범위 id는 `_`, 글자 그대로 `_`·`.`·`..`인
  범위 id는 `%5F`·`%2E`처럼 바꾼다.
- 키는 그대로 쓴다(키 규칙이 `..`·빈 마디·역슬래시·제어 문자를 막는다).
- 본문 앞에 YAML 머리(`---` 줄 사이)를 붙인다: `id`·`content_type`·`tags`·`pinned`·`archived`·
  `version`·`created_at`·`created_by`·`updated_at`·`updated_by`.
- 가져오기는 위치(범위·키)를 **경로에서** 읽고, 머리에서는 `tags`·`pinned`·`archived`·
  `content_type`만 쓴다. `id`·버전·쓴 주체는 참고 값이다. 가져온 항목은 새 id·버전 1이고, 쓴 주체는
  가져오기 주체(기본 `system`)다.
- 머리가 없는 `.md` 파일은 본문만 있는 항목으로 받는다.

가져오기 안전(파일을 디스크에 풀지 않는다. 모든 것을 메모리에서 상한 안에서 읽는다):

- 묶음 전체 거부(`TooLargeError`, 아무것도 쓰지 않음): 압축 크기·항목 수·선언된 풀린 크기 합·
  항목 하나의 선언 크기 상한(zip 폭탄). 실제로 풀린 바이트도 상한으로 끊는다(머리 크기 거짓말 대비).
- 묶음 형식 오류(zip이 아님): `InvalidArchiveError`.
- 항목 하나만 거부(`MemoryImportProblem`): `..`·`.`·빈 마디·절대 경로·드라이브 문자·역슬래시·
  제어 문자·심볼릭 링크(`memory.import_unsafe_path`), 암호화·`.md`가 아님
  (`memory.import_unsupported`), 위치·머리·UTF-8 오류(`memory.import_invalid_file`), 묶음 안
  같은 범위·키(`memory.import_duplicate`), 저장소 쓰기 검사(키 규칙·비밀 검사·크기·개수 한도의
  사유 코드).
- 비밀 검사는 저장소 쓰기 정책(`MemoryPolicy.secrets`)을 그대로 거친다. 미리보기(`dry_run`)도 같은
  검사(`prepare_write`)를 한다. 문제 목록의 경로는 비밀 가림을 거친 값이고 본문은 싣지 않는다.
"""

from __future__ import annotations

import io
import json
import re
import stat
import unicodedata
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import IO, Any, Final, get_args
from urllib.parse import quote, unquote

from pydantic import ValidationError
from ruamel.yaml import YAML

from agent_console_contracts.constants import ErrorCodes
from agent_console_contracts.memory import (
    KnownMemoryAuthorKinds,
    MemoryAuthor,
    MemoryEntry,
    MemoryImportPolicy,
    MemoryImportProblem,
    MemoryImportResult,
    MemoryScopeRef,
)

from ._errors import MemoryStoreError, TooLargeError
from ._keys import KEY_SEPARATOR
from ._policy import prepare_write
from ._scan import DEFAULT_SCAN_PAGE, iter_entries
from ._store import MemoryStore

MARKDOWN_SUFFIX: Final = ".md"
EMPTY_SCOPE_ID_SEGMENT: Final = "_"
"""범위 id가 빈 범위의 경로 마디."""
FRONT_MATTER_FENCE: Final = "---"
DEFAULT_RENAME_FORMAT: Final = "{key} ({n})"
"""`rename` 정책의 새 키 틀(`{key}` = 원래 키, `{n}` = 2부터 오르는 수)."""

_CONTENT_TYPE = re.compile(r"[A-Za-z0-9!#$&^_.+-]{1,64}/[A-Za-z0-9!#$&^_.+-]{1,64}")
_DRIVE = re.compile(r"[A-Za-z]:")
_JSON_LINE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*): (.+)")
_UNSAFE_SEGMENTS = frozenset({"", ".", ".."})
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_MAX_SHOWN_PATH = 512
_MAX_RENAME_TRIES = 10_000


class MemoryTransferCodes:
    """가져오기 문제 사유 코드(열린 문자열 상수, `MemoryImportProblem.code`).

    저장소 쓰기 검사에서 나온 문제는 그 오류의 `code`(예: `memory.invalid_key`)를 그대로 쓴다.
    """

    UNSAFE_PATH: Final = "memory.import_unsafe_path"
    """`..`·절대 경로·역슬래시·제어 문자·심볼릭 링크 등 위험한 zip 안 경로."""
    UNSUPPORTED: Final = "memory.import_unsupported"
    """`.md`가 아니거나 암호화된 항목."""
    INVALID_FILE: Final = "memory.import_invalid_file"
    """위치(범위 종류·범위 id·키)·YAML 머리·UTF-8·압축 데이터 오류."""
    DUPLICATE: Final = "memory.import_duplicate"
    """묶음 안에 같은 범위·키가 두 번 나옴(뒤의 것을 받지 않는다)."""


class InvalidArchiveError(MemoryStoreError):
    """가져올 데이터가 zip으로 읽히지 않는다(`validation_failed`)."""

    code = ErrorCodes.VALIDATION_FAILED


@dataclass(frozen=True, slots=True)
class MemoryTransferLimits:
    """가져오기 상한(설치자 설정으로 바꾼다, design §5.7R.8).

    Attributes:
        max_archive_bytes: 압축된 zip 크기(기본 64 MiB).
        max_files: zip 항목 수(폴더 포함, 기본 50,000).
        max_file_bytes: 항목 하나의 풀린 크기(머리 포함, 기본 256 KiB). 넘는 항목이 있으면 묶음
            전체를 거부한다(내보내기 결과에는 나오지 않는 크기 — 폭탄 표지).
        max_total_bytes: 풀린 크기 합(기본 256 MiB).
        max_front_matter_bytes: YAML 머리 크기(기본 16 KiB).
    """

    max_archive_bytes: int = 64 * 1024 * 1024
    max_files: int = 50_000
    max_file_bytes: int = 256 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_front_matter_bytes: int = 16 * 1024


# ---- 경로 -------------------------------------------------------------------------------


def _percent(text: str) -> str:
    return "".join(f"%{ord(ch):02X}" for ch in text)


def encode_scope_id(scope_id: str) -> str:
    """범위 id → 경로 마디 하나.

    >>> [encode_scope_id(s) for s in ("", "g1/agent a", "_", "..")]
    ['_', 'g1%2Fagent%20a', '%5F', '%2E%2E']
    """
    if not scope_id:
        return EMPTY_SCOPE_ID_SEGMENT
    segment = quote(scope_id, safe="")
    if segment in {EMPTY_SCOPE_ID_SEGMENT, ".", ".."}:
        segment = _percent(segment)
    return segment


def decode_scope_id(segment: str) -> str:
    """경로 마디 → 범위 id(`encode_scope_id`의 반대).

    >>> decode_scope_id("_"), decode_scope_id("g1%2Fagent%20a"), decode_scope_id("%5F")
    ('', 'g1/agent a', '_')
    """
    if segment == EMPTY_SCOPE_ID_SEGMENT:
        return ""
    return unquote(segment, errors="strict")


def entry_archive_path(scope: MemoryScopeRef, key: str) -> str:
    """항목의 zip 안 경로 `<범위 종류>/<범위 id>/<키>.md`.

    >>> entry_archive_path(MemoryScopeRef(kind="notes", id=""), "결정/api")
    'notes/_/결정/api.md'
    """
    return f"{scope.kind}/{encode_scope_id(scope.id)}/{key}{MARKDOWN_SUFFIX}"


def unsafe_archive_path(name: str) -> bool:
    """zip 안 경로가 위험한지: 절대 경로·드라이브 문자·역슬래시·제어 문자·`.`·`..`·빈 마디.

    폴더 항목의 끝 `/` 하나는 허용한다.

    >>> names = ("a/b.md", "../a.md", "/a.md", "a\\\\b.md", "C:a.md", "d/")
    >>> [unsafe_archive_path(p) for p in names]
    [False, True, True, True, True, False]
    """
    if not name or name.startswith("/") or "\\" in name or _DRIVE.match(name):
        return True
    if any(unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"} for ch in name):
        return True
    body = name[:-1] if name.endswith("/") else name
    return any(segment in _UNSAFE_SEGMENTS for segment in body.split("/"))


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def parse_archive_path(name: str) -> tuple[MemoryScopeRef, str]:
    """zip 안 경로 → (범위, 키). 안전 검사(`unsafe_archive_path`)는 따로 한다.

    Raises:
        ValueError: 마디가 셋보다 적음·`.md`가 아님·범위 종류 이름·범위 id 인코딩 오류.

    >>> parse_archive_path("notes/g1%2Fa/결정/api.md")
    (MemoryScopeRef(kind='notes', id='g1/a'), '결정/api')
    """
    if not name.endswith(MARKDOWN_SUFFIX):
        raise ValueError("마크다운(.md) 파일이 아니다")
    segments = name[: -len(MARKDOWN_SUFFIX)].split("/")
    if len(segments) < 3:
        raise ValueError("경로는 <범위 종류>/<범위 id>/<키>.md 모양이어야 한다")
    try:
        scope = MemoryScopeRef(kind=segments[0], id=decode_scope_id(segments[1]))
    except (ValidationError, UnicodeDecodeError) as exc:
        raise ValueError("범위 종류 이름이나 범위 id 표기가 틀렸다") from exc
    return scope, KEY_SEPARATOR.join(segments[2:])


# ---- 머리·본문 ----------------------------------------------------------------------------


def _yaml() -> YAML:
    return YAML(typ="safe", pure=True)


def _author_data(author: MemoryAuthor) -> dict[str, Any]:
    data: dict[str, Any] = author.model_dump(mode="json", exclude_defaults=True)
    return data


def _json_line(name: str, value: Any) -> str:
    return f"{name}: {json.dumps(value, ensure_ascii=False, separators=(', ', ': '))}\n"


def render_markdown(entry: MemoryEntry) -> str:
    """항목 → YAML 머리 + 본문 텍스트(내보내기 파일 하나).

    머리 줄은 `키: <JSON 값>`이다(JSON은 YAML의 부분 집합이라 YAML 도구로 그대로 읽힌다). 가져오기는
    이 모양을 빠른 길로 읽고, 사람이 고친 일반 YAML은 YAML로 읽는다.

    >>> from agent_console_memory.testing import sample_entry
    >>> print(render_markdown(sample_entry(content="본문", tags=["a"])), end="")
    ---
    id: "entry-1"
    content_type: "text/markdown"
    tags: ["a"]
    pinned: false
    archived: false
    version: 1
    created_at: 0.0
    created_by: {"kind": "user"}
    updated_at: 0.0
    updated_by: {"kind": "user"}
    ---
    본문
    """
    meta: dict[str, Any] = {
        "id": entry.id,
        "content_type": entry.content_type,
        "tags": list(entry.tags),
        "pinned": entry.pinned,
        "archived": entry.archived,
        "version": entry.version,
        "created_at": entry.created_at,
        "created_by": _author_data(entry.created_by),
        "updated_at": entry.updated_at,
        "updated_by": _author_data(entry.updated_by),
    }
    lines = "".join(_json_line(name, value) for name, value in meta.items())
    return f"{FRONT_MATTER_FENCE}\n{lines}{FRONT_MATTER_FENCE}\n{entry.content}"


def _json_lines(front: str) -> dict[str, Any] | None:
    """`키: <JSON>` 줄만 있는 머리(내보내기 모양)를 YAML 없이 읽는다. 다른 모양이면 None."""
    out: dict[str, Any] = {}
    for line in front.splitlines():
        match = _JSON_LINE.fullmatch(line)
        if match is None or match.group(1) in out:
            return None
        try:
            out[match.group(1)] = json.loads(match.group(2))
        except ValueError:
            return None
    return out


def parse_markdown(
    text: str, *, max_front_matter_chars: int | None = None
) -> tuple[dict[str, Any], str]:
    """파일 텍스트 → (머리 값, 본문). 첫 줄이 `---`가 아니면 머리 없이 전체가 본문이다.

    Raises:
        ValueError: 머리를 닫는 `---` 줄이 없음·머리가 너무 큼·YAML 오류·머리가 객체가 아님.

    >>> parse_markdown("---\\ntags: [a]\\n---\\n본문\\n")
    ({'tags': ['a']}, '본문\\n')
    >>> parse_markdown('---\\ntags: ["a"]\\npinned: true\\n---\\n')
    ({'tags': ['a'], 'pinned': True}, '')
    >>> parse_markdown("머리 없음")
    ({}, '머리 없음')
    """
    opener = next(
        (o for o in (f"{FRONT_MATTER_FENCE}\n", f"{FRONT_MATTER_FENCE}\r\n") if text.startswith(o)),
        None,
    )
    if opener is None:
        return {}, text
    start = pos = len(opener)
    while True:
        if max_front_matter_chars is not None and pos - start > max_front_matter_chars:
            raise ValueError("YAML 머리가 너무 크다")
        end = text.find("\n", pos)
        line_end = len(text) if end == -1 else end + 1
        if text[pos:line_end].rstrip("\r\n") == FRONT_MATTER_FENCE:
            break
        if end == -1:
            raise ValueError("YAML 머리를 닫는 '---' 줄이 없다")
        pos = line_end
    front, content = text[start:pos], text[line_end:]
    if not front.strip():
        return {}, content
    data: Any = _json_lines(front)
    if data is None:
        try:
            data = _yaml().load(front)
        except Exception as exc:  # YAML 오류·깊은 중첩(RecursionError) 모두 파일 문제다
            raise ValueError("YAML 머리를 읽지 못했다") from exc
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise ValueError("YAML 머리는 객체여야 한다")
    return dict(data), content


@dataclass(frozen=True, slots=True)
class _Meta:
    tags: list[str] | None
    pinned: bool | None
    archived: bool | None
    content_type: str | None


def _meta(data: Mapping[str, Any]) -> _Meta:
    tags = data.get("tags")
    if tags is not None and (
        not isinstance(tags, list) or not all(isinstance(t, str) for t in tags)
    ):
        raise ValueError("tags는 문자열 목록이어야 한다")
    flags: dict[str, bool | None] = {}
    for name in ("pinned", "archived"):
        value = data.get(name)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{name}는 참·거짓이어야 한다")
        flags[name] = value
    content_type = data.get("content_type")
    if content_type is not None and (
        not isinstance(content_type, str) or not _CONTENT_TYPE.fullmatch(content_type)
    ):
        raise ValueError("content_type은 '종류/세부' 모양이어야 한다")
    return _Meta(
        tags=None if tags is None else list(tags),
        pinned=flags["pinned"],
        archived=flags["archived"],
        content_type=content_type,
    )


# ---- 내보내기 -----------------------------------------------------------------------------


def _zip_time(at: float) -> tuple[int, int, int, int, int, int]:
    moment = datetime.fromtimestamp(max(at, 0.0), tz=UTC)
    stamp = (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)
    return max(stamp, _ZIP_EPOCH)


def write_markdown_archive(
    store: MemoryStore,
    target: IO[bytes],
    scopes: Sequence[MemoryScopeRef] | None = None,
    *,
    include_archived: bool = True,
    page_size: int = DEFAULT_SCAN_PAGE,
) -> int:
    """지우지 않은 항목을 마크다운 zip으로 `target`(쓰기 가능한 바이너리 파일)에 쓴다.

    저장소가 `EntryScanner`면 본문까지 한 번에 훑고, 아니면 요약 쪽 + 항목마다 `get`으로
    읽는다(메모리 사용 = 쪽 하나의 요약 + 항목 하나 + zip 쓰기 버퍼). 항목 순서는 저장소가 낸
    순서다.

    Args:
        store: 저장소.
        target: zip을 쓸 곳(파일·`BytesIO`).
        scopes: 내보낼 범위(None = 전부).
        include_archived: 보관 항목도 내보낼지(머리 `archived: true`).
        page_size: 저장소에서 한 번에 읽는 요약 수.

    Returns:
        내보낸 항목 수.
    """
    count = 0
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for summary in iter_entries(
            store, scopes=scopes, include_archived=include_archived, page_size=page_size
        ):
            entry = summary if isinstance(summary, MemoryEntry) else store.get(summary.id)
            if entry is None:  # 훑는 사이에 지워짐
                continue
            info = zipfile.ZipInfo(
                entry_archive_path(entry.scope, entry.key), date_time=_zip_time(entry.updated_at)
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, render_markdown(entry).encode("utf-8"))
            count += 1
    return count


def export_markdown(
    store: MemoryStore,
    scopes: Sequence[MemoryScopeRef] | None = None,
    *,
    include_archived: bool = True,
) -> bytes:
    """지우지 않은 항목을 마크다운 zip 바이트로 낸다(`write_markdown_archive`를 메모리에).

    큰 저장소는 파일에 바로 쓰는 `write_markdown_archive`를 쓴다.
    """
    buffer = io.BytesIO()
    write_markdown_archive(store, buffer, scopes, include_archived=include_archived)
    return buffer.getvalue()


# ---- 가져오기 -----------------------------------------------------------------------------


def import_author() -> MemoryAuthor:
    """가져오기 버전의 기본 쓴 주체(`system`)."""
    return MemoryAuthor(kind=KnownMemoryAuthorKinds.SYSTEM)


def _archive_size(data: bytes | IO[bytes]) -> int:
    if isinstance(data, bytes | bytearray | memoryview):
        return len(data)
    here = data.tell()
    size = data.seek(0, io.SEEK_END)
    data.seek(here)
    return size - here


def _open_archive(data: bytes | IO[bytes], limits: MemoryTransferLimits) -> zipfile.ZipFile:
    size = _archive_size(data)
    if size > limits.max_archive_bytes:
        raise TooLargeError(
            f"가져올 zip은 {limits.max_archive_bytes}바이트까지다",
            limit="max_archive_bytes",
            value=limits.max_archive_bytes,
        )
    source = io.BytesIO(bytes(data)) if isinstance(data, bytes | bytearray | memoryview) else data
    try:
        return zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError, ValueError, EOFError) as exc:
        raise InvalidArchiveError("zip 파일로 읽지 못했다") from exc


def _check_bomb(infos: Sequence[zipfile.ZipInfo], limits: MemoryTransferLimits) -> None:
    if len(infos) > limits.max_files:
        raise TooLargeError(
            f"zip 항목은 {limits.max_files}개까지다", limit="max_files", value=limits.max_files
        )
    total = 0
    for info in infos:
        if info.file_size > limits.max_file_bytes:
            raise TooLargeError(
                f"zip 항목 하나는 풀어서 {limits.max_file_bytes}바이트까지다",
                limit="max_file_bytes",
                value=limits.max_file_bytes,
            )
        total += info.file_size
    if total > limits.max_total_bytes:
        raise TooLargeError(
            f"zip을 풀면 {limits.max_total_bytes}바이트까지다",
            limit="max_total_bytes",
            value=limits.max_total_bytes,
        )


class _Importer:
    def __init__(
        self,
        store: MemoryStore,
        *,
        policy: MemoryImportPolicy,
        dry_run: bool,
        author: MemoryAuthor,
        rename_format: str,
    ) -> None:
        self.store = store
        self.policy = policy
        self.dry_run = dry_run
        self.author = author
        self.rename_format = rename_format
        self.counts = {"created": 0, "overwritten": 0, "renamed": 0, "skipped": 0}
        self.errors: list[MemoryImportProblem] = []
        self.seen: set[tuple[str, str, str]] = set()
        self.taken: set[tuple[str, str, str]] = set()

    def problem(self, name: str, code: str, message: str) -> None:
        shown = self.store.policy.secrets.preview(name)[:_MAX_SHOWN_PATH]
        self.errors.append(MemoryImportProblem(path=shown, code=code, message=message))

    def exists(self, scope: MemoryScopeRef, key: str) -> bool:
        if (scope.kind, scope.id, key) in self.taken:
            return True
        return self.store.find(scope, key) is not None

    def free_key(self, scope: MemoryScopeRef, key: str) -> str | None:
        for n in range(2, _MAX_RENAME_TRIES):
            candidate = self.rename_format.format(key=key, n=n)
            if not self.exists(scope, candidate):
                return candidate
        return None

    def accept(self, name: str, scope: MemoryScopeRef, key: str, meta: _Meta, body: str) -> None:
        where = (scope.kind, scope.id, key)
        if where in self.seen:
            self.problem(name, MemoryTransferCodes.DUPLICATE, "묶음 안에 같은 범위·키가 앞에 있다")
            return
        self.seen.add(where)
        existing = self.exists(scope, key)
        target, kind = key, "created"
        if existing:
            if self.policy == "skip":
                self.counts["skipped"] += 1
                return
            if self.policy == "rename":
                free = self.free_key(scope, key)
                if free is None:
                    self.problem(name, ErrorCodes.ALREADY_EXISTS, "바꿀 새 키를 찾지 못했다")
                    return
                target, kind = free, "renamed"
            else:
                kind = "overwritten"
        try:
            if self.dry_run:
                prepare_write(self.store.policy, target, body, meta.tags or [])
            else:
                self.write(scope, target, meta, body, overwrite=kind == "overwritten")
        except MemoryStoreError as exc:
            self.problem(name, exc.code, exc.message)
            return
        self.taken.add((scope.kind, scope.id, target))
        self.counts[kind] += 1

    def result(self) -> MemoryImportResult:
        return MemoryImportResult(dry_run=self.dry_run, errors=self.errors, **self.counts)

    def write(
        self, scope: MemoryScopeRef, key: str, meta: _Meta, body: str, *, overwrite: bool
    ) -> None:
        entry = self.store.write(
            scope,
            key,
            body,
            author=self.author,
            tags=meta.tags,
            content_type=meta.content_type,
            pinned=meta.pinned,
            create_only=not overwrite,
        ).entry
        if meta.archived is not None and entry.archived != meta.archived:
            self.store.archive(
                entry.id, author=self.author, archived=meta.archived, if_version=entry.version
            )


def import_markdown(
    store: MemoryStore,
    data: bytes | IO[bytes],
    *,
    policy: MemoryImportPolicy = "skip",
    dry_run: bool = False,
    limits: MemoryTransferLimits | None = None,
    author: MemoryAuthor | None = None,
    rename_format: str = DEFAULT_RENAME_FORMAT,
) -> MemoryImportResult:
    """마크다운 zip을 저장소로 가져온다(형식은 모듈 문서).

    Args:
        store: 저장소. 쓰기는 저장소 정책(키 규칙·비밀 검사·크기·개수 한도)을 거친다.
        data: zip 바이트 또는 읽기·위치 이동이 되는 바이너리 파일.
        policy: 같은 범위·키가 있을 때 `skip`(건너뜀)·`overwrite`(새 버전)·`rename`(새 키로 만듦).
        dry_run: 참이면 쓰지 않고 같은 수를 센다(쓰기 검사 중 키·태그·비밀·본문 크기는 미리 보고,
            범위 개수·전체 크기 한도는 실제 쓰기에서만 안다).
        limits: 가져오기 상한(기본 `MemoryTransferLimits()`).
        author: 가져온 버전의 쓴 주체(기본 `system`).
        rename_format: `rename` 새 키 틀(`{key}`·`{n}`).

    Returns:
        `MemoryImportResult`(만듦·덮어씀·새 이름·건너뜀 수와 받지 않은 파일 목록).

    Raises:
        TooLargeError: 묶음 크기·항목 수·풀린 크기 상한(zip 폭탄) — 아무것도 쓰지 않는다.
        InvalidArchiveError: zip이 아님.
        ValueError: 모르는 `policy`.
    """
    if policy not in get_args(MemoryImportPolicy):
        raise ValueError(f"가져오기 정책은 {', '.join(get_args(MemoryImportPolicy))} 중 하나다")
    bounds = limits if limits is not None else MemoryTransferLimits()
    importer = _Importer(
        store,
        policy=policy,
        dry_run=dry_run,
        author=author if author is not None else import_author(),
        rename_format=rename_format,
    )
    with _open_archive(data, bounds) as archive:
        infos = archive.infolist()
        _check_bomb(infos, bounds)
        read_total = 0
        for info in infos:
            name = info.filename
            if unsafe_archive_path(name) or _is_symlink(info):
                importer.problem(name, MemoryTransferCodes.UNSAFE_PATH, "위험한 경로라 받지 않았다")
                continue
            if info.is_dir():
                continue
            if info.flag_bits & 0x1:
                importer.problem(name, MemoryTransferCodes.UNSUPPORTED, "암호화된 항목이다")
                continue
            try:
                scope, key = parse_archive_path(name)
            except ValueError as exc:
                code = (
                    MemoryTransferCodes.UNSUPPORTED
                    if not name.endswith(MARKDOWN_SUFFIX)
                    else MemoryTransferCodes.INVALID_FILE
                )
                importer.problem(name, code, str(exc))
                continue
            try:
                with archive.open(info) as handle:
                    raw = handle.read(bounds.max_file_bytes + 1)
            except (zipfile.BadZipFile, OSError, EOFError, ValueError, NotImplementedError):
                importer.problem(name, MemoryTransferCodes.INVALID_FILE, "압축 데이터가 깨졌다")
                continue
            read_total += len(raw)
            if len(raw) > bounds.max_file_bytes or read_total > bounds.max_total_bytes:
                raise TooLargeError(
                    "풀린 크기가 상한을 넘었다(zip 머리의 크기가 실제와 다름)",
                    limit="max_total_bytes",
                    value=bounds.max_total_bytes,
                )
            try:
                text = raw.decode("utf-8-sig")
                front, body = parse_markdown(
                    text, max_front_matter_chars=bounds.max_front_matter_bytes
                )
                meta = _meta(front)
            except ValueError as exc:  # UnicodeDecodeError 포함
                message = "UTF-8이 아니다" if isinstance(exc, UnicodeDecodeError) else str(exc)
                importer.problem(name, MemoryTransferCodes.INVALID_FILE, message)
                continue
            importer.accept(name, scope, key, meta, body)
    return importer.result()
