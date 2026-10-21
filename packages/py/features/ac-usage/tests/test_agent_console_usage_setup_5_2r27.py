"""5.2R.27: 출처 자동 켜기(auto_enable·test_only)·연결 안내 조각(자리표시자 채우기)·창 이름·
last_received_at·상태 줄 입력 원문 파일 읽기."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

from agent_console_contracts import UsageSettings, UsageSetupSnippet
from agent_console_usage import (
    SETUP_AGENT_CONSOLE_CMD,
    FakeUsageSource,
    RunEventUsageSource,
    StatuslineFileSource,
    UsageService,
    builtin_source_data,
    default_window_labels,
    fill_setup_snippets,
    load_statusline_windows,
    load_usage_sources,
    new_usage_sources,
    update_statusline_file,
)

NOW = 1_800_000_000.0
CMD = "/opt/agent console/bin/agent-console"


def _service(state_dir: Path | None, **kwargs: object) -> UsageService:
    sources = new_usage_sources()
    load_usage_sources(sources)
    return UsageService(sources, clock=lambda: NOW, state_dir=state_dir, **kwargs)  # type: ignore[arg-type]


def _infos(service: UsageService, settings: UsageSettings | None = None) -> dict[str, object]:
    return {i.descriptor.id: i for i in service.sources(settings)}


def test_builtin_descriptor_flags_come_from_data() -> None:
    fake, run, line = (
        FakeUsageSource.descriptor,
        RunEventUsageSource.descriptor,
        StatuslineFileSource.descriptor,
    )
    assert (fake.test_only, fake.auto_enable) == (True, False)
    assert (run.auto_enable, run.needs_setup, run.test_only) == (True, False, False)
    assert (line.auto_enable, line.needs_setup) == (True, True)
    assert {w.id: w.title for w in line.windows}["five_hour"] == "5시간"
    assert {w.id: w.short_title for w in run.windows}["seven_day"] == "7d"
    assert line.setup_help == builtin_source_data("statusline-file")["setup_help"]
    assert "~/.claude" in (line.setup_help or "")


def test_empty_settings_enable_auto_sources_but_not_test_only() -> None:
    service = _service(None)
    for settings in (None, UsageSettings()):
        infos = _infos(service, settings)
        assert {k: i.enabled for k, i in infos.items()} == {  # type: ignore[attr-defined]
            "fake": False,
            "run-events": True,
            "statusline-file": True,
        }


def test_user_list_always_wins() -> None:
    service = _service(None)
    settings = UsageSettings.model_validate(
        {"sources": [{"id": "fake"}, {"id": "statusline-file", "enabled": False}]}
    )
    infos = _infos(service, settings)
    assert {k: i.enabled for k, i in infos.items()} == {  # type: ignore[attr-defined]
        "fake": True,  # 적으면 켜진다
        "run-events": True,  # 적지 않은 출처는 그대로 자동 켜기(다른 출처를 적어도 바뀌지 않음)
        "statusline-file": False,
    }


def test_snippets_are_filled_with_absolute_paths(tmp_path: Path) -> None:
    state = tmp_path / "my ws" / ".state"
    service = _service(state, setup_values={SETUP_AGENT_CONSOLE_CMD: CMD})
    info = _infos(service)["statusline-file"]
    snippets = {s.id: s for s in info.descriptor.setup_snippets}  # type: ignore[attr-defined]
    output = str((state / "usage" / "statusline.json").absolute())
    for snippet in snippets.values():
        assert "{output_path}" not in snippet.text
        assert "{agent_console_cmd}" not in snippet.text
    # settings.json 조각은 그대로 JSON이고, 명령은 셸이 공백 경로를 하나로 읽는다
    command = json.loads(snippets["settings-json"].text)["statusLine"]["command"]
    assert shlex.split(command) == [CMD, "statusline", "--output", output]
    bash = snippets["append-bash"].text
    assert f"{shlex.quote(CMD)} statusline --output {shlex.quote(output)}" in bash
    assert '"$input"' in bash  # 기존 스크립트의 입력 변수에 이어 붙인다
    ps = snippets["append-powershell"].text
    assert f"& '{CMD}' statusline --output '{output}'" in ps
    # 같은 제목 = 같은 탭(셸 선택), 탭 2개
    titles = {s.title for s in snippets.values()}
    assert len(titles) == 2


def test_descriptors_fill_and_missing_values_keep_placeholders() -> None:
    service = _service(None)  # state_dir도 명령도 없음
    [line] = [d for d in service.descriptors() if d.id == "statusline-file"]
    assert all("{output_path}" in s.text for s in line.setup_snippets)
    assert all("{agent_console_cmd}" in s.text for s in line.setup_snippets)


def test_setup_values_function_is_read_each_time(tmp_path: Path) -> None:
    calls: list[int] = []

    def values() -> dict[str, str]:
        calls.append(1)
        return {SETUP_AGENT_CONSOLE_CMD: "/x/agent-console"}

    service = _service(tmp_path, setup_values=values)
    service.sources()
    service.sources()
    assert len(calls) == 2


def test_fill_quotes_by_shell_and_language() -> None:
    snippets = [
        UsageSetupSnippet(id="a", title="t", shell="bash", text="{p}"),
        UsageSetupSnippet(id="b", title="t", shell="powershell", text="{p}"),
        UsageSetupSnippet(id="c", title="t", language="json", text='"{p}"'),
        UsageSetupSnippet(id="d", title="t", shell="bash", text="{p}"),
    ]
    a, b, c, _ = fill_setup_snippets(snippets, {"p": "it's here"})
    assert a.text == "'it'\"'\"'s here'"
    assert b.text == "'it''s here'"
    assert json.loads(c.text) == "'it'\"'\"'s here'"
    assert fill_setup_snippets(snippets[3:], {"p": "/plain/path"})[0].text == "/plain/path"


def test_last_received_at_from_bridge_file(tmp_path: Path) -> None:
    service = _service(tmp_path)
    assert _infos(service)["statusline-file"].last_received_at is None  # type: ignore[attr-defined]
    path = tmp_path / "usage" / "statusline.json"
    update_statusline_file(
        path, json.dumps({"rate_limits": {"five_hour": {"used_percentage": 12}}}), now=NOW - 30
    )
    info = _infos(service)["statusline-file"]
    assert info.last_received_at == NOW - 30  # type: ignore[attr-defined]


async def test_last_received_at_falls_back_to_observed_time() -> None:
    service = _service(None)
    settings = UsageSettings.model_validate(
        {
            "sources": [
                {"id": "fake", "config": {"windows": [{"window": "w", "observed_seconds_ago": 5}]}}
            ]
        }
    )
    assert _infos(service, settings)["fake"].last_received_at is None  # type: ignore[attr-defined]
    await service.collect(settings)
    assert _infos(service, settings)["fake"].last_received_at == NOW - 5  # type: ignore[attr-defined]


async def test_reads_raw_statusline_input_file(tmp_path: Path) -> None:
    """상태 줄 스크립트가 입력을 그대로 남긴 파일(예: echo "$input" > 파일)도 읽는다."""
    raw = tmp_path / "statusline.json"
    raw.write_text(
        json.dumps(
            {
                "session_id": "secret-session",
                "cwd": "/home/me/private",
                "rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": NOW + 600}},
            }
        ),
        encoding="utf-8",
    )
    os.utime(raw, (NOW - 10, NOW - 10))
    reading = load_statusline_windows(raw)
    assert reading.received_at == NOW - 10
    service = _service(tmp_path)
    settings = UsageSettings.model_validate(
        {"sources": [{"id": "statusline-file", "config": {"path": str(raw)}}]}
    )
    [snap] = [s for s in await service.collect(settings) if s.source == "statusline-file"]
    assert (snap.window, snap.used_ratio, snap.observed_at) == ("five_hour", 0.42, NOW - 10)
    assert "secret-session" not in json.dumps(snap.model_dump())  # 창 밖 필드는 싣지 않는다
    assert _infos(service, settings)["statusline-file"].last_received_at == NOW - 10  # type: ignore[attr-defined]


def test_default_window_labels_from_data() -> None:
    labels = default_window_labels()
    assert labels["five_hour"] == "5h"
    assert labels["seven_day"] == "7d"
