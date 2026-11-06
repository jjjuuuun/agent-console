"""폴더에서 가져오기·폴더로 내보내기·가져오기 파일 목록(design §6R.1.2, §6R.13, §6R.18 Q13).

둘 다 **복사**다(원본과 연결하지 않는다). 파일 접근은 주입한 `SpecFiles`만 쓰고, 경로는 모두
`check_project_path`(`..`·절대 경로·링크 거부)를 지난다.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from agent_console_contracts.sdd import (
    ImportDir,
    ImportFile,
    ImportFileListing,
    SpecDefinition,
    SpecDocument,
    SpecExportResult,
)

from ._errors import SpecPathError
from ._files import SpecFiles, check_project_path
from ._ids import unique_id

__all__ = [
    "DEFAULT_IMPORT_LIMIT",
    "ImportedDocuments",
    "export_documents",
    "guess_title",
    "import_documents",
    "list_import_files",
]

DEFAULT_IMPORT_LIMIT = 500
"""가져오기 파일 목록 한 번에 보일 파일 수 기본 상한."""

_TITLE_BYTES = 64 * 1024
_HEADING = re.compile(r"^ {0,3}#(?:[ \t]+(.*?))?[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(```|~~~)")


def guess_title(data: bytes, fallback: str, *, max_bytes: int = _TITLE_BYTES) -> str:
    """첫 `#` 제목(코드 블록 밖, 앞 `max_bytes`만 봄). 없으면 `fallback`."""
    text = data[:max_bytes].decode("utf-8", errors="replace")
    fence: str | None = None
    for line in text.splitlines():
        m = _FENCE.match(line)
        if m is not None:
            fence = None if fence == m.group(1) else (fence or m.group(1))
            continue
        if fence is not None:
            continue
        h = _HEADING.match(line)
        if h is not None and (h.group(1) or "").strip():
            return (h.group(1) or "").strip()
    return fallback


@dataclass(slots=True)
class ImportedDocuments:
    """가져온 문서 목록과 본문(스펙 본문 폴더 기준 파일 → 내용)."""

    documents: list[SpecDocument] = field(default_factory=list)
    contents: dict[str, bytes] = field(default_factory=dict)


def _unique_file(name: str, taken: set[str]) -> str:
    if name.casefold() not in taken:
        return name
    stem, ext = posixpath.splitext(name)
    n = 2
    while f"{stem}-{n}{ext}".casefold() in taken:
        n += 1
    return f"{stem}-{n}{ext}"


def import_documents(
    files: SpecFiles,
    paths: Sequence[str],
    *,
    reserved: Collection[str] = (),
) -> ImportedDocuments:
    """프로젝트 폴더 안 파일들을 새 스펙 문서로 **복사**할 재료를 만든다(쓰지 않는다).

    문서 id = 파일 이름에서 만든 id(겹치면 `-2`…), 제목 = 첫 `#` 제목(없으면 파일 이름), 본문 파일
    이름 = 원본 파일 이름(겹치면 `-2`…), 역할은 비운다(사용자가 정한다).

    Args:
        files: 프로젝트 폴더 파일 접근.
        paths: 폴더 기준 상대 경로(순서 = 문서 순서).
        reserved: 읽을 수 없는 첫 구성요소(예: 앱 구성 폴더).

    Raises:
        SpecPathError: 경로가 틀렸거나(`invalid`·`link`·`reserved`) 파일이 없다(`not_found`).
    """
    out = ImportedDocuments()
    taken_files: set[str] = set()
    taken_ids: set[str] = set()
    for raw in paths:
        norm = check_project_path(raw, files, reserved=reserved)
        data = files.read(norm)
        if data is None:
            raise SpecPathError(raw, "not_found")
        base = posixpath.basename(norm)
        name = _unique_file(base, taken_files)
        taken_files.add(name.casefold())
        stem = posixpath.splitext(base)[0]
        doc_id = unique_id(stem, taken_ids, fallback="doc")
        taken_ids.add(doc_id)
        out.documents.append(
            SpecDocument(id=doc_id, title=guess_title(data, stem) or doc_id, file=name)
        )
        out.contents[name] = data
    return out


def export_documents(
    spec: SpecDefinition,
    contents: Mapping[str, bytes | None],
    files: SpecFiles,
    to_dir: str,
    *,
    overwrite: bool = False,
    reserved: Collection[str] = (),
) -> SpecExportResult:
    """스펙 문서 본문을 프로젝트 폴더 안 `to_dir`로 **복사**한다.

    Args:
        spec: 스펙(문서 목록 순서로 쓴다).
        contents: 스펙 본문 파일 → 내용(None = 본문 없음, 건너뜀).
        files: 프로젝트 폴더 파일 접근.
        to_dir: 폴더 기준 상대 경로(빈 값 = 폴더 루트).
        overwrite: 거짓이면 있는 파일은 건너뛴다.
        reserved: 쓸 수 없는 첫 구성요소(앱 구성 폴더 `.agent-console` 등).

    Returns:
        `SpecExportResult`(쓴 파일·건너뛴 파일, `to_dir` 기준).

    Raises:
        SpecPathError: `to_dir`·대상 경로가 틀렸거나 링크·예약 폴더를 지난다.
    """
    base = check_project_path(to_dir, files, allow_root=True, reserved=reserved)
    written: list[str] = []
    skipped: list[str] = []
    for doc in spec.documents:
        rel = check_project_path(doc.file)
        target = check_project_path(f"{base}/{rel}" if base else rel, files, reserved=reserved)
        data = contents.get(doc.file)
        if data is None or (files.exists(target) and not overwrite):
            skipped.append(rel)
            continue
        files.write(target, data)
        written.append(rel)
    return SpecExportResult(to_dir=base or ".", written=written, skipped=skipped)


def list_import_files(
    files: SpecFiles,
    path: str = "",
    *,
    extensions: Collection[str],
    limit: int = DEFAULT_IMPORT_LIMIT,
    reserved: Collection[str] = (),
) -> ImportFileListing:
    """가져오기에 쓸 폴더 하나의 파일 목록과 바로 아래 하위 폴더(재귀하지 않음, §6R.18 Q13, 6R.20d).

    파일: 숨김(`.`로 시작)·링크·확장자가 맞지 않는 파일은 뺀다. 제목 추정 = 첫 `#` 제목 → 없으면
    파일 이름. 하위 폴더(`dirs`): 숨김·링크(정션 포함)·예약 폴더(루트의 `reserved` 이름)는 뺀다 —
    다시 이 함수에 `path`로 넘겨 한 단계씩 연다. 둘 다 이름 순이고 각각 `limit`까지, 어느 쪽이든
    넘으면 `truncated`.

    Args:
        files: 프로젝트 폴더 파일 접근.
        path: 폴더 기준 상대 경로(빈 값 = 루트).
        extensions: 보일 확장자(점 포함, 대소문자 무시 — 예: 설치자 옵션 `import_extensions`).
        limit: 상한(1 이상).
        reserved: 볼 수 없는 첫 구성요소(앱 구성 폴더).

    Raises:
        SpecPathError: 경로가 틀렸다(`invalid`·`link`·`reserved`), 없다(`not_found`), 폴더가 아니다
            (`not_directory`).
    """
    base = check_project_path(path, files, allow_root=True, reserved=reserved)
    exts = {e.casefold() for e in extensions}
    try:
        entries = files.list(base)
    except FileNotFoundError:
        raise SpecPathError(path, "not_found") from None
    except NotADirectoryError:
        raise SpecPathError(path, "not_directory") from None
    hidden_ok = {r.casefold() for r in reserved}
    folders = sorted(
        (
            e
            for e in entries
            if e.is_dir
            and not e.is_link
            and not e.name.startswith(".")
            and not (not base and e.name.casefold() in hidden_ok)
        ),
        key=lambda e: e.name.casefold(),
    )
    picked = sorted(
        (
            e
            for e in entries
            if not e.is_dir
            and not e.is_link
            and not e.name.startswith(".")
            and e.name.casefold() not in hidden_ok
            and posixpath.splitext(e.name)[1].casefold() in exts
        ),
        key=lambda e: e.name.casefold(),
    )
    limit = max(1, limit)
    shown = picked[:limit]
    out: list[ImportFile] = []
    for e in shown:
        rel = f"{base}/{e.name}" if base else e.name
        data = files.read(rel) or b""
        stem = posixpath.splitext(e.name)[0]
        out.append(ImportFile(name=e.name, size=e.size, title_guess=guess_title(data, stem)))
    dirs = [ImportDir(name=e.name) for e in folders[:limit]]
    return ImportFileListing(
        path=base,
        files=out,
        dirs=dirs,
        truncated=len(picked) > limit or len(folders) > limit,
    )
