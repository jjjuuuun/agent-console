"""대화 저장소 고르기: 호스트 DB 핸들이 있으면 SQLite, 없으면 메모리(경고)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from agent_console_chat import ConversationRepository, QueueStore
from agent_console_contracts import Issue
from agent_console_modkit import DatabaseHandle
from agent_console_store import ProjectAssignStore

from .memory import InMemoryChatStorage
from .repository import SqliteChatStorage

STORAGE_MEMORY = "chat.storage_memory"
"""경고 코드: DB가 없어 대화·대기열을 메모리에만 둔다."""


@dataclass(frozen=True)
class ChatStorage:
    """대화 저장소 묶음.

    Attributes:
        conversations: 대화 저장소(``ConversationRepository``).
        queue: 대기열 저장소(``QueueStore``).
        in_memory: 메모리 저장소인지.
    """

    conversations: ConversationRepository
    queue: QueueStore
    in_memory: bool

    @property
    def projects(self) -> ProjectAssignStore:
        """프로젝트 넣기·개수 포트(대화 저장소 구현이 `ProjectAssignStore`도 구현한다)."""
        return cast(ProjectAssignStore, self.conversations)


def open_chat_storage(database: DatabaseHandle | None) -> ChatStorage:
    """호스트 DB 핸들 위의 대화 저장소(없으면 메모리). 연결은 호스트가 닫는다."""
    if database is None:
        memory = InMemoryChatStorage()
        return ChatStorage(memory.conversations, memory.queue, in_memory=True)
    sqlite = SqliteChatStorage(database.engine)
    return ChatStorage(sqlite.conversations, sqlite.queue, in_memory=False)


def memory_storage_warning() -> Issue:
    return Issue(
        severity="warning",
        code=STORAGE_MEMORY,
        message="DB가 없어 대화·대기열을 메모리에만 둡니다(재시작하면 사라집니다)",
    )
