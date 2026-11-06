"""계약 0.13.2 중 6R.20a·6R.20d(더하기만): `sdd` 1.1.0·`projects` 3.2.0.

- `ImportFileListing.dirs`(선택, 기본 빈 목록): 가져오기 폴더의 바로 아래 하위 폴더.
- `SpecTemplateCreateRequest`: `POST /sdd/templates` 빈 문서 틀 만들기.
- `CopyKindInfo`·`CopyItem`: 복사 대화상자가 종류 이름 표 없이 목록을 채우는 메타데이터.
"""

import pytest
from pydantic import ValidationError

from agent_console_contracts import CopyItem, CopyKindInfo
from agent_console_contracts.schema import build_schema
from agent_console_contracts.sdd import ImportDir, ImportFileListing, SpecTemplateCreateRequest


def test_old_listing_reads_without_dirs() -> None:
    old = ImportFileListing.model_validate({"path": "docs", "files": [], "truncated": False})
    assert old.dirs == []
    listing = ImportFileListing.model_validate({"dirs": [{"name": "아무 폴더"}]})
    assert listing.dirs == [ImportDir(name="아무 폴더")]
    schema = build_schema()["$defs"]
    assert "dirs" not in schema["ImportFileListing"].get("required", [])
    assert schema["ImportDir"]["required"] == ["name"]


def test_template_create_request() -> None:
    req = SpecTemplateCreateRequest.model_validate({"name": "틀"})
    assert req.id is None
    assert req.description == ""
    with pytest.raises(ValidationError):
        SpecTemplateCreateRequest.model_validate({"name": ""})
    with pytest.raises(ValidationError):
        SpecTemplateCreateRequest.model_validate({"name": "x", "id": "../x"})
    assert "SpecTemplateCreateRequest" in build_schema()["$defs"]


def test_copy_kind_metadata_is_open_strings() -> None:
    info = CopyKindInfo.model_validate(
        {"kind": "any-plugin-kind", "library": True, "portable": False}
    )
    assert info.kind == "any-plugin-kind"
    item = CopyItem.model_validate({"kind": "any-plugin-kind", "id": "x"})
    assert (item.name, item.description, item.saved_at) == ("", "", None)
    schema = build_schema()["$defs"]
    assert set(schema["CopyKindInfo"]["required"]) == {"kind", "library", "portable"}
    assert set(schema["CopyItem"]["required"]) == {"kind", "id"}
