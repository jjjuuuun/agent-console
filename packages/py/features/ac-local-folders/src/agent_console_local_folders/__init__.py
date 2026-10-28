"""로컬 폴더 고르기 순수 규칙(작업 5.7R.33d, design §PI.6·§PI.10).

경로 정규화(`~`·따옴표·`..`·Windows 드라이브), 폴더 확인(`check_folder` → 있음·폴더·권한·숨김·
링크·만들 수 있는가·가장 가까운 상위), 하위 **폴더 이름만** 나열(`list_dirs`:
숨김 기본 숨김·링크·잠금·개수·시간 상한·탐색 범위 제한), 폴더 만들기, 기본 시작 위치.

- 파일 시스템은 주입한다(`FileSystem`): 실제 `LocalFileSystem`, 테스트용 `MemoryFileSystem`.
- 숨김 이름·시작 위치는 패키지 데이터(`data/browse_defaults.json`)이고 인자로 바꾼다(X34).
- 프로젝트 등록부(겹침·같은 경로)는 모른다. 그 판단은 `ac-projects`·`ac-mod-projects`가
  `path`로 한다.
"""

from __future__ import annotations

from ._local import LocalFileSystem
from ._memory import MemoryFileSystem
from ._ops import (
    DEFAULT_LIST_LIMIT,
    DEFAULT_LIST_TIMEOUT,
    check_folder,
    default_roots,
    list_dirs,
    make_folder,
    nearest_existing,
    normalize,
)
from ._paths import (
    home_dir,
    is_within,
    normalize_lexical,
    path_key,
    path_module,
    validate_folder_name,
)
from ._rules import (
    BrowseDefaults,
    RootRule,
    load_browse_defaults,
)
from ._types import (
    FileSystem,
    FolderCheck,
    FolderEntry,
    FolderError,
    FolderErrorCode,
    FolderListing,
    FolderRoot,
    FolderStatus,
    PathFlavor,
    PathInfo,
    ScanEntry,
)

__all__ = [
    "DEFAULT_LIST_LIMIT",
    "DEFAULT_LIST_TIMEOUT",
    "BrowseDefaults",
    "FileSystem",
    "FolderCheck",
    "FolderEntry",
    "FolderError",
    "FolderErrorCode",
    "FolderListing",
    "FolderRoot",
    "FolderStatus",
    "LocalFileSystem",
    "MemoryFileSystem",
    "PathFlavor",
    "PathInfo",
    "RootRule",
    "ScanEntry",
    "check_folder",
    "default_roots",
    "home_dir",
    "is_within",
    "list_dirs",
    "load_browse_defaults",
    "make_folder",
    "nearest_existing",
    "normalize",
    "normalize_lexical",
    "path_key",
    "path_module",
    "validate_folder_name",
]
