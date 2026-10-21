"""공통 설정 저장 전 검사: 사용량 출처 설정을 그 출처 ``config_schema``로 본다(4R.13 QA 후속).

``definitions.checks`` 하나로 제공된다. 정의 저장 쪽(``mod-definitions``의 ``PUT /settings``,
``mod-versions`` 되돌리기, ``mod-presets`` 적용)이 error 이슈를 보면 422(``validation_failed``,
``details.issues[].path`` = 문서 기준 위치)로 거부한다. 메시지에 값·스키마 원문은 없다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_console_contracts import Issue, UsageSettings
from agent_console_store import SETTINGS_KIND
from agent_console_usage import UsageService

__all__ = ["UsageSettingsCheck", "usage_settings_of"]


def usage_settings_of(document: Any) -> UsageSettings | None:
    """워크스페이스 설정 문서(원문 매핑 또는 pydantic 모델)의 ``usage`` 부분. 없거나 모델에 맞지
    않으면 None(모델 검증은 저장소가 따로 한다)."""
    raw: Any = (
        document
        if isinstance(document, Mapping)
        else document.model_dump(mode="json", exclude_unset=True)
        if hasattr(document, "model_dump")
        else None
    )
    usage = raw.get("usage") if isinstance(raw, Mapping) else None
    if not isinstance(usage, Mapping):
        return None
    try:
        return UsageSettings.model_validate(usage)
    except ValueError:  # pydantic ValidationError
        return None


class UsageSettingsCheck:
    """``definitions.checks`` 하나: ``usage.sources[i].config`` ↔ 출처 ``config_schema``.

    지금 쓸 수 있는 출처(플러그인 레지스트리 + ``usage.sources`` 포트의 런타임 출처)만 검증한다.
    저장 시점에 없는 출처(연동 꺼짐·미설치)의 설정은 통과시키고, 그 출처가 나타나면
    ``server.warnings``·``GET /usage/sources``의 ``error``가 알린다.

    Args:
        service: 사용량 수집 서비스(검사할 때마다 출처 목록을 다시 읽는다).
        settings_kind: 공통 설정 정의 종류 이름.
    """

    def __init__(
        self,
        service: UsageService,
        *,
        settings_kind: str = SETTINGS_KIND.name,
    ) -> None:
        self._service = service
        self._kind = settings_kind

    def issues(self, kind: str, document: Any) -> Sequence[Issue]:
        if kind != self._kind:
            return []
        usage = usage_settings_of(document)
        if usage is None or not usage.sources:
            return []
        return self._service.config_issues(usage)
