"""폴더 확인·찾아보기·네이티브 선택 창(design §PI.6, X34·X35). FastAPI를 모른다.

- 확인·찾아보기는 서버가 루프백에 묶였을 때만(``allow_remote_browse``로만 넓힘), 아니면 403
  ``folders.remote_disabled``. 응답에 파일 이름·내용이 없다(폴더 이름만, 기존 구성은 **개수**만).
- 선택 창은 루프백에서만, 한 번에 하나(``busy``), 시간 상한, 요청이 끊기면 ``cancel``로 창
  프로세스를 끝낸다. 명령 표는 ``ac-local-folders`` 데이터 + 설정, 코드 제공자는 entry point
  ``agent_console.folder_dialogs``(``FolderDialogProvider``).
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from importlib.metadata import entry_points
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import (
    ErrorCodes,
    ExistingProjectProbe,
    FolderCapabilities,
    FolderCheck,
    FolderCheckRequest,
    FolderConflict,
    FolderEntry,
    FolderListing,
    FolderPickRequest,
    FolderPickResult,
    FolderRoot,
    Issue,
    KnownExistingProjectStates,
    KnownFolderCheckStatuses,
    KnownFolderPickStatuses,
)
from agent_console_local_folders import (
    CancelSignal,
    CommandRunner,
    DialogSpec,
    FileSystem,
    check_folder,
    default_roots,
    list_dirs,
    load_dialog_specs,
    make_folder,
    probe_dialogs,
    run_dialog,
)
from agent_console_local_folders import FolderCheck as LocalCheck
from agent_console_project_space import ManifestInvalid, ProjectSpace, SpaceError, open_space
from agent_console_project_space import read_manifest as read_space_manifest
from agent_console_projects import (
    PathRules,
    RegisteredFolder,
    conflict_status,
    folder_conflicts,
    folder_key,
    path_relation,
    suggest_project_id,
)

from .errors import ProjectError
from .settings import FolderDialogSettings

_log = logging.getLogger("agent_console_mod_projects")

FOLDER_DIALOGS_GROUP = "agent_console.folder_dialogs"
"""코드 선택 창 제공자 entry point 그룹(X35)."""


@runtime_checkable
class FolderDialogProvider(Protocol):
    """코드 선택 창 제공자(X35, entry point ``agent_console.folder_dialogs``).

    ``pick``은 사용자가 고른 폴더 경로(취소면 None)를 돌려준다. ``cancel``이 켜지면 창을 닫고
    None을 돌려준다(요청이 끊김). 실패는 예외로 알린다(결과 ``failed``).
    """

    id: str

    def available(self, environ: Mapping[str, str]) -> bool: ...

    def pick(
        self,
        *,
        initial: str | None,
        title: str | None,
        timeout: float,
        cancel: CancelSignal,
    ) -> str | None: ...


def load_dialog_providers(group: str = FOLDER_DIALOGS_GROUP) -> list[FolderDialogProvider]:
    """설치된 코드 제공자(불러오지 못한 것은 기록하고 건너뜀)."""
    out: list[FolderDialogProvider] = []
    for ep in entry_points(group=group):
        try:
            value = ep.load()
            provider = value() if isinstance(value, type) else value
        except Exception:
            _log.exception("폴더 선택 창 제공자를 불러오지 못했습니다: %s", ep.name)
            continue
        if isinstance(provider, FolderDialogProvider):
            out.append(provider)
        else:
            _log.warning("폴더 선택 창 제공자 모양이 아닙니다: %s", ep.name)
    return out


def count_definitions(
    space: ProjectSpace, directories: Iterable[str], *, limit: int = 10000
) -> int:
    """종류 폴더의 정의 파일 개수(이름·내용은 읽지 않음, 바로 아래 ``*.yaml``·``*.yml``만)."""
    total = 0
    for directory in directories:
        if not directory:
            continue
        try:
            with os.scandir(space.root / directory) as it:
                for entry in it:
                    if entry.name.endswith((".yaml", ".yml")) and entry.is_file(
                        follow_symlinks=False
                    ):
                        total += 1
                        if total >= limit:
                            return total
        except OSError:
            continue
    return total


class FolderService:
    """폴더 확인·찾아보기.

    Args:
        fs: 파일 시스템.
        registered: 지금 등록 폴더(겹침 검사·목록 표시).
        taken_ids: 지금 등록 id(``suggested_id``).
        space_options: 공간 옵션(구성 폴더 이름·종류 — 기존 구성 탐지).
        allowed: 확인·찾아보기를 열지(루프백 또는 설치자 허용).
        environ: ``~`` 풀이·시작 위치.
        roots: 설치자 시작 위치(있으면 탐색 범위도 이것으로 제한).
        rules: 경로 비교 규칙.
        config_dir: 구성 폴더 이름(응답 ``config_dir``).
    """

    def __init__(
        self,
        *,
        fs: FileSystem,
        registered: Callable[[], list[RegisteredFolder]],
        taken_ids: Callable[[], Iterable[str]],
        space_options: Callable[[], Mapping[str, Any]],
        allowed: Callable[[], bool],
        environ: Mapping[str, str] | None = None,
        roots: Sequence[str] | None = None,
        rules: PathRules | None = None,
        config_dir: str | None = None,
    ) -> None:
        self.fs = fs
        self._registered = registered
        self._taken = taken_ids
        self._options = space_options
        self._allowed = allowed
        self.environ: Mapping[str, str] = dict(environ or {})
        self._roots = list(roots) if roots else None
        self._rules = rules
        self.config_dir = config_dir

    def require_allowed(self) -> None:
        """루프백이 아니면 403 ``folders.remote_disabled``."""
        if not self._allowed():
            raise ProjectError(
                ErrorCodes.FOLDERS_REMOTE_DISABLED,
                "서버가 로컬 주소에 묶여 있지 않아 폴더를 찾아볼 수 없습니다",
            )

    @property
    def allowed(self) -> bool:
        return self._allowed()

    # ------------------------------------------------------------ 확인

    def check(self, request: FolderCheckRequest) -> FolderCheck:
        """폴더 확인(``create``면 한 단계 만들기). 등록부 겹침·기존 구성·id 제안을 더한다."""
        self.require_allowed()
        if request.create:
            local = make_folder(request.path, fs=self.fs, environ=self.environ, roots=self._roots)
        else:
            local = check_folder(request.path, fs=self.fs, environ=self.environ, roots=self._roots)
        return self.enrich(local, exclude_project_id=request.exclude_project_id)

    def check_path(self, path: str) -> FolderCheck:
        """경로 확인(선택 창이 고른 경로)."""
        local = check_folder(path, fs=self.fs, environ=self.environ, roots=self._roots)
        return self.enrich(local)

    def enrich(self, local: LocalCheck, *, exclude_project_id: str | None = None) -> FolderCheck:
        """``ac-local-folders`` 확인 결과 + 등록부·기존 구성 → 계약 ``FolderCheck``."""
        data = local.to_dict()
        status: str = data["status"]
        conflict: FolderConflict | None = None
        existing: ExistingProjectProbe | None = None
        suggested: str | None = None
        path = local.path
        if path is not None:
            registered = self._registered()
            if exclude_project_id is not None:
                own = next((r for r in registered if r.id == exclude_project_id), None)
                if (
                    own is not None
                    and own.folder is not None
                    and path_relation(path, own.folder, flavor=self.fs.flavor, rules=self._rules)
                    == "same"
                ):
                    status = KnownFolderCheckStatuses.SAME_PATH
            conflicts = folder_conflicts(
                registered,
                path,
                exclude_project_id=exclude_project_id,
                flavor=self.fs.flavor,
                rules=self._rules,
            )
            found = conflict_status(conflicts)
            if found is not None:
                status = found
                conflict = conflicts[0]
            if local.exists and local.is_dir and local.readable:
                existing = self._existing(path)
            if conflict is None:
                manifest_id = (
                    existing.id
                    if existing is not None and existing.state == KnownExistingProjectStates.FOUND
                    else None
                )
                suggested = suggest_project_id(
                    path,
                    manifest_id=manifest_id,
                    taken_ids=list(self._taken()),
                    flavor=self.fs.flavor,
                    rules=self._rules,
                )
        data.update(
            status=status,
            conflict=conflict,
            existing=existing,
            suggested_id=suggested,
            config_dir=self.config_dir,
        )
        return FolderCheck.model_validate(data)

    def _existing(self, path: str) -> ExistingProjectProbe | None:
        options = self._options()
        try:
            space = open_space(path, **options)
        except (SpaceError, OSError):
            return None
        directories = [
            getattr(k, "directory", "")
            for k in options.get("kinds", ())
            if getattr(k, "is_portable", False)
        ]
        try:
            record = read_space_manifest(space)
        except ManifestInvalid as exc:
            return ExistingProjectProbe(
                state=KnownExistingProjectStates.INVALID,
                definitions=count_definitions(space, directories),
                issue=Issue(
                    severity="warning",
                    code=ErrorCodes.PROJECT_MANIFEST_INVALID,
                    message="프로젝트 설정 파일을 읽을 수 없습니다",
                    details={"reason": exc.reason},
                ),
            )
        if record is None:
            return None
        return ExistingProjectProbe(
            state=KnownExistingProjectStates.FOUND,
            id=record.manifest.id,
            name=record.manifest.name,
            description=record.manifest.description or None,
            definitions=count_definitions(space, directories),
        )

    # ------------------------------------------------------------ 찾아보기

    def roots(self) -> list[FolderRoot]:
        """탐색 시작 위치(설치자 값이 있으면 그것)."""
        if self._roots:
            return [FolderRoot(kind="custom", path=p, label=p) for p in self._roots]
        return [
            FolderRoot(kind=r.kind, path=r.path, label=r.label)
            for r in default_roots(self.environ, fs=self.fs)
        ]

    def listing(self, path: str | None, *, hidden: bool = False) -> FolderListing:
        """하위 폴더 이름만(파일 없음). ``path``가 없으면 첫 시작 위치."""
        self.require_allowed()
        roots = self.roots()
        target = path or (roots[0].path if roots else None)
        if target is None:
            raise ProjectError(ErrorCodes.FOLDERS_NO_HOME, "시작 위치를 찾지 못했습니다")
        result = list_dirs(
            target, fs=self.fs, environ=self.environ, show_hidden=hidden, roots=self._roots
        )
        index = {
            folder_key(r.folder, flavor=self.fs.flavor, rules=self._rules): r.id
            for r in self._registered()
            if r.folder is not None and not r.archived
        }
        entries = [
            FolderEntry(
                name=e.name,
                path=e.path,
                hidden=e.hidden,
                link=e.link,
                locked=e.locked,
                project_id=index.get(folder_key(e.path, flavor=self.fs.flavor, rules=self._rules)),
            )
            for e in result.entries
        ]
        return FolderListing(
            path=result.path,
            parent=result.parent,
            entries=entries,
            roots=roots,
            truncated=result.truncated,
            timed_out=result.timed_out,
            hidden_count=result.hidden_count,
        )


class FolderPicker:
    """네이티브 폴더 선택 창(한 번에 하나).

    Args:
        settings: ``folder_dialog`` 설정.
        runner: 명령 실행기(실제 ``SubprocessRunner``, 테스트는 가짜).
        providers: 코드 제공자(entry point).
        loopback: 서버가 루프백에 묶였나.
        platform: 서버 플랫폼(``sys.platform``).
        which: 실행 파일 찾기(``shutil.which``).
        environ: 환경(디스플레이 판정·명령 환경).
        fs: 파일 시스템(고른 경로 정규화).
        check: 고른 경로 확인(등록부 포함).
    """

    def __init__(
        self,
        *,
        settings: FolderDialogSettings,
        runner: CommandRunner,
        providers: Sequence[FolderDialogProvider],
        loopback: Callable[[], bool],
        platform: str,
        which: Callable[[str], str | None],
        environ: Mapping[str, str],
        fs: FileSystem,
        check: Callable[[str], FolderCheck],
    ) -> None:
        self._settings = settings
        self._runner = runner
        self._providers = list(providers)
        self._loopback = loopback
        self._platform = platform
        self._which = which
        self._environ = dict(environ)
        self._fs = fs
        self._check = check
        self._busy = threading.Lock()
        self._specs: tuple[DialogSpec, ...] | None = None

    def _dialog_specs(self) -> tuple[DialogSpec, ...]:
        if self._specs is None:
            self._specs = load_dialog_specs(
                self._settings.providers,
                include_defaults=self._settings.include_default_providers,
            )
        return self._specs

    def _select(self) -> tuple[FolderDialogProvider | DialogSpec | None, str | None]:
        """(쓸 제공자, 못 쓰는 이유)."""
        if self._settings.mode == "off":
            return None, "off"
        for provider in self._providers:
            try:
                if provider.available(self._environ):
                    return provider, None
            except Exception:
                _log.exception("폴더 선택 창 제공자 판정 실패: %s", getattr(provider, "id", "?"))
        availability = probe_dialogs(
            self._dialog_specs(), platform=self._platform, which=self._which, environ=self._environ
        )
        if availability.selected is not None:
            return availability.selected, None
        return None, availability.reason or "no_provider"

    def capabilities(self, *, browse: bool) -> FolderCapabilities:
        """쓸 수 있는 폴더 고르기 방법."""
        if not self._loopback():
            return FolderCapabilities(browse=browse, native_dialog=False, reason="remote")
        chosen, reason = self._select()
        if chosen is None:
            return FolderCapabilities(browse=browse, native_dialog=False, reason=reason)
        return FolderCapabilities(browse=browse, native_dialog=True, provider=chosen.id)

    def pick(self, request: FolderPickRequest, cancel: threading.Event) -> FolderPickResult:
        """선택 창을 띄우고 고를 때까지 기다린다(스레드에서 부른다).

        Raises:
            ProjectError: 서버가 루프백이 아니다(403 ``folders.remote_disabled``).
        """
        if not self._loopback():
            raise ProjectError(
                ErrorCodes.FOLDERS_REMOTE_DISABLED,
                "서버가 로컬 주소에 묶여 있지 않아 폴더 선택 창을 열 수 없습니다",
            )
        chosen, _ = self._select()
        if chosen is None:
            return FolderPickResult(status=KnownFolderPickStatuses.UNAVAILABLE)
        if not self._busy.acquire(blocking=False):
            return FolderPickResult(status=KnownFolderPickStatuses.BUSY, provider=chosen.id)
        try:
            return self._run(chosen, request, cancel)
        finally:
            self._busy.release()

    def _run(
        self,
        chosen: FolderDialogProvider | DialogSpec,
        request: FolderPickRequest,
        cancel: threading.Event,
    ) -> FolderPickResult:
        timeout = self._settings.timeout_seconds
        if isinstance(chosen, DialogSpec):
            result = run_dialog(
                chosen,
                runner=self._runner,
                initial=request.initial,
                title=request.title,
                timeout=timeout,
                cancel=cancel,
                fs=self._fs,
                environ=self._environ,
            )
            if result.status == KnownFolderPickStatuses.PICKED and result.path is not None:
                return FolderPickResult(
                    status=result.status,
                    path=result.path,
                    check=self._check(result.path),
                    provider=chosen.id,
                )
            return FolderPickResult(status=result.status, provider=chosen.id)
        try:
            path = chosen.pick(
                initial=request.initial, title=request.title, timeout=timeout, cancel=cancel
            )
        except TimeoutError:
            return FolderPickResult(status=KnownFolderPickStatuses.TIMEOUT, provider=chosen.id)
        except Exception:
            _log.exception("폴더 선택 창 제공자 실패: %s", chosen.id)
            return FolderPickResult(status=KnownFolderPickStatuses.FAILED, provider=chosen.id)
        if not path:
            return FolderPickResult(status=KnownFolderPickStatuses.CANCELLED, provider=chosen.id)
        check = self._check(path)
        return FolderPickResult(
            status=KnownFolderPickStatuses.PICKED,
            path=check.path or path,
            check=check,
            provider=chosen.id,
        )


__all__ = [
    "FOLDER_DIALOGS_GROUP",
    "FolderDialogProvider",
    "FolderPicker",
    "FolderService",
    "count_definitions",
    "load_dialog_providers",
]
