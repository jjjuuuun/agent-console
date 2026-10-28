"""프로젝트 순수 규칙(design §PI): 프로젝트 = 로컬 폴더 + 그 폴더 안 구성 사본(`.agent-console/`).

- 등록: 폴더 겹침(`folder_conflicts`·`registry_conflicts`), 상태(`project_status`), 경로 → 프로젝트
  (`project_for_path`), 등록 폴더 묶음(`project_folders`), 등록 id(`suggest_project_id`·
  `registration_id`·`folder_slug`).
- 합치기: 등록부 + 매니페스트 → `Project`(`merge_project`·`split_project`·`initial_manifest`·
  `combined_version`·`ignored_key_issues`).
- 공간 사이 복사: `copy_plan`·`skip_warnings`·`apply_decisions`·`apply_renames`.
- 경로 지킴: `path_fields`·`outside_paths`(스키마 주석 `x-path`만 본다, X33).
- 옛 데이터: `legacy_items`·`legacy_counts`·`without_scope_field`, 프로젝트 층 값
  `project_layer_value`. 옛 범위 규칙(`scope_issues`·`move_plan`·`delete_plan`·`visible`)은 [정리]
  화면 전환까지만 남는다(33t에서 삭제).

서버·웹·저장소 없이 쓴다(의존은 `agent-console-contracts`·`agent-console-local-folders`). 정의 종류
이름·설정 필드 이름을 모르고, 참조 추출·참조 고치기·파일 시스템은 주입받는다.
"""

from __future__ import annotations

from ._copy import (
    CODE_COPY_CONFLICT,
    CODE_COPY_KIND_NOT_PORTABLE,
    CODE_COPY_REFERENCE_CYCLE,
    CODE_COPY_REFERENCE_MISSING,
    CODE_COPY_SKIP_BREAKS_REFERENCE,
    CODE_COPY_SOURCE_MISSING,
    CODE_COPY_UNKNOWN_ACTION,
    DEFAULT_COPY_MESSAGES,
    CopyDecision,
    RewriteReferences,
    SourceDefinition,
    apply_decisions,
    apply_renames,
    copy_plan,
    renames_of,
    skip_warnings,
)
from ._folders import ProjectFolder, ProjectFolderSet, project_folders
from ._identity import (
    FALLBACK_PREFIX,
    MAX_ID_LENGTH,
    folder_slug,
    registration_id,
    suggest_project_id,
)
from ._layer import project_layer_value
from ._legacy import LEGACY_SCOPE_FIELD, legacy_counts, legacy_items, without_scope_field
from ._merge import (
    MANIFEST_KEYS,
    REGISTRATION_KEYS,
    combined_version,
    ignored_key_issues,
    initial_manifest,
    legacy_manifest_values,
    merge_project,
    split_project,
)
from ._model import (
    DefinitionId,
    References,
    ScopedDefinition,
    effective_scope,
    known_project_ids,
)
from ._pathguard import PathField, outside_paths, path_fields
from ._paths import (
    CaseRule,
    PathRelation,
    PathRules,
    folder_key,
    folder_within,
    host_flavor,
    load_path_rules,
    path_relation,
    resolve_folder,
)
from ._registry import (
    ProjectLike,
    ProjectStatusResult,
    RegisteredFolder,
    conflict_details,
    conflict_error_code,
    conflict_status,
    folder_conflicts,
    project_for_path,
    project_status,
    registered_folders,
    registry_conflicts,
)
from ._scope import (
    CODE_CROSS_PROJECT,
    CODE_REFERENCES_UNAVAILABLE,
    CODE_SHARED_USES_PROJECT,
    CODE_UNKNOWN,
    DEFAULT_MESSAGES,
    MOVE_TO_SHARED_SUGGESTION,
    UnknownDefinitionError,
    delete_plan,
    move_plan,
    scope_issues,
    visible,
)

__all__ = [
    "CODE_COPY_CONFLICT",
    "CODE_COPY_KIND_NOT_PORTABLE",
    "CODE_COPY_REFERENCE_CYCLE",
    "CODE_COPY_REFERENCE_MISSING",
    "CODE_COPY_SKIP_BREAKS_REFERENCE",
    "CODE_COPY_SOURCE_MISSING",
    "CODE_COPY_UNKNOWN_ACTION",
    "CODE_CROSS_PROJECT",
    "CODE_REFERENCES_UNAVAILABLE",
    "CODE_SHARED_USES_PROJECT",
    "CODE_UNKNOWN",
    "DEFAULT_COPY_MESSAGES",
    "DEFAULT_MESSAGES",
    "FALLBACK_PREFIX",
    "LEGACY_SCOPE_FIELD",
    "MANIFEST_KEYS",
    "MAX_ID_LENGTH",
    "MOVE_TO_SHARED_SUGGESTION",
    "REGISTRATION_KEYS",
    "CaseRule",
    "CopyDecision",
    "DefinitionId",
    "PathField",
    "PathRelation",
    "PathRules",
    "ProjectFolder",
    "ProjectFolderSet",
    "ProjectLike",
    "ProjectStatusResult",
    "References",
    "RegisteredFolder",
    "RewriteReferences",
    "ScopedDefinition",
    "SourceDefinition",
    "UnknownDefinitionError",
    "apply_decisions",
    "apply_renames",
    "combined_version",
    "conflict_details",
    "conflict_error_code",
    "conflict_status",
    "copy_plan",
    "delete_plan",
    "effective_scope",
    "folder_conflicts",
    "folder_key",
    "folder_slug",
    "folder_within",
    "host_flavor",
    "ignored_key_issues",
    "initial_manifest",
    "known_project_ids",
    "legacy_counts",
    "legacy_items",
    "legacy_manifest_values",
    "load_path_rules",
    "merge_project",
    "move_plan",
    "outside_paths",
    "path_fields",
    "path_relation",
    "project_folders",
    "project_for_path",
    "project_layer_value",
    "project_status",
    "registered_folders",
    "registration_id",
    "registry_conflicts",
    "renames_of",
    "resolve_folder",
    "scope_issues",
    "skip_warnings",
    "split_project",
    "suggest_project_id",
    "visible",
    "without_scope_field",
]
