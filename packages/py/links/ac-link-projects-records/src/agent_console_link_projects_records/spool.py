"""쓰기 실패 대기 파일(design §PI.4.6.6, K33-31).

기록 DB 폴더가 실행 중에 사라지면 남은 기록을 앱 상태 폴더의
``records-spool/<등록 id>/<run id>.jsonl``에 한 줄씩 적어 두었다가, 그 공간이 다시 열리면 기록 DB에
다시 쓰고 지운다. 줄 = ``{"kind": 종류, "data": 모델 JSON}``. 종류별 적용 함수는 주입한다
(``replay.default_appliers``는 store의 Run·NodeRun·이벤트·상호작용). 같은 줄을 두 번 적용해도
중복이 생기지 않는 것은 적용 함수의 몫이다(이벤트는 ``(run_id, seq)`` 중복 무시).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from agent_console_store import atomic_write_bytes

type Apply = Callable[[str, Mapping[str, Any]], bool]
"""``(kind, data) -> 새로 썼나``. 이미 있어 무시했으면 False, 못 쓰면 예외."""


@dataclass
class DrainResult:
    """``RecordsSpool.drain`` 결과.

    Attributes:
        written: 새로 쓴 줄 수.
        duplicates: 이미 있어 무시한 줄 수.
        invalid: 읽을 수 없어 버린 줄 수(JSON이 아니거나 모양이 틀림).
        remaining: 못 쓰고 남은 줄 수(다음 열기 때 다시 시도).
        errors: 적용 중 난 예외(파일마다 첫 번째).
    """

    written: int = 0
    duplicates: int = 0
    invalid: int = 0
    remaining: int = 0
    errors: list[Exception] = field(default_factory=list)


class RecordsSpool:
    """대기 파일 폴더(``root/<공간 id>/<run id>.jsonl``).

    >>> import tempfile
    >>> spool = RecordsSpool(Path(tempfile.mkdtemp()))
    >>> _ = spool.append("p1", "r1", "event", {"seq": 1})
    >>> spool.pending("p1")
    ['r1']
    >>> spool.drain("p1", lambda kind, data: True).written
    1
    >>> spool.pending("p1")
    []
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.Lock()

    def _file(self, space_id: str, run_id: str) -> Path:
        return self._root / quote(space_id, safe="") / (quote(run_id, safe="") + ".jsonl")

    def append(self, space_id: str, run_id: str, kind: str, data: Mapping[str, Any]) -> Path:
        """줄 하나를 덧붙인다(폴더는 만든다). 대기 파일 경로를 돌려준다.

        Raises:
            OSError: 쓸 수 없다.
        """
        line = json.dumps({"kind": kind, "data": dict(data)}, ensure_ascii=False)
        path = self._file(space_id, run_id)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return path

    def pending(self, space_id: str) -> list[str]:
        """대기 중인 run id(정렬)."""
        folder = self._root / quote(space_id, safe="")
        if not folder.is_dir():
            return []
        return sorted(unquote(p.stem) for p in folder.glob("*.jsonl"))

    def drain(self, space_id: str, apply: Apply) -> DrainResult:
        """대기 파일을 run마다 차례로 ``apply``한다. 다 쓰면 파일을 지운다.

        한 줄이 예외를 내면 그 파일은 거기서 멈추고 그 줄부터 남긴다(순서 유지). 읽을 수 없는 줄은
        버리고 ``invalid``로 센다.
        """
        result = DrainResult()
        for run_id in self.pending(space_id):
            path = self._file(space_id, run_id)
            with self._lock:
                self._drain_file(path, apply, result)
        folder = self._root / quote(space_id, safe="")
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
        return result

    def _drain_file(self, path: Path, apply: Apply, result: DrainResult) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return
        keep: list[str] = []
        failed = False
        for line in lines:
            if not line.strip():
                continue
            if failed:
                keep.append(line)
                continue
            try:
                record = json.loads(line)
                kind, data = record["kind"], record["data"]
                if not isinstance(kind, str) or not isinstance(data, dict):
                    raise ValueError("bad record")
            except (ValueError, KeyError, TypeError):
                result.invalid += 1
                continue
            try:
                if apply(kind, data):
                    result.written += 1
                else:
                    result.duplicates += 1
            except Exception as exc:
                failed = True
                result.errors.append(exc)
                keep.append(line)
        result.remaining += len(keep)
        if not keep:
            path.unlink(missing_ok=True)
        elif len(keep) != len(lines):
            atomic_write_bytes(path, ("\n".join(keep) + "\n").encode("utf-8"))


__all__ = ["Apply", "DrainResult", "RecordsSpool"]
