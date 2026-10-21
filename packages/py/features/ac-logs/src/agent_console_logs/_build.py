"""초안 → 색인 레코드(식별·크기 제한·가리기·요약). agent_bench `_insert` 규칙 이식."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import fields, replace
from typing import Any

from agent_console_contracts.logs import LogEvent

from ._draft import TAG_TOOL, LogEventDraft
from ._index import IndexRecord
from ._values import JsonValue, bounded, dirty_surrogates, scrub_surrogates, text

__all__ = ["SUMMARY_CHARS", "build_record", "event_uid", "identity_for"]

SUMMARY_CHARS = 220
"""목록용 요약 길이(agent_bench 그대로)."""


def event_uid(identity: str) -> str:
    """identity → uid(`sha256(identity)[:24]`)."""
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def identity_for(
    draft: LogEventDraft,
    *,
    source_id: str,
    origin: str,
    offset: int,
    index: int,
    generation: int = 0,
) -> str:
    """중복 판정 키.

    1. 초안이 `identity`를 주면 그것(출처가 책임진다).
    2. `TAG_TOOL`(태그 또는 범주) + `call_id` → `tool:{source}:{thread}:{call_id}:{stage}`.
    3. 그 밖 → `{source}:{origin}:{offset}`, 한 행의 두 번째 이벤트부터 `:{index}`.
       `generation`이 0이 아니면(회전된 단위) origin 뒤에 `@{generation}`을 붙인다.
    """
    if draft.identity:
        return draft.identity
    if draft.call_id and (TAG_TOOL in draft.tags or draft.category == TAG_TOOL):
        return f"tool:{source_id}:{draft.thread}:{draft.call_id}:{draft.stage}"
    where = f"{origin}@{generation}" if generation else origin
    return f"{source_id}:{where}:{offset}" + (f":{index}" if index else "")


_DRAFT_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(LogEventDraft))


def _scrub_draft(draft: LogEventDraft) -> LogEventDraft:
    """초안의 모든 문자열(본문·태그·문서·토큰 표본·줄 정보 안까지)의 외톨이 서로게이트를 바꾼다."""
    values = [getattr(draft, name) for name in _DRAFT_FIELDS]
    if not dirty_surrogates(values):  # 흔한 경우: 훑기 한 번으로 끝
        return draft
    changes: dict[str, Any] = {}
    for name in _DRAFT_FIELDS:
        value = getattr(draft, name)
        cleaned = scrub_surrogates(value)
        if cleaned is not value:
            changes[name] = cleaned
    return replace(draft, **changes) if changes else draft


def build_record(
    draft: LogEventDraft,
    *,
    source_id: str,
    event_source: str | None = None,
    origin: str,
    offset: int,
    index: int,
    observed_at: float,
    repo_root: str = "",
    redact: Callable[[JsonValue], JsonValue] | None = None,
    generation: int = 0,
) -> IndexRecord:
    """초안 하나를 색인 레코드로 만든다.

    Args:
        source_id: 출처 id(identity·토큰 키).
        event_source: 이벤트 `source`(진단이면 `"diagnostic"`, 없으면 `source_id`).
        origin·offset·index: 원본 위치(기본 identity).
        observed_at: 색인 시각.
        repo_root: cwd의 본 저장소 경로(worktree일 때).
        redact: 저장 직전 가리기(제목·detail·raw에 적용).
        generation: 원본 단위의 내용 세대(`RawRecord.generation`, 기본 identity에 들어감).

    모든 문자열의 외톨이 서로게이트(깨진 UTF-16 원문 등)는 U+FFFD로 바꾼다(직렬화·색인 쓰기 보호).
    """
    draft = _scrub_draft(draft)
    source_id = scrub_surrogates(source_id)
    origin = scrub_surrogates(origin)
    repo_root = scrub_surrogates(repo_root)
    if event_source is not None:
        event_source = scrub_surrogates(event_source)
    identity = identity_for(
        draft,
        source_id=source_id,
        origin=origin,
        offset=offset,
        index=index,
        generation=generation,
    )
    uid = event_uid(identity)
    title: JsonValue = draft.title
    detail = bounded(draft.detail)
    raw = bounded(draft.raw)
    if redact is not None:
        title, detail, raw = (scrub_surrogates(redact(v)) for v in (title, detail, raw))
    summary_source: JsonValue = detail if detail is not None else raw if raw is not None else ""
    if draft.summary is not None:  # 분류기가 준 평문 요약(가리기는 같은 규칙으로)
        summary_source = (
            scrub_surrogates(redact(draft.summary)) if redact is not None else draft.summary
        )
    summary = text(summary_source)[:SUMMARY_CHARS] if summary_source != "" else ""
    usage = draft.usage
    message_id = draft.message_id
    if usage is not None:
        message_id = message_id or usage.message_id or f"~{uid}"
        usage = usage.model_copy(
            update={
                "thread": usage.thread or draft.thread,
                "message_id": usage.message_id or message_id,
                "model": usage.model or draft.model,
                "time": usage.time if usage.time is not None else draft.time,
            }
        )
    event = LogEvent.model_validate(
        {
            "uid": uid,
            "seq": 0,
            "source": event_source or source_id,
            "ref": origin,
            "observed_at": observed_at,
            "category": draft.category,
            "title": str(title)[:2000] if title is not None else "",
            "summary": summary,
            "stage": draft.stage,
            "status": draft.status,
            "thread": draft.thread,
            "role": draft.role,
            "actor": draft.actor,
            "from": list(draft.from_),
            "to": list(draft.to),
            "via": draft.via,
            "tool": draft.tool,
            "call_id": draft.call_id,
            "turn_id": draft.turn_id,
            "message_id": message_id,
            "session": draft.session,
            "cwd": draft.cwd,
            "repo_root": repo_root,
            "model": draft.model,
            "run_id": draft.run_id,
            "node_path": list(draft.node_path),
            "time": draft.time,
            "evidence": draft.evidence,
            "tags": sorted({draft.category, *draft.tags}),
            "documents": [d.model_dump() for d in draft.documents],
            "correlation": dict(draft.correlation),
            "detail": detail,
            "raw": raw,
        }
    )
    return IndexRecord(event=event, identity=identity, usage=usage, agent=draft.agent)
