"""실행 묶음의 파일을 실행 폴더에 쓰고 경로로 바꾼다(design §R12.4, §2R.8).

리소스 종류(`file`)는 칸에 본문을 싣고 파일을 쓰지 않는다. 백엔드도 파일을 쓰지 않는다. 노드가
`<루트>/<run id>/<node id>/`에 쓰고, 칸 항목을 `{path, root, name, media_type?}`로 바꿔 넘긴다.

**항목 파일 트리**(`write_item_trees`): 파일 칸이 아닌 칸의 항목이 `files: [{name, content, …}]`를
가지면(예: skill = SKILL.md + 부속 파일, 규칙 파일) 그 파일들을 `<트리 폴더>/<칸>/<항목 name>/`에
쓰고 항목을 `{…항목, root, tree_root, files: [{name, path, media_type?}]}`로 바꾼다. 칸 이름은
모른다 — 모양(`files` 목록)만 본다.

안전 규칙:
    - 항목 이름은 폴더 기준 상대 경로여야 한다(절대 경로·`..`·드라이브·역슬래시·제어 문자 거부).
    - 부모 폴더는 한 칸씩 확인하며 만든다: 칸마다 링크가 아니고 실제 경로가 폴더 안일 때만 다음 칸.
      검사를 통과하지 못하면 아무 폴더도 밖에 만들지 않는다.
    - 쓰기 직전 실제 경로(`resolve`)가 폴더 안인지 다시 확인한다.
    - 경로 중간·끝에 심볼릭 링크가 있으면 쓰지 않는다(끝은 `O_NOFOLLOW`로도 막는다).
    - 이미 경로만 있는 항목(`{path, root?}`)은 `path`·`root`가 이 폴더 안일 때만 넘긴다(백엔드가
      그 폴더를 에이전트 접근 폴더로 열기 때문).
    - 본문 값은 이슈·로그에 넣지 않는다.
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from agent_console_contracts import Issue, ResourceBundle

from ._common import NodesCoreErrorCodes

__all__ = [
    "DEFAULT_FILES_SLOT",
    "ITEM_FILES_KEY",
    "ITEM_TREES_DIR",
    "run_folder",
    "safe_part",
    "safe_relative_name",
    "write_files",
    "write_item_trees",
]

ITEM_FILES_KEY: Final = "files"
"""항목 파일 트리로 볼 항목 키(`write_item_trees`)."""

ITEM_TREES_DIR: Final = "_bundle"
"""agent 노드가 실행 폴더 안에서 항목 트리에 쓰는 폴더 이름. 파일 칸 이름의 첫 칸으로는 쓸 수
없다(`write_files(reserved=)`). 노드는 그 아래 `<node id>/`를 트리 폴더로 쓴다(백엔드가 이 폴더를
플러그인 폴더 등으로 넘길 때 이름이 노드마다 다르게)."""

DEFAULT_FILES_SLOT: Final = "files"
"""파일 항목이 든 묶음 칸 이름(알려진 칸 `KnownResourceSlots.FILES`와 같다)."""

_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)
_BINARY: Final = getattr(os, "O_BINARY", 0)


def _has_control(text: str) -> bool:
    return any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in text)


def safe_part(name: str) -> bool:
    """폴더 이름 한 칸으로 쓸 수 있으면 참(구분자·`..`·`.`·드라이브·제어 문자 없음)."""
    return (
        bool(name)
        and name not in (".", "..")
        and not any(ch in name for ch in "/\\:")
        and not _has_control(name)
    )


def safe_relative_name(name: str) -> bool:
    """상대 경로이고 `..`·`.`·빈 칸·드라이브·역슬래시·제어 문자가 없으면 참."""
    if not name or "\\" in name or ":" in name or name.startswith("/") or _has_control(name):
        return False
    return all(part not in ("..", ".", "") for part in name.split("/"))


def run_folder(root: str | os.PathLike[str], run_id: str, node_id: str) -> Path | None:
    """`<root>/<run_id>/<node_id>` 경로. id가 폴더 이름으로 안전하지 않으면 None(만들지 않는다)."""
    if not safe_part(run_id) or not safe_part(node_id):
        return None
    return Path(root) / run_id / node_id


def _issue(code: str, message: str, **details: Any) -> Issue:
    return Issue(severity="warning", code=code, message=message, details=details)


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
    except ValueError:
        return False
    return True


def _safe_parents(folder: Path, target: Path) -> bool:
    """`folder`(실제 경로) 아래 `target`의 부모 폴더를 한 칸씩 확인하며 만든다.

    칸마다 심볼릭 링크가 아니고 실제 경로가 `folder` 안인지 확인한 뒤에만 다음 칸으로 간다.
    없는 칸은 그 확인을 통과한 부모 안에서만 만든다(링크를 따라 밖에 폴더를 만들지 않는다).
    끝 칸(파일)이 링크이거나 밖을 가리키면 거짓.
    """
    current = folder
    parts = target.relative_to(folder).parts
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            return False
        if not current.exists():
            current.mkdir()
        if current.is_symlink() or not current.is_dir():
            return False
        if not _inside(current.resolve(), folder):
            return False
    if target.is_symlink():
        return False
    return _inside(target.resolve(), folder)


def _path_item_inside(item: Mapping[str, Any], folder: Path) -> bool:
    """경로 항목(`{path, root?}`)의 `path`와 `root`가 모두 `folder` 안(링크 해석 후)이면 참."""
    for key in ("path", "root"):
        value = item.get(key)
        if value is None and key == "root":
            continue
        if not isinstance(value, str) or not value:
            return False
        try:
            if not _inside(Path(value).resolve(), folder):
                return False
        except OSError:
            return False
    return True


def _decode(item: Mapping[str, Any]) -> bytes | None:
    content = item.get("content")
    if not isinstance(content, str):
        return None
    if item.get("encoding") == "base64":
        try:
            return base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError):
            return None
    return content.encode("utf-8")


def _write(target: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _NOFOLLOW | _BINARY
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def write_files(
    bundle: ResourceBundle,
    folder: str | os.PathLike[str],
    *,
    slot: str = DEFAULT_FILES_SLOT,
    reserved: Collection[str] = (),
) -> tuple[ResourceBundle, list[Issue]]:
    """묶음의 `slot` 칸 본문 항목(`{name, content, encoding?, media_type?}`)을 `folder`에 쓴다.

    이미 경로만 있는 항목(`content` 없음)은 그대로 둔다. 쓸 수 없는 항목은 칸에서 빼고 경고한다.

    Args:
        bundle: 실행 묶음. 바꾸지 않는다.
        folder: 쓸 폴더(없으면 만든다). 보통 `run_folder(...)`.
        slot: 파일 칸 이름.
        reserved: 첫 경로 칸으로 쓸 수 없는 이름(다른 용도로 비워 둔 폴더, 예: 항목 트리 폴더).

    Returns:
        `(새 묶음, 이슈)`. 쓴 항목은 `{path, root, name, media_type?}`가 된다(`path`는 절대 경로).
        칸이 없거나 비어 있으면 묶음을 그대로 돌려준다.
    """
    items = bundle.slots.get(slot)
    if not isinstance(items, Sequence) or isinstance(items, str) or not items:
        return bundle, []
    base = Path(folder)
    issues: list[Issue] = []
    written: list[Any] = []
    try:
        base.mkdir(parents=True, exist_ok=True)
        if base.is_symlink():
            raise OSError("실행 폴더가 심볼릭 링크입니다")
        real = base.resolve(strict=True)
    except OSError as exc:
        issue = _issue(
            NodesCoreErrorCodes.FILES_WRITE_FAILED,
            "실행 폴더를 만들 수 없어 파일을 전달하지 않습니다",
            slot=slot,
            error=type(exc).__name__,
        )
        return bundle.model_copy(update={"slots": {**bundle.slots, slot: []}}), [issue]
    for index, item in enumerate(items):
        if isinstance(item, Mapping) and "content" not in item and item.get("path"):
            # 이미 경로인 항목(다른 플러그인이 만든 것)도 이 실행 폴더 안일 때만 넘긴다.
            # 백엔드는 이 경로·폴더를 에이전트 접근 폴더(add_dirs)로 쓰기 때문이다.
            if _path_item_inside(item, real):
                written.append(dict(item))
            else:
                issues.append(
                    _issue(
                        NodesCoreErrorCodes.FILES_UNSAFE_PATH,
                        "파일 경로가 실행 폴더 밖이라 전달하지 않습니다",
                        slot=slot,
                        index=index,
                    )
                )
            continue
        name = item.get("name") if isinstance(item, Mapping) else None
        if not isinstance(item, Mapping) or not isinstance(name, str):
            issues.append(
                _issue(
                    NodesCoreErrorCodes.FILES_INVALID_ITEM,
                    "파일 항목 형식이 맞지 않아 전달하지 않습니다",
                    slot=slot,
                    index=index,
                )
            )
            continue
        if not safe_relative_name(name) or name.split("/", 1)[0] in reserved:
            issues.append(
                _issue(
                    NodesCoreErrorCodes.FILES_UNSAFE_PATH,
                    "파일 이름이 실행 폴더 밖이나 예약된 폴더를 가리켜 쓰지 않습니다",
                    slot=slot,
                    index=index,
                )
            )
            continue
        data = _decode(item)
        if data is None:
            issues.append(
                _issue(
                    NodesCoreErrorCodes.FILES_INVALID_ITEM,
                    "파일 본문을 읽을 수 없어 전달하지 않습니다",
                    slot=slot,
                    index=index,
                    name=name,
                )
            )
            continue
        target = real / name
        try:
            if not _safe_parents(real, target):
                issues.append(
                    _issue(
                        NodesCoreErrorCodes.FILES_UNSAFE_PATH,
                        "파일 경로에 심볼릭 링크가 있거나 실행 폴더 밖이라 쓰지 않습니다",
                        slot=slot,
                        index=index,
                        name=name,
                    )
                )
                continue
            _write(target, data)
        except OSError as exc:
            issues.append(
                _issue(
                    NodesCoreErrorCodes.FILES_WRITE_FAILED,
                    "파일을 쓰지 못해 전달하지 않습니다",
                    slot=slot,
                    index=index,
                    name=name,
                    error=type(exc).__name__,
                )
            )
            continue
        entry: dict[str, Any] = {"path": str(target), "root": str(real), "name": name}
        media_type = item.get("media_type")
        if isinstance(media_type, str) and media_type:
            entry["media_type"] = media_type
        written.append(entry)
    return bundle.model_copy(update={"slots": {**bundle.slots, slot: written}}), issues


def _tree_item(
    item: Mapping[str, Any], slot: str, index: int, base: Path
) -> tuple[Any, list[Issue]]:
    """항목 하나의 `files`를 `<base>/<slot>/<name>/`에 쓴다. 쓸 수 없으면 (원래 항목에서 files를
    뺀 사본, 이슈)."""
    name = item.get("name")
    if not isinstance(name, str) or not safe_part(name) or not safe_part(slot):
        stripped = {k: v for k, v in item.items() if k != ITEM_FILES_KEY}
        issue = _issue(
            NodesCoreErrorCodes.FILES_UNSAFE_PATH,
            "항목 이름을 폴더 이름으로 쓸 수 없어 파일을 전달하지 않습니다",
            slot=slot,
            index=index,
        )
        return stripped, [issue]
    folder = base / slot / name
    entries = ResourceBundle(slots={DEFAULT_FILES_SLOT: list(item[ITEM_FILES_KEY])})
    written, issues = write_files(entries, folder)
    relabeled = [
        i.model_copy(update={"details": {**i.details, "slot": slot, "item": index}}) for i in issues
    ]
    files: list[dict[str, Any]] = []
    for entry in written.slots.get(DEFAULT_FILES_SLOT, []):
        if isinstance(entry, Mapping) and "path" in entry:
            files.append({k: v for k, v in entry.items() if k != "root"})
    out = dict(item)
    out[ITEM_FILES_KEY] = files
    out["root"] = str(folder.resolve()) if folder.exists() else str(folder)
    out["tree_root"] = str(base.resolve()) if base.exists() else str(base)
    return out, relabeled


def _has_tree(item: Any) -> bool:
    if not isinstance(item, Mapping):
        return False
    files = item.get(ITEM_FILES_KEY)
    return (
        isinstance(files, Sequence)
        and not isinstance(files, str)
        and any(isinstance(f, Mapping) and "content" in f for f in files)
    )


def write_item_trees(
    bundle: ResourceBundle,
    folder: str | os.PathLike[str],
    *,
    skip: Collection[str] = (DEFAULT_FILES_SLOT,),
) -> tuple[ResourceBundle, list[Issue]]:
    """`skip` 밖 칸 항목 중 `files`(본문 항목 목록)를 가진 것을 `<folder>/<칸>/<name>/`에 쓴다.

    파일 하나하나의 안전 규칙은 `write_files`와 같다(상대 경로만, 링크 거부, 폴더 밖 거부).
    칸·항목 이름은 폴더 이름 한 칸으로 안전해야 한다(`safe_part`). 쓴 항목은
    `{…항목, root: <항목 폴더>, tree_root: <folder>, files: [{name, path, media_type?}]}`가 된다.

    Args:
        bundle: 실행 묶음. 바꾸지 않는다.
        folder: 트리 폴더(없으면 만든다). 같은 Run·노드 안에서 다른 파일과 섞이지 않는 폴더를 준다.
        skip: 다루지 않을 칸(기본: 파일 칸 — `write_files`가 따로 쓴다).

    Returns:
        `(새 묶음, 이슈)`. 트리 항목이 없으면 묶음을 그대로 돌려준다.
    """
    targets = [
        slot
        for slot, value in bundle.slots.items()
        if slot not in skip
        and isinstance(value, Sequence)
        and not isinstance(value, str)
        and any(_has_tree(item) for item in value)
    ]
    if not targets:
        return bundle, []
    base = Path(folder)
    issues: list[Issue] = []
    slots = dict(bundle.slots)
    for slot in targets:
        items: list[Any] = []
        for index, item in enumerate(bundle.slots[slot]):
            if not _has_tree(item):
                items.append(item)
                continue
            written, found = _tree_item(item, slot, index, base)
            items.append(written)
            issues.extend(found)
        slots[slot] = items
    return bundle.model_copy(update={"slots": slots}), issues
