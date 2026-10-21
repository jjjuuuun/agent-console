"""3R.16 QA: 모듈 환경변수·--apply-preset이 서버 시작까지 이어진다(옛 최상위 키는 오류, 4R.18)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_console_server import (
    SETTINGS_REMOVED_KEY,
    ConfigError,
    create_app,
    flag_overrides,
    load_settings,
)
from agent_console_server.testing import API, TEST_TOKEN

_GRAPH = (
    "kind: graph\nid: solo\nschema_version: 1\nname: solo\n"
    "nodes:\n  - {id: you, type: user, position: {x: 0, y: 0}}\nedges: []\n"
)


@pytest.fixture
def presets_dir(tmp_path: Path) -> Path:
    """테스트 안에서 만든 최소 프리셋 `solo`(팀 구성 하나)가 든 프리셋 폴더."""
    root = tmp_path / "presets"
    folder = root / "solo"
    (folder / "graphs").mkdir(parents=True)
    (folder / "graphs" / "solo.yaml").write_text(_GRAPH, encoding="utf-8")
    (folder / "preset.yaml").write_text(
        "kind: preset\nid: solo\nschema_version: 1\nname: solo\nitems:\n  - graphs/solo.yaml\n",
        encoding="utf-8",
    )
    return root


def _graph_ids(settings_path: Path, tmp_path: Path, **kwargs: object) -> set[str]:
    settings = load_settings(settings_path, cwd=tmp_path, **kwargs)  # type: ignore[arg-type]
    app = create_app(settings, environ={}, token=TEST_TOKEN)
    with TestClient(app, headers={"Host": "testserver"}) as client:
        client.headers["X-Console-Token"] = TEST_TOKEN
        res = client.get(f"{API}/graphs")
        assert res.status_code == 200, res.text
        return {g["id"] for g in res.json()}


def _config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "agent-console.yaml"
    path.write_text(
        f"base_dir: {tmp_path}\nworkspace: ws\nsecurity: {{allowed_hosts: [testserver]}}\n{body}",
        encoding="utf-8",
    )
    return path


def _presets(body: str) -> str:
    return f"modules:\n  options:\n    mod-presets: {body}\n"


def test_old_top_level_presets_key_is_rejected(tmp_path: Path, presets_dir: Path) -> None:
    cfg = _config(
        tmp_path, f"presets: {{directories: ['{presets_dir}'], apply_on_start: [solo]}}\n"
    )
    with pytest.raises(ConfigError, match=r"modules\.options\.mod-presets") as exc:
        load_settings(cfg, cwd=tmp_path, environ={})
    assert exc.value.code == SETTINGS_REMOVED_KEY
    good = _config(
        tmp_path, _presets(f"{{directories: ['{presets_dir}'], apply_on_start: [solo]}}")
    )
    assert _graph_ids(good, tmp_path, environ={}) == {"solo"}


def test_env_preset_dirs_and_apply_presets_apply_on_start(
    tmp_path: Path, presets_dir: Path
) -> None:
    cfg = _config(tmp_path, "")
    env = {
        "AGENT_CONSOLE_PRESET_DIRS": str(presets_dir),
        "AGENT_CONSOLE_APPLY_PRESETS": "solo",
    }
    assert _graph_ids(cfg, tmp_path, environ=env) == {"solo"}


def test_flag_apply_preset_applies_on_start(tmp_path: Path, presets_dir: Path) -> None:
    cfg = _config(tmp_path, _presets(f"{{directories: ['{presets_dir}']}}"))
    overrides = flag_overrides({"apply-preset": ["solo"]})
    assert _graph_ids(cfg, tmp_path, environ={}, overrides=overrides) == {"solo"}


def test_old_runtime_keys_rejected_and_env_reach_runs_module(tmp_path: Path) -> None:
    old = _config(tmp_path, "runtime: {max_concurrency: 2}\nworking_directory: proj\n")
    with pytest.raises(ConfigError) as exc:
        load_settings(old, cwd=tmp_path, environ={})
    assert {k.old for k in exc.value.removed} == {"runtime", "working_directory"}
    cfg = _config(
        tmp_path,
        "modules:\n  options:\n"
        "    mod-runs: {runtime: {max_concurrency: 2}, working_directory: proj}\n",
    )
    settings = load_settings(cfg, cwd=tmp_path, environ={})
    runs = settings.modules.options["mod-runs"]
    assert runs["runtime"]["max_concurrency"] == 2
    assert runs["working_directory"] == "proj"
    env = {"AGENT_CONSOLE_MAX_CONCURRENCY": "4", "AGENT_CONSOLE_WORKING_DIRECTORY": "e"}
    s2 = load_settings(cfg, cwd=tmp_path, environ=env)
    assert s2.modules.options["mod-runs"]["working_directory"] == "e"
    assert str(s2.modules.options["mod-runs"]["runtime"]["max_concurrency"]) == "4"
