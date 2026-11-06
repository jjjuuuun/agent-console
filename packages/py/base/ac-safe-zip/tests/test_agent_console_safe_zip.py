from __future__ import annotations

import io
import zipfile

import pytest

from agent_console_safe_zip import (
    ZipFormatError,
    ZipLimitError,
    ZipLimits,
    iter_members,
    open_zip,
    read_zip,
    unsafe_archive_path,
    write_zip,
)


def _zip(entries: list[tuple[zipfile.ZipInfo | str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for info, data in entries:
            archive.writestr(info, data)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "name",
    [
        "../a.md",
        "a/../../b.md",
        "/abs.md",
        "C:a.md",
        "c:/x.md",
        "a\\b.md",
        "a//b.md",
        "./a.md",
        "a\x00.md",
        "a\u200b.md",
        "",
    ],
)
def test_unsafe_paths(name: str) -> None:
    assert unsafe_archive_path(name)


@pytest.mark.parametrize("name", ["a.md", "폴더/문서.md", "d/", "a b/c.md"])
def test_safe_paths(name: str) -> None:
    assert not unsafe_archive_path(name)


def test_member_kinds() -> None:
    link = zipfile.ZipInfo("link.md")
    link.external_attr = 0o120777 << 16
    data = _zip([("ok.md", b"1"), ("../evil.md", b"x"), (link, b"target"), ("dir/", b"")])
    kinds = {m.name: (m.kind, m.data) for m in read_zip(data)}
    assert kinds == {
        "ok.md": ("file", b"1"),
        "../evil.md": ("unsafe", None),
        "link.md": ("unsafe", None),
        "dir/": ("dir", None),
    }


def test_declared_limits_reject_whole_archive() -> None:
    many = _zip([(f"{i}.md", b"x" * 100) for i in range(5)])
    for limits, name in (
        (ZipLimits(max_files=4), "max_files"),
        (ZipLimits(max_file_bytes=50), "max_file_bytes"),
        (ZipLimits(max_total_bytes=300), "max_total_bytes"),
        (ZipLimits(max_archive_bytes=10), "max_archive_bytes"),
    ):
        with pytest.raises(ZipLimitError) as caught:
            read_zip(many, limits)
        assert caught.value.limit == name


def test_total_read_is_bounded() -> None:
    data = _zip([("a.md", b"y" * 600), ("b.md", b"z" * 600)])
    with open_zip(data) as archive, pytest.raises(ZipLimitError) as caught:
        list(iter_members(archive, ZipLimits(max_total_bytes=1000)))
    assert caught.value.limit == "max_total_bytes"


def test_not_a_zip() -> None:
    with pytest.raises(ZipFormatError):
        read_zip(b"not a zip")


def test_write_zip_is_deterministic_and_readable_from_file_object() -> None:
    data = write_zip([("z.md", "한".encode()), ("a.md", b"")])
    assert data == write_zip([("a.md", b""), ("z.md", "한".encode())])
    members = read_zip(io.BytesIO(data))
    assert [m.name for m in members] == ["a.md", "z.md"]
