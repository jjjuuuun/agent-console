"""4R.18 QA: 옛 최상위 키 9개 + 호스트 삭제 키는 한 번에 거부, 새 위치·비밀 비노출."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_server import SETTINGS_REMOVED_KEY, ConfigError, load_settings

OLD_KEYS = {
    "usage": "mod-usage",
    "exports": "mod-exports",
    "versions": "mod-versions",
    "imports": "mod-imports",
    "presets": "mod-presets",
    "resources": "mod-definitions",
    "runtime": "mod-runs",
    "backends": "mod-runs",
    "working_directory": "mod-runs",
}
SECRET = "sk-super-secret-value-123"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "agent-console.yaml"
    path.write_text(f"base_dir: {tmp_path}\nworkspace: ws\n{body}", encoding="utf-8")
    return path


@pytest.mark.parametrize(("old", "module"), sorted(OLD_KEYS.items()))
def test_each_old_key_rejected_with_new_location(tmp_path: Path, old: str, module: str) -> None:
    cfg = _write(tmp_path, f"{old}: {{token: {SECRET}}}\n")
    with pytest.raises(ConfigError) as exc:
        load_settings(cfg, cwd=tmp_path, environ={})
    assert exc.value.code == SETTINGS_REMOVED_KEY
    assert [k.old for k in exc.value.removed] == [old]
    assert f"modules.options.{module}" in str(exc.value)
    assert SECRET not in str(exc.value)
    assert all(SECRET not in k.message for k in exc.value.removed)


def test_all_old_and_host_keys_reported_at_once(tmp_path: Path) -> None:
    body = "".join(f"{k}: {{x: {SECRET}}}\n" for k in OLD_KEYS)
    body += f"console: {{x: {SECRET}}}\ndefault_manual_route_pattern: {SECRET}\n"
    with pytest.raises(ConfigError) as exc:
        load_settings(_write(tmp_path, body), cwd=tmp_path, environ={})
    assert {k.old for k in exc.value.removed} == set(OLD_KEYS) | {
        "console",
        "default_manual_route_pattern",
    }
    assert SECRET not in str(exc.value)
    assert exc.value.code == SETTINGS_REMOVED_KEY


def test_new_location_loads_without_warning(tmp_path: Path) -> None:
    body = "modules:\n  options:\n    mod-usage: {}\n    mod-versions: {}\n"
    settings = load_settings(_write(tmp_path, body), cwd=tmp_path, environ={})
    assert settings.moved_keys == []
