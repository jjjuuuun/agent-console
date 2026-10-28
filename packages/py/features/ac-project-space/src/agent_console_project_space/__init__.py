"""agent-console-project-space: 프로젝트 폴더의 구성 사본 공간.

프로젝트 폴더 하나의 `<폴더>/.agent-console/`를 정의 저장소(workspace 정의 YAML과 같은 형식, 종류별
폴더)로 열고, 폴더 매니페스트 `project.yaml`을 읽고 쓴다(`If-Match`). 등록할 때 매니페스트와
`.gitignore`를 없을 때만 만든다. 비밀처럼 보이는 값은 저장하지 않는다(`secret://` 참조만).
서버·DB 없이 폴더 하나만으로 동작한다. 파일 시스템은 `SpaceFiles`로 주입한다.

설계: specs/agent-console/design.md §PI.4.
"""

from ._errors import (
    ConfigReadonly,
    FolderMissing,
    ManifestInvalid,
    SecretFinding,
    SecretRejected,
    SpaceError,
    UnsafeConfigDir,
)
from ._files import LocalFiles, SpaceFiles
from ._gitignore import default_gitignore_template
from ._init import GitignoreState, InitResult, ManifestState, init_space
from ._layout import DEFAULT_CONFIG_DIR, SpaceLayout
from ._manifest import ManifestRecord, read_manifest, reset_manifest, write_manifest
from ._space import ProjectSpace, SpaceOptions, open_space, portable_kinds, scan_secrets

__all__ = [
    "DEFAULT_CONFIG_DIR",
    "ConfigReadonly",
    "FolderMissing",
    "GitignoreState",
    "InitResult",
    "LocalFiles",
    "ManifestInvalid",
    "ManifestRecord",
    "ManifestState",
    "ProjectSpace",
    "SecretFinding",
    "SecretRejected",
    "SpaceError",
    "SpaceFiles",
    "SpaceLayout",
    "SpaceOptions",
    "UnsafeConfigDir",
    "default_gitignore_template",
    "init_space",
    "open_space",
    "portable_kinds",
    "read_manifest",
    "reset_manifest",
    "scan_secrets",
    "write_manifest",
]
