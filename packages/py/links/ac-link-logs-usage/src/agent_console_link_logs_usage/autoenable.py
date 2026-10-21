"""이 PC에 로그가 있는 출처를 기본으로 켜기(포트 ``logs.source_defaults``, design §5.2R.5).

``local-logs`` 추정은 로그 색인에 표본이 있어야 값이 나온다. 그런데 Claude Code 세션 로그 출처는
대화 원문을 색인에 복사하므로 디스크립터 기본이 꺼짐이다. 이 연동은 "그 로그 폴더가 이 PC에 있으면"
그 출처를 **읽기 전용 기본 출처**로 켠다.

- 규칙은 데이터다(``data/auto_log_sources.json`` 또는 설치자 옵션 ``auto_log_sources_file``). 코드에
  출처 id·경로가 없다.
- 폴더가 있는지만 본다(``stat``). 그 폴더나 ``~/.claude``에 아무것도 쓰지 않는다.
- 설정 파일은 고치지 않는다. 사용자가 ``logs.sources[].enabled``를 적으면(끔 포함) ``mod-logs``가
  그 값을 쓴다(``mod-logs`` ``apply_source_defaults``).
- 이 연동은 ``mod-logs``·``mod-usage``가 둘 다 켜져 있을 때만 켜지므로, 둘 중 하나나 이 연동을 끄면
  자동 켜기도 없다.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from agent_console_logs import expand_user_path

__all__ = ["AutoLogSource", "load_auto_log_sources", "log_source_defaults"]

_RESOURCE = "auto_log_sources.json"


@dataclass(frozen=True, slots=True)
class AutoLogSource:
    """규칙 하나: ``path``(또는 환경 변수 ``env`` 아래 ``env_subpath``) 폴더가 있으면 출처
    ``id``를 켠다.

    환경 변수가 있으면 그 경로만 본다(출처의 기본 루트 규칙과 같다). ``~``는 주입된 환경의 홈이다.
    """

    id: str
    path: str = ""
    env: str = ""
    env_subpath: str = ""

    def target(self, environ: Mapping[str, str]) -> Path | None:
        """볼 폴더(정할 수 없으면 ``None``)."""
        base = environ.get(self.env, "") if self.env else ""
        if base:
            root = expand_user_path(base, environ)
            return root / self.env_subpath if self.env_subpath else root
        if not self.path:
            return None
        found = expand_user_path(self.path, environ)
        # 홈을 모르면 "~"가 남는다: 상대 경로로 읽지 않는다(작업 폴더 기준으로 잘못 보지 않게)
        return found if found.is_absolute() else None


def _rules(items: Iterable[Any]) -> list[AutoLogSource]:
    out: list[AutoLogSource] = []
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("auto_log_sources 항목에는 id(문자열)가 있어야 합니다")
        out.append(
            AutoLogSource(
                id=item["id"],
                path=str(item.get("path") or ""),
                env=str(item.get("env") or ""),
                env_subpath=str(item.get("env_subpath") or ""),
            )
        )
    return out


def load_auto_log_sources(path: Path | None = None) -> list[AutoLogSource]:
    """규칙 데이터(``{"log_sources": [...]}``)를 읽는다. ``path``가 없으면 패키지 데이터.

    Raises:
        ValueError: 형식이 맞지 않을 때.
        OSError: 파일을 읽지 못할 때.
    """
    if path is not None:
        text = path.read_text(encoding="utf-8")
    else:
        text = (files(__package__) / "data" / _RESOURCE).read_text(encoding="utf-8")
    data = json.loads(text)
    items = data.get("log_sources") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("auto_log_sources 데이터에는 log_sources 목록이 있어야 합니다")
    return _rules(items)


def log_source_defaults(
    rules: Iterable[AutoLogSource],
    environ: Mapping[str, str],
    *,
    is_dir: Callable[[Path], bool] = Path.is_dir,
) -> dict[str, bool]:
    """폴더가 있는 규칙의 출처 id → ``True``(없는 것은 넣지 않는다 — 출처 기본값 그대로).

    >>> import tempfile
    >>> home = tempfile.mkdtemp()
    >>> rule = AutoLogSource(id="my-logs", path="~/logs")
    >>> log_source_defaults([rule], {"HOME": home})
    {}
    >>> (Path(home) / "logs").mkdir()
    >>> log_source_defaults([rule], {"HOME": home})
    {'my-logs': True}
    """
    out: dict[str, bool] = {}
    for rule in rules:
        target = rule.target(environ)
        try:
            found = target is not None and is_dir(target)
        except OSError:
            found = False
        if found:
            out.setdefault(rule.id, True)
    return out
