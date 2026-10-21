"""Claude Code statusLine 브리지(design §R4.3 출처 B).

Claude Code는 statusLine 명령에 세션 정보를 JSON으로 stdin에 넣는다. 그중 `rate_limits`만 꺼내
창별로 파일에 쌓고(원자적 쓰기), 짧은 상태 줄을 만든다.
서버 쪽 `StatuslineFileSource`가 이 파일을 읽는다.

- 창 id는 입력의 `rate_limits` 키 그대로다(`five_hour` 등은 데이터이며 코드에 목록이 없다).
- 창·필드가 빠져 있어도 동작한다. 없는 값은 `None`이며 숫자를 지어내지 않는다.
- 입력의 다른 필드(cwd, session_id, transcript_path 등)는 파일에 남기지 않는다.
- 이 모듈은 `~/.claude`를 읽지도 쓰지도 않는다. 경로는 호출자가 준다.

파일 형식(`format` = 1)::

    {"format": 1, "updated_at": 1738420000.0,
     "windows": {"<창 id>": {"observed_at": ..., "used_percentage": 23.5 | null,
                            "resets_at": 1738425600 | null, "data": {<입력의 창 객체 원문>}}}}
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = [
    "DEFAULT_STATUSLINE_FILE",
    "DEFAULT_STATUSLINE_TEMPLATE",
    "STATUSLINE_FILE_FORMAT",
    "StatuslineReading",
    "StatuslineWindow",
    "default_window_labels",
    "format_duration",
    "format_status_line",
    "load_statusline_windows",
    "merge_statusline",
    "parse_statusline",
    "read_statusline_file",
    "statusline_windows",
    "update_statusline_file",
    "write_statusline_file",
]

STATUSLINE_FILE_FORMAT = 1
"""브리지 파일 형식 버전."""

DEFAULT_STATUSLINE_FILE = PurePosixPath("usage/statusline.json")
"""workspace 시스템 기록 폴더(`<workspace>/.state`) 기준 기본 파일 위치."""

DEFAULT_STATUSLINE_TEMPLATE = "{label} {percent}{resets_suffix}"
"""창 하나의 기본 표시 틀. 자리: `label`, `percent`, `resets_in`, `resets_suffix`, `window`."""


@dataclass(frozen=True, slots=True)
class StatuslineWindow:
    """창 하나의 관측값. 입력에 없던 값은 `None`."""

    window: str
    observed_at: float
    used_percentage: float | None = None
    resets_at: float | None = None
    data: Mapping[str, Any] = field(default_factory=dict)

    @property
    def used_ratio(self) -> float | None:
        """사용률(0~1, 넘을 수 있음). 퍼센트가 없으면 `None`."""
        return None if self.used_percentage is None else self.used_percentage / 100.0

    def expired(self, now: float) -> bool:
        """초기화 시각이 지났으면 참(그 뒤의 사용률은 알 수 없다)."""
        return self.resets_at is not None and self.resets_at <= now


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _load(data: str | bytes | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(data, Mapping):
        return data
    loaded = json.loads(data)
    if not isinstance(loaded, Mapping):
        raise ValueError("statusLine 입력이 JSON 객체가 아닙니다")
    return loaded


def parse_statusline(
    data: str | bytes | Mapping[str, Any], *, now: float
) -> list[StatuslineWindow]:
    """statusLine stdin JSON → 창 목록(입력 순서).

    Args:
        data: stdin 원문(문자열·바이트) 또는 이미 읽은 객체.
        now: 관측 시각(Unix epoch 초).

    Returns:
        `rate_limits`의 객체 값마다 창 하나. `rate_limits`가 없거나 객체가 아니면 빈 목록
        (API 키 인증, 세션 첫 응답 전 등). 숫자가 아니거나 음수인 값은 `None`.

    Raises:
        ValueError: JSON이 아니거나 최상위가 객체가 아니다.
    """
    limits = _load(data).get("rate_limits")
    if not isinstance(limits, Mapping):
        return []
    windows: list[StatuslineWindow] = []
    for name, value in limits.items():
        if not isinstance(name, str) or not name or not isinstance(value, Mapping):
            continue
        windows.append(
            StatuslineWindow(
                window=name,
                observed_at=now,
                used_percentage=_number(value.get("used_percentage")),
                resets_at=_number(value.get("resets_at")),
                data=dict(value),
            )
        )
    return windows


def statusline_windows(document: Mapping[str, Any] | None) -> list[StatuslineWindow]:
    """브리지 파일 내용 → 창 목록(창 id 순). 형식이 맞지 않는 항목은 건너뛴다."""
    if not isinstance(document, Mapping):
        return []
    raw = document.get("windows")
    if not isinstance(raw, Mapping):
        return []
    out: list[StatuslineWindow] = []
    for name in sorted(k for k in raw if isinstance(k, str) and k):
        item = raw[name]
        if not isinstance(item, Mapping):
            continue
        observed = _number(item.get("observed_at"))
        if observed is None:
            continue
        data = item.get("data")
        out.append(
            StatuslineWindow(
                window=name,
                observed_at=observed,
                used_percentage=_number(item.get("used_percentage")),
                resets_at=_number(item.get("resets_at")),
                data=dict(data) if isinstance(data, Mapping) else {},
            )
        )
    return out


def merge_statusline(
    previous: Mapping[str, Any] | None,
    windows: Iterable[StatuslineWindow],
    *,
    now: float,
) -> dict[str, Any]:
    """이전 파일 내용에 새 관측 창을 합친 새 파일 내용.

    새 입력에 없는 창은 이전 관측값(자기 `observed_at`)을 그대로 둔다 — 여러 Claude Code 세션이
    번갈아 쓰거나 한 창만 빠진 입력이 와도 다른 창 값을 잃지 않는다. 초기화 시각이 지난 창은 뺀다.
    """
    merged: dict[str, StatuslineWindow] = {w.window: w for w in statusline_windows(previous)}
    for w in windows:
        merged[w.window] = w
    return {
        "format": STATUSLINE_FILE_FORMAT,
        "updated_at": now,
        "windows": {
            name: {
                "observed_at": w.observed_at,
                "used_percentage": w.used_percentage,
                "resets_at": w.resets_at,
                "data": dict(w.data),
            }
            for name, w in sorted(merged.items())
            if not w.expired(now)
        },
    }


def read_statusline_file(path: Path) -> dict[str, Any] | None:
    """브리지 파일을 읽는다. 없으면 `None`.

    Raises:
        ValueError: JSON이 아니거나 객체가 아니다(파일이 손상됨).
        OSError: 읽기 실패(없음 제외).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("statusline 파일이 JSON 객체가 아닙니다")
    return loaded


