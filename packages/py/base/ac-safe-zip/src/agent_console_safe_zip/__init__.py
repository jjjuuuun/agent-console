"""안전한 zip 읽기와 고정 바이트 zip 쓰기(design §5.7R.8·§7R.13).

사용자가 올린 zip을 **디스크에 풀지 않고** 메모리에서 상한 안에서 읽는다. 기능 패키지(메모리
마크다운
가져오기, 위키 페이지 가져오기)가 같은 안전 규칙을 한 곳에서 쓴다.

공개 API:
    ``ZipLimits`` — 압축 크기·항목 수·항목 하나·풀린 합 상한.
    ``open_zip(data, limits)`` — 크기·형식·선언 크기(폭탄) 검사 뒤 `zipfile.ZipFile`.
    ``iter_members(archive, limits)`` — 항목마다 `ZipMember`(종류 + 상한 안에서 읽은 바이트).
    ``read_zip(data, limits)`` — 위 둘을 한 번에(묶음 전체 상한을 쓰기 전에 다 확인할 때).
    ``unsafe_archive_path(name)``·``is_symlink(info)`` — 항목 하나 검사.
    ``write_zip(files)`` — 경로 순·고정 시각·일반 파일 권한(같은 입력이면 같은 바이트).
    예외 ``ZipLimitError``(``limit``·``value``)·``ZipFormatError``.
"""

from __future__ import annotations

import io
import stat
import unicodedata
import zipfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import IO, Final, Literal

__all__ = [
    "ZIP_TIMESTAMP",
    "MemberKind",
    "ZipFormatError",
    "ZipLimitError",
    "ZipLimits",
    "ZipMember",
    "is_symlink",
    "iter_members",
    "open_zip",
    "read_zip",
    "unsafe_archive_path",
    "write_zip",
]

ZIP_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)
"""`write_zip` 항목 시각(고정: 같은 입력이면 같은 바이트)."""

_UNSAFE_SEGMENTS = frozenset({"", ".", ".."})
_CONTROL_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})

type MemberKind = Literal["file", "dir", "unsafe", "encrypted", "broken"]
"""항목 종류: file(읽음) · dir(폴더) · unsafe(위험한 경로·심볼릭 링크) · encrypted · broken(압축
데이터가 깨짐)."""


class ZipLimitError(ValueError):
    """묶음 상한을 넘었다(아무것도 쓰지 않아야 한다).

    Attributes:
        limit: 넘은 상한 이름(`ZipLimits` 필드 이름).
        value: 그 상한 값.
    """

    def __init__(self, message: str, *, limit: str, value: int) -> None:
        super().__init__(message)
        self.limit = limit
        self.value = value


class ZipFormatError(ValueError):
    """zip으로 읽히지 않는다."""


@dataclass(frozen=True, slots=True)
class ZipLimits:
    """zip 읽기 상한(호출자 설정으로 바꾼다).

    Attributes:
        max_archive_bytes: 압축된 zip 크기.
        max_files: 항목 수(폴더 포함).
        max_file_bytes: 항목 하나의 풀린 크기. 선언 크기가 넘으면 묶음 전체를 거부한다(폭탄 표지).
        max_total_bytes: 풀린 크기 합(선언 합과 실제로 읽은 합 둘 다).
    """

    max_archive_bytes: int = 64 * 1024 * 1024
    max_files: int = 50_000
    max_file_bytes: int = 256 * 1024
    max_total_bytes: int = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ZipMember:
    """zip 항목 하나.

    Attributes:
        name: zip 안 경로 원문.
        kind: 항목 종류(`MemberKind`).
        data: `file`이면 읽은 바이트, 그 밖은 None.
    """

    name: str
    kind: MemberKind
    data: bytes | None = None


def unsafe_archive_path(name: str) -> bool:
    """zip 안 경로가 위험한지: 절대 경로·드라이브 문자·역슬래시·제어 문자·`.`·`..`·빈 마디.

    폴더 항목의 끝 `/` 하나는 허용한다.

    >>> names = ("a/b.md", "../a.md", "/a.md", "a\\\\b.md", "C:a.md", "d/")
    >>> [unsafe_archive_path(p) for p in names]
    [False, True, True, True, True, False]
    """
    if not name or name.startswith("/") or "\\" in name:
        return True
    if len(name) >= 2 and name[1] == ":" and name[0].isascii() and name[0].isalpha():
        return True
    if any(unicodedata.category(ch) in _CONTROL_CATEGORIES for ch in name):
        return True
    body = name[:-1] if name.endswith("/") else name
    return any(segment in _UNSAFE_SEGMENTS for segment in body.split("/"))


def is_symlink(info: zipfile.ZipInfo) -> bool:
    """항목이 유닉스 심볼릭 링크로 표시됐는지."""
    return stat.S_ISLNK(info.external_attr >> 16)


