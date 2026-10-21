"""증분 jsonl 파일 출처 기반 클래스(agent_bench `log_store._ingest` 규칙 이식).

- 바이트 오프셋 커서로 이어 읽는다.
- 끝나지 않은 마지막 줄(`\\n` 없음)은 보류한다. `final`이면 읽는다.
- 파일 크기가 커서보다 작으면(잘렸거나 바뀜) 처음부터 다시 읽는다.
  색인 identity 덕분에 중복되지 않는다.
- 회전 감지: 읽은 앞부분(최대 `HEAD_FINGERPRINT_BYTES`)의 지문을 `Cursor.state[HEAD_STATE_KEY]`에
  둔다. 다음에 앞부분이 달라졌으면(같은 이름의 더 큰 새 파일 등) 처음부터 다시 읽고 세대
  (`Cursor.state[GENERATION_STATE_KEY]`, `RawRecord.generation`)를 올린다. 세대가 identity에
  들어가므로 같은 위치의 새 내용이 옛 행과 겹쳐 버려지지 않는다. 다시 읽어도 같은 세대면 중복 0.
  한계: 크기와 앞부분이 같고 그 뒤만 바뀐 파일은 감지하지 못한다(크기·mtime도 같으면 읽지도 않는다).
  파일이 줄면 앞부분(짧으면 첫 줄) 지문이 같을 때만 같은 파일로 보고(세대 유지, identity로 중복 0),
  다르거나 확인할 수 없으면 새 내용으로 보고 세대를 올린다(같은 내용을 다시 쓴 파일은
  중복될 수 있다).
- 심볼릭 링크: 폴더 링크는 따라가지 않는다. 파일 링크는 실제 위치가 루트 안일 때만 읽고,
  같은 실제 파일은 한 번만 낸다(링크가 아닌 경로가 우선). 루트 밖을 가리키는 링크는 건너뛴다.
- 해석하지 못한 줄은 `DIAGNOSTIC_META_KEY`가 붙은 레코드가 된다(버리지 않는다).
- 파일은 `ctx.open_read`로만 연다. 이 클래스에는 쓰기·이동·삭제 경로가 없다.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, ClassVar

from agent_console_contracts.logs import LogSourceDescriptor

from ._glob import glob_match
from ._source import (
    DIAGNOSTIC_META_KEY,
    Cursor,
    LogSourceContext,
    RawRecord,
    ReadResult,
    SourceRef,
)
from ._values import JsonValue

__all__ = ["JSONL_CONFIG_SCHEMA", "JsonlFileSource", "expand_user_path"]

HEAD_FINGERPRINT_BYTES = 4096
"""회전 감지 지문에 쓰는 앞부분 최대 크기(바이트). 커서 위치까지만 본다(완성된 줄만)."""

GENERATION_STATE_KEY = "jsonl_generation"
"""`Cursor.state`에서 내용 세대(정수, 0이면 생략)를 두는 키."""

HEAD_STATE_KEY = "jsonl_head"
"""`Cursor.state`에서 앞부분 지문을 두는 키(`{"len": n, "sha256": hex}`).
하위 클래스는 다른 키를 쓴다."""

JSONL_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "roots": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "default": [],
            "title": "루트 폴더",
            "description": "읽을 폴더 목록. `~`는 홈 폴더. 원본은 읽기만 한다.",
        },
        "include": {
            "type": "array",
            "items": {"type": "string"},
            "default": ["**/*.jsonl"],
            "title": "포함 패턴",
            "description": "루트 기준 상대 경로 글롭(`**` = 여러 폴더).",
        },
        "exclude": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
            "title": "제외 패턴",
        },
    },
}
"""`JsonlFileSource` 기본 설정 스키마(루트·포함·제외). 하위 클래스가 넓힐 수 있다."""


def expand_user_path(value: str, environ: Mapping[str, str]) -> Path:
    """`~`·`~/`를 주입된 환경의 홈(`HOME`, 없으면 `USERPROFILE`)으로 바꾼다.

    홈을 모르면 `~`를 그대로 둔다(프로세스 환경을 몰래 읽지 않는다).
    """
    if value == "~" or value.startswith(("~/", "~\\")):
        home = environ.get("HOME") or environ.get("USERPROFILE")
        if home:
            return Path(home) / value[2:] if len(value) > 1 else Path(home)
    return Path(value)


class JsonlFileSource:
    """폴더 아래 jsonl 파일을 증분으로 읽는 출처의 기반 클래스.

    하위 클래스는 `descriptor`를 정하고, 필요하면 `default_roots`(설정에 루트가 없을 때)와
    `ref_meta`(파일별 분류 맥락)를 바꾼다. 설정 키는 `JSONL_CONFIG_SCHEMA`(roots·include·exclude).

    ref는 루트 기준 상대 경로(`/` 구분)다. 루트가 여럿이고 같은 상대 경로가 겹치면 앞 루트가 이긴다.
    """

    descriptor: ClassVar[LogSourceDescriptor]

    # ---------------------------------------------------------------- 하위 클래스 훅

    def default_roots(self, ctx: LogSourceContext) -> list[Path]:
        """설정 `roots`가 비었을 때 쓸 루트. 기본은 없음(아무것도 읽지 않음)."""
        return []

    def ref_meta(self, root: Path, path: Path, ctx: LogSourceContext) -> Mapping[str, JsonValue]:
        """파일 하나의 분류 맥락(`SourceRef.meta`). 기본은 빈 객체.

        추가 파일(예: 옆의 `.meta.json`)을 읽을 때도 `ctx.open_read`만 쓴다.
        """
        return {}

    def parse_line(self, line: bytes) -> JsonValue:
        """줄 하나를 값으로 해석한다. 실패하면 예외(→ 진단 레코드)."""
        return json.loads(line)

    # ---------------------------------------------------------------- 출처 구현

    def roots(self, ctx: LogSourceContext) -> list[Path]:
        """유효 루트 목록(설정 `roots`, 비었으면 `default_roots`)."""
        configured = ctx.config.get("roots") or []
        if isinstance(configured, str):
            configured = [configured]
        roots = [expand_user_path(str(r), ctx.environ) for r in configured if str(r)]
        return roots or self.default_roots(ctx)

    def _patterns(self, ctx: LogSourceContext, key: str, fallback: Sequence[str]) -> list[str]:
        value = ctx.config.get(key)
        if value is None:
            return list(fallback)
        if isinstance(value, str):
            return [value]
        return [str(v) for v in value]

    def _selected(self, rel: str, include: Sequence[str], exclude: Sequence[str]) -> bool:
        return any(glob_match(p, rel) for p in include) and not any(
            glob_match(p, rel) for p in exclude
        )

    def discover(self, ctx: LogSourceContext) -> Iterable[SourceRef]:
        """루트 아래에서 포함·제외 패턴에 맞는 파일을 찾는다.

        폴더 심볼릭 링크는 따라가지 않는다. 파일 심볼릭 링크는 실제 위치가 그 루트 안일 때만 내고,
        루트 밖을 가리키면 건너뛴다. 같은 실제 파일을 가리키는 경로가 여럿이면 하나만 낸다
        (링크가 아닌 경로가 우선, 그다음 이름순).
        """
        include = self._patterns(ctx, "include", ["**/*.jsonl"])
        exclude = self._patterns(ctx, "exclude", [])
        seen: set[str] = set()
        refs: list[SourceRef] = []
        for root in self.roots(ctx):
            if not root.is_dir():
                continue
            real_root = Path(os.path.realpath(root))
            candidates: list[tuple[str, Path, bool, str]] = []
            for folder, dirs, files in os.walk(root, followlinks=False):
                dirs.sort()
                for name in sorted(files):
                    path = Path(folder) / name
                    rel = path.relative_to(root).as_posix()
                    if rel in seen or not self._selected(rel, include, exclude):
                        continue
                    real = os.path.realpath(path)
                    if not _inside(Path(real), real_root):
                        continue  # 루트 밖을 가리키는 링크
                    candidates.append((rel, path, path.is_symlink(), os.path.normcase(real)))
            owner: dict[str, str] = {}
            for rel, _path, _link, real in sorted(candidates, key=lambda c: (c[2], c[0])):
                owner.setdefault(real, rel)
            for rel, path, _is_link, real in candidates:
                if owner.get(real) != rel:
                    continue  # 같은 실제 파일을 이미 다른 경로로 냄
                try:
                    stat = path.stat()
                except OSError:
                    continue
                seen.add(rel)
                refs.append(
                    SourceRef(
                        ref=rel,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        meta=dict(self.ref_meta(root, path, ctx)),
                    )
                )
        return refs

    def resolve(self, ref: str, ctx: LogSourceContext) -> Path | None:
        """ref → 실제 경로(루트 순서대로).

        루트 밖으로 나가는 ref, 그리고 링크를 따라가면 루트 밖이 되는 경로는 거절한다.
        """
        parts = PurePosixPath(ref).parts
        if not parts or ref.startswith("/") or ".." in parts or ":" in parts[0]:
            return None
        for root in self.roots(ctx):
            candidate = root.joinpath(*parts)
            if candidate.is_file():
                real_root = Path(os.path.realpath(root))
                if not _inside(Path(os.path.realpath(candidate)), real_root):
                    return None
                return candidate
        return None

    def read(
        self, ref: SourceRef, cursor: Cursor, ctx: LogSourceContext, *, budget: int, final: bool
    ) -> ReadResult:
        """`cursor.offset`부터 줄 단위로 읽는다(규칙은 모듈 설명)."""
        path = self.resolve(ref.ref, ctx)
        if path is None:
            return ReadResult(records=[], cursor=cursor, read_bytes=0, exhausted=True)
        size = path.stat().st_size
        offset = cursor.offset
        state = dict(cursor.state)
        generation = _int(state.get(GENERATION_STATE_KEY))
        records: list[RawRecord] = []
        remaining = max(1, budget)
        exhausted = False
        with ctx.open_read(path) as stream:
            same_head = _head_matches(stream, state.get(HEAD_STATE_KEY), size)
            if size < offset or (offset > 0 and same_head is False):
                # 줄었거나 앞부분이 바뀌었다 → 처음부터. 앞부분(또는 첫 줄)이 같으면 같은 파일이
                # 잘린 것(세대 유지, identity로 중복 0). 다르거나 확인할 수 없으면 새 내용으로 보고
                # 세대를 올린다(같은 내용을 다시 쓴 파일이면 중복될 수 있다 — 데이터 손실보다 낫다).
                if same_head is not True:
                    generation += 1
                offset, state = 0, {}
                if generation:
                    state[GENERATION_STATE_KEY] = generation
            start_offset = offset
            stream.seek(offset)
            while remaining > 0:
                start = offset
                line = stream.readline()
                if not line:
                    exhausted = True
                    break
                if not line.endswith(b"\n") and not final:
                    exhausted = True  # 쓰는 중인 마지막 줄은 다음 수집으로 보류
                    break
                offset += len(line)
                remaining -= len(line)
                body = line.rstrip(b"\r\n")
                if not body.strip():
                    continue
                records.append(self._record(ref, start, body, generation))
            else:
                exhausted = offset >= size
            head = state.get(HEAD_STATE_KEY)
            known = head.get("len") if isinstance(head, Mapping) else None
            want = min(offset, HEAD_FINGERPRINT_BYTES)
            if want > 0 and known != want:
                state[HEAD_STATE_KEY] = _head_fingerprint(stream, want)
        return ReadResult(
            records=records,
            cursor=Cursor(offset=offset, state=state),
            read_bytes=offset - start_offset,
            exhausted=exhausted,
        )

    def _record(self, ref: SourceRef, start: int, body: bytes, generation: int = 0) -> RawRecord:
        try:
            data = self.parse_line(body)
        except (ValueError, UnicodeDecodeError) as exc:
            return RawRecord(
                origin=ref.ref,
                offset=start,
                data={"text": body.decode("utf-8", errors="replace")},
                meta={**ref.meta, DIAGNOSTIC_META_KEY: f"{type(exc).__name__}: {exc}"},
                generation=generation,
            )
        return RawRecord(
            origin=ref.ref, offset=start, data=data, meta=dict(ref.meta), generation=generation
        )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _head_fingerprint(stream: BinaryIO, length: int) -> dict[str, JsonValue]:
    """앞 `length` 바이트의 해시 + 그 안에 끝나는 첫 줄의 해시(짧아진 파일 비교용)."""
    stream.seek(0)
    data = stream.read(length)
    head: dict[str, JsonValue] = {"len": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    end = data.find(b"\n")
    if end >= 0:
        line = data[: end + 1]
        head["line_len"] = len(line)
        head["line_sha256"] = hashlib.sha256(line).hexdigest()
    return head


def _digest_at(stream: BinaryIO, length: int) -> str:
    stream.seek(0)
    return hashlib.sha256(stream.read(length)).hexdigest()


def _head_matches(stream: BinaryIO, head: JsonValue, size: int) -> bool | None:
    """저장한 앞부분 지문과 지금 파일이 같은가.

    앞부분 전체를 비교할 수 있으면 그것으로, 파일이 그보다 짧으면 첫 줄로 비교한다.

    Returns:
        True/False, 또는 확인할 수 없으면 None(지문이 없는 옛 커서, 파일이 첫 줄보다 짧음).
    """
    if not isinstance(head, Mapping):
        return None
    length = head.get("len")
    if isinstance(length, int) and 0 < length <= size:
        return _digest_at(stream, length) == head.get("sha256")
    line_len = head.get("line_len")
    if isinstance(line_len, int) and 0 < line_len <= size:
        return _digest_at(stream, line_len) == head.get("line_sha256")
    return None


def _int(value: JsonValue) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0
