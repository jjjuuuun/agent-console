"""Message catalog service: collects catalogs and answers the two REST reads (design §I18N.3).

Merge order (later wins): package catalogs (entry point name order) → user folders (list order).
Package catalogs are read once. User folders are read again when their ``*.json`` files change
(name, size, modification time), so editing a catalog file shows on the next request without a
restart.

The service does not know HTTP. Routes call ``info``, ``catalog`` and ``warnings``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agent_console_contracts import Issue
from agent_console_contracts.i18n import I18nInfo, LanguageInfo, MessageCatalog
from agent_console_i18n import (
    Catalog,
    CatalogIssue,
    CatalogLoad,
    CatalogSet,
    compare_catalogs,
    folder_catalogs,
)

_log = logging.getLogger("agent_console_mod_i18n")

_MISSING_CODES: Final = frozenset({"i18n.missing_key", "i18n.untranslated"})

ISSUE_MESSAGES: Final[Mapping[str, str]] = {
    "i18n.catalog_unreadable": "문구 묶음 파일을 읽을 수 없어 건너뛰었습니다",
    "i18n.catalog_invalid": "문구 묶음 파일의 형식이 맞지 않아 그 부분을 건너뛰었습니다",
    "i18n.catalog_unknown_section": "문구 묶음 파일에 모르는 구역이 있어 그 구역을 건너뛰었습니다",
    "i18n.entry_invalid": "문구 묶음 항목 값이 문자열이 아니라 그 항목을 건너뛰었습니다",
    "i18n.language_invalid": "문구 묶음 파일 이름이 언어 코드가 아니라 그 파일을 건너뛰었습니다",
    "i18n.locales_missing": "문구 묶음 폴더가 없습니다",
    "i18n.source_unavailable": "문구 묶음 패키지를 불러올 수 없어 건너뛰었습니다",
}
"""Server original text (Korean, design §I18N.2 I-7) of the loading issue codes, for
``server.warnings``. The web shows the catalog template of the code when it has one. Unknown codes
use the English ``CatalogIssue.message``."""


class UnknownLanguageError(LookupError):
    """No catalog for the requested language (``i18n.unknown_language``, 404).

    Attributes:
        language: the requested code as given.
        available: languages that have a catalog.
    """

    def __init__(self, language: str, available: Sequence[str]) -> None:
        self.language = language
        self.available = tuple(available)
        super().__init__(f"요청한 언어 {language!r}의 문구 묶음이 없습니다")


@dataclass(frozen=True, slots=True)
class CatalogBody:
    """One language's merged catalog as sent (``MessageCatalog``) and its ``ETag`` version."""

    catalog: MessageCatalog
    version: str


def issue_of(problem: CatalogIssue) -> Issue:
    """A loading problem → a ``server.warnings`` issue (no catalog values, only where it is)."""
    details: dict[str, Any] = dict(problem.details)
    for key in ("source", "language", "section", "key", "path"):
        value = getattr(problem, key)
        if value is not None:
            details[key] = value
    message = ISSUE_MESSAGES.get(problem.code, problem.message)
    where = details.get("path") or details.get("source")
    if where:
        message = f"{message}: {where}"
    return Issue(severity="warning", code=problem.code, message=message, details=details)


def _version(body: Mapping[str, Any]) -> str:
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def folder_signature(folders: Sequence[Path]) -> tuple[Any, ...]:
    """What has to change for the user folders to be read again: ``*.json`` names, sizes, times."""
    out: list[Any] = []
    for folder in folders:
        try:
            with os.scandir(folder) as entries:
                stats = [
                    (entry.name, entry.stat())
                    for entry in entries
                    if entry.name.endswith(".json") and entry.is_file()
                ]
            files = sorted((name, st.st_size, st.st_mtime_ns) for name, st in stats)
        except OSError:
            out.append((str(folder), None))
            continue
        out.append((str(folder), tuple(files)))
    return tuple(out)


@dataclass
class _Snapshot:
    catalogs: CatalogSet
    signature: tuple[Any, ...]
    info: I18nInfo | None = None
    bodies: dict[str, CatalogBody] = field(default_factory=dict)


