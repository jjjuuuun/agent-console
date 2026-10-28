"""폴더 확인·나열·만들기·시작 위치(파일 시스템은 주입)."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence

from ._paths import is_within, normalize_lexical, path_key, path_module, validate_folder_name
from ._rules import BrowseDefaults, load_browse_defaults
from ._types import (
    FileSystem,
    FolderCheck,
    FolderEntry,
    FolderError,
    FolderErrorCode,
    FolderListing,
    FolderRoot,
    PathInfo,
    ScanEntry,
)

__all__ = [
    "DEFAULT_LIST_LIMIT",
    "DEFAULT_LIST_TIMEOUT",
    "check_folder",
    "default_roots",
    "list_dirs",
    "make_folder",
    "nearest_existing",
    "normalize",
]

DEFAULT_LIST_LIMIT = 2000
"""`list_dirs` 기본 최대 항목 수."""
DEFAULT_LIST_TIMEOUT = 3.0
"""`list_dirs` 기본 시간 상한(초)."""

_NO_ENV: Mapping[str, str] = {}


def _info(fs: FileSystem, path: str) -> tuple[PathInfo | None, bool]:
    """(상태, 권한 등으로 모름)."""
    try:
        return fs.info(path), False
    except OSError:
        return None, True


def _real(fs: FileSystem, lexical: str, environ: Mapping[str, str]) -> str:
    try:
        resolved = fs.realpath(lexical)
    except (OSError, ValueError):
        return lexical
    if fs.flavor == "windows" and resolved.startswith("\\\\?\\") and resolved[5:6] == ":":
        resolved = resolved[4:]
    try:
        return normalize_lexical(resolved, flavor=fs.flavor, environ=environ)
    except FolderError:
        return lexical


def _defaults(defaults: BrowseDefaults | None) -> BrowseDefaults:
    return defaults if defaults is not None else load_browse_defaults()


def _is_hidden(name: str, hidden_attr: bool, defaults: BrowseDefaults) -> bool:
    return name.startswith(".") or hidden_attr or defaults.is_hidden_name(name)


def _check_roots(fs: FileSystem, real: str, roots: Sequence[str] | None) -> None:
    if roots is not None and not is_within(real, roots, fs.flavor):
        raise FolderError(
            FolderErrorCode.OUTSIDE_ROOTS, "탐색할 수 있는 범위 밖의 경로입니다.", path=real
        )


def normalize(
    raw: str,
    *,
    fs: FileSystem,
    environ: Mapping[str, str] = _NO_ENV,
    real: bool = True,
) -> str:
    """입력 → 정규화한 절대 경로. `real=True`면 링크를 푼 실제 경로(등록·저장용).

    Raises:
        FolderError: 경로가 아님(`normalize_lexical`과 같음).
    """
    lexical = normalize_lexical(raw, flavor=fs.flavor, environ=environ)
    return _real(fs, lexical, environ) if real else lexical


def nearest_existing(path: str, *, fs: FileSystem) -> str | None:
    """`path`(정규화한 절대 경로)가 폴더면 그 자신, 아니면 가장 가까운 존재하는 상위 폴더."""
    pm = path_module(fs.flavor)
    cur = path
    while True:
        info, _ = _info(fs, cur)
        if info is not None and info.is_dir:
            return cur
        parent = pm.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def check_folder(
    raw: str,
    *,
    fs: FileSystem,
    environ: Mapping[str, str] = _NO_ENV,
    defaults: BrowseDefaults | None = None,
    roots: Sequence[str] | None = None,
) -> FolderCheck:
    """경로 입력 확인. 사용자 입력 때문에 예외를 내지 않는다(문제는 `problem`).

    Args:
        raw: 사용자 입력.
        fs: 파일 시스템.
        environ: `~` 펼치기용 환경변수.
        defaults: 숨김 이름 등 탐색 기본값(기본: 패키지 데이터).
        roots: 주면 이 폴더들 아래만 허용(밖이면 `problem="outside_roots"`).

    등록 겹침·같은 경로(`exclude_project_id`)는 등록부를 아는 쪽이 `path`로 판단한다.
    느린 마운트에서 멈출 수 있으므로 서버는 스레드 + 시간 상한으로 부른다.
    """
    try:
        lexical = normalize_lexical(raw, flavor=fs.flavor, environ=environ)
    except FolderError as exc:
        return FolderCheck(input=raw, path=None, problem=exc.code)
    real = _real(fs, lexical, environ)
    pm = path_module(fs.flavor)
    nearest = nearest_existing(real, fs=fs)
    try:
        _check_roots(fs, real, roots)
    except FolderError as exc:
        return FolderCheck(input=raw, path=real, problem=exc.code, nearest_existing=nearest)
    info, denied = _info(fs, lexical)
    link = path_key(real, fs.flavor) != path_key(lexical, fs.flavor) or bool(
        info is not None and info.is_link
    )
    name = pm.basename(real)
    hidden = bool(name) and _is_hidden(
        name, bool(info is not None and info.hidden_attr), _defaults(defaults)
    )
    if info is None and not denied:
        parent = pm.dirname(real)
        pinfo, _ = _info(fs, parent) if parent != real else (None, True)
        can_create = bool(pinfo is not None and pinfo.is_dir and pinfo.writable and pinfo.readable)
        return FolderCheck(
            input=raw,
            path=real,
            can_create=can_create,
            hidden=hidden,
            link=link,
            nearest_existing=nearest,
        )
    return FolderCheck(
        input=raw,
        path=real,
        exists=True,
        is_dir=bool(info is not None and info.is_dir),
        readable=bool(info is not None and info.readable),
        writable=bool(info is not None and info.writable),
        hidden=hidden,
        link=link,
        nearest_existing=nearest,
    )


def list_dirs(
    path: str,
    *,
    fs: FileSystem,
    environ: Mapping[str, str] = _NO_ENV,
    show_hidden: bool = False,
    limit: int = DEFAULT_LIST_LIMIT,
    timeout: float | None = DEFAULT_LIST_TIMEOUT,
    roots: Sequence[str] | None = None,
    defaults: BrowseDefaults | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FolderListing:
    """하위 **폴더 이름만** 나열(파일은 빼고, 내용은 읽지 않음).

    Args:
        path: 폴더 경로(입력 그대로 받아 정규화).
        fs: 파일 시스템.
        environ: `~` 펼치기용.
        show_hidden: 숨김 폴더(점·숨김 속성·`hidden_names`)도 보일지. 기본 숨김.
        limit: 최대 항목 수. 넘으면 `truncated`.
        timeout: 읽기 시간 상한(초, `None`이면 없음). 넘으면 거기까지 + `truncated`·`timed_out`.
            항목 사이에서만 확인하므로 OS 호출 하나가 멈추면 서버가 스레드로 감싸 끊는다.
        roots: 주면 이 폴더들 아래만 허용(탐색 범위 제한, 링크를 푼 실제 경로로 판단).
        defaults: 숨김 이름 등(기본: 패키지 데이터).
        clock: 시간 함수(테스트 주입).

    Raises:
        FolderError: `not_found`·`not_directory`·`no_access`·`outside_roots`·`io_error`와
            경로 입력 오류.
    """
    if limit < 0:
        raise ValueError("limit은 0 이상이어야 합니다")
    lexical = normalize_lexical(path, flavor=fs.flavor, environ=environ)
    pm = path_module(fs.flavor)
    real_roots: list[str] | None = None
    if roots is not None:
        real_roots = [normalize(r, fs=fs, environ=environ) for r in roots]
        _check_roots(fs, _real(fs, lexical, environ), real_roots)
    info, denied = _info(fs, lexical)
    if denied or (info is not None and info.is_dir and not info.readable):
        raise FolderError(FolderErrorCode.NO_ACCESS, "이 폴더를 읽을 수 없습니다.", path=lexical)
    if info is None:
        raise FolderError(FolderErrorCode.NOT_FOUND, "폴더가 없습니다.", path=lexical)
    if not info.is_dir:
        raise FolderError(FolderErrorCode.NOT_DIRECTORY, "폴더가 아닙니다.", path=lexical)
    found = _defaults(defaults)
    entries: list[FolderEntry] = []
    truncated = timed_out = False
    hidden_count = 0
    start = clock()
    iterator: Iterator[ScanEntry] | None = None
    try:
        iterator = iter(fs.scan(lexical))
        for item in iterator:
            if timeout is not None and clock() - start > timeout:
                truncated = timed_out = True
                break
            if not item.is_dir:
                continue
            hidden = _is_hidden(item.name, item.hidden_attr, found)
            if hidden and not show_hidden:
                hidden_count += 1
                continue
            if len(entries) >= limit:
                truncated = True
                break
            child = pm.join(lexical, item.name)
            cinfo, cdenied = _info(fs, child)
            locked = cdenied or cinfo is None or not cinfo.readable
            entries.append(
                FolderEntry(
                    name=item.name, path=child, hidden=hidden, link=item.is_link, locked=locked
                )
            )
    except PermissionError as exc:
        raise FolderError(
            FolderErrorCode.NO_ACCESS, "이 폴더를 읽을 수 없습니다.", path=lexical
        ) from exc
    except FileNotFoundError as exc:
        raise FolderError(FolderErrorCode.NOT_FOUND, "폴더가 없습니다.", path=lexical) from exc
    except NotADirectoryError as exc:
        raise FolderError(FolderErrorCode.NOT_DIRECTORY, "폴더가 아닙니다.", path=lexical) from exc
    except OSError as exc:
        raise FolderError(
            FolderErrorCode.IO_ERROR, "폴더 목록을 읽지 못했습니다.", path=lexical
        ) from exc
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            close()
    entries.sort(key=lambda e: (e.name.casefold(), e.name))
    parent: str | None = pm.dirname(lexical)
    if parent == lexical or (
        real_roots is not None
        and parent is not None
        and not is_within(_real(fs, parent, environ), real_roots, fs.flavor)
    ):
        parent = None
    return FolderListing(
        path=lexical,
        parent=parent,
        entries=tuple(entries),
        truncated=truncated,
        timed_out=timed_out,
        hidden_count=hidden_count,
    )


def make_folder(
    path: str,
    *,
    fs: FileSystem,
    name: str | None = None,
    environ: Mapping[str, str] = _NO_ENV,
    roots: Sequence[str] | None = None,
    defaults: BrowseDefaults | None = None,
) -> FolderCheck:
    """폴더 하나 만들기(상위는 만들지 않음). 사용자가 누를 때만 부른다.

    Args:
        path: 만들 경로, 또는 `name`을 주면 그 상위 폴더.
        fs: 파일 시스템.
        name: 새 폴더 이름(찾아보기의 [새 폴더]). `validate_folder_name`으로 검사.
        environ: `~` 펼치기용.
        roots: 주면 이 폴더들 아래만 허용.
        defaults: 결과 확인의 숨김 이름.

    Returns:
        만든 폴더의 `check_folder` 결과.

    Raises:
        FolderError: `invalid_name`·`exists`·`missing_parent`·`no_access`·`outside_roots`·
            `io_error`와 경로 입력 오류.
    """
    pm = path_module(fs.flavor)
    base = normalize_lexical(path, flavor=fs.flavor, environ=environ)
    target = pm.join(base, validate_folder_name(name, fs.flavor)) if name is not None else base
    real = _real(fs, target, environ)
    if roots is not None:
        _check_roots(fs, real, [normalize(r, fs=fs, environ=environ) for r in roots])
    parent = pm.dirname(real)
    if parent == real:
        raise FolderError(FolderErrorCode.EXISTS, "이미 있는 폴더입니다.", path=real)
    pinfo, pdenied = _info(fs, parent)
    if pdenied:
        raise FolderError(FolderErrorCode.NO_ACCESS, "상위 폴더에 쓸 수 없습니다.", path=parent)
    if pinfo is None or not pinfo.is_dir:
        raise FolderError(
            FolderErrorCode.MISSING_PARENT, "상위 폴더가 없어 만들 수 없습니다.", path=parent
        )
    if not (pinfo.writable and pinfo.readable):
        raise FolderError(FolderErrorCode.NO_ACCESS, "상위 폴더에 쓸 수 없습니다.", path=parent)
    tinfo, tdenied = _info(fs, real)
    if tinfo is not None or tdenied:
        raise FolderError(FolderErrorCode.EXISTS, "이미 있는 이름입니다.", path=real)
    try:
        fs.mkdir(real)
    except FileExistsError as exc:
        raise FolderError(FolderErrorCode.EXISTS, "이미 있는 이름입니다.", path=real) from exc
    except FileNotFoundError as exc:
        raise FolderError(
            FolderErrorCode.MISSING_PARENT, "상위 폴더가 없어 만들 수 없습니다.", path=parent
        ) from exc
    except PermissionError as exc:
        raise FolderError(
            FolderErrorCode.NO_ACCESS, "상위 폴더에 쓸 수 없습니다.", path=parent
        ) from exc
    except OSError as exc:
        raise FolderError(FolderErrorCode.IO_ERROR, "폴더를 만들지 못했습니다.", path=real) from exc
    return check_folder(real, fs=fs, environ=environ, defaults=defaults)


def default_roots(
    environ: Mapping[str, str],
    *,
    fs: FileSystem,
    defaults: BrowseDefaults | None = None,
) -> tuple[FolderRoot, ...]:
    """기본 탐색 시작 위치(홈 + 루트·마운트·드라이브, 규칙 = `browse_defaults` 데이터).

    있는 폴더만, 같은 경로는 한 번. 설치자 설정(`mod-projects.browse_roots`)이 있으면 서버가
    그것을 대신 쓴다.
    """
    pm = path_module(fs.flavor)
    out: list[FolderRoot] = []
    seen: set[str] = set()

    def add(kind: str, raw: str, label: str, fields: Mapping[str, str]) -> None:
        try:
            path = normalize_lexical(raw, flavor=fs.flavor, environ=environ)
        except FolderError:
            return
        key = path_key(path, fs.flavor)
        if key in seen:
            return
        info, _ = _info(fs, path)
        if info is None or not info.is_dir:
            return
        seen.add(key)
        try:
            text = label.format(path=path, **fields)
        except (KeyError, IndexError, ValueError):
            text = path
        out.append(FolderRoot(kind=kind, path=path, label=text))

    for rule in _defaults(defaults).roots.get(fs.flavor, ()):
        if rule.path is not None:
            for item in rule.each or [""]:
                fields = {"item": item, "name": item, "NAME": item.upper()}
                try:
                    raw = rule.path.format(**fields)
                except (KeyError, IndexError, ValueError):
                    continue
                add(rule.kind, raw, rule.label, fields)
            continue
        parent = rule.parent or ""
        try:
            items = sorted(
                (e.name for e in fs.scan(parent) if e.is_dir), key=lambda n: (n.casefold(), n)
            )
        except OSError:
            continue
        for name in items:
            if rule.name_pattern is not None and not rule.name_pattern.search(name):
                continue
            fields = {"item": name, "name": name, "NAME": name.upper()}
            add(rule.kind, pm.join(parent, name), rule.label, fields)
    return tuple(out)
