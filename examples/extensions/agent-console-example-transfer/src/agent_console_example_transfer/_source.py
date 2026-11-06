"""가져오기 출처(X16) `example-json`: 프로젝트 폴더의 묶음 파일 하나를 읽는다(원본은 읽기만)."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_console_contracts import ImportCandidate, ImportSourceDescriptor, ImportWarning
from agent_console_imports import ImportItem, ImportSourceContext, ScanResult
from agent_console_secret_rules import SecretRules, default_rules

from ._format import (
    FORMAT_ID,
    BundleEntry,
    BundleFormat,
    TransferIssueCodes,
    load_format,
    read_bundle,
)

__all__ = ["SECRET_SUSPECTED", "SKIPPED_LINK", "JsonBundleSource", "json_bundle_sources"]

SKIPPED_LINK = "import.skipped_link"
"""링크(또는 출처 폴더 밖을 가리키는 경로)라 읽지 않음 — 기본 출처와 같은 코드."""
SECRET_SUSPECTED = "import.secret_suspected"
"""평문 비밀로 의심되는 값을 가렸다(위치만) — 기본 출처와 같은 코드."""

_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _mask_at(data: Any, pointer: str, mask: str) -> bool:
    parts = [_unescape(p) for p in pointer.split("/")[1:]]
    if not parts:
        return False
    target = data
    try:
        for part in parts[:-1]:
            target = target[int(part)] if isinstance(target, list) else target[part]
        last = parts[-1]
        if isinstance(target, list):
            target[int(last)] = mask
            return True
        if isinstance(target, dict) and last in target:
            target[last] = mask
            return True
    except (KeyError, IndexError, ValueError, TypeError):
        return False
    return False


class JsonBundleSource:
    """묶음 파일 하나를 읽는 출처.

    - 파일이 없으면 후보 없음(`available=False`). 링크·출처 폴더 밖은 읽지 않는다(`O_NOFOLLOW`).
    - 정의 원문·글 본문에서 평문 비밀로 의심되는 값은 가린 뒤 후보로 내고 경고(위치만)를 단다.
      비밀 참조(`secret://이름`)는 그대로 둔다.

    Args:
        path: 묶음 파일.
        fmt: 형식 설정(내보낼 때와 같아야 한다).
        root: 출처 폴더(이 밖으로 풀리는 경로는 읽지 않음). 없으면 `path`의 폴더.
        secret_rules: 지금의 비밀 의심 규칙을 돌려주는 함수. 없으면 기본 규칙.
    """

    def __init__(
        self,
        path: Path,
        fmt: BundleFormat,
        *,
        root: Path | None = None,
        secret_rules: Callable[[], SecretRules] | None = None,
    ) -> None:
        self._path = path
        self._root = root if root is not None else path.parent
        self._fmt = fmt
        self._rules = secret_rules or default_rules

    @property
    def descriptor(self) -> ImportSourceDescriptor:
        """출처 디스크립터(id = entry point 이름, `available` = 지금 파일이 있는지)."""
        return ImportSourceDescriptor(
            id=FORMAT_ID,
            title=self._fmt.title,
            description=self._fmt.description,
            path=str(self._path),
            available=self._path.is_file() and not self._path.is_symlink(),
        )

    def _inside(self) -> bool:
        try:
            return self._path.resolve().is_relative_to(self._root.resolve())
        except OSError:
            return False

    def _read(self) -> tuple[bytes | None, list[ImportWarning]]:
        name = self._fmt.file_name
        if self._path.is_symlink() or not self._inside():
            message = "링크이거나 출처 폴더 밖이라 읽지 않습니다"
            return None, [ImportWarning(code=SKIPPED_LINK, message=message, keys=[name])]
        if not self._path.is_file():
            return None, []
        limit = self._fmt.max_file_bytes
        try:
            fd = os.open(self._path, _OPEN_FLAGS)
            with os.fdopen(fd, "rb") as fh:
                data = fh.read(limit + 1)
        except OSError as exc:
            message = f"파일을 열 수 없습니다({type(exc).__name__})"
            return None, [
                ImportWarning(code=TransferIssueCodes.UNREADABLE, message=message, keys=[name])
            ]
        if len(data) > limit:
            message = "파일이 너무 커서 읽지 않습니다"
            return None, [
                ImportWarning(code=TransferIssueCodes.TOO_LARGE, message=message, keys=[name])
            ]
        return data, []

    def scan(self) -> ScanResult:
        """후보를 읽는다(쓰기 없음). 없는 파일은 빈 결과."""
        data, warnings = self._read()
        if data is None:
            return ScanResult(root=str(self._path), warnings=warnings)
        entries, problems = read_bundle(data, self._fmt)
        rules = self._rules()
        items = [self._item(index, entry, rules) for index, entry in enumerate(entries)]
        return ScanResult(root=str(self._path), items=items, warnings=[*warnings, *problems])

    def _item(self, index: int, entry: BundleEntry, rules: SecretRules) -> ImportItem:
        fmt = self._fmt
        document = json.loads(json.dumps(entry.document))  # 깊은 사본(가리기용)
        masked = [
            f.path for f in rules.find_suspected(document) if _mask_at(document, f.path, rules.mask)
        ]
        files = dict(entry.files)
        for path, body in entry.files.items():
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError:
                continue
            cleaned = rules.redact_suspected(text)
            if cleaned != text:
                files[path] = cleaned.encode("utf-8")
                masked.append(f"/{fmt.fields.files}/{_escape(path)}")
        warnings = (
            [
                ImportWarning(
                    code=SECRET_SUSPECTED,
                    message="평문 비밀로 보이는 값을 가렸습니다. 비밀은 참조(secret://)로 두세요",
                    keys=masked,
                )
            ]
            if masked
            else []
        )
        canonical = json.dumps(
            {"document": document, "files": sorted(files)}, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")
        name = document.get(fmt.name_field)
        rtype = document.get(fmt.type_field)
        candidate = ImportCandidate(
            id=f"{entry.kind}:{entry.id}",
            path=f"{fmt.file_name}#/{fmt.fields.items}/{index}",
            kind=entry.kind,
            resource_type=rtype if isinstance(rtype, str) and rtype else None,
            name=name if isinstance(name, str) and name else entry.id,
            suggested_id=entry.id,
            size=len(canonical) + sum(len(b) for b in files.values()),
            content_hash=hashlib.sha256(canonical).hexdigest(),
            warnings=warnings,
        )
        return ImportItem(candidate=candidate, document=document, files=files or None)


def json_bundle_sources(ctx: ImportSourceContext) -> list[JsonBundleSource]:
    """출처 공장(entry point `agent_console.import_sources` 값).

    프로젝트(작업) 폴더가 있을 때만 그 폴더의 `file_name` 파일을 읽는 출처 하나를 만든다.
    `ctx.options`는 이 출처의 설치자 옵션(형식 설정 덮어쓰기)이다.

    Raises:
        ValueError: 옵션이 틀렸을 때(로더가 경고로 남기고 이 출처를 건너뛴다).
    """
    if ctx.project_dir is None:
        return []
    fmt = load_format(ctx.options)
    return [
        JsonBundleSource(
            ctx.project_dir / fmt.file_name,
            fmt,
            root=ctx.project_dir,
            secret_rules=ctx.secret_rules,
        )
    ]
