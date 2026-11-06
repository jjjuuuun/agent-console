"""묶음 파일 형식: 설정(형식 이름·필드 이름 — 옵션 데이터)과 쓰기·읽기(순수 함수).

파일 모양(기본 필드 이름, `data/defaults.json`):

    {"format": "<format_name>", "version": 1,
     "definitions": [{"kind": "...", "id": "...", "document": {...},
                      "files": {"<경로>": {"text": "..."} | {"base64": "..."}}}]}

필드 이름·형식 이름·파일 이름은 코드에 두지 않는다. 기본값은 패키지 데이터, 바꾸려면
설치자 옵션(`exports.options.example-json`·가져오기 출처 옵션)에 같은 키로 덮어쓴다.
두 쪽 옵션이 같아야 왕복된다.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib.resources import files as package_files
from pathlib import PurePosixPath
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from agent_console_contracts import ImportWarning

__all__ = [
    "FORMAT_ID",
    "BundleEntry",
    "BundleFields",
    "BundleFormat",
    "TransferIssueCodes",
    "default_format_data",
    "dump_bundle",
    "load_format",
    "read_bundle",
]

FORMAT_ID: Final = "example-json"
"""형식 id = entry point 이름(내보내기 형식 id·가져오기 출처 id)."""


class TransferIssueCodes:
    """이 예제가 내는 경고 코드(문서 상수). 값은 싣지 않고 위치만 싣는다."""

    INVALID_FILE: Final = "example_transfer.invalid_file"
    """파일을 JSON으로 읽을 수 없다(또는 최상위가 객체가 아님)."""
    UNKNOWN_FORMAT: Final = "example_transfer.unknown_format"
    """형식 이름이나 판이 설정과 다르다(다른 도구의 파일일 수 있음)."""
    INVALID_ENTRY: Final = "example_transfer.invalid_entry"
    """정의 항목 모양이 틀렸다(건너뜀)."""
    DUPLICATE_ENTRY: Final = "example_transfer.duplicate_entry"
    """같은 종류·id 항목이 또 있다(뒤 것은 건너뜀)."""
    TOO_LARGE: Final = "example_transfer.too_large"
    """파일이 `max_file_bytes`보다 크다(읽지 않음)."""
    UNREADABLE: Final = "example_transfer.unreadable"
    """파일을 열 수 없다(권한 등)."""


class BundleFields(BaseModel):
    """파일 안 필드 이름. 같은 층(최상위·항목·본문 파일)에서 이름이 겹치면 안 된다."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format: str = Field(min_length=1, description="최상위: 형식 이름 필드.")
    version: str = Field(min_length=1, description="최상위: 형식 판 필드.")
    items: str = Field(min_length=1, description="최상위: 정의 목록 필드.")
    kind: str = Field(min_length=1, description="항목: 정의 종류 필드.")
    id: str = Field(min_length=1, description="항목: 정의 id 필드.")
    document: str = Field(min_length=1, description="항목: 정의 원문 필드.")
    files: str = Field(min_length=1, description="항목: 본문 파일(경로 → 내용) 필드.")
    text: str = Field(min_length=1, description="본문 파일: UTF-8 글 필드.")
    base64: str = Field(min_length=1, description="본문 파일: 바이너리(base64) 필드.")

    @model_validator(mode="after")
    def _distinct(self) -> BundleFields:
        for group in (
            (self.format, self.version, self.items),
            (self.kind, self.id, self.document, self.files),
            (self.text, self.base64),
        ):
            if len(set(group)) != len(group):
                raise ValueError("같은 층의 필드 이름이 겹칩니다")
        return self


