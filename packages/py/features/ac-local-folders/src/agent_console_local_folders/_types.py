"""공개 자료형: 주입하는 파일 시스템 인터페이스, 결과 값, 오류 코드."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

__all__ = [
    "FileSystem",
    "FolderCheck",
    "FolderEntry",
    "FolderError",
    "FolderErrorCode",
    "FolderListing",
    "FolderRoot",
    "FolderStatus",
    "PathFlavor",
    "PathInfo",
    "ScanEntry",
]

PathFlavor = Literal["posix", "windows"]
"""서버 경로 방식. Linux·macOS 서버는 `posix`(`/home/...`), Windows 서버는 `windows`(`C:\\...`)."""


@dataclass(frozen=True)
class PathInfo:
    """경로 하나의 상태(링크는 따라간 결과).

    Attributes:
        is_dir: 폴더인가.
        is_link: 경로 자체가 심볼릭 링크(또는 접합점)인가.
        hidden_attr: OS 숨김 속성(Windows `FILE_ATTRIBUTE_HIDDEN`). 점 이름 규칙은 따로 본다.
        readable: 읽기(폴더면 목록 읽기·들어가기) 권한.
        writable: 쓰기(폴더면 안에 만들기) 권한.
    """

    is_dir: bool
    is_link: bool = False
    hidden_attr: bool = False
    readable: bool = True
    writable: bool = True


@dataclass(frozen=True)
class ScanEntry:
    """`FileSystem.scan`이 돌려주는 항목 하나(파일 포함, 거르기는 이 패키지가 한다)."""

    name: str
    is_dir: bool
    is_link: bool = False
    hidden_attr: bool = False


class FileSystem(Protocol):
    """주입하는 파일 시스템. 실제 구현 `LocalFileSystem`, 테스트용 `MemoryFileSystem`.

    경로 인자는 이 패키지가 정규화한 절대 경로 문자열이다(`flavor` 방식).
    """

    @property
    def flavor(self) -> PathFlavor:
        """경로 방식."""
        ...

    def info(self, path: str) -> PathInfo | None:
        """경로 상태. 없으면 `None`. 알 수 없으면(상위 권한 등) `PermissionError`/`OSError`."""
        ...

    def scan(self, path: str) -> Iterable[ScanEntry]:
        """바로 아래 항목. 없음 `FileNotFoundError`, 폴더 아님 `NotADirectoryError`,
        권한 `PermissionError`. 지연 반복을 권장한다(시간 상한·개수 상한에서 멈춘다)."""
        ...

    def realpath(self, path: str) -> str:
        """링크를 푼 실제 경로(없는 부분은 그대로)."""
        ...

    def mkdir(self, path: str) -> None:
        """폴더 하나 만들기(상위는 만들지 않음). `FileExistsError`·`FileNotFoundError`·
        `PermissionError`."""
        ...


class FolderErrorCode:
    """`FolderError.code`와 `FolderCheck.problem` 값(열린 문자열, 아래는 이 패키지가 내는 것)."""

    EMPTY = "empty"
    INVALID_PATH = "invalid_path"
    RELATIVE = "relative"
    FOREIGN_PATH = "foreign_path"
    NO_HOME = "no_home"
    OUTSIDE_ROOTS = "outside_roots"
    NOT_FOUND = "not_found"
    NOT_DIRECTORY = "not_directory"
    NO_ACCESS = "no_access"
    INVALID_NAME = "invalid_name"
    EXISTS = "exists"
    MISSING_PARENT = "missing_parent"
    IO_ERROR = "io_error"


class FolderError(Exception):
    """폴더 작업 실패. `code`는 `FolderErrorCode` 값, `message`는 기본 한국어 문구."""

    def __init__(self, code: str, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path

    def __repr__(self) -> str:
        return f"FolderError({self.code!r}, {self.message!r})"


class FolderStatus:
    """`FolderCheck.status` 값(화면 확인 상태 중 폴더만 보고 정할 수 있는 것).

    등록 겹침(`taken`·`overlap_*`)은 프로젝트 등록부를 아는 쪽(ac-projects·mod-projects)이 정한다.
    `invalid`면 이유는 `problem`을 본다(다른 OS 경로면 `foreign_path`).
    """

    OK = "ok"
    OK_READONLY = "ok_readonly"
    MISSING = "missing"
    MISSING_PARENT = "missing_parent"
    NOT_DIRECTORY = "not_directory"
    NO_ACCESS = "no_access"
    INVALID = "invalid"


@dataclass(frozen=True)
class FolderCheck:
    """폴더 확인 결과(`check_folder`). 폴더 내용(파일 이름)은 담지 않는다.

    Attributes:
        input: 받은 입력 그대로.
        path: 저장될 경로(정규화 + 링크를 푼 실제 경로). 입력이 경로가 아니면 `None`.
        exists: 있는가(권한 때문에 상태를 모르면 `True`, `readable=False`).
        is_dir: 폴더인가.
        readable: 읽을 수 있는가.
        writable: 쓸 수 있는가.
        can_create: 없고, 상위 폴더가 있고 쓸 수 있어 `make_folder`로 만들 수 있는가.
        hidden: 마지막 이름이 숨김인가(점·숨김 속성·`hidden_names`).
        link: 입력 경로와 저장될 경로가 다른가(심볼릭 링크·접합점을 거침).
        nearest_existing: `path`가 폴더면 그 자신, 아니면 가장 가까운 존재하는 상위 폴더.
        problem: 입력이 쓸 수 없는 경로인 이유(`FolderErrorCode`). 정상이면 `None`.
    """

    input: str
    path: str | None
    exists: bool = False
    is_dir: bool = False
    readable: bool = False
    writable: bool = False
    can_create: bool = False
    hidden: bool = False
    link: bool = False
    nearest_existing: str | None = None
    problem: str | None = None

    @property
    def status(self) -> str:
        """`FolderStatus` 값 하나(우선순위: 입력 문제 → 없음 → 권한 → 폴더 아님 → 쓰기)."""
        if self.problem is not None or self.path is None:
            return FolderStatus.INVALID
        if not self.exists:
            return FolderStatus.MISSING if self.can_create else FolderStatus.MISSING_PARENT
        if not self.readable:
            return FolderStatus.NO_ACCESS
        if not self.is_dir:
            return FolderStatus.NOT_DIRECTORY
        return FolderStatus.OK if self.writable else FolderStatus.OK_READONLY

    def to_dict(self) -> dict[str, Any]:
        """JSON용 dict(`status` 포함)."""
        return {**asdict(self), "status": self.status}


@dataclass(frozen=True)
class FolderEntry:
    """하위 폴더 하나. 파일은 목록에 없다.

    Attributes:
        name: 폴더 이름.
        path: 목록 경로 + 이름(링크는 풀지 않음).
        hidden: 숨김 폴더인가.
        link: 심볼릭 링크·접합점인가(등록할 때 실제 경로로 저장).
        locked: 읽을 수 없어 들어갈 수 없는가.
    """

    name: str
    path: str
    hidden: bool = False
    link: bool = False
    locked: bool = False


@dataclass(frozen=True)
class FolderListing:
    """하위 폴더 목록(`list_dirs`).

    Attributes:
        path: 목록 경로(정규화, 링크는 풀지 않음).
        parent: 상위 폴더. 루트이거나 탐색 범위 밖이면 `None`.
        entries: 하위 폴더(이름순).
        truncated: 개수·시간 상한으로 잘렸는가.
        timed_out: 시간 상한으로 멈췄는가.
        hidden_count: 숨겨서 뺀 폴더 수(잘렸으면 읽은 범위 안에서).
    """

    path: str
    parent: str | None
    entries: tuple[FolderEntry, ...]
    truncated: bool = False
    timed_out: bool = False
    hidden_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """JSON용 dict."""
        return asdict(self)


@dataclass(frozen=True)
class FolderRoot:
    """탐색 시작 위치 하나(`default_roots`).

    Attributes:
        kind: 규칙 데이터의 종류 문자열(기본 데이터: `home`·`root`·`drive`·`mount`).
        path: 절대 경로.
        label: 표시 이름(규칙 데이터의 틀).
    """

    kind: str
    path: str
    label: str
