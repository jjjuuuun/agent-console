"""3R.10 쉬운 기능 모듈 분리(+ 3R.12 정의·리소스, 3R.13 실행): 기능 모듈이 entry point로 조립된다.

- `/modules`에 각 모듈이 `active`이고 웹 역할을 가져갔다(design §3R.1.3 표).
- `modules.disabled`로 끄면 그 모듈 경로만 404, 나머지는 동작한다.
- 옛 최상위 설정 키는 `settings.removed_key` 오류로 새 위치를 알린다(4R.18, F-3).
- `GET /usage?parts=windows`는 실행 기록(토큰 집계)을 읽지 않는다(D11).
- `mod-versions.max_per_definition`(D3)이 저장마다 버전 수를 줄인다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_console_modkit import PortKey
from agent_console_server import CONFIG_FILENAME, SETTINGS_REMOVED_KEY, ConfigError, load_settings
from agent_console_server.testing import API, agent_doc, make_settings, server

USAGE_TOKEN_ROLLUPS: PortKey[Any] = PortKey("usage.token_rollups")

FEATURE_ROLES: dict[str, list[str]] = {
    "mod-usage": ["usage"],
    "mod-imports": ["imports"],
    "mod-exports": ["exports"],
    "mod-presets": ["presets"],
    "mod-versions": ["versions"],
    "mod-definitions": ["definitions:agent", "definitions:graph", "settings"],
    "mod-resources": ["definitions:resource"],
    "mod-runs": ["runs"],
    "mod-chat": ["conversations"],
    "mod-projects": ["projects"],
}
"""design §3R.1.3 표의 web_roles(3R.18 웹 조립과 맞춘다)."""

DEFINITION_LINK_ROLES: dict[str, list[str]] = {
    "link-definitions-teams": ["definitions:teams"],
}
"""design §3R.1.4 연동의 web_roles(3R.32a 웹 연동 부분 판정과 맞춘다)."""

PROBES: dict[str, tuple[str, str]] = {
    "mod-usage": ("GET", "/usage"),
    "mod-imports": ("GET", "/resources/import/sources"),
    "mod-exports": ("GET", "/exporters"),
    "mod-presets": ("GET", "/presets"),
    "mod-versions": ("GET", "/settings/versions"),
    "mod-resources": ("GET", "/resources"),
    "mod-runs": ("GET", "/runs"),
    "mod-chat": ("GET", "/conversations"),
    "mod-projects": ("GET", "/projects"),
}
"""모듈마다 켜져 있으면 200인 대표 경로."""


def test_feature_modules_are_active_with_their_web_roles(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        for module_id, roles in FEATURE_ROLES.items():
            assert infos[module_id]["status"] == "active", infos[module_id]
            assert infos[module_id]["web_roles"] == roles
            assert infos[module_id]["kind"] == "feature"
        for link_id, roles in DEFINITION_LINK_ROLES.items():
            assert infos[link_id]["status"] == "active", infos[link_id]
            assert infos[link_id]["web_roles"] == roles
        assert "server-monolith" not in infos  # 3R.16: 통짜 모듈을 지웠다
        assert "definitions.lookup" in infos["mod-definitions"]["provides"]
        for method, path in PROBES.values():
            assert client.request(method, f"{API}{path}").status_code == 200, path


@pytest.mark.parametrize("module_id", sorted(PROBES))
def test_disabled_module_is_404_and_rest_still_works(tmp_path: Path, module_id: str) -> None:
    settings = make_settings(tmp_path, modules={"disabled": [module_id]})
    with server(settings) as client:
        statuses = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
        assert statuses[module_id] == "disabled"
        for other, (method, path) in PROBES.items():
            code = client.request(method, f"{API}{path}").status_code
            assert code == (404 if other == module_id else 200), (other, path, code)
        assert client.get(f"{API}/agents").status_code == 200


def test_disabling_definitions_leaves_dependent_modules_unsatisfied(tmp_path: Path) -> None:
    """정의 저장소(mod-definitions)가 꺼지면 그것을 필수로 쓰는 모듈은 이유와 함께 꺼진다."""
    settings = make_settings(tmp_path, modules={"disabled": ["mod-definitions"]})
    with server(settings) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        dependents = (
            "mod-imports",
            "mod-exports",
            "mod-presets",
            "mod-versions",
            "mod-resources",
            "mod-runs",
            "link-chat-runs",
            "link-definitions-resources",
            "link-definitions-teams",
            "link-exports-teams",
            "link-runs-teams",
            "link-runs-trace",
            "link-runs-usage",
        )
        for module_id in dependents:
            assert infos[module_id]["status"] == "unsatisfied", (module_id, infos[module_id])
        assert infos["mod-usage"]["status"] == "active"  # 필수 포트 없음
        assert infos["mod-chat"]["status"] == "active"  # 필수 포트 없음(대화 목록은 동작)
        assert client.get(f"{API}/conversations").json() == []
        assert infos["mod-projects"]["status"] == "active"  # 정의 포트는 선택(CRUD는 동작)
        assert client.get(f"{API}/projects").json() == []
        body = client.get(f"{API}/usage").json()
        assert body["rollups"] == []  # 토큰 집계 포트(link-runs-usage) 없음 → 빈 목록
        assert client.get(f"{API}/presets").status_code == 404
        assert client.get(f"{API}/agents").status_code == 404


OLD_TOP_LEVEL_KEYS = {
    "usage": "modules.options.mod-usage",
    "exports": "modules.options.mod-exports",
    "versions": "modules.options.mod-versions",
    "imports": "modules.options.mod-imports",
    "presets": "modules.options.mod-presets",
    "resources": "modules.options.mod-definitions",
    "runtime": "modules.options.mod-runs.runtime",
    "backends": "modules.options.mod-runs.backends",
    "working_directory": "modules.options.mod-runs.working_directory",
}


@pytest.mark.parametrize(("old", "new"), sorted(OLD_TOP_LEVEL_KEYS.items()))
def test_old_keys_are_rejected_with_new_location(tmp_path: Path, old: str, new: str) -> None:
    """4R.18(F-3): 옛 최상위 키는 읽지 않고 `settings.removed_key` 오류로 새 위치를 알린다."""
    config = tmp_path / CONFIG_FILENAME
    value = "proj" if old == "working_directory" else "{}"
    config.write_text(f"{old}: {value}\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_settings(config, environ={})
    assert exc.value.code == SETTINGS_REMOVED_KEY
    assert [(k.old, k.new) for k in exc.value.removed] == [(old, new)]
    assert SETTINGS_REMOVED_KEY in str(exc.value)
    assert new in str(exc.value)


def test_all_old_keys_reported_together(tmp_path: Path) -> None:
    config = tmp_path / CONFIG_FILENAME
    config.write_text("usage: {}\nruntime: {}\nconsole: {}\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_settings(config, environ={})
    assert [k.old for k in exc.value.removed] == ["console", "runtime", "usage"]
    console = exc.value.removed[0]
    assert console.new is None
    assert "1R에서 삭제" in console.message


def test_new_locations_have_no_moved_warning(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    settings = make_settings(
        tmp_path,
        options={
            "mod-usage": {"rollup_run_limit": 3},
            "mod-exports": {"roots": [{"id": "o", "path": str(out)}]},
            "mod-versions": {"max_per_definition": 2},
        },
    )
    assert settings.moved_keys == []
    with server(settings) as client:
        warnings = client.get(f"{API}/server-info").json()["warnings"]
        assert not [w for w in warnings if w["code"] == "settings.moved_key"]
        assert [r["id"] for r in client.get(f"{API}/exports/roots").json()] == ["o"]


def test_imports_project_dir_defaults_to_base_dir_not_runs_working_directory(
    tmp_path: Path,
) -> None:
    """H3(4R.18): `mod-imports.project_dir`는 자기 옵션이다. 생략하면 호스트 `paths.base_dir`이고
    실행 모듈의 `working_directory`를 기본값으로 읽지 않는다. 내보내기 `home`도 가져오기 `home`을
    따라가지 않는다."""
    project = tmp_path / "proj"
    (project / ".claude").mkdir(parents=True)
    home = tmp_path / "nohome"
    settings = make_settings(
        tmp_path,
        options={
            "mod-runs": {"working_directory": str(project)},
            "mod-imports": {"home": str(home)},
        },
    )
    assert "project_dir" not in settings.modules.options["mod-imports"]
    assert "home" not in settings.modules.options.get("mod-exports", {})
    env = {"HOME": str(home)}
    with server(settings, environ=env) as client:
        sources = {s["id"]: s for s in client.get(f"{API}/resources/import/sources").json()}
        assert sources["project-claude"]["available"] is False  # base_dir(tmp_path)에 .claude 없음
    (tmp_path / ".claude").mkdir()
    with server(settings, environ=env) as client:
        sources = {s["id"]: s for s in client.get(f"{API}/resources/import/sources").json()}
        assert sources["project-claude"]["available"] is True
    explicit = make_settings(tmp_path, options={"mod-imports": {"project_dir": str(project)}})
    assert explicit.modules.options["mod-imports"]["project_dir"] == str(project)


def test_usage_windows_only_does_not_read_run_records(tmp_path: Path) -> None:
    calls: list[int] = []
    settings = make_settings(tmp_path, modules={"options": {"mod-usage": {"rollup_run_limit": 7}}})
    with server(settings) as client:
        provider = client.app.state.assembly.port(USAGE_TOKEN_ROLLUPS)  # type: ignore[attr-defined]
        original = provider.rollups

        def counting(*, limit: int, tz: Any) -> Any:
            calls.append(limit)
            return original(limit=limit, tz=tz)

        provider.rollups = counting
        windows = client.get(f"{API}/usage", params={"parts": "windows"}).json()
        assert windows["rollups"] is None
        assert isinstance(windows["windows"], list)
        assert calls == []
        both = client.get(f"{API}/usage").json()
        assert isinstance(both["rollups"], list)
        assert calls == [7]
        tokens = client.get(f"{API}/usage", params={"parts": "tokens"}).json()
        assert tokens["windows"] is None
        assert calls == [7, 7]


def test_versions_max_per_definition_keeps_latest(tmp_path: Path) -> None:
    """D3: 설치자 설정 `modules.options.mod-versions.max_per_definition`이 서버 저장에 연결된다."""
    settings = make_settings(
        tmp_path, modules={"options": {"mod-versions": {"max_per_definition": 2}}}
    )
    with server(settings) as client:
        created = client.post(f"{API}/agents", json=agent_doc("a", "0"))
        etag = created.headers["etag"]
        for i in range(1, 5):
            saved = client.put(
                f"{API}/agents/a", json=agent_doc("a", str(i)), headers={"If-Match": etag}
            )
            assert saved.status_code == 200, saved.text
            etag = saved.headers["etag"]
        versions = client.get(f"{API}/agents/a/versions").json()
        assert len(versions) == 2
        assert f'"{versions[0]["version_hash"]}"' == etag
        # 설정 단일 문서도 같은 규칙
        for name in ("x", "y", "z"):
            client.put(f"{API}/settings", json={"default_backend": name})
        assert len(client.get(f"{API}/settings/versions").json()) == 2
