"""테스트 도구: 이벤트 만들기, 칸·연결 id 바꾸기(R0 판정: id를 모두 바꿔도 같은 수),
테스트 전용 합성 프로필 문서(`demo_profile`), 수집 결과 표본(`load_sample`).

`demo_profile`은 이 폴더의 `demo_profile.yaml`을 읽는다. 기본 프로필 데이터가 아니다.
id·범주·출처 종류는 테스트가 정한 임의 값이다.

`load_sample`은 이 폴더 `samples/`의 이벤트 사본을 읽는다(기본 프로필 골든 테스트 재료,
design §5.5R.10). 사본은 실제 수집 파이프라인(`ac-logs` 수집기 + 기본 분류 데이터)이 합성 기록에서
만든 목록 질의 결과다(`detail`·`raw`는 목록에 없으므로 빠져 있다). 실제 `~/.claude` 기록이 아니다.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

from agent_console_contracts.architecture import (
    ArchitectureCoverage,
    ArchitectureEdge,
    ArchitectureProfile,
)
from agent_console_contracts.logs import LogEvent, TokenSample

__all__ = [
    "SAMPLES",
    "Sample",
    "demo_profile",
    "load_sample",
    "make_event",
    "make_events",
    "rename_profile_ids",
]

_PACKAGE = "agent_console_architecture.testing"
_DEMO_PROFILE = "demo_profile.yaml"


def make_event(seq: int, **fields: Any) -> LogEvent:
    """로그 이벤트 하나. 빈 필수 값(`uid`·`source`·`observed_at`·`category`)을 채운다.

    Args:
        seq: 색인 순번(`uid` 기본값 `e<seq>`).
        **fields: `LogEvent` 필드(JSON 별칭 `from`도 받는다).
    """
    data: dict[str, Any] = {
        "uid": f"e{seq}",
        "seq": seq,
        "source": "src",
        "observed_at": 0.0,
        "category": "unknown",
    }
    data.update(fields)
    return LogEvent.model_validate(data)


def make_events(rows: Iterable[Mapping[str, Any]], *, start: int = 1) -> list[LogEvent]:
    """행 목록 → 이벤트(순번은 `start`부터, 행에 `seq`가 있으면 그 값)."""
    events: list[LogEvent] = []
    for offset, row in enumerate(rows):
        fields = dict(row)
        seq = int(fields.pop("seq", start + offset))
        events.append(make_event(seq, **fields))
    return events


def rename_profile_ids(
    profile: ArchitectureProfile,
    *,
    cell: Callable[[str], str],
    edge: Callable[[str], str] | None = None,
) -> ArchitectureProfile:
    """칸·연결 id를 모두 바꾼 사본(연결 양 끝·수집 범위·부분 표시도 함께 바꾼다).

    Args:
        profile: 원본.
        cell: 칸 id → 새 id.
        edge: 연결 id → 새 id(없으면 그대로).
    """
    rename_edge = edge or (lambda value: value)
    cells = {cell(cid): spec for cid, spec in profile.cells.items()}
    edges = [
        ArchitectureEdge.model_validate(
            {
                **e.model_dump(by_alias=True, exclude_unset=True),
                "id": rename_edge(e.id),
                "from": cell(e.from_),
                "to": cell(e.to),
            }
        )
        for e in profile.edges
    ]
    coverage = {
        kind: ArchitectureCoverage(
            cells=[cell(c) for c in cov.cells],
            partial={cell(c): reason for c, reason in cov.partial.items()},
        )
        for kind, cov in profile.coverage.items()
    }
    return profile.model_copy(update={"cells": cells, "edges": edges, "coverage": coverage})


def demo_profile() -> str:
    """테스트 전용 합성 프로필 문서(YAML, 프로필 id `demo`).

    칸 `input`·`model`·`tools`·`workers`·`memo`, 연결 `ask`·`call`·`back`, 출처 종류
    `kind-a`·`kind-b`. `parse_profiles_document(demo_profile())["demo"]`로 읽는다.

    Returns:
        프로필 문서 YAML 문자열(패키지 자원 `testing/demo_profile.yaml`, 부를 때마다
        새로 읽는다).
    """
    return (
        resources.files(__package__ or _PACKAGE).joinpath(_DEMO_PROFILE).read_text(encoding="utf-8")
    )


SAMPLES: tuple[str, ...] = ("claude_code_session", "run_with_session_log")
"""`load_sample` 이름.

- ``claude_code_session``: Claude Code 세션 로그 하나(메인 + 서브에이전트 1, hook·MCP·위임·
  문서 읽기·파일 쓰기·압축·해석 실패 행 포함). `ac-logs-claude` 합성 픽스처를 `claude-code-jsonl`
  출처로 수집한 것.
- ``run_with_session_log``: 같은 실행을 두 출처로 읽은 것. `fake-agent` 실행 기록(hook·MCP·위임·
  맥락 구성·모델 소요 포함)을 `platform-runs` 출처로, 같은 세션의 Claude Code 세션 로그(같은 도구
  호출 id)를 `claude-code-jsonl` 출처로 수집했다. 같은 도구 호출이 두 출처에 한 번씩 있다.
"""


@dataclass(frozen=True, slots=True)
class Sample:
    """수집 결과 표본: 이벤트(목록 질의 결과, 순번 순), 토큰 표본, 출처 id → 출처 종류."""

    events: list[LogEvent]
    tokens: list[TokenSample]
    source_kinds: dict[str, str]


def load_sample(name: str) -> Sample:
    """수집 결과 표본을 읽는다(부를 때마다 새로 읽는다).

    Args:
        name: `SAMPLES`의 이름.

    Raises:
        KeyError: 모르는 이름.
    """
    if name not in SAMPLES:
        raise KeyError(name)
    text = (
        resources.files(__package__ or _PACKAGE)
        .joinpath("samples", f"{name}.json")
        .read_text(encoding="utf-8")
    )
    data = json.loads(text)
    return Sample(
        events=[LogEvent.model_validate({"observed_at": 0.0, **row}) for row in data["events"]],
        tokens=[TokenSample.model_validate(row) for row in data["tokens"]],
        source_kinds={str(k): str(v) for k, v in data["source_kinds"].items()},
    )
