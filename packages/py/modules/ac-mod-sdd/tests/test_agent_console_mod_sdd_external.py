"""단독 루트 외부 변경 알림(6R.30, design §6R.7 ``sdd.changed``): 밖에서 고친 스펙 문서는 다음 읽기
(목록·보기·작업 목록·문서 GET) 한 번에 ``sdd.changed`` 한 건, 같은 상태로 다시 읽으면 0건, 앱 쓰기는
한 건(저장소 기록 알림과 모듈 쓰기 뒤 알림이 겹쳐도 중복 없음)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.sdd import SddChanged
from agent_console_mod_sdd import SDD_TOPIC, spec_recorded

API = "/api/v1"


def _spy(assembly: Any) -> list[SddChanged]:
    """허브에 나간 ``sdd.changed`` 알림을 모은다(라우트는 루프 스레드라 응답 전에 발행된다)."""
    hub = assembly.services.ws_hub
    seen: list[SddChanged] = []
    original: Callable[..., Any] = hub.publish

    def publish(topic: str, message: Any) -> Any:
        if topic == SDD_TOPIC:
            seen.append(message.payload)
        return original(topic, message)

    hub.publish = publish
    return seen


def _touch(path: Path, extra: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")


@pytest.mark.parametrize(
    "read",
    [
        "/sdd/specs",
        "/sdd/specs/c",
        "/sdd/specs/c/tasks",
        "/sdd/specs/c/documents/tasks",
    ],
)
def test_external_edit_notifies_once_on_next_read(tmp_path: Path, kit: Any, read: str) -> None:
    root = tmp_path / "ws" / "sdd"
    kit.write_template(kit.spec_store(root))
    assembly = kit.make_assembly(tmp_path)
    seen = _spy(assembly)
    with kit.client_for(assembly) as client:
        assert client.post(f"{API}/sdd/specs", json={"name": "C", "template": "flow"}).is_success
        assert [p.spec_id for p in seen] == ["c"]  # 앱 쓰기 한 번 = 한 건
        seen.clear()
        assert client.get(f"{API}{read}").is_success
        assert seen == []  # 바뀐 것 없음

        _touch(root / "specs" / "c" / "tasks.md", "- [ ] 3.1 밖에서 더한 작업\n")
        assert client.get(f"{API}{read}").is_success
        assert len(seen) == 1
        changed = seen[0]
        assert changed.spec_id == "c"
        assert changed.space.project_id is None
        assert not changed.deleted
        view = client.get(f"{API}/sdd/specs/c")
        assert changed.version_hash == view.json()["version_hash"]

        seen.clear()
        for again in ("/sdd/specs", "/sdd/specs/c", "/sdd/specs/c/tasks", read):
            assert client.get(f"{API}{again}").is_success
        assert seen == []  # 같은 상태로 다시 읽으면 0건


def test_app_writes_notify_once_each(tmp_path: Path, kit: Any) -> None:
    root = tmp_path / "ws" / "sdd"
    kit.write_template(kit.spec_store(root))
    assembly = kit.make_assembly(tmp_path)
    seen = _spy(assembly)
    with kit.client_for(assembly) as client:
        client.post(f"{API}/sdd/specs", json={"name": "C", "template": "flow"})
        seen.clear()

        doc = client.get(f"{API}/sdd/specs/c/documents/design")
        saved = client.put(
            f"{API}/sdd/specs/c/documents/design",
            json={"content": "# 설계\n새 내용\n"},
            headers={"If-Match": doc.headers["etag"]},
        )
        assert saved.status_code == 200, saved.text
        assert len(seen) == 1
        view = client.get(f"{API}/sdd/specs/c").json()
        assert seen[0].version_hash == view["version_hash"]

        seen.clear()
        moved = client.post(f"{API}/sdd/specs/c/documents/design/state", json={"to": "approved"})
        assert moved.status_code == 200, moved.text
        assert len(seen) == 1

        seen.clear()
        task = client.get(f"{API}/sdd/specs/c/tasks?ready=true").json()[0]
        patched = client.patch(
            f"{API}/sdd/specs/c/tasks/{task['key']}",
            json={"status": "done", "expected_line_hash": task["line_hash"]},
        )
        assert patched.status_code == 200, patched.text
        assert len(seen) == 1
        seen.clear()
        current = client.get(f"{API}/sdd/specs/c")
        spec = current.json()["spec"]
        spec["rules"]["gates"] = []
        put = client.put(
            f"{API}/sdd/specs/c", json=spec, headers={"If-Match": current.headers["etag"]}
        )
        assert put.status_code == 200, put.text
        assert [p.version_hash for p in seen] == [put.json()["version_hash"]]

        seen.clear()
        assert client.post(f"{API}/sdd/specs", json={"name": "Blank"}).status_code == 201
        assert [p.spec_id for p in seen] == ["blank"]  # 빈 스펙(정의 + 빈 문서)도 한 건

        seen.clear()
        for read in ("/sdd/specs", "/sdd/specs/c", "/sdd/specs/c/tasks", "/sdd/specs/blank"):
            client.get(f"{API}{read}")
        assert seen == []  # 앱이 쓴 상태는 외부 변경이 아니다


def test_template_records_do_not_notify(tmp_path: Path, kit: Any) -> None:
    root = tmp_path / "ws" / "sdd"
    kit.write_template(kit.spec_store(root))
    assembly = kit.make_assembly(tmp_path)
    seen = _spy(assembly)
    with kit.client_for(assembly) as client:
        assert client.get(f"{API}/sdd/templates").is_success
        assert client.get(f"{API}/sdd/templates/flow").is_success
    assert seen == []  # 문서 틀의 "외부 변경 감지" 기록은 스펙 알림이 아니다


def test_spec_recorded_filters_kind_and_isolates_failures() -> None:
    seen: list[tuple[str, str]] = []
    recorded = spec_recorded("spec", lambda i, h: seen.append((i, h)))
    recorded("spec", "a", "v1")
    recorded("spec-template", "t", "v2")
    assert seen == [("a", "v1")]

    def boom(_i: str, _h: str) -> None:
        raise RuntimeError("hub gone")

    spec_recorded("spec", boom)("spec", "a", "v1")  # 알림 실패는 기록·읽기를 막지 않는다
