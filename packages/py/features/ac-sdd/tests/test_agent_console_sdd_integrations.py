"""확장 지점 X42·X43 예제 구현(테스트 가짜)이 프로토콜을 만족하고, 모은 결과가 추적 표로
이어진다."""

from __future__ import annotations

from typing import Any

from agent_console_contracts.sdd import VerificationResult
from agent_console_sdd import (
    AutomationControl,
    ProfileChecker,
    SpecContext,
    TaskIntegration,
    VerificationContext,
    VerificationSource,
    find_task,
    trace,
)
from agent_console_sdd.testing import (
    TEST_TEMPLATE_KIND,
    FakeTaskIntegration,
    FakeVerificationSource,
    MemorySpecFiles,
    memory_repository,
)

TEMPLATE: dict[str, Any] = {
    "kind": TEST_TEMPLATE_KIND,
    "id": "t",
    "name": "틀",
    "documents": [
        {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
        {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
    ],
    "rules": {
        "run_profiles": [
            {"id": "impl", "title": "구현", "graph": "team", "purpose": "implement"},
            {"id": "verify", "title": "검증", "graph": "qa", "purpose": "verify"},
        ]
    },
}


async def test_fakes_satisfy_protocols_and_feed_trace() -> None:
    repo = memory_repository()
    created = repo.store.create(TEST_TEMPLATE_KIND, TEMPLATE)
    repo.store.write_files(
        TEST_TEMPLATE_KIND,
        "t",
        {"req.md": b"**R1** a\n\n**R2** b\n", "tasks.md": b"- [ ] 1 a [req: R1]\n"},
        expected_version=created.version_hash,
    )
    spec_id = repo.create(name="spec", template="t").id
    loaded = repo.load(spec_id)
    ctx = SpecContext(
        space=None,
        spec=loaded.spec,
        index=loaded.index,
        syntax=loaded.syntax,
        version_hash=loaded.stored.version_hash,
        directory=repo.spec_directory(spec_id),
        files=MemorySpecFiles(),
    )
    integration = FakeTaskIntegration()
    source = FakeVerificationSource(
        results=[VerificationResult(source="fake", status="pass", requirement_ids=["R1"], at=1)]
    )
    assert isinstance(integration, TaskIntegration)
    assert isinstance(source, VerificationSource)
    assert not isinstance(integration, ProfileChecker)
    assert not isinstance(integration, AutomationControl)

    task = find_task(loaded.index, "1")
    assert task is not None
    actions = await integration.actions(ctx, task)
    assert [(a.integration, a.id, a.label) for a in actions] == [
        ("fake", "impl", "구현"),
        ("fake", "verify", "검증"),
    ]
    started = await integration.invoke(ctx, task, "impl", {"note": "x"})
    assert (started.status, started.run_id) == ("started", "fake-1")
    unknown = await integration.invoke(ctx, task, "nope", {})
    assert unknown.status == "failed"
    assert unknown.issue is not None
    links = await integration.links(ctx, loaded.index.tasks)
    results = await source.collect(VerificationContext(spec=ctx, options={"k": 1}))
    assert source.calls[0].options == {"k": 1}

    matrix = trace(loaded.index, links, results, syntax=loaded.syntax)
    rows = {r.id: r for r in matrix.rows}
    assert [link.ref for link in rows["R1"].runs] == ["fake-1"]
    assert rows["R1"].gaps == ["task_not_done"]
    assert rows["R2"].gaps == ["no_task", "not_verified"]
