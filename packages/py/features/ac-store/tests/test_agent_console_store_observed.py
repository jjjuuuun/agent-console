"""ObservedVersionRepository: 저장마다 기록 알림, 나머지는 그대로 위임."""

from __future__ import annotations

from agent_console_store import (
    AGENT_KIND,
    DEFAULT_KINDS,
    InMemoryDefinitionStore,
    InMemoryVersionRepository,
    ObservedVersionRepository,
    VersionRepository,
)


def test_record_calls_back_after_each_saved_version() -> None:
    seen: list[tuple[str, str, str]] = []
    inner = InMemoryVersionRepository()
    versions = ObservedVersionRepository(inner, lambda *args: seen.append(args))
    store = InMemoryDefinitionStore(DEFAULT_KINDS, versions=versions)
    first = store.create(AGENT_KIND.name, {"id": "a", "name": "A", "backend": "fake"})
    second = store.save(
        AGENT_KIND.name,
        {"id": "a", "name": "B", "backend": "fake"},
        expected_version=first.version_hash,
    )
    assert seen == [("agent", "a", first.version_hash), ("agent", "a", second.version_hash)]
    assert [v.version_hash for v in store.list_versions("agent", "a")] == [
        second.version_hash,
        first.version_hash,
    ]
    assert versions.trim("agent", "a", keep=1, protect=(second.version_hash,)) == 1
    assert len(seen) == 2  # 정리에는 알리지 않는다
    assert versions.prune_blobs() == 0
    probe: VersionRepository = versions
    assert probe.get("agent", "a", second.version_hash) is not None
