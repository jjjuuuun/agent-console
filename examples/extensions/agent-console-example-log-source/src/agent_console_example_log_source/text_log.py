"""로그 출처·분류기 `example.text_log`: 한 줄짜리 텍스트 로그를 정규화 이벤트로 만든다.

형식(한 줄 = 이벤트 하나)::

    <ISO 8601 시각> <수준> [<스레드>] <메시지>
    2026-10-17T09:00:00Z INFO [worker] 작업 시작
    2026-10-17T09:00:02Z ERROR 연결 실패        # [스레드]는 생략할 수 있다

- 출처(X5)는 `JsonlFileSource`를 상속하고 `parse_line`만 바꾼다. 증분 읽기·끝나지 않은 줄 보류·
  파일 회전 감지·읽기 전용 열기는 기반 클래스가 한다. 해석하지 못한 줄은 예외 → 진단 이벤트.
- 분류기(X6)는 행 단위 무상태다. 수준 → 범주 대응은 **설정 데이터**(`level_categories`,
  `default_category`)이고 코드에 범주 목록이 없다.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, ClassVar, Final

from agent_console_contracts.logs import LogClassifierDescriptor, LogSourceDescriptor
from agent_console_logs import (
    JSONL_CONFIG_SCHEMA,
    ClassifyContext,
    JsonlFileSource,
    JsonValue,
    LogEventDraft,
    RawRecord,
    timestamp,
)

FORMAT_ID: Final = "example.text_log"
"""출처 id = 분류기 id = 출처 디스크립터 `format`(entry point 이름과 같다)."""


def parse_text_line(text: str) -> dict[str, JsonValue]:
    """텍스트 로그 한 줄 → `{time, level, thread, message}`.

    Args:
        text: 줄 내용(줄바꿈 제외).

    Returns:
        해석한 필드. `[스레드]`가 없으면 `thread`는 빈 문자열.

    Raises:
        ValueError: 시각·수준·메시지가 없거나 시각이 ISO 8601이 아닐 때(→ 진단 이벤트).
    """
    parts = text.strip().split(maxsplit=2)
    if len(parts) < 3:
        raise ValueError("텍스트 로그 줄은 '<시각> <수준> [<스레드>] <메시지>' 형식이어야 합니다.")
    when, level, rest = parts
    if timestamp(when) is None:
        raise ValueError(f"시각을 해석하지 못했습니다: {when!r}")
    thread = ""
    if rest.startswith("["):
        end = rest.find("]")
        if end > 0:
            thread, rest = rest[1:end].strip(), rest[end + 1 :].strip()
    if not rest:
        raise ValueError("메시지가 비었습니다.")
    return {"time": when, "level": level.upper(), "thread": thread, "message": rest}


_SOURCE_SCHEMA: Final[dict[str, Any]] = copy.deepcopy(JSONL_CONFIG_SCHEMA)
_SOURCE_SCHEMA["properties"]["include"]["default"] = ["**/*.log"]


class TextLogSource(JsonlFileSource):
    """`roots` 아래 `*.log` 파일을 줄 단위로 읽는 출처(X5 예제). 루트를 정해야 하므로 기본 꺼짐."""

    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id=FORMAT_ID,
        title="텍스트 로그(예제)",
        format=FORMAT_ID,
        description="'<시각> <수준> [<스레드>] <메시지>' 형식의 텍스트 로그를 읽는다(예제 확장).",
        config_schema=_SOURCE_SCHEMA,
        default_enabled=False,
        reads_paths=True,
        setup_help="`roots`에 로그 폴더를 넣는다. 기본 포함 패턴은 `**/*.log`이다.",
    )

    def parse_line(self, line: bytes) -> JsonValue:
        """줄 하나 → 필드 객체. 실패하면 `ValueError`/`UnicodeDecodeError`(→ 진단 레코드)."""
        return parse_text_line(line.decode("utf-8"))


_CLASSIFIER_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "level_categories": {
            "type": "object",
            "additionalProperties": {"type": "string", "minLength": 1},
            "default": {"ERROR": "error", "FATAL": "error"},
            "title": "수준 → 범주",
            "description": "수준(대문자)마다 쓸 범주 이름. 없는 수준은 `default_category`.",
        },
        "default_category": {
            "type": "string",
            "minLength": 1,
            "default": "system",
            "title": "기본 범주",
        },
        "actor": {
            "type": "string",
            "default": "",
            "title": "actor",
            "description": "비우면 스레드 이름을 actor로 쓴다.",
        },
    },
    "additionalProperties": False,
}


class TextLogClassifier:
    """`example.text_log` 행 → 초안 하나(X6 예제). 세션 = 파일(ref), 상태 = 수준 소문자."""

    descriptor: ClassVar[LogClassifierDescriptor] = LogClassifierDescriptor(
        id=FORMAT_ID,
        formats=[FORMAT_ID],
        title="텍스트 로그(예제)",
        description="수준을 설정의 대응표로 범주에 옮긴다.",
        config_schema=_CLASSIFIER_SCHEMA,
    )

    def classify(self, record: RawRecord, ctx: ClassifyContext) -> list[LogEventDraft]:
        """해석한 줄 하나를 정규화 이벤트 초안으로 바꾼다.

        Raises:
            ValueError: 출처가 해석한 모양이 아닐 때(→ 진단 이벤트).
        """
        row = record.data
        if not isinstance(row, Mapping) or not isinstance(row.get("message"), str):
            raise ValueError("example.text_log 레코드가 아닙니다.")
        level = str(row.get("level") or "")
        thread = str(row.get("thread") or "")
        mapping = ctx.config.get("level_categories")
        categories = mapping if isinstance(mapping, Mapping) else {}
        category = categories.get(level) or ctx.config.get("default_category") or "system"
        return [
            LogEventDraft(
                category=str(category),
                title=str(row["message"]),
                status=level.lower(),
                thread=thread,
                actor=str(ctx.config.get("actor") or "") or thread,
                session=ctx.ref.ref,
                time=timestamp(row.get("time")),
                detail=dict(row),
            )
        ]
