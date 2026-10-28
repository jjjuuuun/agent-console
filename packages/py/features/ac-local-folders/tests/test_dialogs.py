"""네이티브 폴더 선택 창: 명령 표·선택·공통 실행기 표 테스트(가짜 실행기, 창을 띄우지 않음)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_console_local_folders import (
    CancelSignal,
    CommandOutcome,
    DialogSpec,
    DialogStatus,
    DialogUnavailableReason,
    MemoryFileSystem,
    load_dialog_specs,
    probe_dialogs,
    run_dialog,
    select_dialog,
)


@dataclass
class FakeRunner:
    """호출을 기록하고 정해 둔 결과를 돌려주는 가짜 실행기."""

    outcome: CommandOutcome | None = None
    error: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        timeout: float,
        cancel: CancelSignal | None = None,
    ) -> CommandOutcome:
        self.calls.append({"argv": list(argv), "env": dict(env), "timeout": timeout})
        if self.error is not None:
            raise self.error
        assert self.outcome is not None
        return self.outcome


def which_of(*names: str) -> Any:
    return lambda n: f"/bin/{n}" if n in names else None


def posix_fs() -> MemoryFileSystem:
    return MemoryFileSystem().add_dir("/home/me/work/app").add_dir("/home/me/한글 폴더")


def win_fs() -> MemoryFileSystem:
    return MemoryFileSystem(flavor="windows").add_dir("C:\\Users\\me\\프로젝트")


SPECS = load_dialog_specs()


# --- 기본 데이터 ---------------------------------------------------------------


def test_default_table_ids_and_shape() -> None:
    ids = [s.id for s in SPECS]
    assert ids == ["windows-powershell", "macos-osascript", "zenity", "kdialog"]
    for spec in SPECS:
        assert spec.requires, spec.id
        assert isinstance(spec.argv[0], str)


@pytest.mark.parametrize(
    ("platform", "found", "environ", "expected", "reason"),
    [
        ("win32", ("powershell",), {}, "windows-powershell", None),
        ("win32", (), {}, None, DialogUnavailableReason.MISSING_COMMAND),
        ("darwin", ("osascript",), {}, "macos-osascript", None),
        ("linux", ("zenity", "kdialog"), {"DISPLAY": ":0"}, "zenity", None),
        ("linux", ("kdialog",), {"WAYLAND_DISPLAY": "wayland-0"}, "kdialog", None),
        ("linux", ("zenity",), {}, None, DialogUnavailableReason.MISSING_ENV),
        ("linux", ("zenity",), {"DISPLAY": ""}, None, DialogUnavailableReason.MISSING_ENV),
        ("linux", (), {"DISPLAY": ":0"}, None, DialogUnavailableReason.MISSING_COMMAND),
        ("freebsd14", ("kdialog",), {"DISPLAY": ":0"}, "kdialog", None),
        ("sunos5", ("zenity",), {"DISPLAY": ":0"}, None, DialogUnavailableReason.NO_PROVIDER),
        # 플랫폼이 다르면 그 OS의 실행 파일이 있어도 쓰지 않는다.
        ("linux", ("powershell", "osascript"), {"DISPLAY": ":0"}, None, "missing_command"),
    ],
)
def test_select_by_platform_which_env(
    platform: str,
    found: tuple[str, ...],
    environ: dict[str, str],
    expected: str | None,
    reason: str | None,
) -> None:
    avail = probe_dialogs(SPECS, platform=platform, which=which_of(*found), environ=environ)
    assert (avail.selected.id if avail.selected else None) == expected
    assert avail.reason == reason
    assert avail.available is (expected is not None)
    chosen = select_dialog(SPECS, platform=platform, which=which_of(*found), environ=environ)
    assert chosen is avail.selected


def test_probe_reports_each_item() -> None:
    avail = probe_dialogs(SPECS, platform="linux", which=which_of("kdialog"), environ={})
    by_id = {p.id: p for p in avail.probes}
    assert by_id["windows-powershell"].reason == DialogUnavailableReason.PLATFORM
    assert by_id["zenity"].reason == DialogUnavailableReason.MISSING_COMMAND
    assert by_id["zenity"].missing == ("zenity",)
    assert by_id["kdialog"].reason == DialogUnavailableReason.MISSING_ENV
    assert by_id["kdialog"].missing == ("DISPLAY", "WAYLAND_DISPLAY")
    data = avail.to_dict()
    assert data["available"] is False
    assert data["provider"] is None
    assert len(data["probes"]) == len(SPECS)


# --- 데이터로 바꾸기(R0: 코드 수정 없이 반영) -------------------------------------


def test_extra_item_comes_first_and_replaces_by_id() -> None:
    specs = load_dialog_specs(
        [
            {
                "id": "my-picker",
                "platforms": ["linux"],
                "requires": ["my-picker"],
                "argv": ["my-picker", "--start", "{initial}"],
            },
            {
                "id": "zenity",
                "platforms": ["linux"],
                "requires": ["zenity"],
                "argv": ["zenity", "--file-selection", "--directory"],
            },
            {"id": "kdialog", "enabled": False},
        ]
    )
    ids = [s.id for s in specs]
    assert ids == ["my-picker", "windows-powershell", "macos-osascript", "zenity"]
    # 바꾼 zenity는 디스플레이 조건이 없다.
    chosen = select_dialog(specs, platform="linux", which=which_of("zenity"), environ={})
    assert chosen is not None
    assert chosen.id == "zenity"
    # 새 항목이 있으면 그것이 먼저다.
    chosen = select_dialog(
        specs, platform="linux", which=which_of("zenity", "my-picker"), environ={}
    )
    assert chosen is not None
    assert chosen.id == "my-picker"


def test_new_platform_by_data_only() -> None:
    specs = load_dialog_specs(
        [
            {
                "id": "haiku",
                "platforms": ["haiku"],
                "requires": ["filepanel"],
                "argv": ["filepanel", "-d"],
            }
        ],
        include_defaults=False,
    )
    chosen = select_dialog(specs, platform="haiku1", which=which_of("filepanel"), environ={})
    assert chosen is not None
    runner = FakeRunner(CommandOutcome(0, b"/home/me/work/app\n"))
    result = run_dialog(chosen, runner=runner, fs=posix_fs())
    assert result.status == DialogStatus.PICKED
    assert runner.calls[0]["argv"] == ["filepanel", "-d"]


def test_defaults_argument_and_spec_objects() -> None:
    spec = DialogSpec(id="obj", argv=("pick",))
    specs = load_dialog_specs([spec], defaults={"dialogs": [{"id": "a", "argv": ["a"]}]})
    assert [s.id for s in specs] == ["obj", "a"]
    assert load_dialog_specs(include_defaults=False) == ()


@pytest.mark.parametrize(
    ("item", "message"),
    [
        ({"argv": ["x"]}, "id"),
        ({"id": "x"}, "argv"),
        ({"id": "x", "argv": []}, "argv"),
        ({"id": "x", "argv": [{"when": "initial", "args": ["a"]}]}, "첫 항목"),
        ({"id": "x", "argv": ["x", {"when": "other", "args": ["a"]}]}, "when"),
        ({"id": "x", "argv": ["x", 3]}, r"argv\[1\]"),
        ({"id": "x", "argv": ["x"], "cancel_exit_codes": ["1"]}, "cancel_exit_codes"),
        ({"id": "x", "argv": ["x"], "cancel_exit_codes": [True]}, "cancel_exit_codes"),
        ({"id": "x", "argv": ["x"], "encoding": "no-such-codec"}, "encoding"),
        ({"id": "x", "argv": ["x"], "env": {"A": 1}}, "env"),
        ({"id": "x", "argv": ["x"], "requires": [""]}, "requires"),
        ({"id": "x", "argv": ["x"], "enabled": "no"}, "enabled"),
        ({"id": "", "enabled": False}, "id"),
    ],
)
def test_invalid_items_rejected(item: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_dialog_specs([item], include_defaults=False)


def test_duplicate_ids_rejected() -> None:
    with pytest.raises(ValueError, match="같은 id"):
        load_dialog_specs([{"id": "a", "argv": ["a"]}, {"id": "a", "argv": ["b"]}])
    with pytest.raises(ValueError, match="같은 id"):
        load_dialog_specs(defaults={"dialogs": [{"id": "a", "argv": ["a"]}] * 2})
    with pytest.raises(ValueError, match="dialogs"):
        load_dialog_specs(defaults={"items": []})


# --- 인자 만들기 ---------------------------------------------------------------


def _spec(spec_id: str) -> DialogSpec:
    return next(s for s in SPECS if s.id == spec_id)


def test_zenity_argv_with_and_without_initial() -> None:
    fs = posix_fs()
    runner = FakeRunner(CommandOutcome(1))
    run_dialog(_spec("zenity"), runner=runner, initial="/home/me/work/app", title="폴더", fs=fs)
    run_dialog(_spec("zenity"), runner=runner, fs=fs)
    assert runner.calls[0]["argv"] == [
        "zenity",
        "--file-selection",
        "--directory",
        "--title=폴더",
        "--filename=/home/me/work/app/",
    ]
    assert runner.calls[1]["argv"] == ["zenity", "--file-selection", "--directory", "--title="]


def test_initial_falls_back_to_nearest_existing_and_drops_invalid() -> None:
    fs = posix_fs()
    runner = FakeRunner(CommandOutcome(1))
    run_dialog(_spec("kdialog"), runner=runner, initial="/home/me/work/app/gone/deeper", fs=fs)
    run_dialog(_spec("kdialog"), runner=runner, initial="relative/path", fs=fs)
    env = {"HOME": "/home/me"}
    run_dialog(_spec("kdialog"), runner=runner, initial="~/work", fs=fs, environ=env)
    assert runner.calls[0]["argv"][-1] == "/home/me/work/app"
    assert runner.calls[1]["argv"] == ["kdialog", "--title", "", "--getexistingdirectory"]
    assert runner.calls[2]["argv"][-1] == "/home/me/work"


def test_user_values_go_to_env_not_script() -> None:
    fs = win_fs()
    runner = FakeRunner(CommandOutcome(0, b""))
    title = "'; Remove-Item C:\\ -Recurse; '\n"
    run_dialog(
        _spec("windows-powershell"),
        runner=runner,
        initial="C:\\Users\\me\\프로젝트",
        title=title,
        fs=fs,
    )
    call = runner.calls[0]
    script = call["argv"][-1]
    assert "Remove-Item" not in script
    assert call["env"]["AGENT_CONSOLE_DIALOG_TITLE"] == "'; Remove-Item C:\\ -Recurse; '"
    assert call["env"]["AGENT_CONSOLE_DIALOG_INITIAL"] == "C:\\Users\\me\\프로젝트"


def test_osascript_passes_values_as_arguments() -> None:
    runner = FakeRunner(CommandOutcome(0, b""))
    run_dialog(_spec("macos-osascript"), runner=runner, title="고르기", fs=posix_fs())
    argv = runner.calls[0]["argv"]
    assert argv[0] == "osascript"
    assert argv[-2:] == ["고르기", ""]


def test_braces_in_script_are_kept() -> None:
    spec = DialogSpec(id="x", argv=("sh-free", "{ $a } {title} {other}"))
    assert spec.build_argv({"title": "t"}) == ["sh-free", "{ $a } t {other}"]


# --- 결과 판정 ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "status", "detail"),
    [
        (CommandOutcome(0, b"/home/me/work/app\n"), DialogStatus.PICKED, None),
        (CommandOutcome(0, b"/home/me/work/app/\r\nextra\n"), DialogStatus.PICKED, None),
        (CommandOutcome(1), DialogStatus.CANCELLED, None),
        (CommandOutcome(0, b""), DialogStatus.CANCELLED, None),
        (CommandOutcome(0, b"  \n"), DialogStatus.CANCELLED, None),
        (CommandOutcome(None, timed_out=True), DialogStatus.TIMEOUT, None),
        (CommandOutcome(-9, b"/home/me/work/app", timed_out=True), DialogStatus.TIMEOUT, None),
        (CommandOutcome(-9, cancelled=True), DialogStatus.CANCELLED, None),
        (
            CommandOutcome(255, stderr=b"Gtk-WARNING: cannot open display"),
            DialogStatus.FAILED,
            "exit_code",
        ),
        (CommandOutcome(0, b"\xff\xfe/bad"), DialogStatus.FAILED, "bad_encoding"),
        (CommandOutcome(0, b"not/absolute\n"), DialogStatus.FAILED, "invalid_path"),
    ],
)
def test_outcome_table(outcome: CommandOutcome, status: str, detail: str | None) -> None:
    result = run_dialog(_spec("zenity"), runner=FakeRunner(outcome), fs=posix_fs())
    assert result.status == status
    assert result.detail == detail
    assert result.provider == "zenity"
    if status == DialogStatus.PICKED:
        assert result.path == "/home/me/work/app"
        assert result.check is not None
        assert result.check.status == "ok"
    else:
        assert result.path is None


def test_failed_message_is_stderr_tail() -> None:
    err = ("x" * 1000 + "end").encode()
    result = run_dialog(
        _spec("zenity"), runner=FakeRunner(CommandOutcome(2, stderr=err)), fs=posix_fs()
    )
    assert result.message is not None
    assert len(result.message) == 500
    assert result.message.endswith("end")
    assert result.exit_code == 2


def test_cancel_exit_codes_are_data() -> None:
    base = {"id": "p", "argv": ["p"]}
    plain = load_dialog_specs([base], include_defaults=False)[0]
    coded = load_dialog_specs([{**base, "cancel_exit_codes": [3]}], include_defaults=False)[0]
    outcome = CommandOutcome(3)
    assert run_dialog(plain, runner=FakeRunner(outcome), fs=posix_fs()).status == "failed"
    assert run_dialog(coded, runner=FakeRunner(outcome), fs=posix_fs()).status == "cancelled"


def test_missing_executable_and_os_error() -> None:
    fs = posix_fs()
    missing = run_dialog(_spec("zenity"), runner=FakeRunner(error=FileNotFoundError()), fs=fs)
    assert (missing.status, missing.detail) == (DialogStatus.UNAVAILABLE, "not_found")
    denied = run_dialog(_spec("zenity"), runner=FakeRunner(error=PermissionError("no")), fs=fs)
    assert (denied.status, denied.detail) == (DialogStatus.FAILED, "os_error")


@pytest.mark.parametrize(
    ("raw", "encoding", "expected"),
    [
        ("/home/me/한글 폴더\n".encode(), "utf-8", "/home/me/한글 폴더"),
        ("\ufeff/home/me/한글 폴더\n".encode(), "utf-8", "/home/me/한글 폴더"),
        ("/home/me/한글 폴더\n".encode("cp949"), "cp949", "/home/me/한글 폴더"),
    ],
)
def test_path_encoding(raw: bytes, encoding: str, expected: str) -> None:
    spec = load_dialog_specs(
        [{"id": "p", "argv": ["p"], "encoding": encoding}], include_defaults=False
    )[0]
    result = run_dialog(spec, runner=FakeRunner(CommandOutcome(0, raw)), fs=posix_fs())
    assert result.status == DialogStatus.PICKED
    assert result.path == expected


def test_windows_path_normalized() -> None:
    out = "c:\\users\\me\\프로젝트\\\r\n".encode()
    result = run_dialog(
        _spec("windows-powershell"), runner=FakeRunner(CommandOutcome(0, out)), fs=win_fs()
    )
    assert result.status == DialogStatus.PICKED
    # 드라이브 대문자 + 링크를 푼 실제 경로(파일 시스템에 있는 대소문자).
    assert result.path == "C:\\Users\\me\\프로젝트"
    assert result.check is not None
    assert result.check.exists


def test_picked_missing_folder_still_reported_with_check() -> None:
    result = run_dialog(
        _spec("zenity"), runner=FakeRunner(CommandOutcome(0, b"/home/me/new\n")), fs=posix_fs()
    )
    assert result.status == DialogStatus.PICKED
    assert result.check is not None
    assert result.check.status == "missing"


def test_timeout_is_passed_and_result_serializes() -> None:
    runner = FakeRunner(CommandOutcome(0, b"/home/me/work/app\n"))
    result = run_dialog(_spec("zenity"), runner=runner, timeout=12.5, fs=posix_fs())
    assert runner.calls[0]["timeout"] == 12.5
    data = result.to_dict()
    assert data["status"] == "picked"
    assert data["check"]["status"] == "ok"
    assert (
        run_dialog(_spec("zenity"), runner=FakeRunner(CommandOutcome(1)), fs=posix_fs()).to_dict()[
            "check"
        ]
        is None
    )
