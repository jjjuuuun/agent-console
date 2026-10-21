"""정의 버전 비교·되돌리기·보존 개수(design §2R.9·§2R.3, R2.5, D3). HTTP 없이도 쓴다.

비교 계산은 ``ac-settings.diff_documents``, 비밀 위치는 저장 전 검사의 평문 이슈(설정
``secret_issue_codes``) + 비밀 의심 규칙(``secrets.rules``, 없으면 기본 규칙)이다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

from agent_console_contracts import ContentChange, DefinitionDiff, DiffChange, Issue
from agent_console_secret_rules import SecretRules, default_rules
from agent_console_settings import MISSING, diff_digests, diff_documents
from agent_console_store import NotFound, StoredDefinition, VersionRequired

from .ports import DefinitionCheck, SavedDefinition, VersionStore
from .settings import DEFAULT_SECRET_ISSUE_CODES

_log = logging.getLogger("agent_console_mod_versions")

SECRET_MASK = "***"
"""비교 결과에서 비밀 위치 값 대신 쓰는 문자열(계약 `DiffChange.secret`)."""

RESTORE_MESSAGE = "restored from {hash}"
"""되돌리기 버전 메시지 기본 문구(`RestoreVersionRequest.message`가 비었을 때)."""


class RestoreRejectedError(ValueError):
    """되돌릴 버전이 저장 전 검사(error 이슈)를 통과하지 못했다 → ``validation_failed``(422).

    Attributes:
        issues: 모든 이슈(path = 버전 문서 기준, 메시지에 값 없음).
    """

    def __init__(self, label: str, issues: Sequence[Issue]) -> None:
        super().__init__(f"{label}에 오류가 있어 저장하지 않았습니다")
        self.issues = list(issues)


class VersionService:
    """버전 비교·되돌리기·보존 개수.

    Args:
        store: 정의 저장소(``definitions.store``).
        checks: 저장 전 검사 목록을 돌려주는 함수(없으면 빈 목록).
        rules: 지금 비밀 의심 규칙을 돌려주는 함수(없으면 기본 규칙).
        secret_issue_codes: 비밀 위치로 볼 검사 이슈 코드.
        max_per_definition: 정의마다 남길 버전 수(None = 모두).
    """

    def __init__(
        self,
        store: VersionStore,
        *,
        checks: Callable[[], Sequence[DefinitionCheck]] = lambda: (),
        rules: Callable[[], SecretRules] | None = None,
        secret_issue_codes: Collection[str] = DEFAULT_SECRET_ISSUE_CODES,
        max_per_definition: int | None = None,
    ) -> None:
        self.store = store
        self._checks = checks
        self._rules = rules or default_rules
        self._secret_codes = frozenset(secret_issue_codes)
        self._keep = max_per_definition

    # ------------------------------------------------------------ 검사

    def issues(self, kind: str, document: Mapping[str, Any]) -> list[Issue]:
        """저장 전 검사 이슈(제공자 전부)."""
        return [i for c in self._checks() for i in c.issues(kind, document)]

    def secret_paths(self, kind: str, document: Mapping[str, Any]) -> list[str]:
        """정의 문서의 비밀 위치(문서 기준 JSON Pointer): 평문 이슈 + 의심 규칙."""
        paths = [i.path or "" for i in self.issues(kind, document) if i.code in self._secret_codes]
        paths += [f.path for f in self._rules().find_suspected(dict(document))]
        return list(dict.fromkeys(paths))

    # ------------------------------------------------------------ 비교

    def _file_digests(self, kind: str, item_id: str, version_hash: str) -> dict[str, str] | None:
        try:
            files = self.store.list_version_files(kind, item_id, version_hash)
        except NotFound:  # 본문 스냅샷이 없는 버전(0003 이전)
            return None
        return {f.path: f.sha256 for f in files}

    def diff(self, kind: str, item_id: str, from_hash: str, to_hash: str | None) -> DefinitionDiff:
        """두 버전 비교. ``to_hash``가 None이면 현재 버전(정의가 없으면 ``NotFound``).

        본문 파일은 해시만 비교한다. 한쪽에 본문 스냅샷이 없으면 본문 비교는 비운다.
        """
        store = self.store
        old = store.get_version(kind, item_id, from_hash)
        target = to_hash or store.get(kind, item_id).version_hash
        new = store.get_version(kind, item_id, target)
        before, after = old.content or {}, new.content or {}
        changes = diff_documents(
            before,
            after,
            before_secrets=self.secret_paths(kind, before),
            after_secrets=self.secret_paths(kind, after),
            mask=SECRET_MASK,
        )
        old_files = self._file_digests(kind, item_id, from_hash)
        new_files = self._file_digests(kind, item_id, target)
        content: list[ContentChange] = []
        if old_files is not None and new_files is not None:
            content = [
                ContentChange(path=c.path, before_hash=c.before, after_hash=c.after)
                for c in diff_digests(old_files, new_files)
            ]
        return DefinitionDiff(
            kind=kind,
            id=item_id,
            from_hash=from_hash,
            to_hash=target,
            changes=[_diff_change(c.op, c.path, c.before, c.after, c.secret) for c in changes],
            content_changes=content,
        )

    # ------------------------------------------------------------ 되돌리기

    def _current(self, kind: str, item_id: str) -> StoredDefinition | None:
        try:
            return self.store.get(kind, item_id)
        except NotFound:
            return None

    def restore(
        self,
        kind: str,
        item_id: str,
        version_hash: str,
        *,
        expected_version: str | None,
        message: str | None = None,
        label: str | None = None,
    ) -> StoredDefinition:
        """버전 ``version_hash``의 문서·본문으로 **새 버전**을 저장한다(지운 정의도 되살린다).

        저장 전 검사를 먼저 한다(error 이슈 → ``RestoreRejectedError``). 정의가 있으면
        ``expected_version``(If-Match)이 필요하다(없으면 ``VersionRequired``, 다르면
        ``VersionConflict``).
        """
        version = self.store.get_version(kind, item_id, version_hash)
        issues = self.issues(kind, version.content or {})
        if any(i.severity == "error" for i in issues):
            raise RestoreRejectedError(label or kind, issues)
        if self._current(kind, item_id) is not None and expected_version is None:
            raise VersionRequired(f"{kind}/{item_id}: If-Match is required to restore")
        return self.store.restore_version(
            kind,
            item_id,
            version_hash,
            expected_version=expected_version,
            message=message or RESTORE_MESSAGE.format(hash=version_hash),
        )

    # ------------------------------------------------------------ 보존 개수(D3)

    @property
    def max_per_definition(self) -> int | None:
        return self._keep

    def retain(self, kind: str, item_id: str, protect: Collection[str] = ()) -> int:
        """정의 하나의 버전을 ``max_per_definition``개로 줄이고 지운 개수를 돌려준다.

        ``protect``(현재 버전 등)는 지우지 않고 개수에 포함한다. 지웠으면 쓰지 않는 blob도 정리한다.
        """
        if self._keep is None:
            return 0
        versions = self.store.versions
        removed = versions.trim(kind, item_id, keep=self._keep, protect=protect)
        if removed:
            versions.prune_blobs()
        return removed

    def on_saved(self, saved: SavedDefinition) -> None:
        """``definitions.saved`` 구독자: 저장된 정의에 보존 개수를 적용한다."""
        self.retain(saved.kind, saved.id, (saved.version_hash,))

    def retain_all(self) -> int:
        """저장소의 모든 정의에 보존 개수를 적용한다(시작 때 한 번)."""
        if self._keep is None:
            return 0
        total = 0
        for kind in self.store.kinds():
            for item_id in self.store.list_ids(kind):
                current = self._current(kind, item_id)
                protect = (current.version_hash,) if current is not None else ()
                total += self.retain(kind, item_id, protect)
        if total:
            _log.info("보존 개수(%d)를 넘는 버전 %d개를 지웠습니다", self._keep, total)
        return total


def _diff_change(op: Any, path: str, before: Any, after: Any, secret: bool) -> DiffChange:
    values: dict[str, Any] = {}
    if before is not MISSING:
        values["before"] = before
    if after is not MISSING:
        values["after"] = after
    return DiffChange(op=op, path=path, secret=secret, **values)


__all__ = ["RESTORE_MESSAGE", "SECRET_MASK", "RestoreRejectedError", "VersionService"]
