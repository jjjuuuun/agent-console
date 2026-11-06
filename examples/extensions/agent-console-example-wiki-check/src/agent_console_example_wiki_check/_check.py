"""머리말 필수 키 쓰기 검사(X50)와 옵션.

옵션 기본값은 패키지 데이터 `data/defaults.json`이고, 사용자 설정 `wiki.write_checks[].options`가
키마다 덮어쓴다. 키 이름·경로 글롭·심각도·검사할 동작·이슈 코드·문구는 전부 옵션이다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import cache
from importlib.resources import files as package_files
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_console_contracts.wiki import WikiIssue
from agent_console_wiki import check_glob, glob_match

__all__ = [
    "CHECK_ID",
    "FrontMatterKeysCheck",
    "FrontMatterKeysOptions",
    "FrontMatterOptionsError",
    "check_options",
    "default_options",
    "missing_keys",
    "parse_options",
]

CHECK_ID = "example.front-matter-keys"
"""기본 검사 id(= entry point 이름 = 사용자 설정 `wiki.write_checks[].id`)."""


class FrontMatterOptionsError(ValueError):
    """옵션이 틀렸다. `problems` = (옵션 위치, 이유) 목록(값 원문은 싣지 않는다)."""

    def __init__(self, problems: list[tuple[str, str]]) -> None:
        self.problems = problems
        super().__init__("; ".join(f"{where}: {why}" for where, why in problems))


class FrontMatterKeysOptions(BaseModel):
    """검사 옵션(모르는 키는 거부)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    keys: list[str] = Field(description="머리말에 있어야 하는 키(비면 검사하지 않음).")
    paths: list[str] = Field(description="검사할 페이지 경로 글롭(위키 폴더 기준, 확장자 없음).")
    severity: Literal["error", "warning", "info"] = Field(
        description="빠진 키의 심각도. error = 쓰기 거부, 나머지 = 저장하고 경고."
    )
    ops: list[str] = Field(description="검사할 쓰기 동작(create·update·move·delete).")
    allow_empty: bool = Field(description="빈 값(null·빈 문자열·빈 목록)도 있다고 볼지.")
    code: str = Field(min_length=1, description="이슈 코드.")
    message: str = Field(description="이슈 문장. `{missing}` = 빠진 키를 쉼표로 이은 것.")

    @field_validator("keys")
    @classmethod
    def _keys(cls, value: list[str]) -> list[str]:
        if any(not k for k in value):
            raise ValueError("빈 키 이름은 쓸 수 없습니다")
        return list(dict.fromkeys(value))

    @field_validator("paths")
    @classmethod
    def _paths(cls, value: list[str]) -> list[str]:
        for pattern in value:
            reason = check_glob(pattern)
            if reason is not None:
                raise ValueError(reason)
        return value


@cache
def _defaults_text() -> str:
    return (package_files(__package__) / "data" / "defaults.json").read_text(encoding="utf-8")


def default_options() -> dict[str, Any]:
    """패키지 데이터 기본 옵션(사본)."""
    loaded: dict[str, Any] = json.loads(_defaults_text())
    return loaded


def _problems(exc: ValidationError) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for err in exc.errors(include_input=False, include_url=False):
        where = "/" + "/".join(str(p) for p in err["loc"]) if err["loc"] else ""
        out.append((where, str(err["msg"])))
    return out


def parse_options(options: Mapping[str, Any] | None) -> FrontMatterKeysOptions:
    """기본값 위에 사용자 옵션을 덮어 검사한다.

    Raises:
        FrontMatterOptionsError: 모르는 키·틀린 값·틀린 글롭.
    """
    merged = {**default_options(), **dict(options or {})}
    try:
        return FrontMatterKeysOptions.model_validate(merged)
    except ValidationError as exc:
        raise FrontMatterOptionsError(_problems(exc)) from None


def check_options(options: Mapping[str, Any] | None) -> list[tuple[str, str]]:
    """저장 전 검사용: (옵션 위치, 이유) 목록. 맞으면 빈 목록."""
    try:
        parse_options(options)
    except FrontMatterOptionsError as exc:
        return exc.problems
    return []


def _present(value: Any, allow_empty: bool) -> bool:
    if allow_empty:
        return True
    return value is not None and value != "" and value != [] and value != {}


def missing_keys(
    front_matter: Mapping[str, Any], keys: Sequence[str], *, allow_empty: bool = False
) -> list[str]:
    """`keys` 중 머리말에 없는(또는 빈) 키, 순서는 `keys` 그대로."""
    return [k for k in keys if k not in front_matter or not _present(front_matter[k], allow_empty)]


class FrontMatterKeysCheck:
    """머리말에 필요한 키가 없으면 이슈 하나를 내는 쓰기 검사(`agent_console_wiki.WikiWriteCheck`).

    Args:
        options: 사용자 설정 `wiki.write_checks[].options`(기본값 위에 덮음).
        check_id: 검사 id. 같은 클래스를 다른 id로 등록할 때 바꾼다.

    Raises:
        FrontMatterOptionsError: 옵션이 틀림(mod-wiki는 `wiki.settings_invalid` 경고로 보이고
            이 검사를 쓰지 않는다).
    """

    def __init__(
        self, options: Mapping[str, Any] | None = None, *, check_id: str = CHECK_ID
    ) -> None:
        self.id = check_id
        self.options = parse_options(options)

    def check(self, subject: Mapping[str, Any], text: str) -> Sequence[WikiIssue]:
        """판단 대상 `{change, author, page, before}`의 `page.front_matter`를 본다."""
        opts = self.options
        if not opts.keys:
            return []
        op = str((subject.get("change") or {}).get("op") or "")
        if op not in opts.ops:
            return []
        page = subject.get("page") or {}
        path = str(page.get("path") or "")
        if not any(glob_match(g, path) for g in opts.paths):
            return []
        front = page.get("front_matter") or {}
        if not isinstance(front, Mapping):
            front = {}
        missing = missing_keys(front, opts.keys, allow_empty=opts.allow_empty)
        if not missing:
            return []
        return [
            WikiIssue(
                severity=opts.severity,
                code=opts.code,
                message=opts.message.replace("{missing}", ", ".join(missing)),
                page=path or None,
                rule_id=self.id,
                details={"missing": missing},
            )
        ]
