"""mod-imports가 받는 포트(이름 = 포트, design §3R.1.2·§3R.1.3).

- 필수 ``definitions.store``: 가져온 정의를 쓸 저장소(``agent_console_imports.DefinitionWriter``).
- 선택 ``secrets.rules``: 지금 비밀 의심 규칙(``() -> SecretRules``). 없으면 출처가 기본 규칙을
  쓴다.
- 선택 ``projects.folders``(5.7R.33k): 등록 프로젝트 폴더(``() -> ProjectFoldersLike``,
  ``entries``의 id·폴더). 있으면 출처는 요청 ``?project=`` 프로젝트 폴더의 ``.claude``이고
  설정 ``project_dir``는 쓰지 않는다. 없으면 설정 그대로.
- 선택 ``definitions.spaces``(5.7R.33k): 등록 id → 그 프로젝트 공간의 정의 저장소. 가져오기 저장
  위치 기본(``target=project``). 없으면 프로젝트 공간에 쓰지 못한다(라이브러리만).
"""

from __future__ import annotations

from collections.abc import Callable

from agent_console_imports import DefinitionWriter
from agent_console_modkit import PortKey
from agent_console_secret_rules import SecretRules

from .projects import DefinitionSpacesLike, ProjectFoldersLike

type SecretRulesReader = Callable[[], SecretRules]
"""지금 비밀 의심 규칙을 돌려주는 함수(``secrets.rules`` 포트 모양)."""

DEFINITIONS_STORE: PortKey[DefinitionWriter] = PortKey("definitions.store", "정의 저장소(쓰기)")
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")
PROJECT_FOLDERS: PortKey[Callable[[], ProjectFoldersLike]] = PortKey(
    "projects.folders", "앱에 등록된 프로젝트 폴더(전체·보관)"
)
DEFINITIONS_SPACES: PortKey[DefinitionSpacesLike] = PortKey(
    "definitions.spaces", "공간 이름(등록 id) → 정의 저장소"
)

__all__ = [
    "DEFINITIONS_SPACES",
    "DEFINITIONS_STORE",
    "PROJECT_FOLDERS",
    "SECRET_RULES",
    "SecretRulesReader",
]
