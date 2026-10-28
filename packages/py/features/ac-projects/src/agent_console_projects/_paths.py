"""프로젝트 폴더 경로 비교(design §PI.2 K33-2·§PI.8). 정규화·포함 판단은 `ac-local-folders`를 쓴다.

- 비교 키 = `ac-local-folders.path_key`(Windows는 대소문자 무시) + 규칙 데이터
  `data/path_rules.json`의 `case_insensitive`(대소문자를 무시하는 POSIX 경로 앞부분, 기본 없음).
  드라이브를 대소문자 무시로 마운트한 경로(예: WSL `/mnt/c`, macOS 외장 볼륨)는 설치자가 규칙을
  더한다. 특정 실행 환경 전용 규칙은 기본 데이터에 두지 않는다(5.7R.33d2).
- 옛 파일의 상대 경로는 기준 폴더(설정 파일 폴더)로 절대화한다(`resolve_folder`).
- 파일 시스템을 읽지 않는다. 링크를 푼 실제 경로는 등록할 때 `ac-local-folders.normalize`가 만든다.
"""

from __future__ import annotations

import fnmatch
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any, Final, Literal

from agent_console_local_folders import (
    FolderError,
    FolderErrorCode,
    PathFlavor,
    is_within,
    normalize_lexical,
    path_key,
    path_module,
)

__all__ = [
    "CaseRule",
    "PathRelation",
    "PathRules",
    "folder_key",
    "folder_within",
    "host_flavor",
    "load_path_rules",
    "path_relation",
    "resolve_folder",
]

type PathRelation = Literal["same", "parent", "child"]
"""두 폴더의 관계. `path_relation(a, b)`는 **b가 a에 대해** 무엇인가(parent = b가 a를 포함)."""

_NO_ENV: Final[Mapping[str, str]] = {}


def host_flavor() -> PathFlavor:
    """이 프로세스의 경로 방식(`os.name`이 nt면 windows). `flavor=None` 인자의 기본값이다."""
    return "windows" if os.name == "nt" else "posix"


@dataclass(frozen=True, slots=True)
class CaseRule:
    """대소문자를 무시하고 비교할 POSIX 경로 앞부분 하나.

    Attributes:
        pattern: 경로 앞부분 패턴(fnmatch, 경로 조각 단위로 맞춤). 예: ``/mnt/?``는
            ``/mnt/c/...``·``/mnt/d``에 맞고 ``/mnt/cd``에는 맞지 않는다.
        description: 설명(표시용).
    """

    pattern: str
    description: str = ""

    def matches(self, path: str) -> bool:
        """`path`(정규화한 POSIX 절대 경로)의 앞부분이 패턴에 맞는가."""
        want = [p for p in self.pattern.split("/") if p]
        have = [p for p in path.split("/") if p]
        if not want or len(have) < len(want):
            return False
        return all(fnmatch.fnmatchcase(h, w) for h, w in zip(have, want, strict=False))


@dataclass(frozen=True, slots=True)
class PathRules:
    """경로 비교 규칙(데이터). 기본값 = 패키지 데이터 `data/path_rules.json`."""

    case_insensitive: tuple[CaseRule, ...] = ()


def _rules_from(data: Mapping[str, Any]) -> list[CaseRule]:
    raw = data.get("case_insensitive", [])
    if not isinstance(raw, list):
        raise ValueError("case_insensitive는 목록이어야 합니다.")
    out: list[CaseRule] = []
    for i, item in enumerate(raw):
        if isinstance(item, str):
            item = {"pattern": item}
        if not isinstance(item, Mapping) or not isinstance(item.get("pattern"), str):
            raise ValueError(f"case_insensitive[{i}]에 pattern(문자열)이 없습니다.")
        desc = item.get("description", "")
        out.append(CaseRule(pattern=item["pattern"], description=str(desc or "")))
    return out


def load_path_rules(
    extra: Mapping[str, Any] | None = None, *, include_defaults: bool = True
) -> PathRules:
    """경로 비교 규칙을 읽는다.

    Args:
        extra: 설치자 데이터(`{"case_insensitive": [{"pattern": ...}, ...]}`). 기본 규칙 뒤에
            붙는다.
        include_defaults: 패키지 기본 데이터를 함께 쓸지.

    Raises:
        ValueError: 데이터 모양이 틀림.

    >>> load_path_rules().case_insensitive
    ()
    >>> [r.pattern for r in load_path_rules({"case_insensitive": ["/mnt/?"]}).case_insensitive]
    ['/mnt/?']
    """
    rules: list[CaseRule] = []
    if include_defaults:
        text = resources.files(__package__).joinpath("data", "path_rules.json").read_text("utf-8")
        rules.extend(_rules_from(json.loads(text)))
    if extra is not None:
        rules.extend(_rules_from(extra))
    return PathRules(case_insensitive=tuple(rules))


