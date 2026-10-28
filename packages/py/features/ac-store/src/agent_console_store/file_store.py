"""파일 기반 정의 저장소: YAML 파일이 진실의 원천이다(design §2.1, §10-6)."""

import os
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .content_path import check_content_path, resolve_inside
from .definition_store import DEFAULT_MAX_CONTENT_BYTES, BaseDefinitionStore, WriteGuard
from .errors import DefinitionCorrupt, InvalidContentPath
from .hashing import HashFn, default_hash
from .interfaces import VersionRepository
from .kinds import DEFAULT_KINDS, DefinitionKind
from .yaml_io import (
    atomic_write_bytes,
    atomic_write_text,
    dump_yaml,
    load_yaml_file,
    merge_into,
    to_plain,
    wrap_value,
)


class FileDefinitionStore(BaseDefinitionStore):
    """`<root>/<kind.directory>/<id>.yaml`(싱글턴은 `<root>/<singleton_file>`)에 저장한다.

    - 쓰기는 임시 파일 + `os.replace`(원자적). 기존 파일이 있으면 주석·키 순서를 보존하며 갱신.
    - 모르는 필드는 그대로 보존된다(손으로 추가한 키도 왕복).
    - 저장마다 `versions`에 스냅샷을 남긴다. SQLite 이력을 쓰려면 `SqliteStorage.versions`를 넘긴다.
      생략하면 메모리 이력이다.
    - 본문 파일(`DefinitionKind.content_field`)은 `<root>/<directory>/<id>/<file>`에 원자적으로
      쓴다. 경로가 그 폴더 밖(`..`, 절대 경로)이거나 workspace root부터 대상까지 심볼릭 링크·
      정션이 하나라도 끼어 있으면 거부한다. `multi_file` 종류는 그 폴더의 모든 파일이 본문이다.
    - 파일이 밖에서 바뀌어도 다음 조회 때 현재 해시를 계산하고 스냅샷을 남긴다.

    Args:
        root: 워크스페이스 폴더(경로는 인자로만 받는다).
        kinds: 다룰 정의 종류. 기본은 graph, agent, settings.
        versions: 버전 이력 저장소.
        hash_fn: 기본 버전 해시 함수(종류별 `hash_fn`이 우선).
        clock: 현재 시각(epoch 초) 공급자.
        max_content_bytes: 정의 하나의 본문 총량 한도(None = 무제한). 넘으면 `ContentTooLarge`.
        max_versions: 정의마다 남길 버전 수(None = 모두). 현재 버전은 항상 남는다.
        write_guard: 쓰기 전 검사 훅(`WriteGuard`). 예외를 던지면 쓰지 않는다.
    """

    def __init__(
        self,
        root: str | Path,
        kinds: Iterable[DefinitionKind] = DEFAULT_KINDS,
        *,
        versions: VersionRepository | None = None,
        hash_fn: HashFn = default_hash,
        clock: Callable[[], float] = time.time,
        max_content_bytes: int | None = DEFAULT_MAX_CONTENT_BYTES,
        max_versions: int | None = None,
        write_guard: WriteGuard | None = None,
    ) -> None:
        super().__init__(
            kinds,
            versions=versions,
            hash_fn=hash_fn,
            clock=clock,
            max_content_bytes=max_content_bytes,
            max_versions=max_versions,
            write_guard=write_guard,
        )
        self.root = Path(root)
        self._digests: dict[Path, tuple[int, int, str]] = {}

    def _path(self, kind: DefinitionKind, id: str) -> Path:
        if kind.singleton_file is not None:
            return self.root / kind.singleton_file
        return self.root / kind.directory / f"{id}.yaml"

    def _read(self, kind: DefinitionKind, id: str) -> dict[str, Any] | None:
        data = load_yaml_file(self._path(kind, id))
        if data is None:
            return None
        plain = to_plain(data)
        assert isinstance(plain, dict)
        return plain

    def _write(self, kind: DefinitionKind, id: str, document: dict[str, Any]) -> None:
        path = self._path(kind, id)
        try:
            existing = load_yaml_file(path)
        except Exception:  # 깨진 파일은 새 내용으로 덮어쓴다
            existing = None
        target: Any = merge_into(existing, document) if existing is not None else None
        if target is None:
            target = wrap_value(document)
        atomic_write_text(path, dump_yaml(target))

    def _remove(self, kind: DefinitionKind, id: str) -> bool:
        try:
            self._path(kind, id).unlink()
        except FileNotFoundError:
            return False
        return True

    def _ids(self, kind: DefinitionKind) -> list[str]:
        if kind.is_singleton:
            return [kind.name] if self._path(kind, kind.name).is_file() else []
        folder = self.root / kind.directory
        if not folder.is_dir():
            return []
        return [p.stem for p in folder.glob("*.yaml") if p.is_file() and not p.name.startswith(".")]

    def _modified_at(self, kind: DefinitionKind, id: str) -> float | None:
        try:
            return self._path(kind, id).stat().st_mtime
        except OSError:
            return None

    # ---- 본문 파일 --------------------------------------------------------
    def _body_dir(self, kind: DefinitionKind, id: str) -> Path:
        return self.root / kind.directory / id

    def _body_path(self, kind: DefinitionKind, id: str, file: str) -> Path:
        return resolve_inside(self._body_dir(kind, id), file, root=self.root)

    def _read_body(self, kind: DefinitionKind, id: str, file: str) -> bytes | None:
        path = self._body_path(kind, id, file)
        try:
            return path.read_bytes()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            return None
        except OSError as exc:
            raise DefinitionCorrupt(f"{kind.name}/{id}/{file}: {exc}") from exc

    def _write_body(self, kind: DefinitionKind, id: str, file: str, data: bytes) -> None:
        path = self._body_path(kind, id, file)
        atomic_write_bytes(path, data)
        self._digests.pop(path, None)

    def _remove_body(self, kind: DefinitionKind, id: str, file: str) -> None:
        path = self._body_path(kind, id, file)
        path.unlink(missing_ok=True)
        self._digests.pop(path, None)
        folder = self._body_dir(kind, id)
        parent = path.parent
        while parent != folder.parent and parent.is_relative_to(folder):
            try:
                parent.rmdir()  # 비어 있을 때만 지워진다
            except OSError:
                break
            parent = parent.parent

    def _body_stat(self, kind: DefinitionKind, id: str, file: str) -> tuple[int, str] | None:
        """크기·수정 시각이 같으면 다시 읽지 않는다(목록이 큰 본문을 매번 읽지 않게)."""
        path = self._body_path(kind, id, file)
        try:
            stat = path.stat()
        except (FileNotFoundError, NotADirectoryError):
            return None
        key = (stat.st_mtime_ns, stat.st_size)
        cached = self._digests.get(path)
        if cached is not None and cached[:2] == key:
            return stat.st_size, cached[2]
        result = super()._body_stat(kind, id, file)
        if result is not None:
            self._digests[path] = (*key, result[1])
        return result

    def _list_body(self, kind: DefinitionKind, id: str) -> list[str]:
        base = self._body_dir(kind, id)
        probe = self.root
        for part in base.relative_to(self.root).parts:
            probe = probe / part
            if probe.is_symlink() or probe.is_junction():
                raise InvalidContentPath(f"{kind.name}/{id}: content folder is a link")
        if not base.is_dir():
            return []
        found: list[str] = []
        for folder, dirs, names in os.walk(base):
            here = Path(folder)
            dirs[:] = [d for d in dirs if not _is_link(here / d)]
            for name in names:
                full = here / name
                if _is_link(full) or not full.is_file():
                    continue
                if name.startswith(".") and name.endswith(".tmp"):
                    continue  # 원자적 쓰기의 임시 파일
                relative = full.relative_to(base).as_posix()
                try:
                    check_content_path(relative)
                except InvalidContentPath:
                    continue  # 이 저장소가 만들 수 없는 이름(손으로 넣은 파일)
                found.append(relative)
        return sorted(found)

    def _body_ids(self, kind: DefinitionKind) -> list[str]:
        folder = self.root / kind.directory
        if not folder.is_dir():
            return []
        return [
            p.name
            for p in folder.iterdir()
            if p.is_dir() and not _is_link(p) and not p.name.startswith(".")
        ]


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()
