"""등록 id 정하기(design §PI.2·§PI.4.4 K33-25, U-23).

- 폴더 id(매니페스트 `id`)가 있으면 그것, 없으면 폴더 이름 slug, slug로 못 바꾸는 이름(한글 등)은
  `proj-<경로 해시 4자>`.
- 이 앱에 같은 id가 이미 있으면(같은 저장소의 git worktree 두 개 등) 등록 id에만 `-2`, `-3`…을
  붙인다. 폴더 파일은 고치지 않는다.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Collection
from typing import Final

from agent_console_local_folders import PathFlavor, path_module

from ._paths import PathRules, folder_key, host_flavor

__all__ = [
    "FALLBACK_PREFIX",
    "MAX_ID_LENGTH",
    "folder_slug",
    "registration_id",
    "suggest_project_id",
]

MAX_ID_LENGTH: Final = 128
"""계약 `Slug`의 최대 길이."""

FALLBACK_PREFIX: Final = "proj-"
_SLUG_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_NOT_SLUG = re.compile(r"[^a-z0-9_-]+")


def folder_slug(
    folder: str, *, flavor: PathFlavor | None = None, rules: PathRules | None = None
) -> str:
    """폴더 경로 → id 후보(폴더 이름을 slug로). 못 바꾸면 `proj-<경로 해시 4자>`.

    영문자는 소문자로, 악센트는 떼고, 그 밖의 글자 묶음은 `-` 하나로 바꾼다. 해시는 비교 키
    (`folder_key`)로 만들어 같은 폴더면 같은 값이다.

    >>> folder_slug("/home/me/Work/My App", flavor="posix")
    'my-app'
    >>> folder_slug("/home/me/결제", flavor="posix").startswith("proj-")
    True
    """
    fl = flavor or host_flavor()
    pm = path_module(fl)
    name = pm.basename(pm.normpath(folder)) if folder else ""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = _NOT_SLUG.sub("-", ascii_name.lower()).strip("-_")
    slug = slug[: MAX_ID_LENGTH - 8].rstrip("-_")
    if slug and _SLUG_OK.match(slug):
        return slug
    digest = hashlib.sha256(folder_key(folder, flavor=fl, rules=rules).encode("utf-8")).hexdigest()
    return FALLBACK_PREFIX + digest[:4]


def registration_id(manifest_id: str, taken_ids: Collection[str]) -> str:
    """등록 id: `manifest_id`가 겹치지 않으면 그대로, 아니면 `-2`부터 빈 번호를 붙인다(K33-25).

    비교는 대소문자를 무시한다(등록부 파일 이름이 대소문자를 무시하는 파일 시스템에서 겹치지 않게).

    >>> registration_id("app", []), registration_id("app", ["App"])
    ('app', 'app-2')
    >>> registration_id("app", ["app", "app-2"])
    'app-3'
    """
    taken = {t.casefold() for t in taken_ids}
    if manifest_id.casefold() not in taken:
        return manifest_id
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = manifest_id[: MAX_ID_LENGTH - len(suffix)] + suffix
        if candidate.casefold() not in taken:
            return candidate
        n += 1


def suggest_project_id(
    folder: str,
    *,
    manifest_id: str | None = None,
    taken_ids: Collection[str] = (),
    flavor: PathFlavor | None = None,
    rules: PathRules | None = None,
) -> str:
    """등록할 때 쓸 id 제안(`FolderCheck.suggested_id`): 매니페스트 id 또는 폴더 slug + 겹침 접미.

    >>> suggest_project_id("/w/payments", taken_ids=["payments"], flavor="posix")
    'payments-2'
    >>> suggest_project_id("/w/wt-2", manifest_id="payments", taken_ids=["payments"])
    'payments-2'
    """
    base = manifest_id or folder_slug(folder, flavor=flavor, rules=rules)
    return registration_id(base, taken_ids)
