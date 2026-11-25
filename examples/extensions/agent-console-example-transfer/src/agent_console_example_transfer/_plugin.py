"""설치하지 않고 쓰기: 서버 설정 `plugins.modules`의 `register(registries)` 진입점."""

from __future__ import annotations

from typing import Any

from agent_console_exports import EXPORTERS_EXTENSION
from agent_console_imports import IMPORT_SOURCES_EXTENSION

from ._exporter import json_bundle_exporter
from ._format import FORMAT_ID
from ._source import json_bundle_sources

__all__ = ["register"]


def register(registries: Any) -> None:
    """묶음의 내보내기·가져오기 공장 레지스트리에 이 형식을 등록한다.

    서버 설정 `plugins.modules: ["agent_console_example_transfer:register"]`로 쓸 때 부른다.
    설치했다면 entry point로 충분하다(둘을 함께 쓰면 같은 key가 두 번 등록되어 그 플러그인이
    실패한다).
    레지스트리 이름은 두 라이브러리 상수(`EXPORTERS_EXTENSION`·`IMPORT_SOURCES_EXTENSION`)다.
    """
    source = f"module {__name__}"
    registries.extension(EXPORTERS_EXTENSION).register(
        FORMAT_ID, json_bundle_exporter, source=source
    )
    registries.extension(IMPORT_SOURCES_EXTENSION).register(
        FORMAT_ID, json_bundle_sources, source=source
    )
