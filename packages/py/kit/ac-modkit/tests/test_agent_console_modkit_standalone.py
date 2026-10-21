"""standalone.run: --with·--config·--host·--port 0·--check."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from agent_console_modkit.host import HostSettings
from agent_console_modkit.standalone import run, select_modules
from agent_console_modkit.testing import ECHO_TRANSFORM, echo_module, fake_module

UPPER = fake_module(
    "mod-upper",
    provides=[ECHO_TRANSFORM],
    on_build=lambda ctx: ctx.provide(ECHO_TRANSFORM, str.upper),
)


def test_check_starts_on_free_port_and_hits_health() -> None:
    out = io.StringIO()
    code = run(echo_module, ["--check", "--port", "0"], available=[], environ={}, out=out)
    text = out.getvalue()
    assert code == 0, text
    assert "echo 0.1.0 [feature] active" in text
    assert "/health → 200" in text


def test_with_adds_modules_from_available_and_config_options(tmp_path: Path) -> None:
    config = tmp_path / "agent-console.json"
    config.write_text(
        json.dumps({"modules": {"options": {"echo": {"prefix": "> "}}}, "server_only": 1}),
        encoding="utf-8",
    )
    served: list[tuple[FastAPI, HostSettings]] = []
    out = io.StringIO()
    code = run(
        echo_module,
        ["--with", "mod-upper", "--config", str(config), "--port", "0"],
        available=[UPPER],
        environ={},
        serve=lambda app, settings: served.append((app, settings)),
        out=out,
    )
    assert code == 0, out.getvalue()
    app, settings = served[0]
    assert settings.port == 0
    assembly: Any = app.state.assembly
    assert [r.id for r in assembly.report] == ["echo", "mod-upper"]
    assert assembly.services.paths.base_dir == tmp_path


def test_unknown_with_and_bad_config_exit_2(tmp_path: Path) -> None:
    out = io.StringIO()
    assert run(echo_module, ["--with", "mod-nope"], available=[], out=out) == 2
    assert "mod-nope" in out.getvalue()
    bad = tmp_path / "c.json"
    bad.write_text("{", encoding="utf-8")
    assert run(echo_module, ["--config", str(bad)], available=[], out=io.StringIO()) == 2
    assert run(echo_module, ["--config", str(tmp_path / "none.json")], out=io.StringIO()) == 2


def test_remote_bind_requires_opt_in() -> None:
    out = io.StringIO()
    assert run(echo_module, ["--host", "0.0.0.0", "--check"], available=[], out=out) == 2
    assert "allow_remote" in out.getvalue()


def test_target_module_not_active_exits_1() -> None:
    needy = fake_module("mod-needy", requires=["definitions.store"])
    out = io.StringIO()
    assert run(needy, ["--check"], available=[], environ={}, out=out) == 1
    assert "unsatisfied" in out.getvalue()
    assert "definitions.store" in out.getvalue()


def test_select_modules_skips_duplicates_and_reports_missing() -> None:
    chosen, missing = select_modules(echo_module, ["echo", "mod-upper", "mod-upper", "x"], [UPPER])
    assert [m.descriptor.id for m in chosen] == ["echo", "mod-upper"]
    assert missing == ["x"]


def test_default_with_is_used_only_without_explicit_with() -> None:
    other = fake_module("mod-other")
    served: list[tuple[FastAPI, HostSettings]] = []

    def serve(app: FastAPI, settings: HostSettings) -> None:
        served.append((app, settings))

    out = io.StringIO()
    code = run(
        echo_module, ["--port", "0"], available=[other], default_with=[UPPER], serve=serve, out=out
    )
    assert code == 0, out.getvalue()
    assert [r.id for r in served[-1][0].state.assembly.report] == ["echo", "mod-upper"]
    code = run(
        echo_module,
        ["--with", "mod-other", "--port", "0"],
        available=[other],
        default_with=[UPPER],
        serve=serve,
        out=out,
    )
    assert code == 0, out.getvalue()
    assert [r.id for r in served[-1][0].state.assembly.report] == ["echo", "mod-other"]