def _archive_size(data: bytes | IO[bytes]) -> int:
    if isinstance(data, bytes | bytearray | memoryview):
        return len(data)
    here = data.tell()
    size = data.seek(0, io.SEEK_END)
    data.seek(here)
    return size - here


def _check_declared(infos: list[zipfile.ZipInfo], limits: ZipLimits) -> None:
    if len(infos) > limits.max_files:
        raise ZipLimitError(
            f"zip 항목은 {limits.max_files}개까지다", limit="max_files", value=limits.max_files
        )
    total = 0
    for info in infos:
        if info.file_size > limits.max_file_bytes:
            raise ZipLimitError(
                f"zip 항목 하나는 풀어서 {limits.max_file_bytes}바이트까지다",
                limit="max_file_bytes",
                value=limits.max_file_bytes,
            )
        total += info.file_size
    if total > limits.max_total_bytes:
        raise ZipLimitError(
            f"zip을 풀면 {limits.max_total_bytes}바이트까지다",
            limit="max_total_bytes",
            value=limits.max_total_bytes,
        )


@contextmanager
def open_zip(data: bytes | IO[bytes], limits: ZipLimits | None = None) -> Iterator[zipfile.ZipFile]:
    """zip을 연다: 압축 크기 → 형식 → 항목 수·선언 크기 상한을 먼저 본다.

    Args:
        data: zip 바이트 또는 읽기·위치 이동이 되는 바이너리 파일.
        limits: 상한(기본 `ZipLimits()`).

    Raises:
        ZipLimitError: 압축 크기·항목 수·선언 크기 상한.
        ZipFormatError: zip이 아님.
    """
    bounds = limits or ZipLimits()
    if _archive_size(data) > bounds.max_archive_bytes:
        raise ZipLimitError(
            f"zip은 {bounds.max_archive_bytes}바이트까지다",
            limit="max_archive_bytes",
            value=bounds.max_archive_bytes,
        )
    source = io.BytesIO(bytes(data)) if isinstance(data, bytes | bytearray | memoryview) else data
    try:
        archive = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError, ValueError, EOFError) as exc:
        raise ZipFormatError("zip 파일로 읽지 못했다") from exc
    with archive:
        _check_declared(archive.infolist(), bounds)
        yield archive


def iter_members(archive: zipfile.ZipFile, limits: ZipLimits | None = None) -> Iterator[ZipMember]:
    """항목을 차례로 읽는다(파일 항목만 바이트를 읽고, 위험한 항목은 읽지 않는다).

    실제로 풀린 바이트도 상한으로 끊는다(zip 머리의 크기 거짓말 대비).

    Raises:
        ZipLimitError: 항목 하나 또는 읽은 합이 상한을 넘음(`max_file_bytes`·`max_total_bytes`).
    """
    bounds = limits or ZipLimits()
    total = 0
    for info in archive.infolist():
        name = info.filename
        if unsafe_archive_path(name) or is_symlink(info):
            yield ZipMember(name, "unsafe")
            continue
        if info.is_dir():
            yield ZipMember(name, "dir")
            continue
        if info.flag_bits & 0x1:
            yield ZipMember(name, "encrypted")
            continue
        try:
            with archive.open(info) as handle:
                raw = handle.read(bounds.max_file_bytes + 1)
        except (zipfile.BadZipFile, OSError, EOFError, ValueError, NotImplementedError):
            yield ZipMember(name, "broken")
            continue
        total += len(raw)
        if len(raw) > bounds.max_file_bytes or total > bounds.max_total_bytes:
            raise ZipLimitError(
                "풀린 크기가 상한을 넘었다(zip 머리의 크기가 실제와 다름)",
                limit="max_total_bytes",
                value=bounds.max_total_bytes,
            )
        yield ZipMember(name, "file", raw)


def read_zip(data: bytes | IO[bytes], limits: ZipLimits | None = None) -> list[ZipMember]:
    """`open_zip` + `iter_members`를 끝까지(묶음 상한을 쓰기 전에 모두 확인한다).

    Raises:
        ZipLimitError: 상한.
        ZipFormatError: zip이 아님.
    """
    with open_zip(data, limits) as archive:
        return list(iter_members(archive, limits))


def write_zip(files: Iterable[tuple[str, bytes]]) -> bytes:
    """(경로, 바이트)들 → zip 바이트(경로 순, 고정 시각, deflate, 일반 파일 권한 0644).

    >>> import zipfile, io
    >>> data = write_zip([("b.md", b"2"), ("a/x.md", b"1")])
    >>> zipfile.ZipFile(io.BytesIO(data)).namelist()
    ['a/x.md', 'b.md']
    >>> data == write_zip([("a/x.md", b"1"), ("b.md", b"2")])
    True
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, payload in sorted(files, key=lambda item: item[0]):
            info = zipfile.ZipInfo(path, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    return buffer.getvalue()
