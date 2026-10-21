"""본문 파일 경로 검사. 정의 옆 폴더 밖으로 나가는 경로, Windows에서 만들 수 없는 이름을 거부한다.

저장소가 만든 워크스페이스는 Windows·macOS·리눅스 사이로 옮겨지므로(R0.4) 이름 규칙은
가장 엄격한 쪽(Windows)에 맞춘다.
"""

import re
from pathlib import Path, PurePosixPath

from .errors import InvalidContentPath

MAX_CONTENT_PATH_LENGTH = 255

_FORBIDDEN_CHARS = set('<>:"|?*')
"""Windows 파일 이름 금지 문자. `:`는 NTFS 대체 스트림·드라이브 문자라 특히 위험하다."""

_RESERVED_NAME = re.compile(r"(?i)(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³])")
"""Windows 예약 장치 이름. 확장자가 붙어도(`nul.txt`) 예약이다."""


def check_content_path(file: object) -> str:
    """`content.file` 값이 정의 폴더 안의 상대 경로인지 검사하고 정규화한 문자열을 돌려준다.

    거부: 문자열이 아님, 빈 값, NUL·제어 문자, 역슬래시, 절대 경로, `:` 등 Windows 금지 문자,
    `.`·`..`·빈 구성요소, 구성요소 끝의 점·공백, Windows 예약 이름(`CON`, `nul.txt` …),
    너무 긴 경로.

    Raises:
        InvalidContentPath: 위 경우.
    """
    if not isinstance(file, str) or not file:
        raise InvalidContentPath("content.file must be a non-empty string")
    if len(file) > MAX_CONTENT_PATH_LENGTH:
        raise InvalidContentPath("content.file is too long")
    if any(ord(ch) < 32 for ch in file) or "\\" in file:
        raise InvalidContentPath(f"content.file has forbidden characters: {file!r}")
    if file.startswith("/"):
        raise InvalidContentPath(f"content.file must be relative: {file!r}")
    if any(ch in _FORBIDDEN_CHARS for ch in file):
        raise InvalidContentPath(f"content.file has characters Windows cannot store: {file!r}")
    if file.endswith("/") or "//" in file or any(p in (".", "..") for p in file.split("/")):
        raise InvalidContentPath(
            f"content.file must not contain '.', '..' or empty parts: {file!r}"
        )
    for part in file.split("/"):
        if part != part.rstrip(". "):
            raise InvalidContentPath(f"content.file part ends with a dot or space: {file!r}")
        if _RESERVED_NAME.fullmatch(part.split(".", 1)[0].rstrip(" ")):
            raise InvalidContentPath(f"content.file uses a reserved device name: {file!r}")
    return "/".join(PurePosixPath(file).parts)


def resolve_inside(base: Path, file: str, *, root: Path | None = None) -> Path:
    """`base` 아래의 `file`(이미 `check_content_path`를 통과한 값) 실제 경로.

    `root`(워크스페이스 폴더)를 주면 검사 기준이 `root`다. `root`에서 대상까지 **존재하는
    모든 구성요소**가 심볼릭 링크·정션이 아니어야 하고, 해석한 경로가 `root` 안이면서 `base`
    안이어야 한다. (`base` 자체가 밖을 가리키는 링크인 경우를 잡기 위해서다. `base`만 기준으로
    하면 `base.resolve()`가 이미 링크를 따라가 검사를 통과해 버린다.) `root`를 생략하면
    `base`를 기준으로 한다.

    Raises:
        InvalidContentPath: 링크가 끼어 있거나 해석한 경로가 밖이다.
    """
    anchor = base if root is None else root
    target = base / file
    try:
        relative = target.relative_to(anchor)
    except ValueError:
        raise InvalidContentPath(f"content.file escapes its folder: {file!r}") from None
    probe = anchor
    for part in relative.parts:
        probe = probe / part
        if probe.is_symlink() or probe.is_junction():
            raise InvalidContentPath(f"content.file passes through a link: {file!r}")
    resolved = target.resolve()
    resolved_anchor = anchor.resolve()
    resolved_base = base.resolve()
    if (
        resolved == resolved_base
        or not resolved.is_relative_to(resolved_anchor)
        or not resolved.is_relative_to(resolved_base)
    ):
        raise InvalidContentPath(f"content.file escapes its folder: {file!r}")
    return target
