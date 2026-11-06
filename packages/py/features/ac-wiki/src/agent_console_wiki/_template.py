"""페이지 틀 렌더(design §7R.18 Q7): 틀 본문·경로 틀을 `ac-text-template`로 채운다(쓰지 않음).

앱이 채우는 이름(`WIKI_TEMPLATE_BUILTIN_VARIABLES`): `title`(받은 제목), `slug`(제목에서 만든 경로
조각 — `slugify`), `date`(주입한 오늘 날짜 `YYYY-MM-DD`). 사용자가 선언한 변수는 `values`로 받는다.
틀이 쓰는데 값이 없는 이름은 빈 글자로 채우고 `missing`에 적는다. 경로 틀을 채운 결과가 페이지 경로
규칙에 어긋나면 `path=null` + `wiki.invalid_path`.
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
from collections.abc import Mapping

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import WikiIssue, WikiPageTemplate, WikiTemplateRender
from agent_console_text_template import render_template, template_variables

from ._errors import WikiPathError
from ._paths import check_page_path

__all__ = ["render_page_template", "slugify"]

_FORBIDDEN = re.compile(r'[\\/:*?"<>|#\[\]\x00-\x1f\x7f]')
_SPACES = re.compile(r"\s+")
_DASHES = re.compile(r"-{2,}")


def slugify(title: str) -> str:
    """제목 → 경로 조각 하나: 소문자, 공백 → `-`, 경로 금지 문자 제거, 한글 유지, 앞뒤 `-`·`.` 뺌.

    >>> slugify("API 버전 정하기 (v2)")
    'api-버전-정하기-(v2)'
    >>> slugify("  ../a/b: c  ")
    'ab-c'
    """
    text = unicodedata.normalize("NFC", title).lower()
    text = _FORBIDDEN.sub("", text)
    text = _SPACES.sub("-", text.strip())
    text = _DASHES.sub("-", text)
    return text.strip("-.")


def render_page_template(
    template: WikiPageTemplate,
    content: str,
    *,
    title: str | None = None,
    values: Mapping[str, str] | None = None,
    today: _dt.date,
) -> WikiTemplateRender:
    """페이지 틀 하나를 채운다(서버 없이 쓰는 순수 함수).

    Args:
        template: 페이지 틀(경로 틀 `path`·선언 변수).
        content: 틀 본문(규칙 본문 파일).
        title: 새 페이지 제목(`title`·`slug`).
        values: 선언 변수 이름 → 값. 앱이 채우는 이름과 겹치면 앱 값이 이긴다.
        today: 오늘 날짜(`date`, 서버 시계로 호출자가 준다).

    Returns:
        `WikiTemplateRender{path, content, missing, issues}`.
    """
    builtin = {
        "title": title or "",
        "slug": slugify(title or ""),
        "date": today.isoformat(),
    }
    filled: dict[str, str] = {k: v for k, v in (values or {}).items() if isinstance(v, str)}
    filled.update(builtin)
    used = template_variables([content, template.path or ""])
    missing = sorted(name for name in used if not filled.get(name))
    for name in used:
        filled.setdefault(name, "")
    body = render_template(content, filled)
    issues: list[WikiIssue] = []
    path: str | None = None
    if template.path:
        raw = render_template(template.path, filled)
        try:
            path = check_page_path(raw)
        except WikiPathError as exc:
            issues.append(
                WikiIssue(
                    severity="warning",
                    code=KnownIssueCodes.WIKI_INVALID_PATH,
                    message="채운 경로를 페이지 경로로 쓸 수 없습니다. 경로를 직접 적으세요.",
                    path="/path",
                    rule_id=template.id,
                    details={"reason": exc.reason},
                )
            )
    return WikiTemplateRender(path=path, content=body, missing=missing, issues=issues)
