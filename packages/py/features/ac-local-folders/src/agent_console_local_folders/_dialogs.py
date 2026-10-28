"""네이티브 폴더 선택 창: 명령 표(데이터) + 공통 실행기(X35, design §PI.6).

명령은 패키지 데이터 `data/folder_dialogs.json`이고, 이 모듈은 특정 OS·도구 이름을 모른다.
플랫폼(`sys.platform` 접두)·실행 파일(`which`)·환경변수만 보고 첫 번째로 쓸 수 있는 항목을 고른다.

전제: 창은 **서버 프로세스가 도는 컴퓨터의 화면**에 뜬다. 그래서 브라우저와 서버가 같은 컴퓨터일 때,
즉 서버가 루프백(127.0.0.1·::1)에 묶였을 때만 쓴다. 이 패키지는 바인딩을 모르므로 차단은 부르는 쪽
(`ac-mod-projects`)이 한다.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from importlib import resources
from typing import Any

from ._local import LocalFileSystem
from ._ops import check_folder
from ._runner import CancelSignal, CommandOutcome, CommandRunner
from ._types import FileSystem, FolderCheck, FolderStatus

__all__ = [
    "DEFAULT_DIALOG_TIMEOUT",
    "DialogArg",
    "DialogAvailability",
    "DialogProbe",
    "DialogResult",
    "DialogSpec",
    "DialogStatus",
    "DialogUnavailableReason",
    "load_dialog_specs",
    "probe_dialogs",
    "run_dialog",
    "select_dialog",
]

DEFAULT_DIALOG_TIMEOUT = 300.0
"""`run_dialog` 기본 시간 상한(초). 사용자가 고를 때까지 기다리므로 길다."""

_PLACEHOLDERS = ("initial", "title")
_DETAIL_LIMIT = 500
_NO_ENV: Mapping[str, str] = {}


class DialogStatus:
    """`DialogResult.status` 값(열린 문자열). `busy`(한 번에 하나)는 부르는 쪽이 정한다."""

    PICKED = "picked"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    FAILED = "failed"


class DialogUnavailableReason:
    """`DialogProbe.reason`·`DialogAvailability.reason` 값(열린 문자열)."""

    NO_PROVIDER = "no_provider"
    """이 플랫폼에 맞는 항목이 없음."""
    MISSING_COMMAND = "missing_command"
    """실행 파일이 없음."""
    MISSING_ENV = "missing_env"
    """필요한 환경변수(예: 디스플레이)가 없음."""
    PLATFORM = "platform"
    """항목 하나가 이 플랫폼용이 아님(`DialogProbe`에만)."""


@dataclass(frozen=True)
class DialogArg:
    """조건부 인자 묶음: `when` 값(`initial`·`title`)이 비어 있지 않을 때만 `args`를 넣는다."""

    when: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class DialogSpec:
    """명령 표 항목 하나.

    Attributes:
        id: 항목 id(설치자 데이터가 같은 id로 바꾸거나 끈다).
        argv: 인자 틀. 문자열 또는 `DialogArg`. `{initial}`·`{title}`만 값으로 바뀐다(셸 없음).
        platforms: `sys.platform` 접두 목록(빈 목록 = 모든 플랫폼).
        requires: 모두 있어야 하는 실행 파일 이름.
        env_requires: 이 중 하나라도 값이 있어야 하는 환경변수(빈 목록 = 조건 없음).
        env: 자식 프로세스에 더할 환경변수 틀(스크립트에 사용자 값을 넘길 때 쓴다).
        cancel_exit_codes: 취소로 볼 종료 코드. 종료 코드 0 + 빈 출력도 취소다.
        encoding: 표준 출력 인코딩.
        label: 표시 이름(선택).
    """

    id: str
    argv: tuple[str | DialogArg, ...]
    platforms: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    env_requires: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    cancel_exit_codes: frozenset[int] = frozenset()
    encoding: str = "utf-8"
    label: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str = "dialog") -> DialogSpec:
        """dict(JSON 항목) → 항목. 형식이 틀리면 `ValueError`."""
        if not isinstance(data, Mapping):
            raise ValueError(f"{where}: 객체여야 합니다")
        ident = data.get("id")
        if not isinstance(ident, str) or not ident:
            raise ValueError(f"{where}: id는 빈 값이 아닌 문자열이어야 합니다")
        where = f"{where}({ident})"
        argv = _argv(data.get("argv"), where)
        env_raw = data.get("env") or {}
        if not isinstance(env_raw, Mapping) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in env_raw.items()
        ):
            raise ValueError(f"{where}: env는 문자열 → 문자열 객체여야 합니다")
        codes = data.get("cancel_exit_codes") or []
        if not isinstance(codes, list) or not all(
            isinstance(c, int) and not isinstance(c, bool) for c in codes
        ):
            raise ValueError(f"{where}: cancel_exit_codes는 정수 목록이어야 합니다")
        encoding = data.get("encoding", "utf-8")
        if not isinstance(encoding, str):
            raise ValueError(f"{where}: encoding은 문자열이어야 합니다")
        try:
            "".encode(encoding)
        except LookupError as exc:
            raise ValueError(f"{where}: 모르는 encoding: {encoding!r}") from exc
        label = data.get("label")
        if label is not None and not isinstance(label, str):
            raise ValueError(f"{where}: label은 문자열이어야 합니다")
        return cls(
            id=ident,
            argv=argv,
            platforms=_strings(data.get("platforms"), f"{where}.platforms"),
            requires=_strings(data.get("requires"), f"{where}.requires"),
            env_requires=_strings(data.get("env_requires"), f"{where}.env_requires"),
            env=dict(env_raw),
            cancel_exit_codes=frozenset(codes),
            encoding=encoding,
            label=label,
        )

    def build_argv(self, values: Mapping[str, str]) -> list[str]:
        """인자 틀 → 실제 인자 목록. `values`는 `initial`·`title`(없으면 빈 값)."""
        out: list[str] = []
        for item in self.argv:
            if isinstance(item, DialogArg):
                if values.get(item.when):
                    out.extend(_fill(a, values) for a in item.args)
            else:
                out.append(_fill(item, values))
        return out

    def build_env(self, values: Mapping[str, str]) -> dict[str, str]:
        """환경변수 틀 → 자식 프로세스에 더할 값."""
        return {k: _fill(v, values) for k, v in self.env.items()}


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{where}: 빈 값이 아닌 문자열 목록이어야 합니다")
    return tuple(value)


def _argv(value: Any, where: str) -> tuple[str | DialogArg, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{where}: argv는 비어 있지 않은 목록이어야 합니다")
    if not isinstance(value[0], str) or not value[0]:
        raise ValueError(f"{where}: argv 첫 항목은 실행 파일 이름(문자열)이어야 합니다")
    items: list[str | DialogArg] = []
    for i, item in enumerate(value):
        if isinstance(item, str):
            items.append(item)
            continue
        if isinstance(item, Mapping):
            when = item.get("when")
            if when not in _PLACEHOLDERS:
                raise ValueError(f"{where}.argv[{i}]: when은 {_PLACEHOLDERS} 중 하나여야 합니다")
            args = _strings(item.get("args"), f"{where}.argv[{i}].args")
            items.append(DialogArg(when=str(when), args=args))
            continue
        raise ValueError(f"{where}.argv[{i}]: 문자열 또는 {{when, args}} 객체여야 합니다")
    return tuple(items)


def _fill(template: str, values: Mapping[str, str]) -> str:
    # str.format을 쓰지 않는다: 스크립트의 중괄호를 그대로 두고 알려진 자리만 바꾼다.
    for name in _PLACEHOLDERS:
        template = template.replace("{" + name + "}", values.get(name, ""))
    return template


def _package_json(name: str) -> Any:
    text = resources.files(__package__).joinpath("data", name).read_text(encoding="utf-8")
    return json.loads(text)


def load_dialog_specs(
    extra: Iterable[Mapping[str, Any] | DialogSpec] | None = None,
    *,
    include_defaults: bool = True,
    defaults: Mapping[str, Any] | None = None,
) -> tuple[DialogSpec, ...]:
    """명령 표. 기본 데이터(`data/folder_dialogs.json`)에 설치자 항목(`extra`)을 합친다.

    합치는 규칙: `extra`의 항목이 기본 항목과 id가 같으면 그 자리를 바꾸고, `"enabled": false`면
    그 항목을 뺀다. 새 id는 기본 항목들 **앞**에 순서대로 둔다(설치자 항목 우선).

    Args:
        extra: 더하거나 바꿀 항목(dict 또는 `DialogSpec`).
        include_defaults: 거짓이면 기본 데이터 없이 `extra`만.
        defaults: 기본 데이터 대신 쓸 표(`{"dialogs": [...]}`, 테스트·다른 앱용).

    Raises:
        ValueError: 형식이 틀림(같은 id가 `extra`에 두 번 등).

    >>> specs = load_dialog_specs(
    ...     [{"id": "mine", "argv": ["my-picker"]}, {"id": "zenity", "enabled": False}])
    >>> [s.id for s in specs][:2], "zenity" in [s.id for s in specs]
    (['mine', 'windows-powershell'], False)
    """
    base: list[DialogSpec] = []
    if include_defaults:
        raw = _package_json("folder_dialogs.json") if defaults is None else defaults
        items = raw.get("dialogs") if isinstance(raw, Mapping) else None
        if not isinstance(items, list):
            raise ValueError("folder_dialogs: dialogs는 목록이어야 합니다")
        base = [DialogSpec.from_dict(d, f"folder_dialogs[{i}]") for i, d in enumerate(items)]
        _no_duplicates([s.id for s in base], "folder_dialogs")
    index = {s.id: i for i, s in enumerate(base)}
    replaced: dict[int, DialogSpec | None] = {}
    added: list[DialogSpec] = []
    seen: list[str] = []
    for i, item in enumerate(extra or ()):
        where = f"folder_dialog.providers[{i}]"
        if isinstance(item, DialogSpec):
            spec: DialogSpec | None = item
            ident = item.id
        else:
            if not isinstance(item, Mapping):
                raise ValueError(f"{where}: 객체여야 합니다")
            ident = str(item.get("id", ""))
            enabled = item.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError(f"{where}: enabled는 참/거짓이어야 합니다")
            if enabled:
                body = {k: v for k, v in item.items() if k != "enabled"}
                spec = DialogSpec.from_dict(body, where)
            else:
                if not ident:
                    raise ValueError(f"{where}: id가 필요합니다")
                spec = None
        seen.append(ident)
        if ident in index:
            replaced[index[ident]] = spec
        elif spec is not None:
            added.append(spec)
    _no_duplicates(seen, "folder_dialog.providers")
    merged = [replaced.get(i, s) for i, s in enumerate(base)]
    return (*added, *(s for s in merged if s is not None))


def _no_duplicates(ids: Sequence[str], where: str) -> None:
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ValueError(f"{where}: 같은 id가 여러 번 있습니다: {dup}")


@dataclass(frozen=True)
class DialogProbe:
    """항목 하나를 이 환경에서 쓸 수 있는가.

    Attributes:
        id: 항목 id.
        available: 쓸 수 있는가.
        reason: 못 쓰는 이유(`DialogUnavailableReason`).
        missing: 없는 실행 파일 이름 또는 (환경변수 조건이면) 그 환경변수 이름들.
    """

    id: str
    available: bool
    reason: str | None = None
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class DialogAvailability:
    """`probe_dialogs` 결과.

    Attributes:
        selected: 쓸 항목(첫 번째로 쓸 수 있는 것). 없으면 `None`.
        probes: 항목별 판정(표 순서).
        reason: `selected`가 없을 때 대표 이유(`DialogUnavailableReason`).
    """

    selected: DialogSpec | None
    probes: tuple[DialogProbe, ...]
    reason: str | None = None

    @property
    def available(self) -> bool:
        """쓸 수 있는 항목이 있는가."""
        return self.selected is not None

    def to_dict(self) -> dict[str, Any]:
        """JSON용 dict(`selected`는 id만)."""
        return {
            "available": self.available,
            "provider": self.selected.id if self.selected else None,
            "reason": self.reason,
            "probes": [asdict(p) for p in self.probes],
        }


def _platform_ok(spec: DialogSpec, platform: str) -> bool:
    return not spec.platforms or any(platform.startswith(p) for p in spec.platforms)


def probe_dialogs(
    specs: Sequence[DialogSpec],
    *,
    platform: str,
    which: Callable[[str], str | None],
    environ: Mapping[str, str],
) -> DialogAvailability:
    """어떤 항목을 쓸 수 있는지 판정한다(명령을 실행하지 않음).

    Args:
        specs: 명령 표(`load_dialog_specs`).
        platform: 서버 프로세스 플랫폼(`sys.platform`).
        which: 실행 파일 찾기(`shutil.which`). 테스트는 가짜를 넣는다.
        environ: 서버 프로세스 환경변수(`os.environ`).

    >>> specs = load_dialog_specs()
    >>> a = probe_dialogs(specs, platform="linux", which=lambda n: None, environ={})
    >>> a.available, a.reason
    (False, 'missing_command')
    >>> a = probe_dialogs(specs, platform="linux",
    ...                   which=lambda n: f"/usr/bin/{n}" if n == "zenity" else None,
    ...                   environ={"DISPLAY": ":0"})
    >>> a.selected.id
    'zenity'
    """
    probes: list[DialogProbe] = []
    selected: DialogSpec | None = None
    for spec in specs:
        if not _platform_ok(spec, platform):
            probes.append(DialogProbe(spec.id, False, DialogUnavailableReason.PLATFORM))
            continue
        missing = tuple(name for name in spec.requires if not which(name))
        if missing:
            probes.append(
                DialogProbe(spec.id, False, DialogUnavailableReason.MISSING_COMMAND, missing)
            )
            continue
        if spec.env_requires and not any(environ.get(n) for n in spec.env_requires):
            probes.append(
                DialogProbe(spec.id, False, DialogUnavailableReason.MISSING_ENV, spec.env_requires)
            )
            continue
        probes.append(DialogProbe(spec.id, True))
        if selected is None:
            selected = spec
    reason: str | None = None
    if selected is None:
        reasons = {p.reason for p in probes}
        if reasons <= {DialogUnavailableReason.PLATFORM}:
            reason = DialogUnavailableReason.NO_PROVIDER
        elif DialogUnavailableReason.MISSING_ENV in reasons:
            reason = DialogUnavailableReason.MISSING_ENV
        else:
            reason = DialogUnavailableReason.MISSING_COMMAND
    return DialogAvailability(selected=selected, probes=tuple(probes), reason=reason)


def select_dialog(
    specs: Sequence[DialogSpec],
    *,
    platform: str,
    which: Callable[[str], str | None],
    environ: Mapping[str, str],
) -> DialogSpec | None:
    """첫 번째로 쓸 수 있는 항목(없으면 `None`). 이유가 필요하면 `probe_dialogs`."""
    return probe_dialogs(specs, platform=platform, which=which, environ=environ).selected


@dataclass(frozen=True)
class DialogResult:
    """`run_dialog` 결과.

    Attributes:
        status: `DialogStatus` 값.
        path: 고른 폴더(정규화 + 링크를 푼 경로, `check.path`). `picked`일 때만.
        check: 고른 경로의 `check_folder` 결과(`picked`, 또는 쓸 수 없는 경로라 `failed`일 때).
        provider: 쓴 항목 id.
        exit_code: 명령 종료 코드(있으면).
        detail: 실패 이유 코드(`not_found`·`os_error`·`exit_code`·`bad_encoding`·`invalid_path`).
        message: 진단용 짧은 문장(표준 오류 끝부분 등, 최대 500자). 화면에 그대로 보이지 않는다.
    """

    status: str
    path: str | None = None
    check: FolderCheck | None = None
    provider: str | None = None
    exit_code: int | None = None
    detail: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON용 dict(`check`는 `FolderCheck.to_dict`)."""
        data = asdict(self)
        data["check"] = self.check.to_dict() if self.check is not None else None
        return data


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value if ch >= " " and ch != "\x7f")


