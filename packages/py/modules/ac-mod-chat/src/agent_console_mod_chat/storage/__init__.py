"""mod-chat의 저장소: `conversations`·`chat_queue`(design §3R.1.7).

- ``BRANCH``: 이 모듈의 마이그레이션 계보(``chat``, 패키지 데이터). 모듈이 켜질 때만 올라간다.
  테이블은 legacy 0002·0003이 만들었다(변경 없음) — 계보의 첫 리비전은 기준점이다.
- ``SqliteChatStorage``: 호스트 ``DatabaseHandle.engine`` 위의 구현. 대화를 지우면 대기열도
  같은 트랜잭션에서 지운다.
- ``InMemoryChatStorage``: 테스트·DB 없는 사용.
"""

from __future__ import annotations

from pathlib import Path

from agent_console_modkit import MigrationBranch

from .memory import InMemoryChatStorage, InMemoryConversationRepository, InMemoryQueueRepository
from .models import QueueCounts, QueuedItem, QueueItemExistsError, QueueItemNotFoundError
from .open import STORAGE_MEMORY, ChatStorage, memory_storage_warning, open_chat_storage
from .repository import SqliteChatStorage, SqliteConversationRepository, SqliteQueueRepository
from .schema import TABLE_NAMES, chat_queue, conversations, metadata

BRANCH = MigrationBranch("chat", Path(__file__).parent / "migrations" / "versions")
"""모듈 서술자 ``migrations``에 넣는 계보."""

__all__ = [
    "BRANCH",
    "STORAGE_MEMORY",
    "TABLE_NAMES",
    "ChatStorage",
    "InMemoryChatStorage",
    "InMemoryConversationRepository",
    "InMemoryQueueRepository",
    "QueueCounts",
    "QueueItemExistsError",
    "QueueItemNotFoundError",
    "QueuedItem",
    "SqliteChatStorage",
    "SqliteConversationRepository",
    "SqliteQueueRepository",
    "chat_queue",
    "conversations",
    "memory_storage_warning",
    "metadata",
    "open_chat_storage",
]
