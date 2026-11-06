"""정의 종류(`ac-store` `DefinitionKind`) 만들기 — 위키·위키 규칙(design §7R.1.1·§7R.1.2, X44).

종류 이름·폴더 이름은 호출자 데이터(서버 모듈 설치자 옵션)다. 이 패키지는 저장 규칙만 정한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from agent_console_contracts.wiki import WikiDefinition, WikiRulesDefinition
from agent_console_store import DefinitionKind

__all__ = ["RULES_CONTENT_FIELD", "definition_kinds"]

RULES_CONTENT_FIELD: Final = "content"
"""위키 규칙의 본문 파일 필드(`WikiRulesDefinition.content`) — 본문 폴더 = 지침·페이지 틀 파일들."""


def definition_kinds(
    *,
    wiki_kind: str,
    wiki_dir: str,
    rules_kind: str,
    rules_dir: str,
    summary_fields: Sequence[str] = (),
) -> tuple[DefinitionKind, DefinitionKind]:
    """(위키 종류, 위키 규칙 종류).

    - 위키: 단일 YAML(본문 없음), `library=False`(프로젝트·단독 공간에만 — 페이지는 폴더 소유), 옮길
      수 있음, 저장은 `If-Match` 필수.
    - 위키 규칙: 여러 파일 본문(`multi_file`, 지침·페이지 틀), 라이브러리·프로젝트 둘 다, 옮길 수
      있음, 저장은 `If-Match` 필수.

    Args:
        wiki_kind / wiki_dir: 위키 종류 이름·폴더.
        rules_kind / rules_dir: 위키 규칙 종류 이름·폴더.
        summary_fields: 목록 요약에 복사할 최상위 문자열 필드(예 `description`).
    """
    wiki = DefinitionKind(
        name=wiki_kind,
        directory=wiki_dir,
        model=WikiDefinition,
        require_version=True,
        summary_fields=tuple(summary_fields),
        library=False,
    )
    rules = DefinitionKind(
        name=rules_kind,
        directory=rules_dir,
        model=WikiRulesDefinition,
        require_version=True,
        content_field=RULES_CONTENT_FIELD,
        multi_file=True,
        summary_fields=tuple(summary_fields),
    )
    return wiki, rules
