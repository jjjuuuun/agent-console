"""에이전트 위키 도구 묶음 `WikiToolkit`(design §7R.1.4, 7R.10).

런타임(실행 엔진·에이전트 노드·SDK)을 모른다. 도구 스펙(`WikiToolSpec`)은 이름·설명·입력
스키마·비동기 호출 함수뿐이라 플랫폼 도구, Claude Agent SDK `@tool`, MCP 서버 어느 쪽으로도 감쌀
수 있다(메모리 `MemoryToolkit`과 같은 모양).

- 도구 7개(동작 = 계약 어휘 `WIKI_ACCESS_OPS`): search·read(section)·list·links·
  write(replace·append·section + template)·move·delete. 모델에게 보이는 이름·설명·결과 머리 줄·
  결과 최대 글자는 접근 설정(`WikiAccessConfig`) 데이터, 매개변수 설명·결과 줄·실패 문구는
  패키지 데이터 `data/tool_text.yaml`.
- 위키 고르기: 입력 `wiki`(생략 = 기본 위키)가 접근 설정에 없거나 그 동작을 허용하지 않으면
  `wiki.denied`, 설정에는 있는데 이 실행 공간에 없으면 `wiki.wiki_unavailable`.
- 모든 동작은 `WikiRepository` 메서드로 한다(쓰기 규칙·비밀 검사·기록·색인은 저장소 몫).
  append·section·template 쓰기는 툴킷이 본문을 만든 뒤 `write(if_hash=)`로 부른다.
- 결과는 텍스트(비밀 가림 `repository.secrets.redact` 뒤 `max_result_chars`로 자름), 실패는
  예외가 아니라 `is_error` + 사유 코드.
- 이벤트 payload(`WikiEventPayload`)에는 **본문·검색어 원문을 싣지 않는다**(크기·해시만).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import inspect
import threading
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any, Final, Protocol

from ruamel.yaml import YAML

from agent_console_contracts.constants import ErrorCodes, KnownIssueCodes
from agent_console_contracts.wiki import (
    WIKI_ACCESS_OPS,
    WIKI_EVENT_PREFIX,
    KnownWikiAuthorKinds,
    WikiAccessConfig,
    WikiAuthor,
    WikiEventPayload,
    WikiHeading,
    WikiIssue,
)
from agent_console_text_template import render_template, template_variables

from ._errors import (
    WikiConflictError,
    WikiError,
    WikiPageExistsError,
    WikiPageNotFoundError,
    WikiPathError,
    WikiRuleRejectedError,
    WikiSecretRejectedError,
    WikiSectionNotFoundError,
    WikiTemplateNotFoundError,
    WikiTooLargeError,
)
from ._parse import parse_page
from ._repository import WikiRepository, WriteOutcome
from ._text import line_starts

__all__ = [
    "TOOL_TEXT_RESOURCE",
    "WIKI_WRITE_MODES",
    "PageComposition",
    "WikiFailure",
    "WikiToolOutcome",
    "WikiToolSpec",
    "WikiToolTarget",
    "WikiToolText",
    "WikiToolkit",
    "WikiWriteBudget",
    "WriteBudget",
    "access_wikis",
    "compose_write",
    "default_wiki",
    "format_author",
    "format_time",
    "load_tool_text",
    "replace_section",
    "section_span",
    "wiki_allowed",
    "wiki_failure",
    "wiki_instructions",
    "wiki_ops",
    "wikis_for",
]

TOOL_TEXT_RESOURCE: Final = "data/tool_text.yaml"
"""도구 문구 기본 데이터 위치(패키지 안 상대 경로)."""

_ERROR: Final = "error"
_RENDER_CHARS: Final = 10_000_000
_MUTATING: Final = frozenset({"write", "move", "delete"})
WIKI_WRITE_MODES: Final[tuple[str, ...]] = ("replace", "append", "section")
"""쓰기 방식(도구 입력 `mode`·`wiki-update` 노드 설정): 통째로 바꾸기·끝에 덧붙이기·절 바꾸기."""
_WRITE_MODES: Final = WIKI_WRITE_MODES


# ---------------------------------------------------------------- 문구


@dataclass(frozen=True, slots=True)
class WikiToolText:
    """도구 문구(데이터, `data/tool_text.yaml`). 도구 이름·설명·머리 줄은 접근 설정이 정한다.

    Attributes:
        inputs: 매개변수 이름 → 설명(`wiki`는 `{choices}` 자리).
        lines: 결과 줄 틀(키 → 틀, 예 `search_item`·`written`).
        errors: 이유(사유 코드 또는 문구 키) → 실패 문장.
    """

    inputs: Mapping[str, str]
    lines: Mapping[str, str]
    errors: Mapping[str, str]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> WikiToolText:
        """데이터 → 문구. `inputs`·`errors`가 없으면 `KeyError`, 나머지 글자 값은 결과 줄 틀."""
        return cls(
            inputs={str(k): str(v) for k, v in data["inputs"].items()},
            lines={
                str(k): str(v)
                for k, v in data.items()
                if k not in ("inputs", "errors", "version") and isinstance(v, str)
            },
            errors={str(k): str(v) for k, v in data["errors"].items()},
        )

    def line(self, key: str, values: Mapping[str, Any]) -> str:
        """결과 줄 하나(없는 키 = 빈 글자)."""
        return _render(self.lines.get(key, ""), values)

    def error(self, key: str, values: Mapping[str, Any]) -> str:
        """실패 문장(없는 키 = `error` 문장)."""
        return _render(self.errors.get(key) or self.errors.get(_ERROR, ""), values)


def load_tool_text() -> WikiToolText:
    """패키지 기본 도구 문구(`data/tool_text.yaml`)."""
    text = files("agent_console_wiki").joinpath(TOOL_TEXT_RESOURCE).read_text("utf-8")
    return WikiToolText.from_mapping(YAML(typ="safe").load(text))


def _render(template: str, values: Mapping[str, Any]) -> str:
    return render_template(template, values, max_chars=_RENDER_CHARS)


# ---------------------------------------------------------------- 접근 판단(순수 함수)


def access_wikis(access: WikiAccessConfig) -> list[str]:
    """접근 설정에 적힌 위키 id(적힌 순서, 겹침 없음)."""
    return list(dict.fromkeys(entry.wiki for entry in access.wikis))


def wiki_ops(access: WikiAccessConfig, wiki: str) -> frozenset[str]:
    """위키 하나에 허용한 동작(같은 위키가 여러 번 적히면 합친다)."""
    return frozenset(op for entry in access.wikis if entry.wiki == wiki for op in entry.access)


def wiki_allowed(access: WikiAccessConfig, wiki: str, op: str) -> bool:
    """`wiki`에서 `op`를 허용했는가."""
    return op in wiki_ops(access, wiki)


def default_wiki(access: WikiAccessConfig) -> str | None:
    """입력 `wiki`를 생략했을 때 쓰는 위키(`default_wiki`, 없으면 첫 위키)."""
    if access.default_wiki:
        return access.default_wiki
    wikis = access_wikis(access)
    return wikis[0] if wikis else None


def wikis_for(access: WikiAccessConfig, op: str) -> list[str]:
    """`op`를 허용한 위키(적힌 순서)."""
    return [w for w in access_wikis(access) if wiki_allowed(access, w, op)]


# ---------------------------------------------------------------- 절 찾기·바꾸기(순수 함수)


def _heading_key(text: str) -> str:
    return text.strip().lstrip("#").strip()


def section_span(
    text: str, headings: Sequence[WikiHeading], section: str
) -> tuple[int, int, int] | None:
    """제목 `section`의 절 위치(코드 포인트) `(제목 시작, 절 본문 시작, 절 끝)`.

    절 = 그 제목 줄부터 같거나 높은 단계의 다음 제목 앞까지. 제목은 앞뒤 공백·앞 `#`을 떼고
    먼저 그대로, 없으면 대소문자를 접어 비교한다(같은 제목이 여럿이면 첫 것).
    `headings`는 `ParsedPage.headings`(줄 번호가 `text` 기준).
    밑줄 제목(setext)의 밑줄 줄은 제목에 넣는다.

    >>> from agent_console_contracts.wiki import WikiHeading
    >>> text = "# A\\nx\\n## B\\ny\\n# C\\n"
    >>> hs = [WikiHeading(level=1, text="A", line=1), WikiHeading(level=2, text="B", line=3),
    ...       WikiHeading(level=1, text="C", line=5)]
    >>> a, b, c = section_span(text, hs, "b")
    >>> text[a:c], text[b:c]
    ('## B\\ny\\n', 'y\\n')
    """
    want = _heading_key(section)
    if not want:
        return None
    order = list(headings)
    found = next((i for i, h in enumerate(order) if _heading_key(h.text) == want), None)
    if found is None:
        folded = want.casefold()
        found = next(
            (i for i, h in enumerate(order) if _heading_key(h.text).casefold() == folded), None
        )
    if found is None:
        return None
    head = order[found]
    starts = line_starts(text)
    total = len(starts)

    def at(line: int) -> int:  # 줄 번호(1부터) → 시작 위치
        return starts[line - 1] if 0 < line <= total else len(text)

    start = at(head.line)
    body_line = head.line + 1
    if head.level <= 2 and body_line <= total:
        under = text[at(body_line) : at(body_line + 1)].strip()
        if under and set(under) <= {"=", "-"}:
            body_line += 1
    body = at(body_line)
    nxt = next(
        (h for h in order[found + 1 :] if h.line > head.line and h.level <= head.level), None
    )
    end = at(nxt.line) if nxt is not None else len(text)
    return start, min(body, end), end


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _ends_line(text: str) -> bool:
    return text.endswith(("\n", "\r"))


def replace_section(text: str, span: tuple[int, int, int], body: str) -> str:
    """절 본문(제목 줄 아래)을 `body`로 바꾼 글. 제목 줄·다른 절의 바이트는 그대로다.

    >>> replace_section("# A\\nold\\n# B\\n", (0, 4, 8), "new")
    '# A\\nnew\\n# B\\n'
    """
    _, body_start, end = span
    nl = _newline(text)
    head = text[:body_start]
    if head and not _ends_line(head):
        head += nl
    if body and end < len(text) and not _ends_line(body):
        body += nl
    return head + body + text[end:]


def _append(text: str, addition: str) -> str:
    if text and not _ends_line(text):
        text += _newline(text)
    return text + addition


@dataclass(frozen=True, slots=True)
class PageComposition:
    """`compose_write` 결과: 쓸 본문과 `WikiRepository.write` 조건.

    Attributes:
        content: 새 본문 전체.
        create_only: 새 페이지로만 쓴다(그사이 생기면 `WikiPageExistsError`).
        if_hash: 이 해시일 때만 쓴다(읽은 뒤 바뀌면 `WikiConflictError`).
    """

    content: str
    create_only: bool = False
    if_hash: str | None = None


def compose_write(
    repo: WikiRepository,
    path: str,
    *,
    content: str | None,
    mode: str = "replace",
    section: str | None = None,
    template: str | None = None,
    title: str | None = None,
    if_hash: str | None = None,
) -> PageComposition:
    """쓰기 방식대로 새 본문을 만든다(쓰지 않는다). 위키 도구 `write`와 다른 쓰기 주체가 같이 쓴다.

    - `template`: 새 페이지만. 틀을 채운 본문 뒤에 `content`를 덧붙인다(있으면).
    - `replace`: `content`가 본문 전체(페이지가 없으면 만든다).
    - `append`: 지금 본문 끝에 `content`(줄을 맞춰 붙임, 페이지가 없으면 `content`로 만든다).
    - `section`: 제목 `section`의 절 본문을 `content`로 바꾼다(제목 줄·다른 절은 그대로).

    Args:
        repo: 위키 저장소. path: 페이지 경로. content: 쓸 글(틀만 쓰면 None).
        mode: `WIKI_WRITE_MODES` 중 하나. section: 절 제목(`section` 방식에서 필수).
        template: 페이지 틀 id. title: 틀의 제목. if_hash: 지금 본문 해시 조건.

    Raises:
        ValueError: 모르는 방식, `section` 방식에 제목 없음, 쓸 글도 틀도 없음.
        WikiConflictError: `if_hash`가 지금 본문과 다름. WikiPageExistsError: 틀인데 이미 있음.
        WikiPageNotFoundError: `section` 방식인데 페이지가 없음. WikiSectionNotFoundError: 절 없음.
        WikiTemplateNotFoundError: 틀 없음.

    >>> from agent_console_wiki import compile_syntax, effective_syntax
    >>> from agent_console_wiki.testing import MemoryWikiPages
    >>> pages = MemoryWikiPages({"log.md": "# 기록\\n- 첫 줄\\n"})
    >>> repo = WikiRepository(pages, wiki_id="notes", syntax=compile_syntax(effective_syntax()))
    >>> compose_write(repo, "log", content="- 둘째 줄\\n", mode="append").content
    '# 기록\\n- 첫 줄\\n- 둘째 줄\\n'
    """
    if mode not in WIKI_WRITE_MODES or (mode == "section" and not section):
        raise ValueError(f"쓰기 방식이 맞지 않습니다: {mode!r}")
    if template is None and content is None:
        raise ValueError("쓸 글도 틀도 없습니다")
    current = repo.current(path)
    if if_hash is not None and (current is None or current.content_hash != if_hash):
        raise WikiConflictError(
            path, expected=if_hash, actual=current.content_hash if current else None
        )
    if template:
        if current is not None:
            raise WikiPageExistsError(path)
        rendered = repo.render_template(template, title=title)
        body = _append(rendered.content, content) if content else rendered.content
        return PageComposition(body, create_only=True)
    assert content is not None
    if mode == "replace":
        return PageComposition(content, if_hash=if_hash)
    if current is None:
        if mode == "section":
            raise WikiPageNotFoundError(path, has_history=repo.has_history(path))
        return PageComposition(content, create_only=True)
    text = current.text
    if mode == "append":
        return PageComposition(_append(text, content), if_hash=current.content_hash)
    headings = parse_page(current.path, current.data, repo.syntax).headings
    span = section_span(text, headings, section or "")
    if span is None:
        raise WikiSectionNotFoundError(path, section or "")
    return PageComposition(replace_section(text, span, content), if_hash=current.content_hash)


# ---------------------------------------------------------------- 스펙·결과


@dataclass(frozen=True, slots=True)
class WikiToolOutcome:
    """도구 호출 하나의 결과.

    Attributes:
        text: 모델에게 돌려줄 텍스트(비밀 가림·최대 글자 적용).
        is_error: 실패 결과인지(실행은 계속된다).
        code: 실패 사유 코드(`wiki.*`, 성공이면 None).
        event_type: 이벤트 type(`wiki.<op>`).
        event: 이벤트 payload(본문·검색어 원문 없음).
        issues: 쓰기·옮기기 경고(성공이어도 있을 수 있음).
    """

    text: str
    is_error: bool
    code: str | None
    event_type: str
    event: WikiEventPayload
    issues: list[WikiIssue] = field(default_factory=list)


type WikiToolCall = Callable[[Mapping[str, Any], str | None], Awaitable[WikiToolOutcome]]
"""(모델이 준 입력, 도구 호출 id 또는 None) → 결과."""

type WikiEventSink = Callable[[str, WikiEventPayload], Awaitable[None] | None]
"""이벤트 받는 쪽(type, payload). 동기·비동기 모두 받는다."""


@dataclass(frozen=True, slots=True)
class WikiToolSpec:
    """도구 하나. `call(args, call_id)`를 부르면 처리하고 이벤트를 낸다.

    Attributes:
        op: 동작(계약 어휘 `WIKI_ACCESS_OPS`).
        name: 모델에게 보이는 이름(접근 설정 데이터).
        description: 모델에게 보이는 설명(데이터).
        input_schema: 입력 JSON Schema(최상위 object).
        call: 비동기 호출 함수.
    """

    op: str
    name: str
    description: str
    input_schema: Mapping[str, Any]
    call: WikiToolCall = field(compare=False)


class WikiWriteBudget(Protocol):
    """쓰기 횟수 한도(실행 하나가 함께 쓴다). `take()`가 거짓이면 `wiki.rate_limited`."""

    def take(self) -> bool:
        """한 번 쓴다. 남은 횟수가 없으면 False."""
        ...


class WriteBudget:
    """`WikiWriteBudget` 기본 구현. None = 한도 없음. 스레드 안전.

    >>> b = WriteBudget(1)
    >>> b.take(), b.take()
    (True, False)
    """

    def __init__(self, limit: int | None) -> None:
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        """한 번 쓴다. 남은 횟수가 없으면 False."""
        with self._lock:
            if self.limit is not None and self.used >= self.limit:
                return False
            self.used += 1
            return True


@dataclass(frozen=True, slots=True)
class WikiToolTarget:
    """도구가 쓸 위키 하나(공간이 준다).

    Attributes:
        repository: 그 위키의 저장소.
        name: 위키 표시 이름(경로 안내 `{wiki_name}`, 비면 위키 id).
        pages_dir: 페이지 폴더(에이전트 작업 폴더 기준 경로, 경로 안내 `{pages_dir}`). 비었는데 안내
            틀이 `pages_dir`를 쓰면 그 위키의 경로 안내를 넣지 않는다.
    """

    repository: WikiRepository
    name: str = ""
    pages_dir: str = ""


type WikiTargetLike = WikiToolTarget | WikiRepository
type WikiResolver = Callable[[str], WikiTargetLike | None]
"""위키 id → 이 실행 공간의 위키(없으면 None = `wiki.wiki_unavailable`)."""


def _as_target(found: WikiTargetLike | None) -> WikiToolTarget | None:
    if found is None or isinstance(found, WikiToolTarget):
        return found
    return WikiToolTarget(found)


def wiki_instructions(
    access: WikiAccessConfig, targets: Iterable[tuple[str, WikiToolTarget]]
) -> list[str]:
    """에이전트 지침 본문(X30 `ToolProvision.instructions`).

    위키마다 합친 규칙 지침(켰을 때)과 경로 안내를 낸다.

    위키는 `targets` 순서, 같은 글은 한 번(규칙을 함께 쓰는 위키). 경로 안내 틀(`path_hint`)이 비면
    안내 없음.

    Args:
        access: 접근 설정(`include_rules_instructions`·`path_hint`).
        targets: (위키 id, 대상) 쌍 — 이 실행에서 쓸 수 있는 위키만.
    """
    out: list[str] = []
    hint = access.path_hint
    hint_vars = template_variables(hint) if hint else set()
    for wiki_id, target in targets:
        if access.include_rules_instructions:
            text = target.repository.rules.instructions.strip()
            if text:
                out.append(text)
        if hint and not ("pages_dir" in hint_vars and not target.pages_dir):
            filled = _render(
                hint,
                {
                    "pages_dir": target.pages_dir,
                    "wiki": wiki_id,
                    "wiki_name": target.name or wiki_id,
                },
            ).strip()
            if filled:
                out.append(filled)
    return list(dict.fromkeys(out))


# ---------------------------------------------------------------- 내부 오류·입력


class _ToolError(Exception):
    def __init__(self, status: str, code: str, *, reason: str | None = None, **values: Any) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.reason = reason or code
        self.values = values
        self.rule_ids: list[str] = []


def _invalid() -> _ToolError:
    return _ToolError(_ERROR, ErrorCodes.VALIDATION_FAILED, reason="invalid_input")


def _string(args: Mapping[str, Any], name: str, *, required: bool = False) -> str | None:
    value = args.get(name)
    if value is None:
        if required:
            raise _invalid()
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise _invalid()
    return value


def _strings(args: Mapping[str, Any], name: str) -> list[str]:
    value = args.get(name)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise _invalid()
    return list(value)


def _integer(args: Mapping[str, Any], name: str) -> int | None:
    value = args.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid()
    return value


def _boolean(args: Mapping[str, Any], name: str, default: bool) -> bool:
    value = args.get(name)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise _invalid()
    return value


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


def _lines(lines: Sequence[int]) -> str:
    return ", ".join(str(n) for n in lines)


def _map_error(exc: BaseException) -> _ToolError:
    """저장소 예외 → 도구 실패(상태·사유 코드·문구 값)."""
    if isinstance(exc, _ToolError):
        return exc
    if isinstance(exc, WikiConflictError):
        return _ToolError("conflict", KnownIssueCodes.WIKI_CONFLICT, hash=exc.actual or "")
    if isinstance(exc, WikiPageExistsError):
        return _ToolError("conflict", exc.code)
    if isinstance(exc, WikiSectionNotFoundError):
        return _ToolError("not_found", exc.code, reason="section_not_found")
    if isinstance(exc, WikiPageNotFoundError | WikiTemplateNotFoundError):
        return _ToolError("not_found", exc.code)
    if isinstance(exc, WikiTooLargeError):
        return _ToolError("too_large", exc.code, limit=f"{exc.limit}={exc.value}")
    if isinstance(exc, WikiRuleRejectedError):
        first = exc.issues[0]
        lines = list(exc.details.get("lines") or [])
        failure = _ToolError(
            "rule_rejected",
            exc.code,
            rule_id=first.rule_id or first.code,
            message=first.message,
            lines=_lines(lines),
        )
        failure.rule_ids = list(dict.fromkeys(i.rule_id or i.code for i in exc.issues))
        return failure
    if isinstance(exc, WikiSecretRejectedError):
        return _ToolError("secret_rejected", exc.code, lines=_lines(exc.lines))
    if isinstance(exc, WikiPathError):
        return _ToolError("invalid_path", exc.code)
    if isinstance(exc, WikiError):
        return _ToolError(_ERROR, exc.code)
    return _ToolError(_ERROR, _ERROR)


@dataclass(frozen=True, slots=True)
class WikiFailure:
    """저장소 예외의 이벤트 값(`WikiEventPayload.status`·`code`·`rule_ids`).

    Attributes:
        status: 이벤트 상태(예 `rule_rejected`·`not_found`·`error`).
        code: 사유 코드(`wiki.*` 등). reason: 문구 키(대개 `code`, 절 없음은 `section_not_found`).
        rule_ids: 거부한 규칙 id(쓰기 규칙 거부일 때).
    """

    status: str
    code: str
    reason: str
    rule_ids: tuple[str, ...] = ()


def wiki_failure(exc: BaseException) -> WikiFailure:
    """저장소 예외 → 이벤트 상태·사유 코드(위키 도구와 같은 분류, 런타임 밖 쓰기 주체가 쓴다).

    >>> wiki_failure(WikiPageExistsError("a")).status
    'conflict'
    """
    failure = _map_error(exc)
    return WikiFailure(failure.status, failure.code, failure.reason, tuple(failure.rule_ids))


def format_author(author: WikiAuthor | None) -> str:
    """쓴 주체 짧은 표시(`<종류>` 또는 `<종류>:<라벨·에이전트 id>`, 없으면 빈 글자).

    >>> format_author(WikiAuthor(kind="agent", agent_id="a1", label="정리꾼"))
    'agent:정리꾼'
    """
    if author is None:
        return ""
    name = author.label or author.agent_id
    return f"{author.kind}:{name}" if name else author.kind


def format_time(epoch: float | None) -> str:
    """Unix epoch 초 → `YYYY-MM-DDTHH:MM:SSZ`(UTC). None은 빈 글자.

    >>> format_time(0)
    '1970-01-01T00:00:00Z'
    """
    if epoch is None:
        return ""
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- 도구 묶음


class WikiToolkit:
    """에이전트 위키 도구 묶음. 접근 설정이 허용한 동작의 도구만 낸다.

    Args:
        wikis: 위키 id → 대상(`WikiToolTarget` 또는 `WikiRepository`). 매핑이나 함수(없으면 None).
            이 실행 공간의 위키만 준다 — 접근 설정에 있어도 여기 없으면 `wiki.wiki_unavailable`.
        access: 리소스 `wiki`의 접근 설정(위키별 허용 동작·도구 이름·설명·머리 줄·최대 글자).
        author: 쓴 주체(기본 `kind=agent`만 — 연동이 실행·노드·라벨을 채워 준다).
        text: 도구 문구(기본 `load_tool_text()`).
        on_event: 호출마다 `(type, payload)`를 받는 쪽(선택, 동기·비동기).
        write_budget: 쓰기 횟수 한도(write·move·delete가 하나씩 쓴다, 실행 단위로 공유, 선택).
        max_search_results: 검색 결과 최대 수(입력 `limit`의 상한).
        max_list_results: 목록 최대 수(입력 `limit`의 상한).
        timer: 처리 시간 측정 시계(초).
    """

    def __init__(
        self,
        wikis: Mapping[str, WikiTargetLike] | WikiResolver,
        *,
        access: WikiAccessConfig,
        author: WikiAuthor | None = None,
        text: WikiToolText | None = None,
        on_event: WikiEventSink | None = None,
        write_budget: WikiWriteBudget | None = None,
        max_search_results: int = 20,
        max_list_results: int = 200,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        if isinstance(wikis, Mapping):
            table = dict(wikis)
            self._resolve: WikiResolver = lambda wiki: table.get(wiki)
        else:
            self._resolve = wikis
        self.access = access
        self.author = author if author is not None else WikiAuthor(kind=KnownWikiAuthorKinds.AGENT)
        self.text = text if text is not None else load_tool_text()
        self.on_event = on_event
        self.write_budget = write_budget
        self.max_search_results = max(1, max_search_results)
        self.max_list_results = max(1, max_list_results)
        self._timer = timer

    # ---- 대상 ----------------------------------------------------------------------------

    def target(self, wiki: str) -> WikiToolTarget | None:
        """위키 id → 이 실행의 대상(접근 설정과 관계없이, 없으면 None)."""
        try:
            return _as_target(self._resolve(wiki))
        except Exception:  # 공간 읽기 실패 = 쓸 수 없는 위키
            return None

    def unavailable(self) -> list[str]:
        """접근 설정에는 있는데 이 실행 공간에 없는 위키(실행 준비 점검 경고용)."""
        return [w for w in access_wikis(self.access) if self.target(w) is None]

    def instructions(self) -> list[str]:
        """에이전트 지침 본문(`wiki_instructions` — 이 실행에서 쓸 수 있는 위키만)."""
        pairs: list[tuple[str, WikiToolTarget]] = []
        for wiki in access_wikis(self.access):
            if not wiki_ops(self.access, wiki):
                continue
            found = self.target(wiki)
            if found is not None:
                pairs.append((wiki, found))
        return wiki_instructions(self.access, pairs)

    # ---- 스펙 ----------------------------------------------------------------------------

    def _tool(self, op: str) -> tuple[str, str]:
        tool = getattr(self.access.tools, op)
        return tool.name, tool.description

    def _prop(self, name: str, schema: Mapping[str, Any]) -> dict[str, Any]:
        return {**schema, "description": self.text.inputs.get(name, "")}

    def input_schema(self, op: str) -> dict[str, Any]:
        """동작 `op`의 입력 JSON Schema(매개변수 이름은 계약 어휘, 설명은 데이터)."""
        string = {"type": "string"}
        wikis = wikis_for(self.access, op)
        props: dict[str, Any] = {}
        required: list[str] = []

        def add(name: str, schema: Mapping[str, Any], *, need: bool = False) -> None:
            props[name] = self._prop(name, schema)
            if need:
                required.append(name)

        if op == "search":
            add("query", string, need=True)
        elif op != "list":
            add("path", string, need=True)
        props["wiki"] = {
            "type": "string",
            "enum": wikis,
            "description": _render(self.text.inputs.get("wiki", ""), {"choices": ", ".join(wikis)}),
        }
        if op in ("search", "list"):
            add("prefix", string)
        if op == "search":
            add("tags", {"type": "array", "items": string})
        if op in ("search", "list"):
            cap = self.max_search_results if op == "search" else self.max_list_results
            add("limit", {"type": "integer", "minimum": 1, "maximum": cap})
        if op == "read":
            add("section", string)
        if op == "write":
            add("content", string)
            add("mode", {"type": "string", "enum": list(_WRITE_MODES)})
            add("section", string)
            add("template", string)
            add("title", string)
        if op == "move":
            add("to", string, need=True)
            add("rewrite_links", {"type": "boolean"})
        if op in _MUTATING:
            add("if_hash", string)
        if op in ("write", "move", "delete"):
            add("message", string)
        return {"type": "object", "properties": props, "required": required}

    def specs(self) -> list[WikiToolSpec]:
        """허용된 동작의 도구 스펙(계약 어휘 순서). 허용한 위키가 없는 동작은 빠진다."""
        out: list[WikiToolSpec] = []
        for op in WIKI_ACCESS_OPS:
            if not wikis_for(self.access, op):
                continue
            name, description = self._tool(op)

            async def call(
                args: Mapping[str, Any], call_id: str | None = None, *, _op: str = op
            ) -> WikiToolOutcome:
                return await self.call(_op, args, call_id)

            out.append(
                WikiToolSpec(
                    op=op,
                    name=name,
                    description=description,
                    input_schema=self.input_schema(op),
                    call=call,
                )
            )
        return out

    # ---- 호출 ----------------------------------------------------------------------------

    async def call(
        self, op: str, args: Mapping[str, Any], call_id: str | None = None
    ) -> WikiToolOutcome:
        """동작 하나를 처리하고 이벤트를 낸다. 실패는 예외가 아니라 `is_error` 결과다.

        Args:
            op: 동작(`WIKI_ACCESS_OPS`).
            args: 모델이 준 입력.
            call_id: 모델의 도구 호출 id(이벤트 `tool_use_id`).

        Raises:
            ValueError: 모르는 동작(모델 입력이 아니라 호출 코드의 잘못).
        """
        if op not in WIKI_ACCESS_OPS:
            raise ValueError(f"모르는 동작: {op!r}")
        started = self._timer()
        payload: dict[str, Any] = {"op": op, "tool": self._tool(op)[0], "tool_use_id": call_id}
        values: dict[str, Any] = {"wiki": "", "path": "", "section": "", "template": ""}
        issues: list[WikiIssue] = []
        repo: WikiRepository | None = None
        try:
            wiki, target = self._pick(op, args, payload, values)
            repo = target.repository
            text = await self._dispatch(op, repo, wiki, args, payload, values, issues)
            status, code, is_error = "ok", None, False
        except Exception as exc:  # 실패는 결과로 돌려준다
            failure = _map_error(exc)
            status, code, is_error = failure.status, failure.code, True
            values.update(failure.values)
            for key in ("lines", "hash"):
                if not values.get(key):
                    values[key] = self.text.line("unknown", {})
            if failure.rule_ids:
                payload["rule_ids"] = failure.rule_ids
            text = f"[{code}] {self.text.error(failure.reason, values)}"
        if repo is not None:
            # 가리기 실패는 결과를 막지 않는다(본문은 이미 저장소 규칙을 통과)
            with contextlib.suppress(Exception):
                text = repo.secrets.redact(text)
        payload["status"] = status
        payload["code"] = code
        payload["duration_ms"] = max(0.0, (self._timer() - started) * 1000)
        event = WikiEventPayload.model_validate(payload)
        event_type = f"{WIKI_EVENT_PREFIX}{op}"
        if self.on_event is not None:
            result = self.on_event(event_type, event)
            if inspect.isawaitable(result):
                await result
        return WikiToolOutcome(
            text=self._clip(text),
            is_error=is_error,
            code=code,
            event_type=event_type,
            event=event,
            issues=issues,
        )

    def _clip(self, text: str) -> str:
        limit = self.access.max_result_chars
        if len(text) <= limit:
            return text
        suffix = self.text.line("truncated", {"limit": limit})
        if len(suffix) >= limit:
            return text[:limit]
        return text[: limit - len(suffix)] + suffix

    def _pick(
        self, op: str, args: Mapping[str, Any], payload: dict[str, Any], values: dict[str, Any]
    ) -> tuple[str, WikiToolTarget]:
        wiki = _string(args, "wiki") or default_wiki(self.access)
        if not wiki:
            raise _ToolError("denied", KnownIssueCodes.WIKI_DENIED)
        payload["wiki"] = wiki
        values["wiki"] = wiki
        path = args.get("path")
        if isinstance(path, str):
            payload["path"] = path
            values["path"] = path
        if not wiki_allowed(self.access, wiki, op):
            raise _ToolError("denied", KnownIssueCodes.WIKI_DENIED)
        target = self.target(wiki)
        if target is None:
            raise _ToolError("wiki_unavailable", KnownIssueCodes.WIKI_WIKI_UNAVAILABLE)
        return wiki, target

    def _spend(self) -> None:
        if self.write_budget is not None and not self.write_budget.take():
            raise _ToolError("rate_limited", KnownIssueCodes.WIKI_RATE_LIMITED)

    @staticmethod
    async def _run[T](fn: Callable[[], T]) -> T:
        return await asyncio.to_thread(fn)

    def _warnings(self, found: Sequence[WikiIssue], issues: list[WikiIssue]) -> list[str]:
        issues.extend(found)
        return [
            self.text.line(
                "warning_item",
                {
                    "code": i.code,
                    "rule_id": i.rule_id or "",
                    "message": i.message,
                    "lines": _lines([i.line] if i.line else []),
                },
            )
            for i in found
            if i.severity != "info"
        ]

    async def _dispatch(
        self,
        op: str,
        repo: WikiRepository,
        wiki: str,
        args: Mapping[str, Any],
        payload: dict[str, Any],
        values: dict[str, Any],
        issues: list[WikiIssue],
    ) -> str:
        if op == "search":
            return await self._search(repo, wiki, args, payload)
        if op == "list":
            return await self._list(repo, wiki, args, payload)
        path = _string(args, "path", required=True) or ""
        if op == "read":
            return await self._read(repo, wiki, path, args, payload, values)
        if op == "links":
            return await self._links(repo, path, payload)
        if op == "write":
            return await self._write(repo, wiki, path, args, payload, values, issues)
        if op == "move":
            return await self._move(repo, wiki, path, args, payload, values, issues)
        return await self._delete(repo, wiki, path, args, payload, values, issues)

    # ---- 읽기 쪽 --------------------------------------------------------------------------

    async def _search(
        self, repo: WikiRepository, wiki: str, args: Mapping[str, Any], payload: dict[str, Any]
    ) -> str:
        query = _string(args, "query", required=True) or ""
        prefix = _string(args, "prefix")
        tags = _strings(args, "tags")
        limit = min(
            max(_integer(args, "limit") or self.max_search_results, 1), self.max_search_results
        )
        payload.update(query_chars=len(query), query_sha256=_sha(query))
        result = await self._run(lambda: repo.search(query, prefix=prefix, tags=tags, limit=limit))
        payload["results"] = len(result.items)
        if not result.items:
            return self.text.line("search_empty", {})
        lines = [
            self.text.line(
                "search_item",
                {
                    "wiki": wiki,
                    "path": hit.path,
                    "title": hit.title or hit.path,
                    "snippet": hit.snippet.replace("\n", " "),
                    "score": "" if hit.score is None else hit.score,
                },
            )
            for hit in result.items
        ]
        if result.degraded:
            lines.append(self.text.line("search_degraded", {}))
        return "\n".join(line for line in lines if line)

    async def _list(
        self, repo: WikiRepository, wiki: str, args: Mapping[str, Any], payload: dict[str, Any]
    ) -> str:
        prefix = _string(args, "prefix")
        limit = min(max(_integer(args, "limit") or self.max_list_results, 1), self.max_list_results)
        listing = await self._run(lambda: repo.list_pages(prefix=prefix))
        items = listing.items[:limit]
        payload["results"] = len(items)
        if not items:
            return self.text.line("list_empty", {})
        lines = [
            self.text.line(
                "list_item",
                {
                    "wiki": wiki,
                    "path": page.path,
                    "title": page.title or page.path,
                    "tags": ", ".join(page.tags),
                    "backlinks": page.backlinks,
                    "broken_links": page.broken_links,
                },
            )
            for page in items
        ]
        total = listing.total or len(listing.items)
        if len(items) < total or listing.truncated:
            lines.append(self.text.line("list_truncated", {"shown": len(items), "total": total}))
        return "\n".join(line for line in lines if line)

    async def _read(
        self,
        repo: WikiRepository,
        wiki: str,
        path: str,
        args: Mapping[str, Any],
        payload: dict[str, Any],
        values: dict[str, Any],
    ) -> str:
        section = _string(args, "section")
        view = await self._run(lambda: repo.view(path))
        payload.update(path=view.page.path, bytes=view.page.bytes, sha256=view.content_hash)
        body = view.content
        if section:
            values["section"] = section
            span = section_span(body, view.headings, section)
            if span is None:
                raise _ToolError(
                    "not_found", KnownIssueCodes.WIKI_NOT_FOUND, reason="section_not_found"
                )
            body = body[span[0] : span[2]]
        unknown = self.text.line("unknown", {})
        head = {
            "wiki": wiki,
            "path": view.page.path,
            "updated_at": format_time(view.page.updated_at) or unknown,
            "author": format_author(view.page.updated_by) or unknown,
            "hash": view.content_hash,
            "section": section or "",
        }
        lines = [_render(self.access.result_header, head), self.text.line("read_meta", head)]
        if section:
            lines.append(self.text.line("read_section", head))
        return "\n".join([*(line for line in lines if line), body])

    async def _links(self, repo: WikiRepository, path: str, payload: dict[str, Any]) -> str:
        view = await self._run(lambda: repo.view(path))
        payload["path"] = view.page.path
        t = self.text
        out_lines: list[str] = []
        broken_lines: list[str] = []
        unknown = t.line("unknown", {})
        for link in view.links:
            vals = {
                "raw": link.raw,
                "target": link.target or "",
                "label": link.label,
                "resolved": link.resolved or "",
                "status": link.status,
                "suggested_path": link.suggested_path or unknown,
            }
            if link.broken:
                broken_lines.append(t.line("links_broken_item", vals))
            elif link.resolved:
                out_lines.append(t.line("links_out_item", vals))
            else:
                out_lines.append(t.line("links_other_item", vals))
        in_lines = [
            t.line("links_in_item", {"path": b.path, "title": b.title or b.path, "count": b.count})
            for b in view.backlinks
        ]
        payload["results"] = len(view.links) + len(view.backlinks)
        parts: list[str] = []
        for title, items in (
            ("links_out_title", out_lines),
            ("links_in_title", in_lines),
            ("links_broken_title", broken_lines),
        ):
            parts.append(t.line(title, {}))
            parts.extend(items or [t.line("links_none", {})])
        return "\n".join(p for p in parts if p)

    # ---- 쓰기 쪽 --------------------------------------------------------------------------

    def _outcome_text(
        self, wiki: str, outcome: WriteOutcome, payload: dict[str, Any], issues: list[WikiIssue]
    ) -> str:
        if outcome.version is not None:
            payload["version"] = outcome.version.version
        key = "unchanged" if not outcome.changed else "created" if outcome.created else "written"
        vals = {
            "wiki": wiki,
            "path": outcome.path,
            "hash": outcome.content_hash,
            "version": outcome.version.version if outcome.version else "",
        }
        warn = self._warnings(outcome.issues, issues)
        rule_ids = [i.rule_id for i in outcome.issues if i.rule_id]
        if rule_ids:
            payload["rule_ids"] = list(dict.fromkeys(rule_ids))
        return "\n".join([self.text.line(key, vals), *warn])

    async def _write(
        self,
        repo: WikiRepository,
        wiki: str,
        path: str,
        args: Mapping[str, Any],
        payload: dict[str, Any],
        values: dict[str, Any],
        issues: list[WikiIssue],
    ) -> str:
        content = _string(args, "content")
        mode = _string(args, "mode") or "replace"
        section = _string(args, "section")
        template = _string(args, "template")
        title = _string(args, "title")
        if_hash = _string(args, "if_hash")
        message = _string(args, "message")
        if mode not in _WRITE_MODES or (mode == "section" and not section):
            raise _invalid()
        if template is None and content is None:
            raise _invalid()
        values.update(section=section or "", template=template or "")
        self._spend()
        author = self.author

        def work() -> tuple[WriteOutcome, int]:
            outcome, body = _compose()
            return outcome, len(body.encode("utf-8", errors="surrogatepass"))

        def _write_body(body: str, **kw: Any) -> tuple[WriteOutcome, str]:
            return repo.write(path, body, author=author, message=message, **kw), body

        def _compose() -> tuple[WriteOutcome, str]:
            plan = compose_write(
                repo,
                path,
                content=content,
                mode=mode,
                section=section,
                template=template,
                title=title,
                if_hash=if_hash,
            )
            return _write_body(plan.content, create_only=plan.create_only, if_hash=plan.if_hash)

        outcome, size = await self._run(work)
        payload.update(path=outcome.path, sha256=outcome.content_hash, bytes=size)
        return self._outcome_text(wiki, outcome, payload, issues)

    async def _move(
        self,
        repo: WikiRepository,
        wiki: str,
        path: str,
        args: Mapping[str, Any],
        payload: dict[str, Any],
        values: dict[str, Any],
        issues: list[WikiIssue],
    ) -> str:
        to = _string(args, "to", required=True) or ""
        rewrite = _boolean(args, "rewrite_links", True)
        if_hash = _string(args, "if_hash")
        message = _string(args, "message")
        payload["to"] = to
        values["to"] = to
        self._spend()
        result = await self._run(
            lambda: repo.move(
                path,
                to,
                author=self.author,
                rewrite_links=rewrite,
                if_hash=if_hash,
                message=message,
            )
        )
        payload.update(path=result.from_, to=result.to, results=len(result.rewritten))
        vals = {
            "wiki": wiki,
            "path": result.from_,
            "to": result.to,
            "rewritten": len(result.rewritten),
            "conflicts": ", ".join(result.conflicts),
        }
        lines = [self.text.line("moved", vals)]
        if result.conflicts:
            lines.append(self.text.line("move_conflicts", vals))
        lines.extend(self._warnings(result.issues, issues))
        return "\n".join(line for line in lines if line)

    async def _delete(
        self,
        repo: WikiRepository,
        wiki: str,
        path: str,
        args: Mapping[str, Any],
        payload: dict[str, Any],
        values: dict[str, Any],
        issues: list[WikiIssue],
    ) -> str:
        if_hash = _string(args, "if_hash")
        message = _string(args, "message")
        self._spend()
        outcome = await self._run(
            lambda: repo.delete(path, author=self.author, if_hash=if_hash, message=message)
        )
        payload.update(path=outcome.path, sha256=outcome.content_hash)
        if outcome.version is not None:
            payload.update(version=outcome.version.version, bytes=outcome.version.bytes)
        vals = {"wiki": wiki, "path": outcome.path}
        return "\n".join([self.text.line("deleted", vals), *self._warnings(outcome.issues, issues)])