@dataclass(frozen=True, slots=True)
class StatuslineReading:
    """파일 하나를 읽은 결과: 창 목록과 마지막으로 값이 들어온 시각(없으면 `None`)."""

    windows: list[StatuslineWindow]
    received_at: float | None


def load_statusline_windows(path: Path) -> StatuslineReading:
    """브리지 파일 **또는 statusLine 입력을 그대로 남긴 파일**을 읽어 창 목록으로.

    - 브리지 파일(`format`): `statusline_windows`, 받은 시각 = `updated_at`.
    - 입력 원문(`rate_limits`가 최상위에 있는 객체, 예: 상태 줄 스크립트의
      `echo "$input" > 파일`): `parse_statusline`, 관측·받은 시각 = 파일 수정 시각.
      `rate_limits` 밖의 필드(cwd·session_id 등)는 쓰지 않는다.
    - 파일이 없으면 빈 목록·`None`.

    Raises:
        ValueError: JSON이 아니거나 객체가 아니다(파일이 손상됨).
        OSError: 읽기 실패(없음 제외).
    """
    document = read_statusline_file(path)
    if document is None:
        return StatuslineReading([], None)
    if "format" not in document and "rate_limits" in document:
        mtime = path.stat().st_mtime
        return StatuslineReading(parse_statusline(document, now=mtime), mtime)
    return StatuslineReading(statusline_windows(document), _number(document.get("updated_at")))