def _initial_dir(initial: str | None, fs: FileSystem, environ: Mapping[str, str]) -> str:
    """대화상자 시작 폴더: 있는 폴더면 그대로, 아니면 가장 가까운 존재하는 상위, 없으면 빈 값."""
    raw = _clean(initial).strip()
    if not raw:
        return ""
    check = check_folder(raw, fs=fs, environ=environ)
    if check.path is not None and check.exists and check.is_dir:
        return check.path
    return check.nearest_existing or ""


def _tail(data: bytes, encoding: str) -> str | None:
    text = data.decode(encoding, errors="replace").strip()
    return text[-_DETAIL_LIMIT:] if text else None


def run_dialog(
    spec: DialogSpec,
    *,
    runner: CommandRunner,
    initial: str | None = None,
    title: str | None = None,
    timeout: float = DEFAULT_DIALOG_TIMEOUT,
    cancel: CancelSignal | None = None,
    fs: FileSystem | None = None,
    environ: Mapping[str, str] = _NO_ENV,
) -> DialogResult:
    """명령 표 항목 하나를 실행해 사용자가 고른 폴더를 얻는다(공통 실행기).

    셸 없이 실행하고, 표준 출력 첫 줄을 경로로 읽어 `check_folder`로 정규화한다.
    취소 종료 코드 또는 (종료 코드 0 + 빈 출력) → `cancelled`, 시간 상한 → `timeout`(프로세스는
    실행기가 끝냄), `cancel` 신호 → `cancelled`, 실행 파일 없음 → `unavailable`, 그 밖 → `failed`.
    사용자 입력 때문에 예외를 내지 않는다.

    Args:
        spec: 항목(`select_dialog`).
        runner: 명령 실행기(`SubprocessRunner` 또는 가짜).
        initial: 시작 폴더(없거나 없는 경로면 가장 가까운 상위, 그것도 없으면 생략).
        title: 창 제목·안내 문장(제어 문자는 뺌).
        timeout: 시간 상한(초).
        cancel: 중단 신호(요청이 끊기면 부르는 쪽이 켬).
        fs: 경로 확인용 파일 시스템(기본 `LocalFileSystem()`).
        environ: `~` 펼치기용 환경변수(자식 프로세스 환경이 아님).
    """
    fs = fs if fs is not None else LocalFileSystem()
    values = {"initial": _initial_dir(initial, fs, environ), "title": _clean(title)}
    argv = spec.build_argv(values)
    try:
        outcome: CommandOutcome = runner(
            argv, env=spec.build_env(values), timeout=timeout, cancel=cancel
        )
    except FileNotFoundError:
        return DialogResult(DialogStatus.UNAVAILABLE, provider=spec.id, detail="not_found")
    except (OSError, ValueError) as exc:
        return DialogResult(
            DialogStatus.FAILED, provider=spec.id, detail="os_error", message=str(exc)[:500]
        )

    def done(status: str, **kw: Any) -> DialogResult:
        return DialogResult(status, provider=spec.id, exit_code=outcome.exit_code, **kw)

    if outcome.cancelled:
        return done(DialogStatus.CANCELLED)
    if outcome.timed_out:
        return done(DialogStatus.TIMEOUT)
    if outcome.exit_code in spec.cancel_exit_codes:
        return done(DialogStatus.CANCELLED)
    if outcome.exit_code != 0:
        return done(
            DialogStatus.FAILED, detail="exit_code", message=_tail(outcome.stderr, spec.encoding)
        )
    try:
        text = outcome.stdout.decode(spec.encoding)
    except UnicodeDecodeError:
        return done(DialogStatus.FAILED, detail="bad_encoding")
    lines = text.lstrip("\ufeff").splitlines()
    first = lines[0] if lines else ""
    if not first.strip():
        return done(DialogStatus.CANCELLED)
    check = check_folder(first, fs=fs, environ=environ)
    if check.path is None or check.status == FolderStatus.INVALID:
        return done(DialogStatus.FAILED, check=check, detail="invalid_path", message=check.problem)
    return done(DialogStatus.PICKED, path=check.path, check=check)
