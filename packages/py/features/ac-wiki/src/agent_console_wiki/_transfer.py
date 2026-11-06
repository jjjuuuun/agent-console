"""위키 페이지 zip 내보내기·가져오기(design §7R.1.2·§7R.13·§7R.18 Q16).

형식: zip 항목 하나 = 페이지 파일 하나, 경로 = 위키 폴더 기준 파일 경로 그대로(확장자 포함).
머리말은 본문의 일부라 따로 다루지 않는다.

가져오기 안전(`ac-safe-zip` — 메모리 마크다운 가져오기와 같은 규칙, 디스크에 풀지 않음):

- 묶음 전체(아무것도 쓰지 않음): 압축 크기·항목 수·선언·실제 풀린 크기 상한 → 결과 `issues`
  (`wiki.too_large`, `details.limit`), zip이 아님 → `WikiZipFormatError`. 모든 항목을 다 읽은
  **뒤에** 쓴다.
- 항목 하나만 `rejected`: 위험한 경로·심볼릭 링크·숨김·예약 이름(`wiki.invalid_path`), 암호화·깨진
  데이터, 묶음 안 같은 페이지, 쓰기 판단(쓰기 규칙·비밀 검사·크기 — 그 오류 코드). 페이지 확장자가
  아닌 파일은 `skipped`.
- 같은 경로 페이지가 있으면 `policy`: `skip` · `overwrite`(새 버전 `update`) · `rename`(새 경로 틀 —
  패키지 데이터 `import_rename`). 새로 만든 페이지의 기록은 `import`.
- `dry_run`: 쓰지 않고 같은 판단(`preview`와 같은 쓰기 판단)으로 결과만 계산한다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import IO, get_args

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import (
    KnownWikiAuthorKinds,
    KnownWikiImportStatuses,
    KnownWikiVersionOps,
    WikiAuthor,
    WikiImportItem,
    WikiImportPolicy,
    WikiImportResult,
    WikiIssue,
)
from agent_console_safe_zip import ZipFormatError, ZipLimitError, ZipLimits, read_zip, write_zip
from agent_console_text_template import render_template

from ._errors import WikiError, WikiZipFormatError
from ._paths import check_page_path, split_extension
from ._repository import WikiRepository
from ._ruleset import rules_text

__all__ = ["export_zip", "import_zip"]

_MAX_RENAME_TRIES = 10_000


def export_zip(repository: WikiRepository, *, prefix: str | None = None) -> bytes:
    """위키 페이지 파일을 zip 바이트로 낸다(경로 순·고정 시각 — 같은 페이지면 같은 바이트).

    Args:
        repository: 위키 저장소.
        prefix: 이 경로로 시작하는 페이지만(None = 전부).
    """
    files: list[tuple[str, bytes]] = []
    for info in repository.pages.list(repository.syntax.page_extensions):
        if prefix and not info.file.startswith(prefix):
            continue
        data = repository.pages.read(info.file)
        if data is not None:
            files.append((info.file, data))
    return write_zip(files)


def _issue(code: str, message: str, **details: object) -> WikiIssue:
    return WikiIssue(severity="error", code=code, message=message, details=dict(details))


def _from_error(exc: WikiError) -> list[WikiIssue]:
    nested = exc.details.get("issues")
    if isinstance(nested, list) and nested:
        return [WikiIssue.model_validate(i) for i in nested]
    return [WikiIssue(severity="error", code=exc.code, message=str(exc), details=exc.details)]


def import_zip(
    repository: WikiRepository,
    data: bytes | IO[bytes],
    *,
    policy: WikiImportPolicy = "skip",
    dry_run: bool = False,
    author: WikiAuthor | None = None,
    limits: ZipLimits | None = None,
    rename_format: str | None = None,
) -> WikiImportResult:
    """페이지 zip을 위키로 가져온다(규칙은 모듈 문서).

    Args:
        repository: 위키 저장소(쓰기 판단·기록·색인을 그대로 거친다).
        data: zip 바이트 또는 바이너리 파일.
        policy: 같은 경로 페이지가 있을 때.
        dry_run: 쓰지 않고 결과만.
        author: 쓴 쪽(기본 `system`).
        limits: zip 상한(기본 `ZipLimits()` — 서버 모듈은 설치자 옵션으로).
        rename_format: `rename` 새 경로 틀(`{path}`·`{n}`, 기본 패키지 데이터).

    Raises:
        WikiZipFormatError: zip이 아님.
        ValueError: 모르는 `policy`.
    """
    if policy not in get_args(WikiImportPolicy.__value__):
        raise ValueError(
            f"가져오기 정책은 {', '.join(get_args(WikiImportPolicy.__value__))} 중 하나다"
        )
    who = author or WikiAuthor(kind=KnownWikiAuthorKinds.SYSTEM)
    fmt = rename_format or rules_text("import_rename") or "{path}-{n}"
    try:
        members = read_zip(data, limits)
    except ZipLimitError as exc:
        return WikiImportResult(
            dry_run=dry_run,
            issues=[
                _issue(KnownIssueCodes.WIKI_TOO_LARGE, str(exc), limit=exc.limit, value=exc.value)
            ],
        )
    except ZipFormatError as exc:
        raise WikiZipFormatError() from exc

    extensions = repository.syntax.page_extensions
    items: list[WikiImportItem] = []
    seen: set[str] = set()
    taken: set[str] = set()
    key = repository.syntax.key

    def exists(path: str) -> bool:
        return key(path) in taken or repository.current(path) is not None

    for member in members:
        name = member.name
        if member.kind == "dir":
            continue
        shown = repository.secrets.redact(name)[:512] or "?"
        if member.kind == "unsafe":
            items.append(
                WikiImportItem(
                    path=shown,
                    status=KnownWikiImportStatuses.REJECTED,
                    issues=[
                        _issue(KnownIssueCodes.WIKI_INVALID_PATH, "위험한 경로라 받지 않았습니다.")
                    ],
                )
            )
            continue
        if member.kind in ("encrypted", "broken") or member.data is None:
            items.append(
                WikiImportItem(
                    path=shown,
                    status=KnownWikiImportStatuses.REJECTED,
                    issues=[
                        _issue(
                            "validation_failed",
                            "암호화됐거나 깨진 항목이라 받지 않았습니다.",
                            kind=member.kind,
                        )
                    ],
                )
            )
            continue
        split = split_extension(name, extensions)
        if split is None:
            items.append(WikiImportItem(path=shown, status=KnownWikiImportStatuses.SKIPPED))
            continue
        try:
            path = check_page_path(split[0])
        except WikiError as exc:
            items.append(
                WikiImportItem(
                    path=shown, status=KnownWikiImportStatuses.REJECTED, issues=_from_error(exc)
                )
            )
            continue
        if key(path) in seen:
            items.append(
                WikiImportItem(
                    path=path,
                    status=KnownWikiImportStatuses.REJECTED,
                    issues=[
                        _issue(
                            KnownIssueCodes.WIKI_PAGE_EXISTS,
                            "묶음 안에 같은 페이지가 앞에 있습니다.",
                        )
                    ],
                )
            )
            continue
        seen.add(key(path))
        target, status = path, KnownWikiImportStatuses.CREATED
        if exists(path):
            if policy == "skip":
                items.append(WikiImportItem(path=path, status=KnownWikiImportStatuses.SKIPPED))
                continue
            if policy == "rename":
                free = _free_path(path, fmt, exists)
                if free is None:
                    items.append(
                        WikiImportItem(
                            path=path,
                            status=KnownWikiImportStatuses.REJECTED,
                            issues=[
                                _issue(
                                    KnownIssueCodes.WIKI_PAGE_EXISTS, "새 경로를 찾지 못했습니다."
                                )
                            ],
                        )
                    )
                    continue
                target, status = free, KnownWikiImportStatuses.RENAMED
            else:
                status = KnownWikiImportStatuses.OVERWRITTEN
        text = member.data.decode("utf-8", errors="replace")
        try:
            if dry_run:
                preview = repository.preview(target, text, author=who)
                if preview.would_reject:
                    rejected = [i for i in preview.issues if i.severity == "error"]
                    items.append(
                        WikiImportItem(
                            path=path, status=KnownWikiImportStatuses.REJECTED, issues=rejected
                        )
                    )
                    continue
            else:
                repository.import_page(
                    target,
                    member.data,
                    author=who,
                    record_op=KnownWikiVersionOps.IMPORT
                    if status != KnownWikiImportStatuses.OVERWRITTEN
                    else KnownWikiVersionOps.UPDATE,
                )
        except WikiError as exc:
            items.append(
                WikiImportItem(
                    path=path, status=KnownWikiImportStatuses.REJECTED, issues=_from_error(exc)
                )
            )
            continue
        taken.add(key(target))
        items.append(
            WikiImportItem(
                path=path,
                status=status,
                to=target if status == KnownWikiImportStatuses.RENAMED else None,
            )
        )
    return WikiImportResult(dry_run=dry_run, items=items)


def _free_path(path: str, fmt: str, exists: Callable[[str], bool]) -> str | None:
    for n in range(2, _MAX_RENAME_TRIES):
        candidate = render_template(fmt, {"path": path, "n": n})
        try:
            candidate = check_page_path(candidate)
        except WikiError:
            return None
        if not exists(candidate):
            return candidate
    return None