class I18nService:
    """Merged catalogs, the language list and loading warnings.

    Args:
        packages: package catalogs already read (``agent_console_i18n.package_catalogs``).
        folders: user folders as written in the settings (source names), in merge order.
        base_dir: base folder of relative ``folders`` (usually the settings file folder).
        default_language: ``I18nInfo.default_language``.
        fallback_language: ``I18nInfo.fallback_language`` and the base of ``complete``.
        read_folders: injected folder reader (tests). Default ``folder_catalogs``.
    """

    def __init__(
        self,
        *,
        packages: CatalogLoad = CatalogLoad(),  # noqa: B008 - frozen, empty
        folders: Sequence[str | Path] = (),
        base_dir: Path | None = None,
        default_language: str = "en",
        fallback_language: str = "en",
        read_folders: Callable[..., CatalogLoad] = folder_catalogs,
    ) -> None:
        self._packages = packages
        self._folders = tuple(folders)
        self._base_dir = base_dir
        self._resolved = tuple(self._resolve(f) for f in self._folders)
        self.default_language = default_language
        self.fallback_language = fallback_language
        self._read_folders = read_folders
        self._lock = threading.Lock()
        self._snapshot: _Snapshot | None = None
        self._logged: set[tuple[str, str | None, str | None, str | None]] = set()

    def _resolve(self, folder: str | Path) -> Path:
        path = Path(folder).expanduser()
        if self._base_dir is not None and not path.is_absolute():
            path = self._base_dir / path
        return path

    # ------------------------------------------------------------ loading

    def _current(self) -> _Snapshot:
        signature = folder_signature(self._resolved)
        with self._lock:
            snap = self._snapshot
            if snap is not None and snap.signature == signature:
                return snap
            user = self._read_folders(list(self._folders), base_dir=self._base_dir)
            catalogs = CatalogSet.from_load(self._packages, user)
            self._log_issues(catalogs.issues)
            snap = _Snapshot(catalogs=catalogs, signature=signature)
            self._snapshot = snap
            return snap

    def _log_issues(self, issues: Sequence[CatalogIssue]) -> None:
        for problem in issues:
            key = (problem.code, problem.source, problem.path, problem.key)
            if key in self._logged:
                continue
            self._logged.add(key)
            _log.warning(
                "Message catalog skipped: %s (%s)",
                problem.message,
                problem.path or problem.source or problem.code,
            )

    def catalogs(self) -> CatalogSet:
        """The current merged catalog set (reads user folders again if they changed)."""
        return self._current().catalogs

    # ------------------------------------------------------------ reads

    def info(self) -> I18nInfo:
        """``GET /i18n``: languages (code order) with sources and completeness."""
        snap = self._current()
        if snap.info is not None:
            return snap.info
        catalogs = snap.catalogs
        base = catalogs.catalog(self.fallback_language)
        languages = []
        for code in catalogs.languages():
            merged = catalogs.catalog(code)
            missing = self._missing(base, merged)
            languages.append(
                LanguageInfo(
                    code=code,
                    sources=list(catalogs.sources(code)),
                    complete=missing == 0,
                    missing=missing,
                )
            )
        info = I18nInfo(
            languages=languages,
            default_language=self.default_language,
            fallback_language=self.fallback_language,
        )
        snap.info = info
        return info

    @staticmethod
    def _missing(base: Catalog | None, merged: Catalog | None) -> int:
        if base is None or merged is None or base.language == merged.language:
            return 0
        return sum(1 for issue in compare_catalogs(base, merged) if issue.code in _MISSING_CODES)

    def catalog(self, language: str) -> CatalogBody:
        """``GET /i18n/{lang}``: the merged catalog of the language that matches ``language``.

        Raises:
            UnknownLanguageError: no catalog matches.
        """
        snap = self._current()
        catalogs = snap.catalogs
        matched = catalogs.match(language)
        if matched is None:
            raise UnknownLanguageError(language, catalogs.languages())
        body = snap.bodies.get(matched)
        if body is None:
            merged = catalogs.catalog(matched)
            assert merged is not None  # matched comes from the same set
            data = {"language": merged.language, **merged.to_dict()}
            body = CatalogBody(MessageCatalog.model_validate(data), _version(data))
            snap.bodies[matched] = body
        return body

    def warnings(self) -> list[Issue]:
        """``server.warnings``: catalogs and entries skipped while loading (``i18n.*`` codes)."""
        return [issue_of(problem) for problem in self._current().catalogs.issues]


__all__ = [
    "ISSUE_MESSAGES",
    "CatalogBody",
    "I18nService",
    "UnknownLanguageError",
    "folder_signature",
    "issue_of",
]
