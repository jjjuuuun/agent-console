"""실행 프로필 입력 틀: 변수 표·값·치환(`ac-text-template`), design §6R.1.5·§6R.18 Q9.

입력이 기록 DB·로그에 남으므로 절대 경로는 넣지 않는다(`spec_dir`는 프로젝트 폴더 기준 상대 경로).
변수 이름은 `\\w`만 쓸 수 있어(`ac-text-template` 규칙) 문서 id·필드 이름의 다른 글자는 `_`로
바꾼다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from agent_console_contracts.sdd import (
    ParsedTask,
    RunProfile,
    SpecDefinition,
    SpecDocument,
    SpecTemplate,
    TemplateVariable,
)
from agent_console_text_template import DEFAULT_MAX_RENDER_CHARS, fill_value

from ._errors import SpecPathError

__all__ = [
    "FIELD_VARIABLE_PREFIX",
    "check_relative_dir",
    "document_variable",
    "field_variable",
    "render_run_input",
    "run_input_values",
    "run_input_variables",
]

FIELD_VARIABLE_PREFIX = "task_field_"
"""작업 필드 변수 접두(`task_field_<필드>`). 필드 이름은 데이터라 어떤 이름이든 이 접두로 쓴다."""

_NON_WORD = re.compile(r"\W")
_DRIVE = re.compile(r"^[A-Za-z]:")
_LIST_JOIN = ", "

# (이름, 설명, 예) — 이름 표는 코드 개념(입력 틀이 읽을 수 있는 작업·스펙 값)이다.
_FIXED: tuple[tuple[str, str, str | None], ...] = (
    ("task_id", "작업 줄 머리의 작업 id입니다(없으면 빈 값).", "2.3"),
    ("task_key", "작업 키입니다(작업 id, 없으면 문서·순번).", "2.3"),
    ("task_title", "작업 제목입니다.", None),
    ("task_body", "작업 아래 하위 목록·문단 원문입니다.", None),
    ("task_status", "지금 작업 상태 id입니다.", "todo"),
    ("task_requirements", "작업이 가리키는 요구 id(쉼표로 이음)입니다.", "R1.1, R1.2"),
    ("task_dependencies", "작업이 기다리는 작업 키(쉼표로 이음)입니다.", "2.1, 2.2"),
    ("stage_id", "작업이 속한 단계 id입니다(없으면 빈 값).", None),
    ("stage_title", "작업이 속한 단계 제목입니다(없으면 빈 값).", None),
    ("spec_id", "스펙 id입니다.", None),
    ("spec_name", "스펙 이름입니다.", None),
    ("spec_dir", "스펙 문서 폴더입니다(프로젝트 폴더 기준 상대 경로).", None),
)


def _word(name: str) -> str:
    return _NON_WORD.sub("_", name)


def document_variable(document_id: str) -> str:
    """문서 파일 변수 이름(`doc_<문서 id>_file`, `\\w` 밖 글자는 `_`)."""
    return f"doc_{_word(document_id)}_file"


def field_variable(field: str) -> str:
    """작업 필드 변수 이름(`task_field_<필드>`, `\\w` 밖 글자는 `_`)."""
    return f"{FIELD_VARIABLE_PREFIX}{_word(field)}"


def run_input_variables(
    documents: Sequence[SpecDocument], *, fields: Iterable[str] = ()
) -> list[TemplateVariable]:
    """입력 틀에서 쓸 수 있는 변수 표(스펙·문서 틀 공용, `GET …/variables`).

    Args:
        documents: 문서 목록(문서마다 `doc_<id>_file`).
        fields: 이름을 미리 보일 작업 필드(예: 문법 `roles`의 필드). 다른 필드도
            `task_field_<필드>`로 쓸 수 있다.

    Returns:
        고정 변수 → `task_field_<필드>` 안내 → 주어진 필드 → 문서 파일 순서.
    """
    out = [TemplateVariable(name=n, description=d, example=e) for n, d, e in _FIXED]
    out.append(
        TemplateVariable(
            name=f"{FIELD_VARIABLE_PREFIX}<필드>",
            description="작업 줄의 [필드: 값] 값입니다. <필드> 자리에 필드 이름을 씁니다.",
            example=f"{FIELD_VARIABLE_PREFIX}owner",
        )
    )
    seen = {v.name for v in out}
    for f in fields:
        name = field_variable(f)
        if name not in seen:
            seen.add(name)
            out.append(TemplateVariable(name=name, description=f"작업 필드 '{f}' 값입니다."))
    for doc in documents:
        name = document_variable(doc.id)
        if name not in seen:
            seen.add(name)
            out.append(
                TemplateVariable(
                    name=name,
                    description=f"문서 '{doc.title}'의 파일 이름입니다(스펙 폴더 기준).",
                    example=doc.file,
                )
            )
    return out


def check_relative_dir(path: str) -> str:
    """프로젝트 폴더 기준 상대 폴더 경로인지 검사하고 `/`로 정규화한다(빈 값 = 폴더 루트).

    Raises:
        SpecPathError: 절대 경로·드라이브·`..`.
    """
    norm = path.replace("\\", "/")
    if norm.startswith("/") or _DRIVE.match(norm):
        raise SpecPathError(path, "invalid")
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise SpecPathError(path, "invalid")
    return "/".join(parts)


def run_input_values(
    task: ParsedTask,
    spec: SpecDefinition | SpecTemplate,
    *,
    spec_dir: str,
) -> dict[str, str]:
    """입력 틀 변수 값(모두 문자열).

    Args:
        task: 실행할 작업.
        spec: 스펙.
        spec_dir: 스펙 문서 폴더(프로젝트 폴더 기준 상대 경로).

    Raises:
        SpecPathError: `spec_dir`이 절대 경로이거나 `..`를 포함한다.
    """
    values: dict[str, str] = {
        "task_id": task.id or "",
        "task_key": task.key,
        "task_title": task.title,
        "task_body": task.body,
        "task_status": task.status,
        "task_requirements": _LIST_JOIN.join(task.requirements),
        "task_dependencies": _LIST_JOIN.join(task.dependencies),
        "stage_id": task.stage.id if task.stage else "",
        "stage_title": task.stage.title if task.stage else "",
        "spec_id": spec.id,
        "spec_name": spec.name,
        "spec_dir": check_relative_dir(spec_dir),
    }
    for key, value in task.fields.items():
        values.setdefault(field_variable(key), value)
    for doc in spec.documents:
        values.setdefault(document_variable(doc.id), doc.file)
    return values


def render_run_input(
    profile: RunProfile,
    task: ParsedTask,
    spec: SpecDefinition | SpecTemplate,
    *,
    spec_dir: str,
    extra: Mapping[str, str] | None = None,
    max_chars: int = DEFAULT_MAX_RENDER_CHARS,
) -> dict[str, Any]:
    """실행 프로필 `input`을 작업 값으로 치환한 실행 입력.

    모르는 변수는 원문 그대로 남는다(규칙 검사 `sdd.unknown_variable`이 미리 알린다). 값 안의
    `{…}`는 다시 치환하지 않는다.

    Args:
        profile: 실행 프로필.
        task: 실행할 작업.
        spec: 스펙.
        spec_dir: 스펙 문서 폴더(프로젝트 폴더 기준 상대 경로, 절대 경로 거부).
        extra: 더할 변수(호출자 몫 — 같은 이름이면 작업 값이 이긴다).
        max_chars: 문자열 하나의 치환 결과 상한.

    Raises:
        SpecPathError: `spec_dir`이 상대 경로가 아니다.
    """
    values: dict[str, str] = dict(extra or {})
    values.update(run_input_values(task, spec, spec_dir=spec_dir))
    filled = fill_value(dict(profile.input), values, max_chars=max_chars)
    assert isinstance(filled, dict)
    return filled
