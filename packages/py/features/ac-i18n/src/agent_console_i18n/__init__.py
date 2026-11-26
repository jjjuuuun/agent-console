"""Agent Console 문구 묶음 라이브러리(design §I18N.3·§I18N.8).

언어별 JSON 문구 묶음(``text``·``codes``·``ns`` 세 구역)을 읽고, 출처 순서대로 합치고,
원문 키·코드 키로 조회하고, 언어 간 키·자리표시자를 검사한다.
서버·HTTP·계약 모델을 모른다(표준 라이브러리만).

공개 API(요지):

- 모델: ``Catalog``, ``CatalogIssue``, ``read_catalog``, ``normalize_language``, ``is_language_tag``
- 불러오기: ``MESSAGE_CATALOGS_GROUP``(entry point 그룹), ``package_catalogs``, ``folder_catalogs``,
  ``load_catalog_folder``, ``load_catalog_file``, ``CatalogLoad``
- 병합·조회: ``CatalogSet``, ``Translator``, ``merge_catalogs``, ``match_language``,
  ``placeholders``, ``render``
- 검사: ``compare_catalogs``, ``is_complete``, ``check_codes``, ``check_texts``, ``check_details``,
  ``schema_texts``, ``SchemaTextKeys``, ``flatten_ns``
- 테스트 도구: ``agent_console_i18n.testing``
"""

from __future__ import annotations

from agent_console_i18n._checks import (
    DEFAULT_SCHEMA_TEXT_KEYS,
    PLURAL_SUFFIXES,
    SchemaTextKeys,
    check_codes,
    check_details,
    check_texts,
    compare_catalogs,
    flatten_ns,
    is_complete,
    schema_texts,
)
from agent_console_i18n._loading import (
    LOCALES_DIR,
    MESSAGE_CATALOGS_GROUP,
    CatalogLoad,
    folder_catalogs,
    load_catalog_file,
    load_catalog_folder,
    package_catalogs,
)
from agent_console_i18n._lookup import (
    CatalogSet,
    Translator,
    match_language,
    merge_catalogs,
    placeholders,
    render,
)
from agent_console_i18n._model import (
    CODES,
    NS,
    SECTIONS,
    TEXT,
    Catalog,
    CatalogIssue,
    Origin,
    Section,
    is_language_tag,
    normalize_language,
    read_catalog,
)

__all__ = [
    "CODES",
    "DEFAULT_SCHEMA_TEXT_KEYS",
    "LOCALES_DIR",
    "MESSAGE_CATALOGS_GROUP",
    "NS",
    "PLURAL_SUFFIXES",
    "SECTIONS",
    "TEXT",
    "Catalog",
    "CatalogIssue",
    "CatalogLoad",
    "CatalogSet",
    "Origin",
    "SchemaTextKeys",
    "Section",
    "Translator",
    "check_codes",
    "check_details",
    "check_texts",
    "compare_catalogs",
    "flatten_ns",
    "folder_catalogs",
    "is_complete",
    "is_language_tag",
    "load_catalog_file",
    "load_catalog_folder",
    "match_language",
    "merge_catalogs",
    "normalize_language",
    "package_catalogs",
    "placeholders",
    "read_catalog",
    "render",
    "schema_texts",
]
