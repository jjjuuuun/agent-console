"""agent-console-sdd: SDD 핵심 — 작업 문법 데이터·병합, 마크다운 작업 문서 파싱, 작업 줄 고치기.

서버·실행·프로젝트를 모른다. 문서 원문(문자열)과 계약 모델(`agent_console_contracts.sdd`)만 받는다.

공개 API:
    문법(design §6R.1.3)
    - ``load_default_syntax() -> SpecSyntax``: 패키지 기본 문법(`data/default_syntax.yaml`).
    - ``merge_syntax(*layers, task_statuses=None) -> EffectiveSyntax``: 층 병합(None = 상속,
      값마다 출처).
    - ``effective_syntax(rules, settings, *, default=None)``: 기본 → 설정 → 스펙 세 층.
    - ``status_infos(statuses)``·``document_state_infos(states)``: 라벨을 푼 보기(라벨 없으면 id).
    - ``compile_syntax(syntax) -> CompiledSyntax``: 정규식 컴파일(`ac-safe-regex`)과 문법 이슈.
    파싱
    - ``parse_spec(spec, files, syntax, *, max_tasks, timeout_ms, clock) -> SpecIndex``.
    - ``find_task(index, key)``, ``task_key(document_id, ordinal)``, ``line_hash(line)``,
      ``split_lines(text)``, ``analyze_head(line, syntax) -> HeadLine``(머리 줄 분석).
    줄 고치기(design §6R.1.4)
    - ``patch_task(text, task, *, syntax, status, fields, field_format) -> str``.
    - 예외 ``TaskPatchError``(ValueError, ``code``·``details``), ``TaskChangedError``(줄 해시 다름).
    계획·추적(design §6R.1.6)
    - ``plan(index, syntax) -> TaskPlan``(위상 층·병목·순환, ``task_weight``),
      ``trace(index, links, results, *, syntax, ...) -> TraceMatrix``(빈 곳 5종), ``sum_totals``.
    관문·규칙(design §6R.1.5, §6R.18 Q5·Q12)
    - ``gate_context(spec, index, *, task, change)``, ``evaluate_gates(rules, target, ctx, *,
      operators) -> list[GateBlock]``, ``require_gates``, ``gate_documents(gate)``.
    - ``check_rules(rules, *, operators, documents, settings, graphs) -> list[SpecIssue]``.
    실행 입력(design §6R.1.5, Q9)
    - ``run_input_variables(documents, *, fields)``, ``run_input_values``, ``render_run_input``.
    틀·스펙(design §6R.1.1·§6R.1.2, Q8)
    - ``instantiate``·``spec_to_template`` → ``SpecDraft``, ``blank_documents()``,
      ``definition_kinds(...)``(정의 종류 두 개).
    - ``SpecRepository(store, *, spec_kind, template_kind, ...)``: 만들기·저장·문서 본문·상태
    전환·작업
      고치기(줄 해시 충돌, 한 번 재시도)·틀 목록·틀로 저장.
    파일·가져오기/내보내기(design §6R.13, Q13)
    - ``SpecFiles``(프로토콜)·``SpecFileEntry``·``LocalSpecFiles``·``check_project_path``.
    - ``import_documents``·``export_documents``·``list_import_files``·``guess_title``.
    확장 지점: ``VerificationSource``(X42)·``TaskIntegration``(X43)·선택 능력 ``ProfileChecker``·
    ``AutomationControl``, 맥락 ``SpecContext``·``VerificationContext``.
    오류: ``SddError`` 하위(``code`` = 계약 오류 코드).
"""

from __future__ import annotations

