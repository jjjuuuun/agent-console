"""열린 프로젝트 공간 캐시(``projects.spaces``·``definitions.spaces``, design §PI.10).

공간 하나 = 등록 폴더의 ``<config_dir>/``(``ac-project-space.open_space``). 여는 것은 쓰기가 없고
파일 핸들도 잡지 않지만, 정의 저장소의 버전 기록소(주입이 없으면 메모리)를 공간과 함께 들고 있으므로
캐시한다. 상한(최근에 쓴 것부터 남김)과 유휴 시간이 지나면 뺀다(시간은 다음 접근 때 본다 — 타이머
스레드 없음). 폴더가 바뀌거나(경로 다시 지정) 종류·구성 폴더 이름이 바뀌면 새로 연다.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_console_project_space import (
    DEFAULT_CONFIG_DIR,
    FolderMissing,
    ProjectSpace,
    open_space,
)
from agent_console_store import DefinitionStore, VersionRepository

type FolderResolver = Callable[[str], str | None]
"""등록 id → 정규화한 폴더(지정 안 됨 = None). 모르는 id는 ``LookupError``."""
type OptionsFactory = Callable[[], Mapping[str, Any]]
"""지금 공간 옵션(``SpaceOptions``: kinds·config_dir·layout·secret_rules 등)."""
type VersionsFactory = Callable[[str, Path], VersionRepository | None]
"""(등록 id, 공간 root) → 그 공간의 버전 기록소. None이면 메모리(공간 캐시와 수명이 같음)."""


@dataclass
class _Entry:
    key: tuple[Any, ...]
    space: ProjectSpace
    used: float


class ProjectSpaceCache:
    """``projects.spaces`` 구현(스레드 안전).

    Args:
        resolve: 등록 id → 폴더.
        options: 지금 공간 옵션.
        max_open: 캐시 상한.
        idle_seconds: 이 시간 동안 안 쓴 공간은 다음 접근 때 다시 연다(0 = 무제한).
        versions: 공간별 버전 기록소 공장(기록 DB 연결용, 33x). 없으면 메모리.
        clock: 단조 시각.
    """

    def __init__(
        self,
        resolve: FolderResolver,
        *,
        options: OptionsFactory,
        max_open: int = 8,
        idle_seconds: float = 300.0,
        versions: VersionsFactory | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._resolve = resolve
        self._options = options
        self._max_open = max(1, max_open)
        self._idle = idle_seconds
        self._versions = versions
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, _Entry] = OrderedDict()

    def open(self, project_id: str) -> ProjectSpace:
        """등록 id의 공간(캐시). 아무것도 만들거나 쓰지 않는다.

        Raises:
            LookupError: 모르는 프로젝트.
            FolderMissing: 폴더가 지정되지 않았거나 없다.
            SpaceError: 그 밖에 열 수 없다.
        """
        folder = self._resolve(project_id)
        if folder is None:
            raise FolderMissing(f"project {project_id} has no folder")
        options = dict(self._options())
        kinds = tuple(getattr(k, "name", k) for k in options.get("kinds", ()))
        key = (folder, options.get("config_dir"), kinds, id(options.get("layout")))
        now = self._clock()
        with self._lock:
            self._expire(now)
            entry = self._entries.get(project_id)
            if entry is not None and entry.key == key:
                if not Path(folder).is_dir():
                    self._entries.pop(project_id, None)
                    raise FolderMissing(f"project folder is missing: {Path(folder).name}")
                entry.used = now
                self._entries.move_to_end(project_id)
                return entry.space
        if self._versions is not None:
            root = Path(folder) / str(options.get("config_dir", DEFAULT_CONFIG_DIR))
            repo = self._versions(project_id, root)
            if repo is not None:
                options["versions"] = repo
        space = open_space(folder, **options)
        with self._lock:
            self._entries[project_id] = _Entry(key, space, now)
            self._entries.move_to_end(project_id)
            while len(self._entries) > self._max_open:
                self._entries.popitem(last=False)
        return space

    def close(self, project_id: str) -> None:
        """캐시에서 뺀다."""
        with self._lock:
            self._entries.pop(project_id, None)

    def clear(self) -> None:
        """캐시를 비운다."""
        with self._lock:
            self._entries.clear()

    def open_ids(self) -> list[str]:
        """지금 캐시에 있는 등록 id(오래된 순)."""
        with self._lock:
            return list(self._entries)

    def _expire(self, now: float) -> None:
        if self._idle <= 0:
            return
        stale = [k for k, e in self._entries.items() if now - e.used > self._idle]
        for k in stale:
            self._entries.pop(k, None)


class DefinitionSpacesView:
    """``definitions.spaces`` 구현: 공간 캐시 위의 정의 저장소 보기."""

    def __init__(self, spaces: ProjectSpaceCache) -> None:
        self._spaces = spaces

    def open(self, project_id: str) -> DefinitionStore:
        """그 프로젝트 공간의 정의 저장소. 예외는 ``ProjectSpaceCache.open``과 같다."""
        return self._spaces.open(project_id).definitions


__all__ = [
    "DefinitionSpacesView",
    "FolderResolver",
    "OptionsFactory",
    "ProjectSpaceCache",
    "VersionsFactory",
]
