"""디스크립터 색인(내부): (id, version) 및 (id, None)=최신 버전 → 디스크립터."""

from collections.abc import Iterable

from agent_console_contracts import EdgeTypeDescriptor, NodeTypeDescriptor


def latest_index[D: (NodeTypeDescriptor, EdgeTypeDescriptor)](
    descriptors: Iterable[D],
) -> dict[tuple[str, int | None], D]:
    """(id, version) 및 (id, None)=최신 버전 → 디스크립터. 같은 (id, version)은 처음 것."""
    index: dict[tuple[str, int | None], D] = {}
    for desc in descriptors:
        index.setdefault((desc.id, desc.version), desc)
        latest = index.get((desc.id, None))
        if latest is None or desc.version > latest.version:
            index[(desc.id, None)] = desc
    return index
