"""평문 점검 캐시가 정의를 바꾸는 모든 저장소 쓰기 경로에서 버려지는지(3R.12 QA).

서버의 쓰기 요청 미들웨어가 사라졌으므로, 가져오기(create/save)·되돌리기·본문/파일 쓰기·삭제가
``definitions.saved``/삭제 알림으로 캐시를 버리는지 저장소 공개 API 수준에서 확인한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_mod_definitions import (
    DEFINITIONS_STORE,
    SERVER_WARNINGS,
    VERSIONS_MEMORY,
    module,
)
from agent_console_modkit import BaseServices, Paths, assemble

PLAIN = "ghp_PlainToken123456"


def _setup(tmp_path: Path) -> tuple[Any, Any]:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    assembly = assemble([module], base=base)
    store = assembly.port(DEFINITIONS_STORE)
    [source] = assembly.ports(SERVER_WARNINGS)
    assert store is not None

    def warnings() -> list[Any]:
        return [w for w in source() if w.code != VERSIONS_MEMORY]  # 평문 점검만 본다

    return store, warnings


def _ids(warnings: Any) -> set[str]:
    return {w.details["id"] for w in warnings()}


def test_every_write_path_drops_cache(tmp_path: Path) -> None:
    store, warnings = _setup(tmp_path)
    assert warnings() == []  # 캐시 채움
    clean = store.create("agent", {"id": "a", "name": "a", "backend_options": {}})
    assert warnings() == []
    # save(덮어쓰기)
    dirty = store.save(
        "agent",
        {"id": "a", "name": "a", "backend_options": {"token": PLAIN}},
        expected_version=clean.version_hash,
    )
    assert _ids(warnings) == {"a"}
    # restore_version(깨끗한 옛 버전으로 되돌리기)
    store.restore_version("agent", "a", clean.version_hash, expected_version=dirty.version_hash)
    assert _ids(warnings) == set()
    # 리소스 본문 쓰기(write_content): 문서 밖 본문은 문서 점검 대상이 아니어도 캐시는 일관해야 한다
    res = store.create("resource", {"id": "r", "type": "instruction", "name": "r", "config": {}})
    assert warnings() == []
    store.write_content(
        "resource", "r", b"hello", file="content.txt", expected_version=res.version_hash
    )
    assert warnings() == []
    # 삭제
    store.create("agent", {"id": "b", "name": "b", "backend_options": {"token": PLAIN}})
    assert _ids(warnings) == {"b"}
    store.delete("agent", "b")
    assert _ids(warnings) == set()
