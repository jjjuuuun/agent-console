"""대화 서비스 오류. `code`는 계약 `ErrorCodes` 값이라 전송 계층이 HTTP 상태로 바꿀 수 있다."""

from typing import Any

from agent_console_contracts import ErrorCodes


class ChatError(Exception):
    """대화 서비스 오류의 공통 베이스.

    Attributes:
        code: 계약 오류 코드(`ErrorCodes`). 서버는 `HTTP_STATUS_BY_ERROR_CODE`로 상태를 고른다.
        details: 화면·로그용 추가 정보(비밀 없음).
    """

    code: str = ErrorCodes.BAD_REQUEST

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})


class ConversationNotFoundError(ChatError):
    """대화가 없다."""

    code = ErrorCodes.NOT_FOUND


class GraphNotFoundError(ChatError):
    """대화가 고른 팀 구성(그래프)이 없다."""

    code = ErrorCodes.NOT_FOUND


class QueuedMessageNotFoundError(ChatError):
    """대기열 항목이 없다(이미 실행됐거나 취소됨)."""

    code = ErrorCodes.NOT_FOUND


class TurnNotFoundError(ChatError):
    """턴(Run)이 이 대화에 없다(`turns(before=)` 커서 등)."""

    code = ErrorCodes.NOT_FOUND


class ConversationBusyError(ChatError):
    """실행 중인 턴이 있고 설정 `chat.busy_policy = reject`라 새 메시지를 받지 않는다."""

    code = ErrorCodes.CONVERSATION_BUSY


class TurnNotResumableError(ChatError):
    """이어 갈 수 없는 턴: 대화의 마지막 턴이 아니다(뒤에 새 턴이 생김, design §2R.10)."""

    code = ErrorCodes.RUN_NOT_RESUMABLE


class ChatFeatureUnavailableError(ChatError):
    """주입하지 않은 의존(실행 연결)이 필요한 동작이다(예: 턴 실행기 없이 메시지 전송).

    대화·대기열 관리는 그대로 동작하고 이 동작만 꺼진다. 조립 계층은 `dependency`를 자기 포트
    이름으로 바꿔 알릴 수 있다(서버: 409 `feature_unavailable{module, port}`).

    Attributes:
        dependency: 빠진 의존(`ChatService` 인자 이름: `launcher`·`runs`).
    """

    code = ErrorCodes.FEATURE_UNAVAILABLE

    def __init__(self, dependency: str, message: str | None = None) -> None:
        super().__init__(
            message or f"이 동작에 필요한 연결({dependency})이 없습니다",
            details={"dependency": dependency},
        )
        self.dependency = dependency


class InvalidMessageError(ChatError):
    """빈 메시지 등 요청 값이 잘못됐다."""

    code = ErrorCodes.BAD_REQUEST
