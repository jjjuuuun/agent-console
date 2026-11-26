"""계약 0.16.0(P1.19, design §1.1 B-2·V-2, §I18N.7).

- 지움(`definitions` 3.0.0): `WorkspaceSettings.default_backend`. 옛 키가 든 `settings.yaml`·내보낸
  문서는 읽기가 실패하지 않고 모르는 키로 보존된다(`IGNORED_SETTINGS_KEYS`).
- 더함: 하위 모듈 `i18n` 1.0.0(`I18nInfo`·`LanguageInfo`·`MessageCatalog`),
  `UiPreferences.language`, `ErrorCodes.I18N_UNKNOWN_LANGUAGE`(404), 문구 묶음 불러오기 이슈
  코드 `i18n.*`, 위젯 `language`(`common` 2.1.0). 0.15.1(릴리스하지 않음)의 `projects` 4.1.0·
  `sdd` 1.4.0을 합쳤다. 같은 `projects` 4.1.0에 `CopyKindInfo.open_role`(여는 화면 역할)을 더했다.
"""

from __future__ import annotations

import hashlib
import importlib
import io
import json
from typing import Any

import pytest
from pydantic import ValidationError
from ruamel.yaml import YAML

import agent_console_contracts as contracts
from agent_console_contracts import (
    CONTRACT_SUBMODULES,
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    IGNORED_SETTINGS_KEYS,
    CopyKindInfo,
    ErrorCodes,
    I18nInfo,
    KnownIssueCodes,
    KnownUiWidgets,
    LanguageInfo,
    MessageCatalog,
    UiPreferences,
    WorkspaceSettings,
    ignored_settings_keys,
)
from agent_console_contracts.schema import build_schema

I18N_LOADING_CODES = {
    "I18N_CATALOG_UNREADABLE": "i18n.catalog_unreadable",
    "I18N_CATALOG_INVALID": "i18n.catalog_invalid",
    "I18N_CATALOG_UNKNOWN_SECTION": "i18n.catalog_unknown_section",
    "I18N_ENTRY_INVALID": "i18n.entry_invalid",
    "I18N_LANGUAGE_INVALID": "i18n.language_invalid",
    "I18N_LOCALES_MISSING": "i18n.locales_missing",
    "I18N_SOURCE_UNAVAILABLE": "i18n.source_unavailable",
}
"""`ac-i18n` 불러오기가 내는 문제 코드(서버가 `ServerInfo.warnings`로 옮긴다)."""


def _sha(doc: Any) -> str:
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 버전


def test_contracts_version_is_0_16_0() -> None:
    assert CONTRACTS_VERSION == "0.16.0"
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == "0.16.0"
    assert CONTRACT_VERSIONS == {
        "common": "2.1.0",
        "resources": "1.1.0",
        "logs": "2.0.0",
        "i18n": "1.0.0",
        "definitions": "3.0.0",
        "runs": "1.9.0",
        "usage": "1.1.0",
        "projects": "4.1.0",
        "chat": "1.4.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.3.0",
        "sdd": "1.4.0",
        "wiki": "1.3.0",
        "modules": "1.7.0",
    }
    assert constants["CONTRACT_VERSIONS"] == CONTRACT_VERSIONS
    assert list(CONTRACT_VERSIONS) == list(CONTRACT_SUBMODULES)


# ---------------------------------------------------------------- default_backend 삭제


def test_default_backend_field_is_gone() -> None:
    assert "default_backend" not in WorkspaceSettings.model_fields
    props = build_schema()["$defs"]["WorkspaceSettings"]["properties"]
    assert "default_backend" not in props
    assert "default_backend" in IGNORED_SETTINGS_KEYS


def test_old_settings_yaml_reads_and_keeps_default_backend() -> None:
    """옛 키가 든 `settings.yaml` 원문: 읽기가 실패하지 않고, 저장 때 그대로 되돌려 쓴다."""
    text = "default_backend: fake-agent\nagent_defaults:\n  model: m-1\nui:\n  language: ko\n"
    yaml = YAML(typ="safe")
    doc = yaml.load(text)
    settings = WorkspaceSettings.model_validate(doc)
    assert settings.model_extra == {"default_backend": "fake-agent"}
    assert settings.agent_defaults.backend is None  # 옛 키는 공통 기본값이 아니다
    assert settings.ui.language == "ko"
    stored = settings.model_dump(mode="json", exclude_unset=True)
    assert stored == doc
    assert _sha(stored) == _sha(doc)  # 버전 해시 입력 불변
    out = io.StringIO()
    yaml.dump(stored, out)
    assert yaml.load(out.getvalue()) == doc
    assert ignored_settings_keys(settings) == ["default_backend"]
    assert ignored_settings_keys(doc) == ["default_backend"]


@pytest.mark.parametrize("value", ["fake-agent", "", 3, {"id": "x"}, ["a"]])
def test_any_old_default_backend_value_reads(value: Any) -> None:
    """옛 모델이 거부하던 값(문자열이 아님)도 이제는 모르는 키라 읽기가 실패하지 않는다."""
    settings = WorkspaceSettings.model_validate({"default_backend": value})
    assert settings.model_dump(mode="json", exclude_unset=True) == {"default_backend": value}


def test_null_default_backend_is_not_reported() -> None:
    assert ignored_settings_keys({"default_backend": None}) == []
    assert ignored_settings_keys(WorkspaceSettings.model_validate({"default_backend": None})) == []


