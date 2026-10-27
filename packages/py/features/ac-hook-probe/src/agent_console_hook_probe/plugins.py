"""hook probe 기록을 읽는 로그 출처(X5 `hook-probe-jsonl`)와 분류기(X6 `hook-probe`).

기록 한 줄(`hook-probe/1`) → 이벤트 둘: 시작(`stage=start`, `started_at`)과 끝(`stage=complete`,
`ended_at`). 둘은 같은 `call_id`(= probe 실행 id)라 색인이 소요 시간을 계산한다(명시 id 짝).
도구 호출과는 `correlation.call_id = tool_use_id`로 이어진다(다른 출처의 도구 이벤트와 같은
근거 이름).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar

from agent_console_contracts import x_ui
from agent_console_contracts.logs import LogClassifierDescriptor, LogSourceDescriptor
from agent_console_logs import (
    JSONL_CONFIG_SCHEMA,
    ClassifyContext,
    JsonlFileSource,
    JsonValue,
    LogEventDraft,
    LogSourceContext,
    RawRecord,
    timestamp,
)

from ._record import RECORD_FORMAT

__all__ = [
    "CLASSIFIER_ID",
    "DEFAULT_INCLUDE",
    "PROBE_FOLDER",
    "SOURCE_ID",
    "HookProbeClassifier",
    "HookProbeSource",
]

SOURCE_ID = "hook-probe-jsonl"
CLASSIFIER_ID = "hook-probe"
PROBE_FOLDER = "hook-probe"
"""Run 파일 폴더 안 기록 폴더 이름(`<state>/runs/<run>/<node>/hook-probe/`)."""

DEFAULT_INCLUDE = [f"**/{PROBE_FOLDER}/*.jsonl"]

_SOURCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        **JSONL_CONFIG_SCHEMA["properties"],
        "roots": {
            **JSONL_CONFIG_SCHEMA["properties"]["roots"],
            "description": (
                "읽을 폴더 목록. 비우면 Run 파일 폴더. "
                "직접 감싼 hook(도구 실행 전후에 도는 명령)의 기록 폴더를 더할 수 있다."
            ),
        },
        "include": {**JSONL_CONFIG_SCHEMA["properties"]["include"], "default": DEFAULT_INCLUDE},
        "run_layout": {
            "type": "boolean",
            "default": True,
            "title": "Run 폴더 구조 읽기",
            "description": (
                "경로를 `<run>/<노드…>/hook-probe/<파일>`로 보고 run_id·node_path를 채운다"
                "(기록의 context가 있으면 그쪽이 우선)."
            ),
            **x_ui(tier="advanced"),
        },
    },
}


class HookProbeSource(JsonlFileSource):
    """hook probe 기록 jsonl 출처. 이미 플랫폼 데이터라 기본 켜짐."""

    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id=SOURCE_ID,
        title="hook probe 기록",
        format=CLASSIFIER_ID,
        description=(
            "hook 감싸기(`agent-console-hook-probe`)가 남긴 입출력·결정·소요 시간 기록을 읽는다."
        ),
        config_schema=_SOURCE_SCHEMA,
        default_enabled=True,
        reads_paths=True,
        setup_help=(
            "플랫폼 실행에서 `observe.hook_probe`를 켜면 Run 파일 폴더에 기록이 생긴다. "
            "외부 Claude Code 세션은 hook 명령 앞에 "
            "`agent-console-hook-probe --out <폴더> --`를 붙이고 그 폴더를 `roots`에 더한다."
        ),
    )

    def default_roots(self, ctx: LogSourceContext) -> list[Path]:
        """호스트 상태 폴더(`ctx.paths["state"]`)의 `runs`. 상태 폴더를 모르면 없음."""
        state = ctx.paths.get("state")
        return [Path(state) / "runs"] if state is not None else []

    def ref_meta(self, root: Path, path: Path, ctx: LogSourceContext) -> Mapping[str, JsonValue]:
        """`run_layout`이면 경로에서 run_id·node_path를 꺼낸다."""
        if ctx.config.get("run_layout", True) is False:
            return {}
        parts = PurePosixPath(path.relative_to(root).as_posix()).parts
        if len(parts) < 3 or parts[-2] != PROBE_FOLDER:
            return {}
        return {"run_id": parts[0], "node_path": list(parts[1:-2])}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _strs(value: Any) -> tuple[str, ...]:
    if isinstance(value, list | tuple):
        return tuple(str(v) for v in value if isinstance(v, str) and v)
    if isinstance(value, str) and value:
        return tuple(p for p in value.split("/") if p)
    return ()


def _v1(
    row: Mapping[str, Any], ref_meta: Mapping[str, Any], cfg: Mapping[str, Any]
) -> list[LogEventDraft]:
    raw_context = row.get("context")
    context: Mapping[str, Any] = raw_context if isinstance(raw_context, Mapping) else {}
    raw_decision = row.get("decision")
    decision: Mapping[str, Any] = raw_decision if isinstance(raw_decision, Mapping) else {}
    event = _text(row.get("event")) or "hook"
    tool = _text(row.get("tool"))
    matcher = _text(row.get("matcher"))
    label = " ".join(p for p in (event, tool or matcher) if p)
    value = _text(decision.get("value")) or "none"
    probe_id = _text(row.get("probe_id"))
    tool_use_id = _text(row.get("tool_use_id"))
    correlation: dict[str, str | list[str]] = {}
    if tool_use_id:
        correlation["call_id"] = tool_use_id
    if probe_id:
        correlation[_text(cfg.get("probe_basis")) or "hook_probe"] = probe_id
    category = _text(cfg.get("category")) or "hook"
    failed = value == "error"
    start = LogEventDraft(
        category=category,
        title=f"{label} 시작",
        stage="start",
        thread=_text(row.get("agent_id")),
        role=_text(row.get("agent_type")),
        actor=_text(cfg.get("actor")),
        via=event,
        tool=tool,
        call_id=probe_id,
        session=_text(row.get("session_id")),
        cwd=_text(row.get("cwd")),
        run_id=_text(context.get("run_id")) or _text(ref_meta.get("run_id")),
        node_path=_strs(context.get("node_path") or context.get("node"))
        or _strs(ref_meta.get("node_path")),
        time=timestamp(row.get("started_at")),
        tags=("hook", f"hook:{event}", f"decision:{value}"),
        correlation=correlation,
        detail={"input": row.get("input"), "matcher": matcher or None},
    )
    exit_code = row.get("exit_code")
    outcome = f"exit {exit_code}" if exit_code is not None else _text(row.get("error")) or "signal"
    end = replace(
        start,
        category=(_text(cfg.get("error_category")) or "error") if failed else category,
        title=f"{label} → {value} ({outcome})",
        stage="complete",
        status=value,
        time=timestamp(row.get("ended_at")),
        detail={k: v for k, v in row.items() if k != "input"},
        raw=dict(row),
    )
    return [start, end]


_Parser = Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], list[LogEventDraft]]

_PARSERS: dict[str, _Parser] = {
    RECORD_FORMAT: _v1,
}
"""기록 형식 → 해석 함수. 형식이 바뀌면 버전을 더한다(옛 기록도 계속 읽는다)."""


class HookProbeClassifier:
    """`hook-probe/1` 기록 → 시작·끝 이벤트(행 단위 무상태)."""

    descriptor: ClassVar[LogClassifierDescriptor] = LogClassifierDescriptor(
        id=CLASSIFIER_ID,
        formats=[CLASSIFIER_ID],
        title="hook probe",
        description="hook 이벤트·매처·입력·결정·종료 코드·소요 시간을 이벤트로 만든다.",
        config_schema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "default": "hook",
                    "title": "범주",
                    "description": "hook 이벤트의 범주 id.",
                },
                "error_category": {
                    "type": "string",
                    "default": "error",
                    "title": "실패 범주",
                    "description": (
                        "막지 않는 오류(종료 코드 0·2 외)·실행 실패 끝 이벤트의 범주. "
                        "오류로 세지 않으려면 `hook`으로."
                    ),
                },
                "actor": {
                    "type": "string",
                    "default": "hook",
                    "title": "actor",
                },
                "probe_basis": {
                    "type": "string",
                    "default": "hook_probe",
                    "title": "실행 상관 근거 이름",
                    "description": "시작·끝 이벤트를 잇는 correlation 키.",
                },
            },
        },
    )

    def classify(self, record: RawRecord, ctx: ClassifyContext) -> list[LogEventDraft]:
        """기록 한 줄 → 이벤트 둘. 모르는 형식이면 ValueError(→ 진단 이벤트)."""
        row = record.data
        if not isinstance(row, Mapping):
            raise ValueError("hook probe 기록은 JSON 객체여야 합니다.")
        parser = _PARSERS.get(_text(row.get("format")))
        if parser is None:
            raise ValueError(f"알 수 없는 hook probe 기록 형식: {row.get('format')!r}")
        return parser(row, record.meta, ctx.config)
