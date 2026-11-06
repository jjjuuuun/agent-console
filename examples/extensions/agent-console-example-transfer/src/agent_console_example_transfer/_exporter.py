"""내보내기 형식(X8) `example-json`: 고른 정의(+ 함께 쓰는 정의)를 JSON 파일 하나로."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from agent_console_contracts import ExporterDescriptor, ExportSelection, Issue
from agent_console_exports import ExportCatalog, ExportIssueCodes, ExportOutput, OutputFile

from ._format import FORMAT_ID, BundleEntry, BundleFormat, dump_bundle, load_format

__all__ = ["OPTIONS_SCHEMA", "JsonBundleExporter", "json_bundle_exporter"]

OPTIONS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "include_dependencies": {
            "type": "boolean",
            "default": True,
            "title": "함께 쓰는 정의 포함",
            "description": (
                "고른 정의가 쓰는 정의(팀 구성의 에이전트·리소스 등)도 같은 파일에 담는다."
            ),
        }
    },
    "additionalProperties": False,
}
"""요청 옵션(`ExportRequest.options`) 스키마. 서비스가 이 스키마로 검사한다."""


class JsonBundleExporter:
    """정의를 묶음 파일 하나로 만드는 형식. `plan`은 순수하다(카탈로그를 읽기만 한다).

    평문 비밀 검사는 이 형식이 하지 않는다. `ExportService`가 모든 형식의 산출물을
    마지막에 `ac-secret-rules`로 검사해 가린다(형식과 무관한 안전망). 비밀 참조
    (`secret://이름`)는 참조 그대로 담긴다 — 값이 아니다.

    Args:
        fmt: 형식 설정(`load_format`).
    """

    def __init__(self, fmt: BundleFormat) -> None:
        self._fmt = fmt
        self._descriptor = ExporterDescriptor(
            id=FORMAT_ID,
            title=fmt.title,
            description=fmt.description,
            config_schema=OPTIONS_SCHEMA,
            kinds=[],  # 빈 목록 = 종류를 가리지 않는다(정의 원문을 그대로 옮긴다)
        )

    @property
    def descriptor(self) -> ExporterDescriptor:
        """형식 디스크립터(id = entry point 이름)."""
        return self._descriptor

    @property
    def format(self) -> BundleFormat:
        """형식 설정."""
        return self._fmt

    def plan(
        self,
        items: Sequence[ExportSelection],
        catalog: ExportCatalog,
        options: Mapping[str, Any],
    ) -> ExportOutput:
        """고른 정의 → 파일 하나(`file_name`). 함께 쓰는 정의는 고른 정의 뒤에 한 번씩 담는다."""
        include = options.get("include_dependencies", True) is not False
        entries: list[BundleEntry] = []
        warnings: list[Issue] = []
        seen: set[tuple[str, str]] = set()
        stack = [(item.kind, item.id) for item in reversed(items)]
        while stack:
            kind, ident = stack.pop()
            if (kind, ident) in seen:
                continue
            seen.add((kind, ident))
            document = catalog.document(kind, ident)
            if document is None:
                warnings.append(
                    Issue(
                        severity="warning",
                        code=ExportIssueCodes.NOT_FOUND,
                        message="함께 쓰이는 정의를 찾지 못해 건너뜁니다",
                        details={"kind": kind, "id": ident},
                    )
                )
                continue
            kept = {k: v for k, v in document.items() if k not in self._fmt.drop_fields}
            entries.append(BundleEntry(kind, ident, kept, dict(catalog.files(kind, ident))))
            if include:
                stack.extend((d.kind, d.id) for d in reversed(catalog.dependencies(kind, ident)))
        data = dump_bundle(entries, self._fmt)
        return ExportOutput(
            files=[OutputFile(self._fmt.file_name, data, "application/json")], warnings=warnings
        )


def json_bundle_exporter(options: Mapping[str, Any]) -> JsonBundleExporter:
    """형식 공장(entry point `agent_console.exporters` 값): 설치자 옵션 → 형식.

    Raises:
        ValueError: 옵션이 틀렸을 때(서비스 로더가 경고로 남기고 이 형식을 건너뛴다).
    """
    return JsonBundleExporter(load_format(options))