def folder_key(
    path: str, *, flavor: PathFlavor | None = None, rules: PathRules | None = None
) -> str:
    """폴더 비교 키(같은 폴더면 같은 값). `path`는 정규화한 절대 경로다.

    >>> folder_key("C:\\\\Work\\\\App\\\\", flavor="windows")
    'c:\\\\work\\\\app'
    >>> rules = load_path_rules({"case_insensitive": ["/mnt/?"]})
    >>> folder_key("/mnt/c/Work", flavor="posix", rules=rules), folder_key("/a/B", flavor="posix")
    ('/mnt/c/work', '/a/B')
    """
    fl = flavor or host_flavor()
    key = path_key(path, fl)
    if fl == "posix" and rules is not None and any(r.matches(key) for r in rules.case_insensitive):
        key = key.casefold()
    return key


def folder_within(
    path: str,
    root: str,
    *,
    flavor: PathFlavor | None = None,
    rules: PathRules | None = None,
) -> bool:
    """`path`가 `root`와 같거나 그 아래인가(정규화한 절대 경로끼리).

    >>> folder_within("/w/app/src", "/w/app", flavor="posix")
    True
    >>> folder_within("/w/apple", "/w/app", flavor="posix")
    False
    """
    fl = flavor or host_flavor()
    return is_within(
        folder_key(path, flavor=fl, rules=rules), [folder_key(root, flavor=fl, rules=rules)], fl
    )


def path_relation(
    a: str, b: str, *, flavor: PathFlavor | None = None, rules: PathRules | None = None
) -> PathRelation | None:
    """b가 a에 대해 같음(`same`)·상위(`parent`, b가 a를 포함)·하위(`child`)인가. 무관하면 None.

    >>> path_relation("/w/app", "/w/app/", flavor="posix")
    'same'
    >>> path_relation("/w/app/x", "/w/app", flavor="posix")
    'parent'
    >>> path_relation("/w", "/w/a", flavor="posix")
    'child'
    """
    fl = flavor or host_flavor()
    ka, kb = folder_key(a, flavor=fl, rules=rules), folder_key(b, flavor=fl, rules=rules)
    if ka == kb:
        return "same"
    if is_within(ka, [kb], fl):
        return "parent"
    if is_within(kb, [ka], fl):
        return "child"
    return None


def resolve_folder(
    value: object,
    *,
    base_dir: str | None = None,
    flavor: PathFlavor | None = None,
    environ: Mapping[str, str] = _NO_ENV,
) -> str | None:
    """등록부의 폴더 값 → 정규화한 절대 경로(파일 시스템을 읽지 않음).

    상대 경로(옛 `working_directory`)는 `base_dir`(설정 파일 폴더) 기준으로 절대화한다
    (design §PI.8).
    빈 값·경로가 아닌 값·`base_dir` 없는 상대 경로는 None(상태 `folder_unset`).

    >>> resolve_folder("sub/../app/", base_dir="/w", flavor="posix")
    '/w/app'
    >>> resolve_folder("c:/Work", flavor="windows"), resolve_folder("rel", flavor="posix")
    ('C:\\\\Work', None)
    """
    if not isinstance(value, str) or not value.strip():
        return None
    fl = flavor or host_flavor()
    return absolute_path(value.strip(), base_dir, flavor=fl, environ=environ)


def absolute_path(
    text: str,
    base_dir: str | None,
    *,
    flavor: PathFlavor,
    environ: Mapping[str, str] = _NO_ENV,
) -> str | None:
    """경로 글자 → 정규화한 절대 경로. 상대 경로만 `base_dir`에 붙인다(다른 OS 경로·풀 수 없는 `~`·
    `base_dir` 없는 상대 경로는 None). 파일 시스템을 읽지 않는다."""
    try:
        return normalize_lexical(text, flavor=flavor, environ=environ)
    except FolderError as exc:
        if exc.code != FolderErrorCode.RELATIVE or base_dir is None:
            return None
    try:
        return normalize_lexical(
            path_module(flavor).join(base_dir, text), flavor=flavor, environ=environ
        )
    except FolderError:
        return None
