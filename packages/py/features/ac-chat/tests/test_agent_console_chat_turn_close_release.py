"""턴 마무리 중 세션 기록(저장)이 실패해도 손잡이가 `_active`에 영영 남지 않는다.

턴이 running으로 굳지 않고, 대화가 바쁨으로 남지 않으며, 마무리 알림(`_start_next`)이 나간다.
"""

from agent_console_chat import ChatService
from agent_console_chat.testing import (
    FakeLauncher,
    MemoryConversations,
    MemoryEvents,
    MemoryGraphs,
    MemoryRuns,
)
from agent_console_contracts import (
    CreateConversationRequest,
    Graph,
    NodeSpec,
    PostMessageRequest,
    Run,
)


class FailingSave(MemoryConversations):
    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def save(self, conversation):  # type: ignore[no-untyped-def]
        if self.fail:
            raise OSError("disk full")
        super().save(conversation)


async def test_turn_not_stuck_running_when_session_save_fails() -> None:
    runs, events = MemoryRuns(), MemoryEvents()
    launcher = FakeLauncher(runs, events)
    conversations = FailingSave()
    notes: list[str | None] = []
    service = ChatService(
        conversations,
        MemoryGraphs([Graph(id="g", name="g", nodes=[NodeSpec(id="pl", type="agent")])]),
        launcher=launcher,
        runs=runs,
        events=events,
        listener=lambda summary: notes.append(summary.last_status),
    )
    conv = service.create(CreateConversationRequest(graph_id="g"))
    run = await service.post_message(conv.id, PostMessageRequest(text="하나"))
    assert isinstance(run, Run)
    conversations.fail = True
    launcher.finish(run.id)
    await service.wait_idle()
    [turn] = service.turns(conv.id)
    assert turn.status == "completed"
    assert not service.is_busy(conv.id)
    assert notes[-1] == "completed"  # 실패 경로에서도 마무리 알림