def test_exported_settings_document_round_trips_old_key() -> None:
    """내보낸 문서(JSON으로 옮긴 설정)에 옛 키가 있어도 다시 읽어 같은 문서가 된다."""
    exported = {
        "format": "zz-bundle",
        "documents": [
            {
                "kind": "settings",
                "body": {
                    "default_backend": "old",
                    "logs": {"projects": {"groups": []}},
                    "zz-future": 1,
                },
            }
        ],
    }
    body = json.loads(json.dumps(exported))["documents"][0]["body"]
    settings = WorkspaceSettings.model_validate(body)
    assert settings.model_dump(mode="json", exclude_unset=True) == body
    assert ignored_settings_keys(settings) == ["logs.projects", "default_backend"]
    full = settings.model_dump(mode="json")
    assert full["default_backend"] == "old"  # 모르는 키는 전체 직렬화에도 남는다


def test_settings_without_old_key_has_no_default_backend() -> None:
    full = WorkspaceSettings().model_dump(mode="json")
    assert "default_backend" not in full


# ---------------------------------------------------------------- UiPreferences.language


def test_ui_language_field() -> None:
    assert UiPreferences().language is None
    assert UiPreferences.model_validate({"language": "en-US"}).language == "en-US"
    with pytest.raises(ValidationError):
        UiPreferences.model_validate({"language": 3})
    # 생략하면 저장 문서에 나타나지 않는다(옛 문서 해시 불변)
    assert "language" not in WorkspaceSettings().model_dump(mode="json", exclude_unset=True)
    schema = build_schema()["$defs"]["UiPreferences"]["properties"]["language"]
    assert schema["x-ui"]["widget"] == KnownUiWidgets.LANGUAGE == "language"
    assert schema["x-ui"]["tier"] == "basic"
    assert schema["title"]
    assert schema["description"]
    assert "enum" not in json.dumps(schema)  # 계약에 언어 목록이 없다
    assert build_schema()["x-constants"]["KNOWN_UI_WIDGETS"]["LANGUAGE"] == "language"


# ---------------------------------------------------------------- i18n 하위 모듈


def test_i18n_submodule_exports() -> None:
    module = importlib.import_module("agent_console_contracts.i18n")
    assert set(module.__all__) == {"I18nInfo", "LanguageInfo", "MessageCatalog"}
    for name in module.__all__:
        assert getattr(contracts, name) is getattr(module, name)
    assert build_schema()["x-modules"]["i18n"] == ["I18nInfo", "LanguageInfo", "MessageCatalog"]


def test_i18n_info_and_language_info() -> None:
    info = I18nInfo.model_validate(
        {
            "languages": [
                {"code": "en", "sources": ["zz-pkg"], "complete": True, "missing": 0},
                {"code": "xx", "sources": ["zz-pkg", "folder:1"], "complete": False},
            ],
            "default_language": "en",
            "fallback_language": "en",
            "zz-future": True,
        }
    )
    assert [lang.code for lang in info.languages] == ["en", "xx"]
    assert info.languages[1].missing is None  # 서버가 세지 않음
    with pytest.raises(ValidationError):
        LanguageInfo.model_validate({"code": "en", "sources": [], "complete": True, "missing": -1})
    with pytest.raises(ValidationError):
        LanguageInfo.model_validate({"code": "", "sources": [], "complete": True})
    schema = build_schema()["$defs"]["LanguageInfo"]
    assert set(schema["required"]) == {"code", "sources", "complete"}
    info_schema = build_schema()["$defs"]["I18nInfo"]
    assert set(info_schema["required"]) == {"languages", "default_language", "fallback_language"}


def test_message_catalog_shape() -> None:
    raw = {
        "language": "en",
        "text": {"화면 언어": "Screen language"},
        "codes": {"i18n.unknown_language": "No messages for {language}"},
        "ns": {"zz-ns": {"title": "T", "nested": {"a": "b"}}},
    }
    catalog = MessageCatalog.model_validate(raw)
    assert catalog.model_dump(mode="json") == raw
    schema = build_schema()["$defs"]["MessageCatalog"]
    assert set(schema["required"]) == {"language", "text", "codes", "ns"}


# ---------------------------------------------------------------- 코드


def test_unknown_language_error_code() -> None:
    assert ErrorCodes.I18N_UNKNOWN_LANGUAGE == "i18n.unknown_language"
    assert HTTP_STATUS_BY_ERROR_CODE["i18n.unknown_language"] == 404
    constants = build_schema()["x-constants"]
    assert constants["ERROR_CODES"]["I18N_UNKNOWN_LANGUAGE"] == "i18n.unknown_language"
    assert constants["HTTP_STATUS_BY_ERROR_CODE"]["i18n.unknown_language"] == 404


@pytest.mark.parametrize(("name", "code"), sorted(I18N_LOADING_CODES.items()))
def test_i18n_loading_issue_codes(name: str, code: str) -> None:
    assert getattr(KnownIssueCodes, name) == code
    assert build_schema()["x-constants"]["KNOWN_ISSUE_CODES"][name] == code


# ---------------------------------------------------------------- CopyKindInfo.open_role


def test_copy_kind_info_open_role() -> None:
    """여는 화면 역할은 열린 문자열이고 선택이다(옛 응답 = null, 계약에 역할 목록 없음)."""
    old = CopyKindInfo.model_validate({"kind": "zz-kind", "library": True, "portable": False})
    assert old.open_role is None
    fresh = CopyKindInfo.model_validate(
        {"kind": "zz-kind", "library": True, "portable": False, "open_role": "zz-role:any"}
    )
    assert fresh.open_role == "zz-role:any"
    schema = build_schema()["$defs"]["CopyKindInfo"]
    assert "open_role" in schema["properties"]
    assert "open_role" not in schema.get("required", [])
    assert "enum" not in json.dumps(schema["properties"]["open_role"])
    assert CONTRACT_VERSIONS["projects"] == "4.1.0"
