"""`ExportService`: 형식 목록 → 미리보기(파일 목록·충돌) → 보관 파일(zip) 또는 허용 폴더에 쓰기."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from agent_console_contracts import (
    ExporterDescriptor,
    ExportFile,
    ExportPlan,
    ExportRequest,
    ExportResult,
    ExportRootInfo,
    ExportWriteRequest,
    Issue,
)
from agent_console_secret_rules import SecretRules, default_rules

from ._archive import build_zip
from ._errors import (
    ExportItemNotFoundError,
    ExportValidationError,
    UnknownExporterError,
    UnknownExportRootError,
)
from ._folder import FolderWriter
from ._interfaces import ExportCatalog, Exporter, ExportIssueCodes, ExportOutput
from ._paths import path_problem
from ._secrets import scrub_output

__all__ = ["DEFAULT_ARCHIVE_NAME", "ExportArchive", "ExportService"]

_log = logging.getLogger(__name__)

DEFAULT_ARCHIVE_NAME = "{exporter}.zip"
"""보관 파일 이름 템플릿(`{exporter}` = 형식 id)."""


@dataclass(frozen=True, slots=True)
class ExportArchive:
    """보관 파일 결과: 파일 이름·zip 바이트·미리보기(파일 목록·경고)."""

    filename: str
    data: bytes
    plan: ExportPlan


def _pointer(parts: Sequence[Any]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


class ExportService:
    """정의를 형식 플러그인으로 내보낸다. 정의는 읽기만 한다.

    Args:
        exporters: 형식 id → 형식(`build_exporters` 결과).
        catalog: 정의 읽기 창구(`ExportCatalog`).
        writer: 허용 폴더 쓰기(없으면 폴더 쓰기 꺼짐 — 루트 목록이 빈다).
        secret_rules: 지금의 비밀 의심 규칙을 돌려주는 함수(없으면 기본 규칙). 모든 산출물의
            마지막 검사에 쓴다.
        archive_name: 보관 파일 이름 템플릿.
    """

    def __init__(
        self,
        exporters: Mapping[str, Exporter],
        catalog: ExportCatalog,
        *,
        writer: FolderWriter | None = None,
        secret_rules: Callable[[], SecretRules] | None = None,
        archive_name: str = DEFAULT_ARCHIVE_NAME,
    ) -> None:
        self._exporters = dict(exporters)
        self._catalog = catalog
        self._writer = writer or FolderWriter()
        self._rules = secret_rules or default_rules
        self._archive_name = archive_name

    # ------------------------------------------------------------ 조회

    def descriptors(self) -> list[ExporterDescriptor]:
        """형식 디스크립터(id 순)."""
        return [self._exporters[k].descriptor for k in sorted(self._exporters)]

    def roots(self, *, expose_paths: bool = True) -> list[ExportRootInfo]:
        """폴더 쓰기를 허용한 루트(없으면 빈 목록 = 폴더 쓰기 꺼짐)."""
        return self._writer.root_infos(expose_paths=expose_paths)

    # ------------------------------------------------------------ 만들기

    def _exporter(self, exporter_id: str) -> Exporter:
        exporter = self._exporters.get(exporter_id)
        if exporter is None:
            raise UnknownExporterError(f"내보내기 형식이 없습니다: {exporter_id}")
        return exporter

    def _check_request(self, exporter: Exporter, request: ExportRequest) -> None:
        descriptor = exporter.descriptor
        issues: list[Issue] = []
        if descriptor.kinds:
            for index, item in enumerate(request.items):
                if item.kind not in descriptor.kinds:
                    issues.append(
                        Issue(
                            severity="error",
                            code=ExportIssueCodes.KIND_UNSUPPORTED,
                            message="이 형식이 지원하지 않는 정의 종류입니다",
                            path=f"/items/{index}/kind",
                            details={"kind": item.kind},
                        )
                    )
        try:
            validator = Draft202012Validator(descriptor.config_schema)
            errors = validator.iter_errors(request.options)
            for error in sorted(errors, key=lambda e: [str(p) for p in e.path]):
                issues.append(
                    Issue(
                        severity="error",
                        code=ExportIssueCodes.INVALID_OPTIONS,
                        message="옵션이 형식의 스키마에 맞지 않습니다",
                        path=_pointer(["options", *error.path]),
                        details={"rule": str(error.validator)},
                    )
                )
        except SchemaError:
            _log.warning("내보내기 형식 %s의 옵션 스키마가 잘못됐습니다", descriptor.id)
        if issues:
            raise ExportValidationError("내보내기 요청이 잘못됐습니다", issues=issues)
        for item in request.items:
            if self._catalog.document(item.kind, item.id) is None:
                raise ExportItemNotFoundError(f"정의가 없습니다: {item.kind}/{item.id}")

    @staticmethod
    def _check_output(output: ExportOutput) -> None:
        issues: list[Issue] = []
        seen: set[str] = set()
        for file in output.files:
            problem = path_problem(file.path)
            if problem is None and file.path.casefold() in seen:
                problem = "같은 경로(대소문자 무시)가 두 번 있습니다"
            seen.add(file.path.casefold())
            if problem is not None:
                issues.append(
                    Issue(
                        severity="error",
                        code=ExportIssueCodes.UNSAFE_PATH,
                        message=problem,
                        details={"file": file.path},
                    )
                )
        if issues:
            raise ExportValidationError("형식이 안전하지 않은 경로를 만들었습니다", issues=issues)

    def output(self, request: ExportRequest) -> ExportOutput:
        """요청을 검사하고 형식으로 파일 내용을 만든 뒤 평문 비밀 마지막 검사를 거친다.

        Raises:
            UnknownExporterError: 형식이 없을 때.
            ExportValidationError: 종류·옵션이 잘못됐거나 형식이 안전하지 않은 경로를 만들었을 때.
            ExportItemNotFoundError: 고른 정의가 없을 때.
        """
        exporter = self._exporter(request.exporter)
        self._check_request(exporter, request)
        output = exporter.plan(request.items, self._catalog, request.options)
        self._check_output(output)
        return scrub_output(output, self._rules())

    @staticmethod
    def _refuse_errors(output: ExportOutput) -> None:
        errors = [w for w in output.warnings if w.severity == "error"]
        if errors:
            raise ExportValidationError("형식이 내보낼 수 없다고 했습니다", issues=output.warnings)

    def plan(self, request: ExportRequest) -> ExportPlan:
        """미리보기(파일 경로·크기·동작 + 경고). `root`가 있으면 그 폴더 기준으로 동작을 계산한다
        (없음 create · 같은 내용 skip · 다른 내용 conflict), 없으면 모두 create.
        아무것도 쓰지 않는다.
        """
        output = self.output(request)
        if request.root is not None:
            files = self._writer.plan(output.files, request.root, request.subdir)
        else:
            files = [
                ExportFile(path=f.path, media_type=f.media_type, size=len(f.data))
                for f in output.files
            ]
        return ExportPlan(files=files, warnings=output.warnings)

    def archive(self, request: ExportRequest) -> ExportArchive:
        """보관 파일(zip)을 메모리에서 만든다(`root`·`subdir`는 무시, 디스크에 쓰지 않음).

        Raises:
            ExportValidationError: 형식 경고에 error가 있을 때(그 밖은 `output`과 같음).
        """
        output = self.output(request)
        self._refuse_errors(output)
        plan = ExportPlan(
            files=[
                ExportFile(path=f.path, media_type=f.media_type, size=len(f.data))
                for f in output.files
            ],
            warnings=output.warnings,
        )
        name = self._archive_name.replace("{exporter}", request.exporter)
        return ExportArchive(filename=name, data=build_zip(output.files), plan=plan)

    def write(self, request: ExportWriteRequest) -> ExportResult:
        """허용 루트 아래 `subdir`에 쓴다(`on_conflict`, 기본 fail).

        Raises:
            UnknownExportRootError: 루트가 없거나 쓸 수 없을 때.
            ExportValidationError: 경로가 안전하지 않거나 형식 경고에 error가 있을 때.
            ExportConflictError: `fail`인데 다른 내용의 파일이 있을 때(아무것도 쓰지 않음).
        """
        if request.root not in {r.id for r in self._writer.roots()}:
            raise UnknownExportRootError(f"내보내기 루트가 없습니다: {request.root}")
        output = self.output(request)
        self._refuse_errors(output)
        files = self._writer.write(
            output.files, request.root, request.subdir, on_conflict=request.on_conflict
        )
        return ExportResult(files=files, warnings=output.warnings)
