"""보관 파일(zip) 만들기. 메모리에서만 만든다(디스크에 쓰지 않는다)."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from typing import Final

from ._interfaces import OutputFile

__all__ = ["ZIP_TIMESTAMP", "build_zip"]

ZIP_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)
"""항목 시각(고정: 같은 입력이면 같은 바이트)."""


def build_zip(files: Iterable[OutputFile]) -> bytes:
    """파일들 → zip 바이트(경로 순, 고정 시각, deflate, 일반 파일 권한 0644)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(files, key=lambda f: f.path):
            info = zipfile.ZipInfo(file.path, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, file.data)
    return buffer.getvalue()
