"""메모리 파일 시스템(테스트·예제용 `FileSystem` 구현). 디스크에 닿지 않는다."""

from __future__ import annotations

import errno
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from ._paths import path_key, path_module
from ._types import PathFlavor, PathInfo, ScanEntry

__all__ = ["MemoryFileSystem"]

_MAX_LINKS = 40


@dataclass
class _Node:
    path: str
    kind: Literal["dir", "file", "link"]
    target: str | None = None
    hidden: bool = False
    readable: bool = True
    writable: bool = True


class MemoryFileSystem:
    """경로 방식(`posix`/`windows`)을 고를 수 있는 가짜 파일 시스템.

    호스트 OS와 무관하게 Windows 경로·숨김 속성·링크·권한 없음을 흉내 낸다. 경로는 정규화한
    절대 경로로 넣는다. 없는 상위 폴더는 자동으로 만든다. `windows`는 대소문자를 무시한다.

    >>> fs = MemoryFileSystem().add_dir("/w/app").add_file("/w/notes.txt")
    >>> [e.name for e in fs.scan("/w")]
    ['app', 'notes.txt']
    """

    def __init__(self, flavor: PathFlavor = "posix") -> None:
        self._flavor: PathFlavor = flavor
        self._nodes: dict[str, _Node] = {}
        self._children: dict[str, list[str]] = {}
        self.scan_calls: list[str] = []
        """`scan`을 부른 경로(테스트 단언용)."""
        self.mkdir_calls: list[str] = []
        """`mkdir`로 만든 경로(테스트 단언용)."""
        if flavor == "posix":
            self._nodes["/"] = _Node("/", "dir")

    @property
    def flavor(self) -> PathFlavor:
        """경로 방식."""
        return self._flavor

    # ------------------------------------------------------------------ 만들기
    def _key(self, path: str) -> str:
        return path_key(path, self._flavor)

    def _put(self, node: _Node) -> None:
        pm = path_module(self._flavor)
        key = self._key(node.path)
        parent = pm.dirname(node.path)
        if parent != node.path:
            if self._key(parent) not in self._nodes:
                self._put(_Node(parent, "dir"))
            siblings = self._children.setdefault(self._key(parent), [])
            if key not in siblings:
                siblings.append(key)
        self._nodes[key] = node

    def add_dir(
        self, path: str, *, hidden: bool = False, readable: bool = True, writable: bool = True
    ) -> MemoryFileSystem:
        """폴더 추가(`hidden` = OS 숨김 속성). 자기 자신을 돌려준다(이어 쓰기)."""
        self._put(_Node(path, "dir", hidden=hidden, readable=readable, writable=writable))
        return self

    def add_file(self, path: str) -> MemoryFileSystem:
        """파일 추가."""
        self._put(_Node(path, "file"))
        return self

    def add_link(self, path: str, target: str) -> MemoryFileSystem:
        """심볼릭 링크 추가(`target`은 절대 경로)."""
        self._put(_Node(path, "link", target=target))
        return self

    # ------------------------------------------------------------------ 풀기
    def _resolve(self, path: str, depth: int = 0) -> str:
        if depth > _MAX_LINKS:
            raise OSError(errno.ELOOP, "too many links", path)
        pm = path_module(self._flavor)
        parts: list[str] = []
        cur = path
        while True:
            parent = pm.dirname(cur)
            if parent == cur:
                break
            parts.append(pm.basename(cur))
            cur = parent
        resolved = cur
        for part in reversed(parts):
            nxt = pm.join(resolved, part)
            node = self._nodes.get(self._key(nxt))
            if node is not None and node.kind == "link" and node.target is not None:
                nxt = self._resolve(node.target, depth + 1)
            elif node is not None:
                nxt = node.path  # 저장된 표기(Windows 대소문자)
            resolved = nxt
        return resolved

    def _guard_ancestors(self, resolved: str) -> None:
        pm = path_module(self._flavor)
        cur = pm.dirname(resolved)
        while True:
            node = self._nodes.get(self._key(cur))
            if node is not None and node.kind == "dir" and not node.readable:
                raise PermissionError(errno.EACCES, "permission denied", resolved)
            parent = pm.dirname(cur)
            if parent == cur:
                return
            cur = parent

    def _lookup(self, path: str) -> _Node | None:
        resolved = self._resolve(path)
        self._guard_ancestors(resolved)
        return self._nodes.get(self._key(resolved))

    # ------------------------------------------------------------------ FileSystem
    def info(self, path: str) -> PathInfo | None:
        """경로 상태(링크를 따라감). 읽을 수 없는 상위 폴더 아래면 `PermissionError`."""
        node = self._lookup(path)
        if node is None:
            return None
        own = self._nodes.get(self._key(path))
        return PathInfo(
            is_dir=node.kind == "dir",
            is_link=own is not None and own.kind == "link",
            hidden_attr=node.hidden,
            readable=node.readable,
            writable=node.writable,
        )

    def scan(self, path: str) -> Iterator[ScanEntry]:
        """바로 아래 항목(넣은 순서)."""
        self.scan_calls.append(path)
        node = self._lookup(path)
        if node is None:
            raise FileNotFoundError(errno.ENOENT, "not found", path)
        if node.kind != "dir":
            raise NotADirectoryError(errno.ENOTDIR, "not a directory", path)
        if not node.readable:
            raise PermissionError(errno.EACCES, "permission denied", path)
        pm = path_module(self._flavor)
        for key in list(self._children.get(self._key(node.path), [])):
            child = self._nodes[key]
            try:
                target = self._lookup(child.path)
            except OSError:
                target = None
            yield ScanEntry(
                name=pm.basename(child.path),
                is_dir=target is not None and target.kind == "dir",
                is_link=child.kind == "link",
                hidden_attr=child.hidden,
            )

    def realpath(self, path: str) -> str:
        """링크를 푼 경로(저장된 표기)."""
        resolved = self._resolve(path)
        node = self._nodes.get(self._key(resolved))
        return node.path if node is not None else resolved

    def mkdir(self, path: str) -> None:
        """폴더 하나 만들기."""
        pm = path_module(self._flavor)
        resolved = self._resolve(path)
        if self._key(resolved) in self._nodes:
            raise FileExistsError(errno.EEXIST, "exists", path)
        parent = self._lookup(pm.dirname(resolved))
        if parent is None or parent.kind != "dir":
            raise FileNotFoundError(errno.ENOENT, "no parent", path)
        if not parent.writable:
            raise PermissionError(errno.EACCES, "permission denied", path)
        self._put(_Node(resolved, "dir"))
        self.mkdir_calls.append(resolved)
