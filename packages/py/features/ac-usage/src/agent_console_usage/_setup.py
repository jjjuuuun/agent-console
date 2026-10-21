"""출처 표시·연결 안내 데이터와 조각 채우기(design §5.2R.5 "사용량", ux-overhaul §8.3).

- 기본 출처의 `auto_enable`·`needs_setup`·`test_only`·`windows`·`setup_help`·`setup_snippets`는
  패키지 데이터 `data/sources.json` 한 곳에 있다(README 조각도 같은 파일에서 나온다).
- `fill_setup_snippets`: 조각 본문의 `{이름}` 자리표시자를 값으로 채운다. 값은 조각의 셸·언어에 맞게
  따옴표를 씌운다(공백이 든 경로도 그대로 붙여 넣을 수 있게). 모르는 자리표시자는 그대로 둔다.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Mapping, Sequence
from functools import cache
from importlib.resources import files
from typing import Any

from agent_console_contracts import UsageSetupSnippet, UsageWindowInfo

__all__ = [
    "SETUP_AGENT_CONSOLE_CMD",
    "SETUP_OUTPUT_PATH",
    "builtin_source_data",
    "descriptor_fields",
    "fill_setup_snippets",
    "fill_setup_text",
]

SETUP_OUTPUT_PATH = "output_path"
"""자리표시자 이름: 상태 줄 브리지 파일의 절대 경로."""

SETUP_AGENT_CONSOLE_CMD = "agent_console_cmd"
"""자리표시자 이름: `agent-console` 명령(가능하면 절대 경로)."""

_DATA_RESOURCE = "sources.json"
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_DESCRIPTOR_KEYS = ("auto_enable", "needs_setup", "test_only", "setup_help")


@cache
def _data() -> dict[str, Any]:
    text = (files(__package__) / "data" / _DATA_RESOURCE).read_text(encoding="utf-8")
    loaded = json.loads(text)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("sources"), dict):
        raise ValueError("data/sources.json 형식이 맞지 않습니다")
    return loaded


def builtin_source_data(section: str) -> dict[str, Any]:
    """기본 출처 하나의 데이터(사본). 없는 이름이면 빈 dict.

    Args:
        section: `data/sources.json`의 `sources` 아래 키(기본 출처 id와 같다).
    """
    found = _data()["sources"].get(section)
    return json.loads(json.dumps(found)) if isinstance(found, dict) else {}


def descriptor_fields(section: str) -> dict[str, Any]:
    """`UsageSourceDescriptor(**...)`에 넣을 데이터 필드(데이터에 있는 것만).

    >>> sorted(descriptor_fields("fake"))
    ['test_only']
    """
    data = builtin_source_data(section)
    out: dict[str, Any] = {k: data[k] for k in _DESCRIPTOR_KEYS if k in data}
    if "windows" in data:
        out["windows"] = [UsageWindowInfo.model_validate(w) for w in data["windows"]]
    if "setup_snippets" in data:
        out["setup_snippets"] = [
            UsageSetupSnippet.model_validate(s) for s in data["setup_snippets"]
        ]
    return out


def _quote(value: str, snippet: UsageSetupSnippet) -> str:
    if snippet.shell.lower() in ("powershell", "pwsh"):
        return "'" + value.replace("'", "''") + "'"
    # 셸 명령(bash 등)과 JSON 안의 statusLine 명령(셸이 실행한다)은 POSIX 셸 규칙
    quoted = shlex.quote(value)
    if snippet.language.lower() == "json":
        quoted = json.dumps(quoted, ensure_ascii=False)[1:-1]
    return quoted


def fill_setup_text(snippet: UsageSetupSnippet, values: Mapping[str, str]) -> str:
    """조각 본문의 자리표시자를 채운 문자열(모르는 자리표시자·빈 값은 그대로).

    >>> s = UsageSetupSnippet(
    ...     id="x", title="x", shell="bash", text="run {cmd} --out {path} {other}"
    ... )
    >>> fill_setup_text(s, {"cmd": "/opt/ac/bin/agent-console", "path": "/my dir/s.json"})
    "run /opt/ac/bin/agent-console --out '/my dir/s.json' {other}"
    """

    def repl(match: re.Match[str]) -> str:
        value = values.get(match.group(1))
        return match.group(0) if not value else _quote(value, snippet)

    return _PLACEHOLDER.sub(repl, snippet.text)


def fill_setup_snippets(
    snippets: Sequence[UsageSetupSnippet], values: Mapping[str, str]
) -> list[UsageSetupSnippet]:
    """조각 목록의 본문을 채운 사본(`fill_setup_text`). 값이 없으면 원본 그대로."""
    if not values:
        return list(snippets)
    return [s.model_copy(update={"text": fill_setup_text(s, values)}) for s in snippets]