class BundleFormat(BaseModel):
    """형식 설정(기본값 `data/defaults.json` + 설치자 옵션 덮어쓰기).

    Attributes:
        title: 형식·출처 표시 이름.
        description: 설명.
        file_name: 내보낼 파일 이름 = 가져올 때 프로젝트 폴더에서 찾을 파일(상대 경로, `..` 금지).
        format_name: 파일의 형식 이름 값(다르면 가져오지 않음).
        format_version: 형식 판(다르면 가져오지 않음).
        fields: 파일 안 필드 이름.
        name_field: 미리보기 이름으로 쓸 정의 필드.
        type_field: 미리보기 리소스 종류로 쓸 정의 필드(문자열일 때만).
        drop_fields: 내보낼 때 정의에서 뺄 최상위 필드.
        max_file_bytes: 가져올 때 읽을 최대 크기.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1)
    description: str = ""
    file_name: str = Field(min_length=1)
    format_name: str = Field(min_length=1)
    format_version: int = Field(ge=1)
    fields: BundleFields
    name_field: str = Field(min_length=1)
    type_field: str = Field(min_length=1)
    drop_fields: tuple[str, ...] = ()
    max_file_bytes: int = Field(ge=1)

    @field_validator("file_name")
    @classmethod
    def _relative(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            "\\" in value
            or ":" in value
            or path.is_absolute()
            or any(part in ("", ".", "..") for part in value.split("/"))
        ):
            raise ValueError("file_name은 '..' 없는 상대 경로여야 합니다")
        return value


def default_format_data() -> dict[str, Any]:
    """패키지 데이터의 기본 형식 설정 사본."""
    raw = package_files("agent_console_example_transfer").joinpath("data/defaults.json")
    data: dict[str, Any] = json.loads(raw.read_text(encoding="utf-8"))
    return data


def load_format(options: Mapping[str, Any] | None = None) -> BundleFormat:
    """기본값에 설치자 옵션을 덮어쓴 형식 설정. `fields`는 키 하나씩 덮어쓴다.

    Raises:
        ValueError: 옵션이 틀렸을 때(모르는 키·빈 이름·겹치는 필드 이름·절대 경로). 메시지에 값은
            넣지 않는다.
    """
    data = default_format_data()
    for key, value in (options or {}).items():
        if key == "fields" and isinstance(value, Mapping):
            data["fields"] = {**data["fields"], **value}
        else:
            data[key] = value
    try:
        return BundleFormat.model_validate(data)
    except ValidationError as exc:
        where = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise ValueError(f"묶음 형식 옵션이 잘못됐습니다: {', '.join(where)}") from None


@dataclass(frozen=True, slots=True)
class BundleEntry:
    """묶음 안 정의 하나.

    Attributes:
        kind: 정의 종류 이름(저장소 kind — 이 예제는 종류를 모른다, 받은 그대로).
        id: 정의 id.
        document: 정의 원문.
        files: 본문 파일(경로 → 내용). 본문이 없으면 빈 매핑.
    """

    kind: str
    id: str
    document: Mapping[str, Any]
    files: Mapping[str, bytes] = field(default_factory=dict)


def _encode_file(data: bytes, fields: BundleFields) -> dict[str, str]:
    try:
        return {fields.text: data.decode("utf-8")}
    except UnicodeDecodeError:
        return {fields.base64: base64.b64encode(data).decode("ascii")}


def dump_bundle(entries: Sequence[BundleEntry], fmt: BundleFormat) -> bytes:
    """정의들 → 묶음 파일 내용(UTF-8 JSON, 들여쓰기 2, 끝 줄바꿈). 순서는 받은 그대로."""
    f = fmt.fields
    items = []
    for entry in entries:
        item: dict[str, Any] = {f.kind: entry.kind, f.id: entry.id, f.document: entry.document}
        if entry.files:
            item[f.files] = {p: _encode_file(entry.files[p], f) for p in sorted(entry.files)}
        items.append(item)
    data = {f.format: fmt.format_name, f.version: fmt.format_version, f.items: items}
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _warning(code: str, message: str, *keys: str) -> ImportWarning:
    return ImportWarning(code=code, message=message, keys=list(keys))


def _decode_files(raw: Any, fields: BundleFields) -> dict[str, bytes] | None:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        return None
    out: dict[str, bytes] = {}
    for path, body in raw.items():
        if not isinstance(path, str) or not path or not isinstance(body, Mapping):
            return None
        text, b64 = body.get(fields.text), body.get(fields.base64)
        if isinstance(text, str) and b64 is None:
            out[path] = text.encode("utf-8")
        elif isinstance(b64, str) and text is None:
            try:
                out[path] = base64.b64decode(b64, validate=True)
            except (binascii.Error, ValueError):
                return None
        else:
            return None
    return out


def read_bundle(data: bytes, fmt: BundleFormat) -> tuple[list[BundleEntry], list[ImportWarning]]:
    """묶음 파일 내용 → 정의들 + 경고(파일 전체가 틀리면 정의 없이 경고 하나).

    틀린 항목·겹치는 항목은 건너뛰고 경고(위치만 — 내용은 싣지 않는다)를 남긴다. 예외를 내지 않는다.
    """
    f = fmt.fields
    try:
        top = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return [], [_warning(TransferIssueCodes.INVALID_FILE, "JSON 파일로 읽을 수 없습니다")]
    if not isinstance(top, dict):
        return [], [_warning(TransferIssueCodes.INVALID_FILE, "최상위가 객체가 아닙니다")]
    if top.get(f.format) != fmt.format_name or top.get(f.version) != fmt.format_version:
        return [], [
            _warning(
                TransferIssueCodes.UNKNOWN_FORMAT,
                "형식 이름이나 판이 설정과 다릅니다",
                f"/{f.format}",
                f"/{f.version}",
            )
        ]
    raw_items = top.get(f.items)
    if not isinstance(raw_items, list):
        return [], [
            _warning(TransferIssueCodes.INVALID_FILE, "정의 목록이 없습니다", f"/{f.items}")
        ]
    entries: list[BundleEntry] = []
    warnings: list[ImportWarning] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_items):
        where = f"/{f.items}/{index}"
        kind = raw.get(f.kind) if isinstance(raw, dict) else None
        ident = raw.get(f.id) if isinstance(raw, dict) else None
        document = raw.get(f.document) if isinstance(raw, dict) else None
        files = _decode_files(raw.get(f.files), f) if isinstance(raw, dict) else None
        if (
            not isinstance(kind, str)
            or not kind
            or not isinstance(ident, str)
            or not ident
            or not isinstance(document, dict)
            or files is None
        ):
            warnings.append(
                _warning(
                    TransferIssueCodes.INVALID_ENTRY, "정의 항목 모양이 틀려 건너뜁니다", where
                )
            )
            continue
        if (kind, ident) in seen:
            warnings.append(
                _warning(
                    TransferIssueCodes.DUPLICATE_ENTRY, "같은 정의가 또 있어 건너뜁니다", where
                )
            )
            continue
        seen.add((kind, ident))
        entries.append(BundleEntry(kind=kind, id=ident, document=document, files=files))
    return entries, warnings