def default_window_labels() -> dict[str, str]:
    """창 id → 짧은 이름(패키지 데이터 `data/sources.json`의 `statusline-file` 창).

    예: `five_hour` → `5h`.

    `agent-console statusline`이 `--label`이 없을 때 쓴다. 데이터를 읽지 못하면 빈 dict.
    """
    try:
        text = (files(__package__) / "data" / "sources.json").read_text(encoding="utf-8")
        windows = json.loads(text)["sources"]["statusline-file"]["windows"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    out: dict[str, str] = {}
    for item in windows if isinstance(windows, list) else []:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str):
            label = item.get("short_title") or item.get("title")
            if isinstance(label, str) and label:
                out[item["id"]] = label
    return out


def write_statusline_file(path: Path, document: Mapping[str, Any]) -> None:
    """원자적으로 쓴다(같은 폴더의 임시 파일 → `os.replace`). 폴더가 없으면 만든다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(document, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def update_statusline_file(
    path: Path, data: str | bytes | Mapping[str, Any], *, now: float
) -> list[StatuslineWindow]:
    """stdin JSON을 파싱해 파일에 합쳐 쓰고, 지금 유효한 창 목록을 돌려준다.

    입력에 창이 하나도 없으면 파일을 건드리지 않는다(이전 관측값 유지). 기존 파일이 손상돼
    있으면 새 입력만으로 다시 쓴다.

    Raises:
        ValueError: 입력이 JSON 객체가 아니다(파일은 그대로).
        OSError: 쓰기 실패.
    """
    windows = parse_statusline(data, now=now)
    try:
        previous = read_statusline_file(path)
    except (ValueError, OSError):
        previous = None
    if not windows:
        return [w for w in statusline_windows(previous) if not w.expired(now)]
    document = merge_statusline(previous, windows, now=now)
    write_statusline_file(path, document)
    return statusline_windows(document)


def format_duration(seconds: float) -> str:
    """남은 시간을 짧게(`3d4h`, `2h13m`, `45m`, `<1m`)."""
    total = int(seconds // 60)
    if total < 1:
        return "<1m"
    days, rest = divmod(total, 60 * 24)
    hours, minutes = divmod(rest, 60)
    if days:
        return f"{days}d{hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"


def format_status_line(
    windows: Iterable[StatuslineWindow],
    *,
    now: float,
    labels: Mapping[str, str] | None = None,
    template: str = DEFAULT_STATUSLINE_TEMPLATE,
    separator: str = " · ",
    empty: str = "",
    missing: str = "-",
) -> str:
    """창 목록 → 한 줄 상태 표시.

    Args:
        windows: 표시할 창(순서 유지). 초기화 시각이 지난 창은 뺀다.
        now: 현재 시각(남은 시간 계산).
        labels: 창 id → 표시 이름(없으면 창 id 그대로).
        template: 창 하나의 틀. 자리 `label`, `window`, `percent`(`23%` 또는 `missing`),
            `resets_in`(`2h13m` 또는 빈 문자열), `resets_suffix`(` (2h13m)` 또는 빈 문자열).
        separator: 창 사이 구분자.
        empty: 보일 창이 없을 때의 문자열.
        missing: 사용률이 없을 때 `percent` 자리 값(숫자를 지어내지 않는다).

    Raises:
        KeyError: 틀에 모르는 자리가 있다.
    """
    names = labels or {}
    parts: list[str] = []
    for w in windows:
        if w.expired(now):
            continue
        resets_in = format_duration(w.resets_at - now) if w.resets_at is not None else ""
        percent = missing if w.used_percentage is None else f"{round(w.used_percentage)}%"
        parts.append(
            template.format(
                label=names.get(w.window, w.window),
                window=w.window,
                percent=percent,
                resets_in=resets_in,
                resets_suffix=f" ({resets_in})" if resets_in else "",
            )
        )
    return separator.join(parts) if parts else empty
