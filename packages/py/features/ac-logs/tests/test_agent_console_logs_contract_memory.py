"""MemoryLogIndex가 색인 계약 테스트 묶음을 통과한다(SQLite 구현도 같은 묶음을 쓴다)."""

from agent_console_logs import LogIndex
from agent_console_logs.testing import LogIndexContractTests, MemoryLogIndex


class TestMemoryLogIndex(LogIndexContractTests):
    def make_index(self) -> LogIndex:
        return MemoryLogIndex()
