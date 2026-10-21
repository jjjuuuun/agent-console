"""포트 키와 모듈 이벤트 토픽(design §3R.1.2, modularity §3.2).

포트·토픽은 **이름 문자열**로 식별한다. 같은 이름이면 같은 포트다. 타입 매개변수는 정적 검사용이며
실행 중에는 이름만 맞춘다(모양 확인은 각 연결 쌍의 계약 테스트가 한다).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PortKey[T]:
    """모듈 사이에 주고받는 구현 하나(또는 목록)의 이름.

    Args:
        name: 포트 이름(예: ``"definitions.store"``). 같은 이름 = 같은 포트.
        description: 사람이 읽는 설명(보고용).
        multi: 참이면 여러 모듈이 제공해도 충돌이 아니고, 소비자는 모듈 id 순 **목록**으로 받는다
            (``ModuleContext.ports``).

    같음·해시는 ``name``만 본다.
    """

    name: str
    description: str = field(default="", compare=False)
    multi: bool = field(default=False, compare=False)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("포트 이름이 비어 있습니다")


@dataclass(frozen=True)
class Topic[T]:
    """프로세스 안 모듈 이벤트 토픽(``EventBus``). WS 토픽과는 별개다.

    Args:
        name: 토픽 이름(예: ``"runs.event"``). 같은 이름 = 같은 토픽.
    """

    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("토픽 이름이 비어 있습니다")


__all__ = ["PortKey", "Topic"]
