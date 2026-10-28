"""프로젝트 범위 순수 규칙(design §UX-P): 보이는지, 범위 검사, 옮기기·삭제 계획, 로그 묶음 제안,
프로젝트 층 값, 등록된 프로젝트 폴더(`project_folders`).

서버·웹·다른 기능 패키지 없이 쓴다(의존은 `agent-console-contracts`뿐). 정의 종류 이름을 모르고
(`project` 필드·요약 `extra.project` 유무로 판단), 참조 추출은 함수로 주입받는다(X25).
"""

from __future__ import annotations

from ._folders import ProjectFolderSet, project_folders
from ._layer import project_layer_value
from ._logs import log_paths_from_sessions, normalize_path, suggest_log_projects
from ._model import (
    DefinitionId,
    References,
    ScopedDefinition,
    effective_scope,
    known_project_ids,
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
    "CODE_CROSS_PROJECT",
    "CODE_REFERENCES_UNAVAILABLE",
    "CODE_SHARED_USES_PROJECT",
    "CODE_UNKNOWN",
    "DEFAULT_MESSAGES",
    "MOVE_TO_SHARED_SUGGESTION",
    "DefinitionId",
    "ProjectFolderSet",
    "References",
    "ScopedDefinition",
    "UnknownDefinitionError",
    "delete_plan",
    "effective_scope",
    "known_project_ids",
    "log_paths_from_sessions",
    "move_plan",
    "normalize_path",
    "project_folders",
    "project_layer_value",
    "scope_issues",
    "suggest_log_projects",
    "visible",
]
