"""X6 `claude-code`: Claude Code 세션 기록 행 → 이벤트 초안(행 단위 무상태, F-7).

`claude_logs.py`(agent_bench 실험기) 규칙을 옮겼다. 바뀐 점(design §4R.13):

- 응답 묶기·호출 짝은 들고 있지 않는다. 행마다 `message_id`·`call_id`를 실어 질의 때 묶는다.
- 도구 이름 특수 처리(위임·파일 변경·문서 읽기·MCP 이름 패턴)·범주·태그·hook 등 행 대응은 전부
  분류기 설정 데이터(`data/classifier_config.schema.json` 기본값)다. 코드에 도구 이름 목록이 없다.
- 토큰은 응답 행의 `message.usage`를 `TokenSample`로 싣는다. 색인이 (출처, thread, message_id)마다
  output이 가장 큰 표본 하나만 센다(F-8).
- `thinking` 본문은 어디에도 싣지 않는다(있었다는 표시만, `detail`·`raw` 모두).
- 목록 요약(`summary`)은 사람이 읽는 평문이다. 위치는 설정 `summaries`(행 종류별)·행 규칙
  `summary`(detail 기준 JSON 포인터)이고, 못 찾으면 코어 기본(detail 전체 문자열)이다.
  원문은 detail·raw에 남는다.

이 모듈이 아는 것은 Claude Code 기록의 **구조**(행 `type`이 user·assistant, `message.content` 블록
`text`·`tool_use`·`tool_result`, `message.id`·`usage`, `timestamp`·`sessionId`·`cwd`·`promptId`·
`parentUuid`·`isSidechain`·`agentId`)뿐이다.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, ClassVar

from agent_console_contracts.logs import LogClassifierDescriptor, LogDocumentRef, TokenSample
from agent_console_logs import (
    TAG_SESSION_TITLE,
    TAG_TOOL,
    AgentInfo,
    ClassifyContext,
    JsonValue,
    LogEventDraft,
    RawRecord,
    json_pointer,
    scrub_surrogates,
    timestamp,
)

from ._schemas import classifier_config_schema
from ._source import CLAUDE_CODE_FORMAT, META_KIND_SUBAGENT

__all__ = [
    "MCP_PATTERN_GROUPS",
    "OMITTED_KEY",
    "ClaudeCodeClassifier",
    "McpPatternError",
    "compile_mcp_pattern",
    "omitted_row",
    "summary_text",
]

OMITTED_KEY = "omitted"
"""원문을 저장하지 않는 행 규칙(`store_raw: false`)이 크기·해시를 싣는 키."""

MCP_PATTERN_GROUPS = ("server", "tool")
"""`mcp_tool_pattern` 틀에 있어야 하는 자리 표시 이름."""

_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)
_TEMPLATE = re.compile(r"\{(/[^{}]*)\}")
_SUMMARY_SLOT = re.compile(r"\{(/[^{}|]*)(?:\|(keys|count))?\}")
_KEYS_JOIN = ", "


class McpPatternError(ValueError):
    """`mcp_tool_pattern` 틀이 잘못됐다(자리 표시가 없거나 겹침)."""


@lru_cache(maxsize=64)
def compile_mcp_pattern(pattern: str) -> re.Pattern[str]:
    """MCP 도구 이름 틀(`mcp__{server}__{tool}`)을 매처로 바꾼다.

    사용자 정규식을 받지 않는다. 틀은 글자 그대로 + 자리 표시 `{server}`·`{tool}`(각각 정확히
    한 번) + `*`(아무 글자)다. 자리 표시는 비어 있지 않은 가장 짧은 글자열이고, 이름 전체가
    맞아야 한다(그래서 마지막 자리 표시는 나머지 전부).

    Raises:
        McpPatternError: 자리 표시가 없거나 두 번 이상 나온다.
    """
    parts = re.split(r"(\{server\}|\{tool\}|\*)", pattern)
    names = [p for p in parts if p in ("{server}", "{tool}")]
    if sorted(names) != sorted(f"{{{g}}}" for g in MCP_PATTERN_GROUPS):
        raise McpPatternError(
            "mcp_tool_pattern에는 {server}와 {tool}이 각각 정확히 한 번 있어야 합니다"
        )
    out: list[str] = []
    for part in parts:
        if part in ("{server}", "{tool}"):
            out.append(f"(?P<{part[1:-1]}>.+?)")
        elif part == "*":
            out.append(".*?")
        else:
            out.append(re.escape(part))
    return re.compile("".join(out) + r"\Z", re.DOTALL)


def _scalar_text(value: Any) -> str | None:
    """조건·틀 비교용 문자열(값이 없거나 객체·목록이면 None, 참·거짓·숫자는 JSON 문자열)."""
    if value is None or isinstance(value, Mapping | list):
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _fill(template: str, row: JsonValue) -> str:
    def repl(m: re.Match[str]) -> str:
        value = json_pointer(row, m.group(1))
        if value is None:
            return ""
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    return _TEMPLATE.sub(repl, template)


def _matches(rule: Mapping[str, Any], row: JsonValue) -> bool:
    conditions = rule.get("match")
    if not isinstance(conditions, Mapping) or not conditions:
        return False
    for pointer, expected in conditions.items():
        actual = _scalar_text(json_pointer(row, str(pointer)))
        if actual is None:
            return False
        patterns = [expected] if isinstance(expected, str) else list(expected or [])
        if not any(fnmatchcase(actual, str(p)) for p in patterns):
            return False
    return True


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def omitted_row(row: Mapping[str, Any], keep: Sequence[str] = ()) -> dict[str, Any]:
    """원문 대신 저장할 값: `keep` 포인터 값(같은 위치) + `omitted`{`bytes`, `sha256`}.

    크기·해시는 행을 키 정렬·공백 없는 JSON(UTF-8)으로 쓴 것 기준이다(같은 내용이면 같은 해시).

    Args:
        row: 원본 행(JSON 객체).
        keep: 남길 값의 JSON 포인터(빈 문자열·없는 값은 건너뛴다).

    Returns:
        새 객체. 원본을 바꾸지 않는다.

    예:
        >>> omitted_row({"type": "x", "body": "비밀"}, ["/type"])["type"]
        'x'
    """
    data = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    out: dict[str, Any] = {}
    for pointer in keep:
        value = json_pointer(row, pointer) if pointer.startswith("/") else None
        if value is None:
            continue
        *parents, last = [_unescape(t) for t in pointer[1:].split("/")]
        target = out
        for token in parents:
            nested = target.get(token)
            if not isinstance(nested, dict):
                nested = target[token] = {}
            target = nested
        target[last] = value
    out[OMITTED_KEY] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return out


def _cfg_map(cfg: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = cfg.get(key)
    return value if isinstance(value, Mapping) else {}


def _cfg_list(cfg: Mapping[str, Any], key: str) -> list[Any]:
    value = cfg.get(key)
    return list(value) if isinstance(value, list) else []


def _strs(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(v) for v in value if isinstance(v, str) and v)
    return ()


def _blocks(content: Any) -> list[Mapping[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, Mapping)]
    return []


def _block_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping) and isinstance(value.get("text"), str):
        return str(value["text"])
    return None


def _plain(value: Any) -> str | None:
    """요약용 평문: 문자열은 그대로, 내용 블록 목록은 text 블록을 이어 붙인다(없으면 None)."""
    if isinstance(value, list):
        found = "\n".join(t for v in value if (t := _block_text(v)) is not None)
    else:
        found = _block_text(value) or ""
    found = found.strip()
    return found or None


def _is_template(item: str) -> bool:
    """요약 항목이 틀인지(`{/`가 있거나 `/`로 시작하지 않음). 빈 문자열은 포인터(detail 전체)."""
    return "{/" in item or (item != "" and not item.startswith("/"))


def _slot_text(value: Any, *, mode: str | None) -> str | None:
    """틀 자리 표시 값: 평문·숫자·참거짓(JSON), `|keys`면 객체 키 목록, `|count`면 항목 수.

    객체·빈 값은 None(`|count`는 목록·객체의 항목 수이고 0도 값이다).
    """
    if mode == "count":
        return str(len(value)) if isinstance(value, Mapping | list) else None
    if mode == "keys":
        if isinstance(value, Mapping) and value:
            return _KEYS_JOIN.join(str(k) for k in value)
        return None
    if isinstance(value, bool | int | float):
        return json.dumps(value)
    return _plain(value)


def _render_summary(detail: JsonValue, template: str) -> str | None:
    """요약 틀을 채운다. 자리 표시 중 하나라도 값이 없으면 None(다음 항목으로 넘어가게)."""
    missing = False

    def repl(m: re.Match[str]) -> str:
        nonlocal missing
        found = _slot_text(json_pointer(detail, m.group(1)), mode=m.group(2))
        if found is None:
            missing = True
            return ""
        return found

    out = _SUMMARY_SLOT.sub(repl, template).strip()
    return None if missing or not out else out


def summary_text(detail: JsonValue, pointers: Any) -> str | None:
    """`pointers` 항목 중 처음으로 평문이 나오는 것. 없으면 None.

    항목은 detail 기준 JSON 포인터(값이 문자열이면 그대로, 내용 블록 목록이면 text 블록을 잇는다)
    또는 틀이다. 틀은 `{/포인터}`를 그 값(평문·숫자·참거짓)으로, `{/포인터|keys}`를 객체 키
    목록으로, `{/포인터|count}`를 목록·객체 항목 수로 바꾸며, 자리 표시가 하나라도 비면
    건너뛴다. `/`로 시작하지 않는 항목은 틀이다(자리 표시가 없으면 그 글자 그대로 — 마지막
    대체 문구로 쓴다).
    """
    if not isinstance(pointers, list):
        return None
    for item in pointers:
        if not isinstance(item, str):
            continue
        if _is_template(item):
            found = _render_summary(detail, item)
        else:
            found = _plain(json_pointer(detail, item))
        if found is not None:
            return found
    return None


def _file_name(path: str) -> str:
    return PureWindowsPath(path).name if "\\" in path else PurePosixPath(path).name


def document_kind(kinds: Mapping[str, Any], path: str) -> str | None:
    """문서 경로 → 종류(`document_kinds` 데이터). 없으면 None.

    키가 글롭(`*`·`?`·`[`)이 아니면 파일 이름과 같을 때, 글롭이면 `/`로 맞춘 경로 전체에 맞을 때
    (`*`는 `/`도 넘는다, 예: `*/.claude/rules/*.md`) 그 종류다. 파일 이름이 먼저, 그다음 글롭은
    긴 것부터 본다.
    """
    found = kinds.get(_file_name(path))
    if found:
        return str(found)
    normalized = path.replace("\\", "/")
    globs = sorted((k for k in kinds if any(c in k for c in "*?[")), key=lambda k: (-len(k), k))
    for key in globs:
        if fnmatchcase(normalized, key) and kinds[key]:
            return str(kinds[key])
    return None


class ClaudeCodeClassifier:
    """Claude Code 세션 기록 분류기(X6). 행 단위 무상태 — 같은 행과 맥락이면 늘 같은 결과다."""

    descriptor: ClassVar[LogClassifierDescriptor] = LogClassifierDescriptor(
        id=CLAUDE_CODE_FORMAT,
        formats=[CLAUDE_CODE_FORMAT],
        title="Claude Code 세션 기록",
        description=(
            "사용자 입력·모델 응답·도구 호출/결과·서브에이전트 위임/결과·MCP·hook 행을 이벤트로 "
            "바꾼다. 도구 이름 특수 처리와 hook 등 행 대응은 설정 데이터다."
        ),
        config_schema=classifier_config_schema(),
    )

    # ---------------------------------------------------------------- 진입점

    def classify(self, record: RawRecord, ctx: ClassifyContext) -> list[LogEventDraft]:
        """원본 행 하나 → 초안 목록.

        Raises:
            ValueError: 행이 JSON 객체가 아니거나 설정(MCP 틀 등)이 잘못됨(→ 진단 이벤트).
        """
        row = record.data
        if not isinstance(row, Mapping):
            raise ValueError("Claude Code 기록 행은 JSON 객체여야 합니다")
        cfg = ctx.config
        # 외톨이 서로게이트(깨진 UTF-16 `\ud800` 등)는 모델(LogLane·LogDocumentRef·TokenSample)
        # 검증에서 거부되므로, 모델을 만들기 전에 행·맥락을 한 번 정리한다(U+FFFD).
        row = scrub_surrogates(row)
        meta: Mapping[str, JsonValue] = scrub_surrogates(record.meta)
        # 내부 추론 본문은 처음부터 지운 사본으로만 다룬다(detail·raw 어디에도 남지 않게).
        row = self._scrub(row, set(_strs(cfg.get("thinking_block_types"))), self._note(cfg))
        base = self._base(row, meta, cfg)
        return self._with_row_correlation(self._drafts(row, base, meta, cfg), row, cfg)

    @staticmethod
    def _with_row_correlation(
        drafts: list[LogEventDraft], row: Mapping[str, Any], cfg: Mapping[str, Any]
    ) -> list[LogEventDraft]:
        """설정 `row_correlation`(근거 이름 → 포인터): 행에 값이 있으면 그 행의 모든 이벤트에
        근거를 더한다(이벤트가 이미 가진 같은 근거는 그대로 둔다).

        예: 응답 행 `requestRef` → `request_id`.
        """
        extra: dict[str, str] = {}
        for basis, pointer in _cfg_map(cfg, "row_correlation").items():
            text = _scalar_text(json_pointer(row, str(pointer)))
            if text:
                extra[str(basis)] = text
        if not extra:
            return drafts
        return [replace(d, correlation={**extra, **d.correlation}) for d in drafts]

    def _drafts(
        self,
        row: Mapping[str, Any],
        base: Mapping[str, Any],
        meta: Mapping[str, JsonValue],
        cfg: Mapping[str, Any],
    ) -> list[LogEventDraft]:
        for rule in [*_cfg_list(cfg, "extra_row_rules"), *_cfg_list(cfg, "row_rules")]:
            if isinstance(rule, Mapping) and _matches(rule, row):
                return [self._rule_event(rule, row, base, meta)]
        kind = row.get("type")
        if kind == "assistant":
            return self._assistant(row, base, meta, cfg)
        if kind == "user":
            return self._user(row, base, meta, cfg)
        cats = _cfg_map(cfg, "categories")
        draft = LogEventDraft(
            **base,
            category=str(cats.get("other") or "other"),
            title=_scalar_text(kind) or "알 수 없는 행",
            detail=row,
            raw=row,
        )
        return [self._summarized(draft, cfg, "other")]

    # ---------------------------------------------------------------- 공통

    @staticmethod
    def _summarized(draft: LogEventDraft, cfg: Mapping[str, Any], kind: str) -> LogEventDraft:
        """설정 `summaries[kind]` 포인터로 목록 요약(평문)을 붙인다(못 찾으면 코어 기본)."""
        found = summary_text(draft.detail, _cfg_map(cfg, "summaries").get(kind))
        return replace(draft, summary=found) if found is not None else draft

    def _base(
        self, row: Mapping[str, Any], meta: Mapping[str, JsonValue], cfg: Mapping[str, Any]
    ) -> dict[str, Any]:
        session = _scalar_text(meta.get("session")) or _scalar_text(row.get("sessionId")) or ""
        thread = _scalar_text(meta.get("thread")) or ""
        agent_id = _scalar_text(row.get("agentId"))
        if not thread or (
            meta.get("kind") != META_KIND_SUBAGENT and row.get("isSidechain") is True and agent_id
        ):
            # 옛 형식: 서브에이전트 행이 메인 파일 안에 isSidechain으로 섞여 있다.
            template = str(cfg.get("subagent_thread_template") or "{value}")
            thread = template.replace("{value}", agent_id) if agent_id else session
        role = _scalar_text(meta.get("role")) or ""
        agent = None
        parent = _scalar_text(meta.get("parent"))
        if meta.get("kind") == META_KIND_SUBAGENT and thread:
            agent = AgentInfo(id=thread, label=role or None, parent_id=parent or None)
        return {
            "thread": thread,
            "actor": thread,
            "role": role,
            "session": session,
            "cwd": _scalar_text(row.get("cwd")) or "",
            "turn_id": _scalar_text(row.get("promptId")) or "",
            "time": timestamp(row.get("timestamp")),
            "agent": agent,
        }

    def _rule_event(
        self,
        rule: Mapping[str, Any],
        row: Mapping[str, Any],
        base: Mapping[str, Any],
        meta: Mapping[str, JsonValue],
    ) -> LogEventDraft:
        fields = _cfg_map(rule, "fields")
        maps = _cfg_map(rule, "value_maps")
        values: dict[str, Any] = {}
        for name, pointer in fields.items():
            text = _scalar_text(json_pointer(row, str(pointer)))
            if text is None:
                continue
            mapping = maps.get(name)
            if isinstance(mapping, Mapping) and text in mapping:
                text = str(mapping[text])
            elif name == "category":
                continue  # 범주는 대응표에 있을 때만 바꾼다(없으면 규칙의 기본 범주)
            if text:
                values[str(name)] = text
        correlation: dict[str, str | list[str]] = {}
        for basis, pointer in _cfg_map(rule, "correlation").items():
            text = _scalar_text(json_pointer(row, str(pointer)))
            if text:
                correlation[str(basis)] = text
        detail_pointer = str(rule.get("detail") or "")
        detail = json_pointer(row, detail_pointer) if detail_pointer else row
        raw: JsonValue = row
        if rule.get("store_raw") is False:
            # 원문(요청 본문 등)을 색인에 넣지 않는다: 크기·해시와 keep 값만(design §5.5R 5.5R.34).
            detail = raw = omitted_row(row, _strs(rule.get("keep")))
        merged = dict(base)
        for key in ("role", "turn_id"):
            if key in values:
                merged[key] = values.pop(key)
        return LogEventDraft(
            **merged,
            category=values.pop("category", "") or str(rule.get("category") or "other"),
            title=_fill(str(rule.get("title") or ""), row) or _scalar_text(row.get("type")) or "",
            stage=values.pop("stage", "") or str(rule.get("stage") or "info"),
            status=values.pop("status", "") or str(rule.get("status") or ""),
            tags=_strs(rule.get("tags")),
            correlation=correlation,
            detail=row if detail is None else detail,
            raw=raw,
            summary=summary_text(row if detail is None else detail, rule.get("summary")),
            **values,
        )

    # ---------------------------------------------------------------- 응답 행

    def _assistant(
        self,
        row: Mapping[str, Any],
        base: Mapping[str, Any],
        meta: Mapping[str, JsonValue],
        cfg: Mapping[str, Any],
    ) -> list[LogEventDraft]:
        message = row.get("message")
        message = message if isinstance(message, Mapping) else {}
        message_id = _scalar_text(message.get("id")) or ""
        model = _scalar_text(message.get("model")) or ""
        cats = _cfg_map(cfg, "categories")
        thinking_types = set(_strs(cfg.get("thinking_block_types")))
        note = self._note(cfg)
        usage = self._usage(message, base, message_id, model)
        failed = row.get("isApiErrorMessage") is True
        common = {**base, "message_id": message_id, "model": model}
        events: list[LogEventDraft] = []
        for block in _blocks(message.get("content")):
            kind = _scalar_text(block.get("type")) or ""
            if kind == "tool_use":
                events.append(self._tool_call(block, common, meta, cfg))
            elif kind in thinking_types:
                thinking = LogEventDraft(
                    **common,
                    category=str(cats.get("thinking") or "llm"),
                    title="내부 추론",
                    stage="complete",
                    detail={"type": kind, "note": note},
                )
                events.append(self._summarized(thinking, cfg, "thinking"))
            elif kind == "text":
                text = _scalar_text(block.get("text")) or ""
                if not text.strip():
                    continue
                answer = LogEventDraft(
                    **common,
                    category=str(cats.get("api_error" if failed else "assistant_text") or "llm"),
                    title="API 오류 응답" if failed else "모델 응답",
                    stage="complete",
                    status="failed" if failed else "",
                    detail={"text": text, "stop_reason": message.get("stop_reason")},
                )
                events.append(
                    self._summarized(answer, cfg, "api_error" if failed else "assistant_text")
                )
            else:
                other = LogEventDraft(
                    **common,
                    category=str(cats.get("other") or "other"),
                    title=f"응답 블록 · {kind or '?'}",
                    detail=block,
                )
                events.append(self._summarized(other, cfg, "other"))
        if not events:
            events.append(
                LogEventDraft(
                    **common,
                    category=str(cats.get("api_error" if failed else "assistant_text") or "llm"),
                    title="모델 응답(내용 없음)",
                    stage="complete",
                    status="failed" if failed else "",
                    detail={"stop_reason": message.get("stop_reason")},
                )
            )
        first = events[0]
        events[0] = replace(first, usage=usage, raw=row)
        return events

    @staticmethod
    def _usage(
        message: Mapping[str, Any], base: Mapping[str, Any], message_id: str, model: str
    ) -> TokenSample | None:
        usage = message.get("usage")
        if not isinstance(usage, Mapping):
            return None
        counts = {
            k: usage[k]
            for k in _USAGE_KEYS
            if isinstance(usage.get(k), int) and not isinstance(usage.get(k), bool)
        }
        if not counts:
            return None
        return TokenSample(
            thread=str(base.get("thread") or ""),
            message_id=message_id,
            model=model,
            time=base.get("time"),
            **counts,
        )

    @staticmethod
    def _note(cfg: Mapping[str, Any]) -> str:
        return str(cfg.get("thinking_note") or "")

    @staticmethod
    def _scrub(value: Any, thinking_types: set[str], note: str) -> Any:
        """내부 추론 블록을 표시로 바꾼 사본(원본은 바꾸지 않음)."""
        if isinstance(value, Mapping):
            kind = value.get("type")
            if isinstance(kind, str) and kind in thinking_types:
                return {"type": kind, "note": note}
            return {
                str(k): ClaudeCodeClassifier._scrub(v, thinking_types, note)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [ClaudeCodeClassifier._scrub(v, thinking_types, note) for v in value]
        return value

    def _tool_call(
        self,
        block: Mapping[str, Any],
        common: Mapping[str, Any],
        meta: Mapping[str, JsonValue],
        cfg: Mapping[str, Any],
    ) -> LogEventDraft:
        cats = _cfg_map(cfg, "categories")
        tags_cfg = _cfg_map(cfg, "tags")
        name = _scalar_text(block.get("name")) or ""
        call_id = _scalar_text(block.get("id")) or ""
        data = block.get("input")
        data = data if isinstance(data, Mapping) else {}
        thread = str(common.get("thread") or "")
        tags = [TAG_TOOL, *_strs(tags_cfg.get("tool_call"))]
        fields: dict[str, Any] = {
            "category": str(cats.get("tool_call") or "tool"),
            "title": name or "도구 호출",
            "detail": {"name": name, "input": data},
        }
        delegation = self._find_tool(cfg, "delegation_tools", name)
        mcp = self._mcp(cfg, name)
        summary_kind = "tool_call"
        if delegation is not None:
            summary_kind = "delegation"
            pointer = str(delegation.get("target_pointer") or "/subagent_type")
            value = _scalar_text(json_pointer(data, pointer)) or ""
            links = meta.get("subagents")
            target = links.get(call_id) if isinstance(links, Mapping) else None
            if not isinstance(target, str) or not target:
                fallback = str(delegation.get("fallback_target") or "{value}")
                target = fallback.replace("{value}", value or "subagent")
            tags += _strs(tags_cfg.get("delegation"))
            fields.update(
                category=str(cats.get("delegation") or "handoff"),
                title=f"서브에이전트 위임 · {value}" if value else "서브에이전트 위임",
                from_=(thread,) if thread else (),
                to=(target,),
                via=str(delegation.get("via") or name),
            )
        elif mcp is not None:
            summary_kind = "mcp_call"
            server, tool = mcp
            tags += _strs(tags_cfg.get("mcp"))
            fields.update(
                category=str(cats.get("mcp_call") or "mcp"),
                title=f"MCP · {server}/{tool}",
                detail={"name": name, "server": server, "tool": tool, "input": data},
                correlation={"mcp_server": server},
            )
        documents = self._documents(cfg, name, data)
        draft = LogEventDraft(
            **common,
            tool=name,
            call_id=call_id,
            stage="start",
            tags=tuple(dict.fromkeys(tags)),
            documents=documents,
            **fields,
        )
        return self._summarized(draft, cfg, summary_kind)

    @staticmethod
    def _find_tool(cfg: Mapping[str, Any], key: str, name: str) -> Mapping[str, Any] | None:
        for item in _cfg_list(cfg, key):
            if isinstance(item, Mapping) and item.get("name") == name:
                return item
        return None

    @staticmethod
    def _mcp(cfg: Mapping[str, Any], name: str) -> tuple[str, str] | None:
        pattern = str(cfg.get("mcp_tool_pattern") or "")
        if not pattern or not name:
            return None
        found = compile_mcp_pattern(pattern).match(name)
        if found is None:
            return None
        return found.group("server") or "", found.group("tool") or ""

    def _documents(
        self, cfg: Mapping[str, Any], name: str, data: Mapping[str, Any]
    ) -> tuple[LogDocumentRef, ...]:
        kinds = _cfg_map(cfg, "document_kinds")
        default_kind = str(cfg.get("default_document_kind") or "document")
        out: list[LogDocumentRef] = []
        for key in ("file_change_tools", "document_read_tools"):
            item = self._find_tool(cfg, key, name)
            if item is None:
                continue
            path = _scalar_text(json_pointer(data, str(item.get("path_pointer") or "/file_path")))
            if not path:
                continue
            kind = document_kind(kinds, path) or default_kind
            out.append(
                LogDocumentRef(path=path, kind=kind, action=str(item.get("action") or "mentioned"))
            )
        return tuple(out)

    # ---------------------------------------------------------------- 사용자 행

    def _user(
        self,
        row: Mapping[str, Any],
        base: Mapping[str, Any],
        meta: Mapping[str, JsonValue],
        cfg: Mapping[str, Any],
    ) -> list[LogEventDraft]:
        message = row.get("message")
        message = message if isinstance(message, Mapping) else {}
        blocks = _blocks(message.get("content"))
        cats = _cfg_map(cfg, "categories")
        events: list[LogEventDraft] = []
        texts = [
            t for b in blocks if b.get("type") == "text" and (t := _scalar_text(b.get("text")))
        ]
        others = [b for b in blocks if b.get("type") not in ("text", "tool_result")]
        results = [b for b in blocks if b.get("type") == "tool_result"]
        if texts or others:
            events.append(self._input(row, texts, others, base, meta, cfg))
        for block in results:
            events.append(self._tool_result(block, row, base, cfg, single=len(results) == 1))
        if not events:
            events.append(
                LogEventDraft(
                    **base,
                    category=str(cats.get("input") or "input"),
                    title="빈 입력",
                    stage="input",
                    detail=row,
                )
            )
        events[0] = replace(events[0], raw=row)
        return events

    def _input(
        self,
        row: Mapping[str, Any],
        texts: Sequence[str],
        others: Sequence[Mapping[str, Any]],
        base: Mapping[str, Any],
        meta: Mapping[str, JsonValue],
        cfg: Mapping[str, Any],
    ) -> LogEventDraft:
        cats = _cfg_map(cfg, "categories")
        text = "\n".join(texts)
        detail: dict[str, Any] = {"text": text}
        if others:
            detail["blocks"] = [
                {"type": _scalar_text(b.get("type")) or "?"} for b in others
            ]  # 이미지 등 본문은 싣지 않는다(종류만)
        limit = cfg.get("title_chars")
        chars = limit if isinstance(limit, int) and limit > 0 else 80
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        title = first_line[:chars] + ("…" if len(first_line) > chars else "")
        is_subagent = meta.get("kind") == META_KIND_SUBAGENT
        thread = str(base.get("thread") or "")
        if is_subagent and row.get("parentUuid") is None:
            parent = _scalar_text(meta.get("parent")) or ""
            correlation: dict[str, str | list[str]] = {}
            call_id = _scalar_text(meta.get("tool_use_id"))
            if call_id:
                correlation["tool_use_id"] = call_id
            received = LogEventDraft(
                **base,
                category=str(cats.get("input") or "input"),
                title="위임 작업 수신",
                stage="input",
                from_=(parent,) if parent else (),
                to=(thread,) if thread else (),
                correlation=correlation,
                detail=detail,
            )
            return self._summarized(received, cfg, "input")
        tags: tuple[str, ...] = ()
        if not is_subagent and texts and cfg.get("session_title_from_input", True) is not False:
            skips = _strs(cfg.get("session_title_skip_prefixes"))
            if not any(text.lstrip().startswith(p) for p in skips):
                tags = (TAG_SESSION_TITLE,)
        draft = LogEventDraft(
            **base,
            category=str(cats.get("input") or "input"),
            title=title or "입력",
            stage="input",
            tags=tags,
            detail=detail,
        )
        return self._summarized(draft, cfg, "input")

    def _tool_result(
        self,
        block: Mapping[str, Any],
        row: Mapping[str, Any],
        base: Mapping[str, Any],
        cfg: Mapping[str, Any],
        *,
        single: bool,
    ) -> LogEventDraft:
        cats = _cfg_map(cfg, "categories")
        tags_cfg = _cfg_map(cfg, "tags")
        call_id = _scalar_text(block.get("tool_use_id")) or ""
        failed = block.get("is_error") is True
        tags: list[str] = [TAG_TOOL, *_strs(tags_cfg.get("tool_result"))]
        if failed:
            tags += _strs(tags_cfg.get("tool_failed"))
        fields: dict[str, Any] = {
            "category": str(cats.get("tool_result") or "tool"),
            "title": "도구 결과" + (" (오류)" if failed else ""),
        }
        delegation = _cfg_map(cfg, "delegation_result")
        pointer = str(delegation.get("agent_id_pointer") or "")
        agent_id = _scalar_text(json_pointer(row, pointer)) if pointer and single else None
        if agent_id:
            template = str(cfg.get("subagent_thread_template") or "{value}")
            thread = str(base.get("thread") or "")
            tags += _strs(tags_cfg.get("delegation"))
            fields.update(
                category=str(cats.get("delegation_result") or "merge"),
                title="서브에이전트 결과" + (" (오류)" if failed else ""),
                from_=(template.replace("{value}", agent_id),),
                to=(thread,) if thread else (),
                via=str(delegation.get("via") or ""),
            )
        draft = LogEventDraft(
            **base,
            call_id=call_id,
            stage="complete",
            status="failed" if failed else "completed",
            tags=tuple(dict.fromkeys(tags)),
            detail={"output": block.get("content"), "is_error": failed},
            **fields,
        )
        return self._summarized(draft, cfg, "delegation_result" if agent_id else "tool_result")