from ._check import check_rules
from ._compiled import (
    KNOWN_LIST_ITEMS,
    CompiledSyntax,
    FieldSpan,
    HeadLine,
    analyze_head,
    compile_syntax,
    line_hash,
    split_lines,
)
from ._errors import (
    DocumentChangedError,
    DocumentExistsError,
    DocumentMissingError,
    GateBlockedError,
    SddError,
    SpecNotFoundError,
    SpecPathError,
    TemplateExistsError,
    TransitionDeniedError,
)
from ._files import LocalSpecFiles, SpecFileEntry, SpecFiles, check_project_path
from ._gates import GateBlock, evaluate_gates, gate_context, gate_documents, require_gates
from ._graphs import dependency_cycles
from ._ids import slug_id, unique_id
from ._integrations import (
    AutomationControl,
    ProfileChecker,
    SpecContext,
    TaskIntegration,
    VerificationContext,
    VerificationSource,
)
from ._parse import SpecFileContent, find_task, parse_spec, task_key
from ._patch import DEFAULT_FIELD_FORMAT, TaskChangedError, TaskPatchError, patch_task
from ._plan import plan, task_weight
from ._repository import DocumentContent, LoadedSpec, SpecRepository, StoredSpec
from ._run_input import (
    FIELD_VARIABLE_PREFIX,
    check_relative_dir,
    document_variable,
    field_variable,
    render_run_input,
    run_input_values,
    run_input_variables,
)
from ._syntax import (
    DEFAULT_SYNTAX_RESOURCE,
    SyntaxLayer,
    document_state_infos,
    effective_syntax,
    load_default_syntax,
    merge_syntax,
    status_infos,
)
from ._templates import (
    BLANK_SPEC_RESOURCE,
    CONTENT_FIELD,
    SpecDraft,
    blank_documents,
    definition_kinds,
    instantiate,
    spec_to_template,
)
from ._trace import DEFAULT_FAILED_RESULTS, DEFAULT_RUN_LINK_KINDS, sum_totals, trace
from ._transfer import (
    DEFAULT_IMPORT_LIMIT,
    ImportedDocuments,
    export_documents,
    guess_title,
    import_documents,
    list_import_files,
)

__all__ = [
    "BLANK_SPEC_RESOURCE",
    "CONTENT_FIELD",
    "DEFAULT_FAILED_RESULTS",
    "DEFAULT_FIELD_FORMAT",
    "DEFAULT_IMPORT_LIMIT",
    "DEFAULT_RUN_LINK_KINDS",
    "DEFAULT_SYNTAX_RESOURCE",
    "FIELD_VARIABLE_PREFIX",
    "KNOWN_LIST_ITEMS",
    "AutomationControl",
    "CompiledSyntax",
    "DocumentChangedError",
    "DocumentContent",
    "DocumentExistsError",
    "DocumentMissingError",
    "FieldSpan",
    "GateBlock",
    "GateBlockedError",
    "HeadLine",
    "ImportedDocuments",
    "LoadedSpec",
    "LocalSpecFiles",
    "ProfileChecker",
    "SddError",
    "SpecContext",
    "SpecDraft",
    "SpecFileContent",
    "SpecFileEntry",
    "SpecFiles",
    "SpecNotFoundError",
    "SpecPathError",
    "SpecRepository",
    "StoredSpec",
    "SyntaxLayer",
    "TaskChangedError",
    "TaskIntegration",
    "TaskPatchError",
    "TemplateExistsError",
    "TransitionDeniedError",
    "VerificationContext",
    "VerificationSource",
    "analyze_head",
    "blank_documents",
    "check_project_path",
    "check_relative_dir",
    "check_rules",
    "compile_syntax",
    "definition_kinds",
    "dependency_cycles",
    "document_state_infos",
    "document_variable",
    "effective_syntax",
    "evaluate_gates",
    "export_documents",
    "field_variable",
    "find_task",
    "gate_context",
    "gate_documents",
    "guess_title",
    "import_documents",
    "instantiate",
    "line_hash",
    "list_import_files",
    "load_default_syntax",
    "merge_syntax",
    "parse_spec",
    "patch_task",
    "plan",
    "render_run_input",
    "require_gates",
    "run_input_values",
    "run_input_variables",
    "slug_id",
    "spec_to_template",
    "split_lines",
    "status_infos",
    "sum_totals",
    "task_key",
    "task_weight",
    "trace",
    "unique_id",
]
