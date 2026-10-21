"""출처 B: `agent-console statusline` 브리지가 쓴 파일(design §R4.3, 연결 안내 §5.2R.5)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from agent_console_contracts import (
    KnownUsageTrust,
    UsageSourceDescriptor,
    UsageWindowSnapshot,
    x_ui,
)
from agent_console_usage._interfaces import UsageSourceContext
from agent_console_usage._setup import SETUP_OUTPUT_PATH, descriptor_fields
from agent_console_usage.statusline import DEFAULT_STATUSLINE_FILE, load_statusline_windows

__all__ = ["StatuslineFileSource"]


class StatuslineFileSource:
    """브리지 파일의 창별 관측값. 파일이 없으면 빈 목록(아직 연결하지 않음).

    config `path`: 파일 경로. 상대 경로면 workspace 시스템 기록 폴더(`state_dir`) 기준이며
    기본은 `usage/statusline.json`. 상태 폴더도 절대 경로도 없으면 빈 목록이다.
    statusLine 입력을 그대로 남긴 파일도 읽는다(`load_statusline_windows`).

    연결 안내(`needs_setup`·`setup_snippets`·`setup_help`·`windows`)는 패키지 데이터
    `data/sources.json`이다. 조각의 `{output_path}`는 `setup_values`가 읽을 파일의 절대 경로로
    채운다.
    """

    descriptor = UsageSourceDescriptor(
        id="statusline-file",
        title="Claude Code 상태 줄",
        description=(
            "대화형 Claude Code가 statusLine 명령에 넘기는 사용량(5시간·7일 사용률)을 "
            "`agent-console statusline`이 파일로 남긴 값. Pro/Max 구독, 세션 첫 응답 이후에만 있다."
        ),
        trust=KnownUsageTrust.OFFICIAL,
        config_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "default": str(DEFAULT_STATUSLINE_FILE),
                    "title": "파일 경로",
                    "description": (
                        "상태 줄 브리지가 쓰는 파일입니다. 상대 경로면 작업 공간의 .state 폴더 "
                        "기준입니다."
                    ),
                    **x_ui(
                        tier="basic",
                        when="상태 줄 브리지가 다른 파일에 쓰도록 설정했을 때 맞춰 바꾸세요.",
                    ),
                },
            },
            "additionalProperties": False,
        },
        docs_url="https://code.claude.com/docs/en/statusline",
        **descriptor_fields("statusline-file"),
    )

    def resolve_path(self, ctx: UsageSourceContext) -> Path | None:
        """읽을 파일 경로. 상대 경로인데 `state_dir`가 없으면 `None`."""
        path = Path(str(ctx.config.get("path", DEFAULT_STATUSLINE_FILE)))
        if path.is_absolute():
            return path
        return None if ctx.state_dir is None else ctx.state_dir / path

    def setup_values(self, ctx: UsageSourceContext) -> Mapping[str, str]:
        """연결 조각 자리표시자 값: `output_path` = 읽을 파일의 절대 경로(모르면 없음)."""
        path = self.resolve_path(ctx)
        return {} if path is None else {SETUP_OUTPUT_PATH: str(path.absolute())}

    def received_at(self, ctx: UsageSourceContext) -> float | None:
        """파일에 마지막으로 값이 들어온 시각(브리지 `updated_at` 또는 원문 파일 수정 시각)."""
        path = self.resolve_path(ctx)
        if path is None:
            return None
        return load_statusline_windows(path).received_at

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        path = self.resolve_path(ctx)
        if path is None:
            return []
        return [
            UsageWindowSnapshot(
                source=ctx.source_id,
                window=w.window,
                used_ratio=w.used_ratio,
                resets_at=w.resets_at,
                observed_at=w.observed_at,
                raw=dict(w.data),
            )
            for w in load_statusline_windows(path).windows
        ]
