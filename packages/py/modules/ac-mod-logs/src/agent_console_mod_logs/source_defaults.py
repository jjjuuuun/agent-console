"""다른 모듈이 정하는 로그 출처 기본 켜기(포트 ``logs.source_defaults``, design §5.2R.5).

설정에 ``enabled``를 적지 않은 출처의 기본값은 디스크립터 ``default_enabled``다. 연동 모듈이
"이 PC에 그 로그가 있으면 기본으로 읽는다" 같은 판단을 하고 싶을 때 이 포트로 출처 id → 기본값을
준다. ``mod-logs``는 출처 이름을 모르고 받은 값을 그대로 적용만 한다.

- 사용자가 ``logs.sources[].enabled``를 적었으면(켬·끔 모두) 그 값이 이긴다.
- 설정 파일에는 쓰지 않는다(지금 읽은 설정 사본에만 반영).
- 제공자가 여럿이면 먼저 온 것(제공 모듈 id 순)이 이긴다. 제공자 하나가 실패하면 그것만 건너뛴다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping

from agent_console_contracts.logs import LogSettings, LogSourceSetting

__all__ = ["SourceDefaults", "apply_source_defaults", "collect_source_defaults"]

_log = logging.getLogger("agent_console_mod_logs")

type SourceDefaults = Callable[[], Mapping[str, bool]]
"""``logs.source_defaults`` 포트 한 항목: 지금 기본값(출처 id → 켬/끔)을 돌려주는 함수."""


def collect_source_defaults(providers: Iterable[SourceDefaults]) -> dict[str, bool]:
    """제공자들의 기본값을 합친다(먼저 온 제공자가 이김, 실패한 제공자는 건너뜀).

    >>> collect_source_defaults([lambda: {"a": True}, lambda: {"a": False, "b": False}])
    {'a': True, 'b': False}
    """
    out: dict[str, bool] = {}
    for provider in providers:
        try:
            found = provider()
        except Exception:
            _log.exception("로그 출처 기본값 제공자가 실패했습니다")
            continue
        for key, value in found.items():
            out.setdefault(str(key), bool(value))
    return out


def apply_source_defaults(
    settings: LogSettings | None, defaults: Mapping[str, bool]
) -> LogSettings | None:
    """``enabled``를 적지 않은 출처에 기본값을 넣은 설정 **사본**(원본은 그대로).

    >>> s = LogSettings.model_validate({"sources": [{"id": "x", "enabled": False}]})
    >>> out = apply_source_defaults(s, {"x": True, "y": True})
    >>> [(i.id, i.enabled) for i in out.sources]
    [('x', False), ('y', True)]
    """
    if not defaults:
        return settings
    base = settings if settings is not None else LogSettings()
    current = list(base.sources or [])
    by_id = {item.id: index for index, item in enumerate(current)}
    changed = False
    for source_id, enabled in defaults.items():
        index = by_id.get(source_id)
        if index is None:
            current.append(LogSourceSetting(id=source_id, enabled=enabled))
            changed = True
        elif current[index].enabled is None:
            current[index] = current[index].model_copy(update={"enabled": enabled})
            changed = True
    if not changed:
        return settings
    return base.model_copy(update={"sources": current})
