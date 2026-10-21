"""채팅 설정 층(공통 → 팀 구성) 해석 도우미."""

from collections.abc import Callable

from agent_console_contracts import ChatSettings, Graph

from ._ports import ChatSettingsResolver


def overlay_chat_settings(common: ChatSettings, graph: Graph | None) -> ChatSettings:
    """공통 채팅 설정 위에 팀 구성 층(`graph.settings.chat`)에서 **지정한 필드만** 덮어쓴다.

    채팅 설정 필드는 모두 스칼라라 층 규칙은 "지정하면 교체, 생략하면 상속"이다.

    Args:
        common: 공통 층 값(`WorkspaceSettings.chat`).
        graph: 팀 구성. None이거나 채팅 설정이 없으면 공통 값 그대로.

    Returns:
        유효 채팅 설정(새 객체).
    """
    team = graph.settings.chat if graph is not None and graph.settings is not None else None
    if team is None:
        return common.model_copy()
    merged = common.model_dump()
    merged.update(team.model_dump(exclude_unset=True))
    return ChatSettings.model_validate(merged)


def layered_chat_settings(
    common: ChatSettings | Callable[[], ChatSettings] | None = None,
) -> ChatSettingsResolver:
    """`ChatService(settings=...)`에 넘길 해석기를 만든다.

    Args:
        common: 공통 층 값, 또는 호출할 때마다 최신 공통 값을 돌려주는 함수(설정 파일이
            바뀌어도 서비스를 다시 만들 필요가 없게). None이면 스키마 기본값.
    """

    def resolve(graph: Graph | None) -> ChatSettings:
        base = common() if callable(common) else (common or ChatSettings())
        return overlay_chat_settings(base, graph)

    return resolve
