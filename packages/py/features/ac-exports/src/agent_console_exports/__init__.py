"""agent-console-exports: 내보내기 확장 지점(X8, design §2R.7).

흐름: 형식 목록 → 미리보기(파일 목록·충돌·경고, 쓰기 없음) → 보관 파일(zip, 메모리) 또는 허용 폴더에
쓰기. 형식은 플러그인이다(entry point `agent_console.exporters` = 형식 공장). 서비스는 형식 이름을
모른다.

공개 API:
    - 확장 지점: ``Exporter``(``descriptor``, 순수
      ``plan(items, catalog, options) -> ExportOutput``),
      ``ExporterFactory``(설치자 옵션 → 형식), ``EXPORTERS_GROUP``, ``EXPORTERS_EXTENSION``,
      산출물 ``ExportOutput``·``OutputFile``, 이슈 코드 ``ExportIssueCodes``
    - 주입 프로토콜: ``ExportCatalog``(``document``·``files``·``dependencies``), ``DependencyLike``
    - 로딩: ``new_exporter_factories``, ``load_exporter_factories``, ``build_exporters``,
      ``as_exporter_factory``, ``as_exporter``
    - 서비스: ``ExportService(exporters, catalog, *, writer, secret_rules)`` —
      ``descriptors``·``roots``·
      ``plan``·``archive``·``write``·``output``, 결과 ``ExportArchive``
    - 쓰기: ``FolderWriter(roots, *, protected)``, ``ExportRoot``, ``build_zip``, ``path_problem``
    - 오류: ``ExportError``(``code`` = 계약 오류 코드) — ``UnknownExporterError``·
      ``UnknownExportRootError``·``ExportItemNotFoundError``(not_found), ``ExportValidationError``
      (validation_failed), ``ExportConflictError``(already_exists)
    - 기본 형식(첫 구현): ``agent_console_exports.claude_dir`` — ``ClaudeDirExporter``,
      ``claude_dir_exporter``
"""

from ._archive import ZIP_TIMESTAMP, build_zip
from ._errors import (
    ExportConflictError,
    ExportError,
    ExportItemNotFoundError,
    ExportValidationError,
    UnknownExporterError,
    UnknownExportRootError,
)
from ._folder import ExportRoot, FolderWriter
from ._interfaces import (
    EXPORTERS_EXTENSION,
    EXPORTERS_GROUP,
    DependencyLike,
    ExportCatalog,
    Exporter,
    ExporterFactory,
    ExportIssueCodes,
    ExportOutput,
    OutputFile,
)
from ._loading import (
    as_exporter,
    as_exporter_factory,
    build_exporters,
    load_exporter_factories,
    new_exporter_factories,
)
from ._paths import path_problem
from ._secrets import scrub_output
from ._service import DEFAULT_ARCHIVE_NAME, ExportArchive, ExportService

__all__ = [
    "DEFAULT_ARCHIVE_NAME",
    "EXPORTERS_EXTENSION",
    "EXPORTERS_GROUP",
    "ZIP_TIMESTAMP",
    "DependencyLike",
    "ExportArchive",
    "ExportCatalog",
    "ExportConflictError",
    "ExportError",
    "ExportIssueCodes",
    "ExportItemNotFoundError",
    "ExportOutput",
    "ExportRoot",
    "ExportService",
    "ExportValidationError",
    "Exporter",
    "ExporterFactory",
    "FolderWriter",
    "OutputFile",
    "UnknownExportRootError",
    "UnknownExporterError",
    "as_exporter",
    "as_exporter_factory",
    "build_exporters",
    "build_zip",
    "load_exporter_factories",
    "new_exporter_factories",
    "path_problem",
    "scrub_output",
]
