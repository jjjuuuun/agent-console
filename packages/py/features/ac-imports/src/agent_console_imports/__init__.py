"""agent-console-imports: 외부 설정에서 정의를 **복사해** 가져오기(design §R11, §R9.5).

원본은 읽기만 한다. 흐름: 출처 목록 → 후보 스캔(미리보기, 쓰기 없음) → 고른 항목 가져오기(복사).

공개 API:
    - 확장 지점: ``ImportSource``(``descriptor``, ``scan() -> ScanResult``), 출처 공장
      ``ImportSourceFactory``(``ImportSourceContext`` → 출처들), entry point
      ``IMPORT_SOURCES_GROUP``, 묶음 이름 ``IMPORT_SOURCES_EXTENSION``
    - 로딩: ``new_import_source_factories``, ``load_import_source_factories``,
      ``build_import_sources``
    - 서비스: ``ImportService(sources, store)`` — ``descriptors``·``preview``·``apply(request, *,
      stamp=None)``(요청 ``project`` → 쓴 정의의 범위 필드 ``SCOPE_FIELD``, ``request_stamp``),
      오류 ``ImportServiceError``·``UnknownImportSourceError``, 저장소 프로토콜 ``DefinitionWriter``
    - 기본 출처(첫 구현): ``agent_console_imports.claude`` — ``ClaudeDirectorySource``,
      ``claude_sources``
"""

from ._interfaces import (
    IMPORT_SOURCES_EXTENSION,
    IMPORT_SOURCES_GROUP,
    DefinitionWriter,
    ImportItem,
    ImportSource,
    ImportSourceContext,
    ImportSourceFactory,
    ScanResult,
)
from ._loading import (
    as_import_source_factory,
    build_import_sources,
    load_import_source_factories,
    new_import_source_factories,
)
from ._service import (
    SCOPE_FIELD,
    ImportService,
    ImportServiceError,
    UnknownImportSourceError,
    request_stamp,
)

__all__ = [
    "IMPORT_SOURCES_EXTENSION",
    "IMPORT_SOURCES_GROUP",
    "SCOPE_FIELD",
    "DefinitionWriter",
    "ImportItem",
    "ImportService",
    "ImportServiceError",
    "ImportSource",
    "ImportSourceContext",
    "ImportSourceFactory",
    "ScanResult",
    "UnknownImportSourceError",
    "as_import_source_factory",
    "build_import_sources",
    "load_import_source_factories",
    "new_import_source_factories",
    "request_stamp",
]
