"""P1.15: 위키 신선도 창(설치자 ``freshness_seconds``, design §1.1 B-1).

호스트 시계를 주입해(``BaseServices(clock=)``) 창 안 재사용·창 지남·0이면 매번 확인을 보고, 같은
프로세스의 바뀜(페이지 쓰기·위키 정의·위키 규칙·규칙 본문 파일·규칙 되돌리기·토픽
``definitions.saved``)이 창과 무관하게 바로 보이는지, ``POST scan``이 창을 무시하는지, 바깥 편집이
창만큼만 늦는지, 같은 위키를 동시에 열면 확인을 한 번만 하는지 본다. 페이지 파일 나열 횟수는
``LocalWikiPages.list``를 세어 잰다.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_wiki import WIKI_SERVICE, WikiModuleSettings, WikiService, module
from agent_console_mod_wiki.ports import DEFINITIONS_SAVED
from agent_console_mod_wiki.settings import package_defaults
from agent_console_mod_wiki.testing import SimpleWikiSpace, spaces_module, static_settings_module
from agent_console_modkit import Assembly, BaseServices, ExtensionRegistries, ModulesConfig, Paths
from agent_console_modkit import assemble as assemble_modules
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_store import FileDefinitionStore
from agent_console_wiki import LocalWikiPages, definition_kinds

API = "/api/v1"
TOKEN = "f" * 32
WINDOW = 5.0


class Clock:
    """호스트 시계(``datetime``)를 손으로 돌린다."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 26, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Counter:
    """메서드 호출 수 세기(원래 동작은 그대로)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, owner: Any, name: str) -> None:
        self.calls = 0
        original = getattr(owner, name)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, name, wrapper)


@dataclasses.dataclass
class Env:
    client: TestClient
    assembly: Assembly
    service: WikiService
    clock: Clock
    lists: Counter
    reads: Counter
    settings: dict[str, Any]
    tmp: Path

    def pages_dir(self, wiki: str, space: str | None = None) -> Path:
        scope = self.service.scope(space)
        return scope.pages_root / wiki

    def paths(self, wiki: str, **query: str) -> list[str]:
        res = self.client.get(f"{API}/wiki/wikis/{wiki}/pages", params=query)
        assert res.status_code == 200, res.text
        return [p["path"] for p in res.json()["items"]]

    def publish_saved(self, kind: str, item_id: str, space: str | None = None) -> None:
        item = SimpleNamespace(kind=kind, id=item_id, version_hash="v", space=space)
        self.assembly.services.events.publish(DEFINITIONS_SAVED, item)


def _space(root: Path) -> SimpleWikiSpace:
    kinds = definition_kinds(
        wiki_kind="wiki", wiki_dir="wikis", rules_kind="wiki-rules", rules_dir="wiki-rules"
    )
    cfg = root / ".agent-console"
    return SimpleWikiSpace(store=FileDefinitionStore(cfg, kinds), pages_root=cfg / "wiki-pages")


def _open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, window: float = WINDOW
) -> Iterator[Env]:
    clock = Clock()
    settings: dict[str, Any] = {"wiki": {}}
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=ExtensionRegistries(),
        clock=clock,
    )
    spaces = spaces_module({"pa": _space(tmp_path / "A"), "pb": _space(tmp_path / "B")})
    assembly = assemble_modules(
        [module, static_settings_module(lambda: settings), spaces],
        ModulesConfig(options={"mod-wiki": {"freshness_seconds": window}}),
        base=base,
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    service = assembly.port(WIKI_SERVICE)
    assert isinstance(service, WikiService)
    lists = Counter(monkeypatch, LocalWikiPages, "list")
    reads = Counter(monkeypatch, WikiService, "get_wiki")
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield Env(client, assembly, service, clock, lists, reads, settings, tmp_path)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    yield from _open(tmp_path, monkeypatch)


@pytest.fixture
def env0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    yield from _open(tmp_path, monkeypatch, window=0)


def _wiki(env: Env, name: str = "w", **query: str) -> str:
    made = env.client.post(f"{API}/wiki/wikis", json={"name": name}, params=query)
    assert made.status_code == 201, made.text
    wiki: str = made.json()["wiki"]["id"]
    return wiki


def _put(env: Env, wiki: str, path: str, content: str, **query: str) -> None:
    res = env.client.put(
        f"{API}/wiki/wikis/{wiki}/pages/{path}",
        json={"content": content},
        headers={"If-None-Match": "*"},
        params=query,
    )
    assert res.status_code == 201, res.text


def _write_file(env: Env, wiki: str, file: str, text: str, space: str | None = None) -> None:
    target = env.pages_dir(wiki, space) / file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_settings_default_and_schema() -> None:
    assert package_defaults()["freshness_seconds"] == 2.0
    assert WikiModuleSettings().freshness_seconds == 2.0
    field = WikiModuleSettings.model_json_schema()["properties"]["freshness_seconds"]
    assert field["minimum"] == 0
    assert field["x-ui"]["tier"] == "advanced"
    with pytest.raises(ValueError, match="greater than or equal"):
        WikiModuleSettings(freshness_seconds=-1)


def test_window_reuses_fingerprint_and_listing(env: Env) -> None:
    wiki = _wiki(env)
    _put(env, wiki, "a", "# A\n")
    env.paths(wiki)
    lists, reads = env.lists.calls, env.reads.calls
    for _ in range(3):
        assert env.paths(wiki) == ["a"]
        env.client.get(f"{API}/wiki/wikis/{wiki}/graph")
        env.client.get(f"{API}/wiki/wikis")
    assert (env.lists.calls, env.reads.calls) == (lists, reads)  # 창 안: 다시 확인하지 않는다
    env.clock.advance(WINDOW)
    env.paths(wiki)
    assert env.reads.calls == reads + 1
    assert env.lists.calls == lists + 1


def test_zero_window_checks_every_request(env0: Env) -> None:
    wiki = _wiki(env0)
    _put(env0, wiki, "a", "# A\n")
    lists, reads = env0.lists.calls, env0.reads.calls
    for n in (1, 2, 3):
        env0.paths(wiki)
        assert env0.reads.calls == reads + n
        assert env0.lists.calls >= lists + n
    _write_file(env0, wiki, "b.md", "# B\n")
    assert env0.paths(wiki) == ["a", "b"]  # 1.0.0처럼 바깥 편집이 바로 보인다


def test_page_writes_show_at_once(env: Env) -> None:
    wiki = _wiki(env)
    _put(env, wiki, "a", "# A\n")
    assert env.paths(wiki) == ["a"]
    _put(env, wiki, "b", "# B\n[[a]]\n")
    assert env.paths(wiki) == ["a", "b"]
    cards = env.client.get(f"{API}/wiki/wikis").json()
    assert cards[0]["pages"] == 2
    page = env.client.get(f"{API}/wiki/wikis/{wiki}/pages/a").json()
    assert [b["path"] for b in page["backlinks"]] == ["b"]
    res = env.client.delete(f"{API}/wiki/wikis/{wiki}/pages/b")
    assert res.status_code == 204
    assert env.paths(wiki) == ["a"]
    assert env.client.get(f"{API}/wiki/wikis").json()[0]["pages"] == 1


def test_outside_edit_waits_for_window_or_scan(env: Env) -> None:
    wiki = _wiki(env)
    _put(env, wiki, "a", "# A\n")
    assert env.paths(wiki) == ["a"]
    _write_file(env, wiki, "b.md", "# B\n")
    assert env.paths(wiki) == ["a"]  # 창 안: 바깥 편집은 늦게 보일 수 있다
    scanned = env.client.post(f"{API}/wiki/wikis/{wiki}/scan").json()
    assert scanned["imported"] == ["b"]
    assert env.paths(wiki) == ["a", "b"]  # scan은 창과 무관하게 다시 읽는다
    _write_file(env, wiki, "c.md", "# C\n")
    assert env.paths(wiki) == ["a", "b"]
    env.clock.advance(WINDOW + 1)
    assert env.paths(wiki) == ["a", "b", "c"]  # 창이 지나면 보인다


def test_viewed_page_edited_outside_shows_new_links(env: Env) -> None:
    wiki = _wiki(env)
    _put(env, wiki, "a", "# A\n")
    _put(env, wiki, "b", "# B\n")
    assert env.client.get(f"{API}/wiki/wikis/{wiki}/pages/a").json()["links"] == []
    _write_file(env, wiki, "a.md", "# A\n[[b]] 바깥에서 고침\n")
    view = env.client.get(f"{API}/wiki/wikis/{wiki}/pages/a").json()
    assert [(link["target"], link["status"]) for link in view["links"]] == [("b", "ok")]
    back = env.client.get(f"{API}/wiki/wikis/{wiki}/pages/b").json()
    assert [p["path"] for p in back["backlinks"]] == ["a"]


def test_wiki_definition_save_shows_at_once(env: Env) -> None:
    wiki = _wiki(env)
    _put(env, wiki, "a", "# A\n")
    got = env.client.get(f"{API}/wiki/wikis/{wiki}")
    body = got.json()["wiki"]
    body["home"] = "a"
    saved = env.client.put(
        f"{API}/wiki/wikis/{wiki}", json=body, headers={"If-Match": got.headers["etag"]}
    )
    assert saved.status_code == 200, saved.text
    again = env.client.get(f"{API}/wiki/wikis/{wiki}")
    assert again.json()["wiki"]["home"] == "a"
    assert again.headers["etag"] == saved.headers["etag"]
    assert env.client.get(f"{API}/wiki/wikis").json()[0]["home"] == "a"


def _rules(env: Env, rule_id: str = "r", **query: str) -> str:
    made = env.client.post(
        f"{API}/wiki/rules",
        json={"id": rule_id, "name": "규칙", "page_templates": []},
        params=query,
    )
    assert made.status_code == 201, made.text
    etag: str = made.headers["etag"]
    return etag


def _templates(env: Env, wiki: str, **query: str) -> list[tuple[str, str]]:
    res = env.client.get(f"{API}/wiki/wikis/{wiki}/templates", params=query)
    assert res.status_code == 200, res.text
    return [(t["id"], t.get("content") or "") for t in res.json()]


def test_rules_changes_show_at_once(env: Env) -> None:
    etag = _rules(env)
    made = env.client.post(f"{API}/wiki/wikis", json={"name": "w", "rules": ["r"]})
    wiki = made.json()["wiki"]["id"]
    assert _templates(env, wiki) == []
    # 규칙 저장
    saved = env.client.put(
        f"{API}/wiki/rules/r",
        json={
            "kind": "wiki-rules",
            "id": "r",
            "name": "규칙",
            "page_templates": [{"id": "note", "file": "note.md", "path": "notes/{slug}"}],
        },
        headers={"If-Match": etag},
    )
    assert saved.status_code == 200, saved.text
    assert [t[0] for t in _templates(env, wiki)] == ["note"]
    # 본문 파일 쓰기
    first_version = saved.headers["etag"]
    wrote = env.client.put(
        f"{API}/wiki/rules/r/files/note.md",
        content="# {title} 첫 틀\n".encode(),
        headers={"If-Match": first_version},
    )
    assert wrote.status_code == 200, wrote.text
    assert _templates(env, wiki) == [("note", "# {title} 첫 틀\n")]
    wrote2 = env.client.put(
        f"{API}/wiki/rules/r/files/note.md",
        content="# {title} 둘째 틀\n".encode(),
        headers={"If-Match": wrote.headers["etag"]},
    )
    assert _templates(env, wiki) == [("note", "# {title} 둘째 틀\n")]
    # 되돌리기(첫 본문으로)
    target = wrote.headers["etag"].strip('"')
    restored = env.client.post(
        f"{API}/wiki/rules/r/versions/{target}/restore",
        json={},
        headers={"If-Match": wrote2.headers["etag"]},
    )
    assert restored.status_code == 200, restored.text
    assert _templates(env, wiki) == [("note", "# {title} 첫 틀\n")]
    # 본문 파일 지우기
    deleted = env.client.delete(
        f"{API}/wiki/rules/r/files/note.md", headers={"If-Match": restored.headers["etag"]}
    )
    assert deleted.status_code == 200, deleted.text
    assert _templates(env, wiki) == [("note", "")]
    # 규칙 지우기
    gone = env.client.delete(f"{API}/wiki/rules/r", headers={"If-Match": deleted.headers["etag"]})
    assert gone.status_code == 204, gone.text
    issues = env.client.get(f"{API}/wiki/wikis/{wiki}").json()["issues"]
    assert "wiki.rules_missing" in {i["code"] for i in issues}


def test_definitions_saved_topic_invalidates(env: Env) -> None:
    wiki = _wiki(env)
    for space in ("pa", "pb"):
        _wiki(env, "w", project=space)
    for query in ({}, {"project": "pa"}, {"project": "pb"}):
        env.paths(wiki, **query)
    reads = env.reads.calls

    env.publish_saved("wiki", wiki, space="pa")  # 위키 종류 → 그 공간의 그 위키만
    for query in ({}, {"project": "pa"}, {"project": "pb"}):
        env.paths(wiki, **query)
    assert env.reads.calls == reads + 1

    env.publish_saved("wiki-rules", "r", space="pb")  # 규칙 종류 → 그 공간 전부
    for query in ({}, {"project": "pa"}, {"project": "pb"}):
        env.paths(wiki, **query)
    assert env.reads.calls == reads + 2

    env.publish_saved("wiki-rules", "r")  # 공간 없음 = 라이브러리·단독 공간
    for query in ({}, {"project": "pa"}, {"project": "pb"}):
        env.paths(wiki, **query)
    assert env.reads.calls == reads + 3

    env.publish_saved("settings", "settings")  # 다른 종류(공통 설정 등) → 전부
    for query in ({}, {"project": "pa"}, {"project": "pb"}):
        env.paths(wiki, **query)
    assert env.reads.calls == reads + 6


def test_settings_change_applies_after_saved_event(env: Env) -> None:
    wiki = _wiki(env)
    _put(env, wiki, "a", "# A\n")
    first = env.service.repository(None, wiki)
    env.settings["wiki"] = {"max_versions_per_page": 3}
    assert env.service.repository(None, wiki) is first  # 알림 없는 바뀜은 창만큼 늦다
    env.publish_saved("settings", "settings")
    second = env.service.repository(None, wiki)
    assert second is not first
    assert second.limits.max_versions_per_page == 3


def test_space_values_are_compared_every_request(env: Env) -> None:
    wiki = _wiki(env)
    scope = env.service.scope(None)
    env.service.repository_of(scope, wiki)
    reads = env.reads.calls
    env.service.repository_of(scope, wiki)
    assert env.reads.calls == reads
    moved = dataclasses.replace(scope, pages_root=env.tmp / "elsewhere")
    env.service.repository_of(moved, wiki)
    assert env.reads.calls == reads + 1  # 페이지 폴더가 다르면 창 안이어도 다시 확인


def test_concurrent_opens_check_once(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    wiki = _wiki(env)
    env.service.state.checked.clear()  # 확인 기록을 비운다
    original = WikiService._check

    def slow(self: WikiService, *args: Any, **kwargs: Any) -> Any:
        time.sleep(0.05)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(WikiService, "_check", slow)
    scope = env.service.scope(None)
    reads = env.reads.calls
    barrier = threading.Barrier(5)
    repos: list[Any] = []

    def open_repo() -> None:
        barrier.wait()
        repos.append(env.service.repository_of(scope, wiki))

    threads = [threading.Thread(target=open_repo) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert env.reads.calls == reads + 1
    assert len({id(r) for r in repos}) == 1


def test_close_forgets_checks(env: Env) -> None:
    wiki = _wiki(env)
    env.paths(wiki)
    assert env.service.state.checked
    env.service.close()
    assert not env.service.state.checked


def test_invalidation_during_check_is_not_lost(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    wiki = _wiki(env)
    scope = env.service.scope(None)
    env.service.state.checked.clear()
    original = WikiService._repository_for

    def racing(self: WikiService, *args: Any, **kwargs: Any) -> Any:
        found = original(self, *args, **kwargs)
        self.rules_changed(scope)  # 확인하는 사이 다른 요청이 규칙을 저장했다
        return found

    monkeypatch.setattr(WikiService, "_repository_for", racing)
    env.service.repository_of(scope, wiki)
    assert (scope.key, wiki) not in env.service.state.checked  # 낡은 확인을 남기지 않는다
    monkeypatch.setattr(WikiService, "_repository_for", original)
    reads = env.reads.calls
    env.service.repository_of(scope, wiki)
    assert env.reads.calls == reads + 1
    env.service.repository_of(scope, wiki)
    assert env.reads.calls == reads + 1
