"""`agent-console logs purge`: 로그 색인 비우기(M-3). 로직은 `agent_console_logs.purge_index`.

여기서는 색인 파일을 열고, 인자를 넘기고, 결과를 한 줄로 쓴다. 원본 로그 파일은 건드리지 않는다.
기본은 세기만 한다(dry-run). `--yes`가 있어야 지운다. 출처·범주 이름은 사용자가 주는 데이터다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


@dataclass(frozen=True, slots=True)
class PurgeOptions:
    """명령 인자(검사 전).

    Attributes:
        sources: 출처 id(빈 목록 = 조건 없음).
        categories: 범주 id(빈 목록 = 조건 없음).
        before: 이 시각보다 이른 이벤트(`parse_before`로 읽은 epoch 초).
        rescan: 커서도 지워 다음 수집에서 다시 색인되게 한다.
        apply: True면 실제로 지운다(`--yes`). False면 센다.
        everything: 조건 없이 색인 전체를 지우는 것을 허락한다(`--all`).
    """

    sources: Sequence[str] = ()
    categories: Sequence[str] = ()
    before: float | None = None
    rescan: bool = True
    apply: bool = False
    everything: bool = False


def parse_before(text: str) -> float:
    """`--before` 값 → epoch 초. 숫자(epoch 초) 또는 ISO 8601 날짜·시각(시간대 없으면 로컬).

    Raises:
        ValueError: 읽을 수 없는 값.
    """
    value = text.strip()
    try:
        return float(value)
    except ValueError:
        pass
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"--before는 epoch 초나 ISO 8601 시각입니다: {text!r}") from None
    return moment.timestamp()


def run_purge(index_path: Path, options: PurgeOptions, *, out: TextIO, err: TextIO) -> int:
    """색인 파일을 열고 비운다(또는 센다). 종료 코드를 돌려준다.

    - 조건이 하나도 없는데 `everything`이 아니면 2(실수로 전부 지우지 않게).
    - 파일·테이블이 없으면 2(만들지 않는다).
    """
    from agent_console_logs import purge_index
    from agent_console_logs.sqlite import open_existing_log_index

    scoped = bool(options.sources or options.categories or options.before is not None)
    if not scoped and not options.everything:
        err.write(
            "agent-console logs purge: 범위(--source·--category·--before)가 없습니다. "
            "색인 전체를 비우려면 --all을 주세요\n"
        )
        return EXIT_USAGE
    try:
        index = open_existing_log_index(index_path)
    except (FileNotFoundError, LookupError) as exc:
        err.write(f"agent-console logs purge: {exc}\n")
        return EXIT_USAGE
    try:
        result = purge_index(
            index,
            sources=list(options.sources) or None,
            categories=list(options.categories) or None,
            before=options.before,
            rescan=options.rescan,
            dry_run=not options.apply,
        )
    except ValueError as exc:
        err.write(f"agent-console logs purge: {exc}\n")
        return EXIT_USAGE
    except Exception as exc:  # DB 잠김 등
        err.write(f"agent-console logs purge: 실패({type(exc).__name__}: {exc})\n")
        return EXIT_FAILED
    finally:
        index.close()
    verb = "지웠습니다" if options.apply else "지울 행(dry-run, 지우지 않음)"
    out.write(
        f"{verb}: 이벤트 {result.events} · 토큰 표본 {result.usage} · "
        f"커서 {result.cursors} · 에이전트 {result.agents}\n"
    )
    if not options.apply:
        out.write("실제로 지우려면 --yes를 주세요.\n")
    elif options.rescan and result.cursors:
        out.write("다음 수집에서 범위 출처를 처음부터 다시 읽습니다.\n")
    return EXIT_OK


__all__ = ["PurgeOptions", "parse_before", "run_purge"]
