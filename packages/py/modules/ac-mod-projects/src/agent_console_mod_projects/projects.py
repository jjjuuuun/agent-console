"""프로젝트 등록·조회·수정·등록 해제(design §PI.2·§PI.4.6·§PI.8·§PI.16). FastAPI를 모른다.

- 등록부(앱) = 폴더·보관·라벨, 매니페스트(폴더) = 이름·설명·프로젝트 층·속성(K33-1).
- 등록 = 폴더 확인 → 겹침 검사(K33-2) → ``init_space``(매니페스트·``.gitignore``는 없을 때만, 있으면
  채택, 깨졌으면 아무것도 쓰지 않음 — K33-35) → 등록부 쓰기.
- ``ProjectView`` 상태는 폴더 상태만 읽어 계산하고 시간 상한 안에서 끝낸다(느린 드라이브).
- 옛 등록부(이름·설정이 등록부에 있음)는 읽을 때 그 값을 쓰고, 첫 저장 때 매니페스트로 옮긴다
  (K33-9 — 시작 때 고쳐 쓰지 않음).
"""

from __future__ import annotations

import concurrent.futures
import copy
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_console_contracts import (
    IGNORED_PROJECT_KEYS,
    ErrorCodes,
    Issue,
    KnownIssueCodes,
    KnownProjectRecordsStates,
    KnownProjectStatuses,
    KnownRecordsUnavailableReasons,
    ManifestResetRequest,
    ManifestResetResult,
    Project,
    ProjectCreate,
    ProjectFolderUnavailableDetails,
    ProjectManifest,
    ProjectRecordsUnavailableDetails,
    ProjectRegistration,
    ProjectUpdate,
    ProjectView,
    VersionConflictDetails,
)
from agent_console_local_folders import FileSystem, FolderError, check_folder
from agent_console_project_space import (
    ConfigReadonly,
    ManifestInvalid,
    ManifestRecord,
    ProjectSpace,
    SpaceError,
    append_gitignore,
    init_space,
    missing_gitignore_lines,
    open_space,
    read_manifest,
    reset_manifest,
    write_manifest,
)
from agent_console_projects import (
    MANIFEST_KEYS,
    PathRules,
    ProjectFolderSet,
    RegisteredFolder,
    combined_version,
    conflict_details,
    conflict_error_code,
    folder_conflicts,
    ignored_key_issues,
    initial_manifest,
    merge_project,
    project_folders,
    project_status,
    registered_folders,
    registry_conflicts,
    resolve_folder,
    suggest_project_id,
)
from agent_console_store import (
    AlreadyExists,
    RecordsSpaces,
    RecordsState,
    StoredDefinition,
    VersionConflict,
    is_network_fs,
)

from .errors import ProjectError
from .repository import ProjectRepository
from .spaces import ProjectSpaceCache

type SpaceOptionsFactory = Callable[[], Mapping[str, Any]]

_UNAVAILABLE = KnownProjectRecordsStates.UNAVAILABLE
_REASONS = KnownRecordsUnavailableReasons


@dataclass
class _Probe:
    """폴더를 읽어 얻은 상태(시간 상한 안에서 계산)."""

    status: str
    detail: str | None = None
    manifest: ManifestRecord | None = None
    config_writable: bool = False
    issues: list[Issue] = field(default_factory=list)
    records: RecordsState | None = None


class ProjectManager:
    """프로젝트 동작 묶음. ``projects.lookup``·``projects.folders`` 구현이기도 하다.

    Args:
        repository: 등록부.
        fs: 폴더 상태 읽기(``ac-local-folders`` ``FileSystem``).
        spaces: 열린 공간 캐시(등록부가 바뀌면 그 id를 비운다).
        space_options: 공간을 열 때 옵션(종류·구성 폴더 이름·비밀 규칙 등).
        base_dir: 옛 상대 경로의 기준(설정 파일 폴더).
        rules: 경로 비교 규칙.
        records: 기록 공간 포트(없으면 None — ``link_disabled``).
        records_prefix: 기록 공간 이름 접두.
        status_timeout: 상태 계산 시간 상한(초).
        environ: ``~`` 풀이용 환경.
        clock: 보관 시각(epoch 초).
        working_directory: (deprecated) ``ProjectFolderSet.current``용 비교 폴더.
        config_dir: 구성 폴더 이름(``ProjectView.config_dir``).
    """

    def __init__(
        self,
        repository: ProjectRepository,
        *,
        fs: FileSystem,
        spaces: ProjectSpaceCache,
        space_options: SpaceOptionsFactory,
        base_dir: Path,
        rules: PathRules | None = None,
        records: Callable[[], RecordsSpaces | None] = lambda: None,
        records_prefix: str = "project:",
        status_timeout: float = 2.0,
        environ: Mapping[str, str] | None = None,
        clock: Callable[[], float] = time.time,
        working_directory: Path | None = None,
        config_dir: str | None = None,
    ) -> None:
        self.repository = repository
        self.fs = fs
        self.spaces = spaces
        self._options = space_options
        self.base_dir = base_dir
        self.rules = rules
        self._records = records
        self._prefix = records_prefix
        self._timeout = status_timeout
        self.environ: Mapping[str, str] = dict(environ or {})
        self._clock = clock
        self._working_directory = working_directory
        self.config_dir = config_dir
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="project-status"
        )

    def close(self) -> None:
        """상태 계산 스레드를 정리한다(기다리지 않음)."""
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------ 공통

    def resolve(self, registration: ProjectRegistration | Mapping[str, Any]) -> str | None:
        """등록부 폴더 → 정규화한 절대 경로(옛 상대 경로는 ``base_dir`` 기준). 없으면 None."""
        raw = (
            registration.folder
            if isinstance(registration, ProjectRegistration)
            else registration.get("folder") or registration.get("working_directory")
        )
        return resolve_folder(
            raw, base_dir=str(self.base_dir), flavor=self.fs.flavor, environ=self.environ
        )

    def folder_of(self, project_id: str) -> str | None:
        """등록 id → 폴더(``projects.spaces`` 해석기). 모르는 id는 ``LookupError``."""
        stored = self.repository.find(project_id)
        if stored is None:
            raise LookupError(project_id)
        return self.resolve(stored.document)

    def registered(self) -> list[RegisteredFolder]:
        """등록 폴더 목록(겹침 검사용, 상대 경로는 절대화)."""
        return registered_folders(
            self.repository.registrations(), base_dir=str(self.base_dir), flavor=self.fs.flavor
        )

    def _open(self, folder: str) -> ProjectSpace:
        return open_space(folder, **self._options())

    def _read(self, folder: str | None) -> tuple[ProjectSpace | None, ManifestRecord | None]:
        """폴더의 공간·매니페스트(폴더가 없으면 (None, None)). 깨진 매니페스트는 예외."""
        if folder is None or not Path(folder).is_dir():
            return None, None
        space = self._open(folder)
        return space, read_manifest(space)

    def _records_state(self, project_id: str, writable: bool) -> RecordsState:
        port = self._records()
        if port is None:
            return RecordsState(state=_UNAVAILABLE, reason=_REASONS.LINK_DISABLED)
        try:
            return port.state(self._prefix + project_id)
        except Exception:
            return RecordsState(state=_UNAVAILABLE, reason=_REASONS.CORRUPT)

    # ------------------------------------------------------------ 상태

    def _probe(self, project_id: str, folder: str | None, conflicts: Mapping[str, Any]) -> _Probe:
        result = project_status(
            RegisteredFolder(project_id, folder), fs=self.fs, conflicts=conflicts
        )
        probe = _Probe(status=result.status, detail=result.detail)
        if result.status == KnownProjectStatuses.READY and folder is not None:
            try:
                space = self._open(folder)
            except SpaceError as exc:
                probe.status = KnownProjectStatuses.NO_ACCESS
                probe.detail = type(exc).__name__
                space = None
            if space is not None:
                probe.config_writable = space.config_writable
                try:
                    probe.manifest = read_manifest(space)
                except ManifestInvalid as exc:
                    probe.status = KnownProjectStatuses.MANIFEST_INVALID
                    probe.detail = exc.reason
                probe.issues.extend(self._space_issues(project_id, space))
        probe.records = self._records_state(project_id, probe.config_writable)
        return probe

    def _space_issues(self, project_id: str, space: ProjectSpace) -> list[Issue]:
        out: list[Issue] = []
        if is_network_fs(space.folder):
            out.append(
                Issue(
                    severity="info",
                    code=KnownIssueCodes.PROJECT_NETWORK_FS,
                    message=(
                        "네트워크 드라이브라 두 앱이 같은 기록·메모리를 동시에 쓰면 잠금이 "
                        "보장되지 않습니다"
                    ),
                    details={
                        "project_id": project_id,
                        "files": [space.layout.records_file, space.layout.memory_file],
                    },
                )
            )
        if space.config_writable:
            try:
                exists = space.files.read_bytes(space.gitignore_path) is not None
                lines = missing_gitignore_lines(space) if exists else []
            except OSError:
                lines = []
            if lines:
                out.append(
                    Issue(
                        severity="info",
                        code=KnownIssueCodes.PROJECT_GITIGNORE_OUTDATED,
                        message="git 제외 목록(.gitignore)에 새 줄이 빠져 있습니다",
                        details={"project_id": project_id, "lines": lines},
                    )
                )
        return out

    def _probe_bounded(
        self, project_id: str, folder: str | None, conflicts: Mapping[str, Any]
    ) -> _Probe:
        future = self._pool.submit(self._probe, project_id, folder, conflicts)
        try:
            return future.result(timeout=self._timeout)
        except concurrent.futures.TimeoutError:
            return _Probe(
                status=KnownProjectStatuses.NO_ACCESS,
                detail="timeout",
                records=RecordsState(state=_UNAVAILABLE, reason=_REASONS.BUSY),
            )

    def _view(self, stored: StoredDefinition, conflicts: Mapping[str, Any]) -> ProjectView:
        folder = self.resolve(stored.document)
        probe = self._probe_bounded(stored.id, folder, conflicts)
        doc = dict(stored.document)
        if folder is not None:
            doc["folder"] = folder
            doc.pop("working_directory", None)
        record = probe.manifest
        try:
            project = merge_project(doc, record.manifest if record else None, flavor=self.fs.flavor)
        except ValueError:
            project = merge_project(
                {k: v for k, v in doc.items() if k not in MANIFEST_KEYS},
                None,
                flavor=self.fs.flavor,
            )
        state = probe.records or RecordsState(state=_UNAVAILABLE, reason=_REASONS.LINK_DISABLED)
        records_writable = bool(state.writable and probe.config_writable)
        records_issue: Issue | None = None
        if not records_writable:
            reason = state.reason or (
                _REASONS.FOLDER_MISSING
                if probe.status != KnownProjectStatuses.READY
                else _REASONS.READONLY
            )
            records_issue = Issue(
                severity="info",
                code=KnownIssueCodes.PROJECT_RECORDS_UNAVAILABLE,
                message="이 프로젝트의 대화·실행 기록을 쓸 수 없습니다",
                details=ProjectRecordsUnavailableDetails(
                    project_id=stored.id,
                    reason=reason,
                    backup_path=str(state.backup_path) if state.backup_path else None,
                ).model_dump(mode="json", exclude_none=True),
            )
        records_state = state.state
        return ProjectView(
            project=project,
            status=probe.status,
            status_detail=probe.detail,
            version_hash=combined_version(stored.version_hash, record.version if record else None),
            config_writable=probe.config_writable,
            manifest_id=record.manifest.id if record else None,
            kinds=[getattr(k, "name", str(k)) for k in self._portable()],
            issues=[*ignored_key_issues(stored.document), *probe.issues],
            config_dir=self.config_dir,
            records_state=records_state,
            records_writable=records_writable,
            records_issue=records_issue,
        )

    def _portable(self) -> list[Any]:
        kinds = self._options().get("kinds", ())
        return [k for k in kinds if getattr(k, "is_portable", False)]

    def _conflicts(self) -> Mapping[str, Any]:
        return registry_conflicts(
            self.repository.registrations(),
            base_dir=str(self.base_dir),
            flavor=self.fs.flavor,
            rules=self.rules,
        )

    def list_views(self) -> list[ProjectView]:
        """모든 등록(보관 포함, id 순)과 상태."""
        conflicts = self._conflicts()
        return [self._view(s, conflicts) for s in self.repository.documents()]

    def get_view(self, project_id: str) -> ProjectView:
        """한 프로젝트와 상태. 없으면 ``NotFound``."""
        stored = self.repository.get(project_id)
        stored.model(ProjectRegistration)
        return self._view(stored, self._conflicts())

    # ------------------------------------------------------------ projects.lookup

    def get_project(self, project_id: str) -> Project | None:
        """합친 프로젝트(매니페스트를 읽을 수 없으면 옛 등록부 값). 없으면 None."""
        stored = self.repository.find(project_id)
        if stored is None:
            return None
        return self._merged(stored)

    def list_projects(self) -> list[Project]:
        """모든 프로젝트(id 순, 보관 포함)."""
        return [self._merged(s) for s in self.repository.documents()]

    def _merged(self, stored: StoredDefinition) -> Project:
        folder = self.resolve(stored.document)
        doc = dict(stored.document)
        if folder is not None:
            doc["folder"] = folder
            doc.pop("working_directory", None)
        manifest: ProjectManifest | None = None
        try:
            _, record = self._read(folder)
            manifest = record.manifest if record else None
        except (SpaceError, OSError):
            manifest = None
        return merge_project(doc, manifest, flavor=self.fs.flavor)

    def folder_set(self) -> ProjectFolderSet:
        """``projects.folders`` 값(보관·폴더 없음 제외)."""
        return project_folders(
            self.repository.registrations(),
            base_dir=self.base_dir,
            working_directory=self._working_directory,
            flavor=self.fs.flavor,
            rules=self.rules,
        )

    # ------------------------------------------------------------ 등록

    def normalize_folder(self, raw: str) -> tuple[str, bool]:
        """입력 경로 → (저장할 경로, 폴더가 있나). 경로가 아니면 ``FolderError``."""
        check = check_folder(raw, fs=self.fs, environ=self.environ)
        if check.path is None:
            raise FolderError(check.problem or "invalid_path", "쓸 수 있는 경로가 아닙니다")
        return check.path, bool(check.exists and check.is_dir)

    def _reject_conflicts(self, folder: str, *, exclude: str | None, live_only: bool) -> None:
        found = folder_conflicts(
            self.registered(),
            folder,
            exclude_project_id=exclude,
            flavor=self.fs.flavor,
            rules=self.rules,
        )
        if live_only:
            found = [c for c in found if not c.archived]
        if found:
            first = found[0]
            raise ProjectError(
                conflict_error_code(first),
                "이미 등록된 프로젝트 폴더와 같거나 겹칩니다",
                conflict_details(first).model_dump(mode="json", exclude_none=True),
            )

    def create(self, body: ProjectCreate) -> ProjectView:
        """폴더를 프로젝트로 등록한다(201).

        Raises:
            FolderError: 경로가 아니다(상대 경로·다른 OS 경로 등).
            ProjectError: 같은 폴더(``project.folder_taken``, 보관이면 ``details.archived``)·겹침.
            AlreadyExists: 요청 id가 이미 있다.
            SecretRejected: 만들 매니페스트에 평문 비밀이 있다.
        """
        folder, exists = self.normalize_folder(body.folder)
        self._reject_conflicts(folder, exclude=None, live_only=False)
        taken = self.repository.ids()
        existing: ManifestRecord | None = None
        if exists:
            try:
                existing = read_manifest(self._open(folder))
            except ManifestInvalid:
                existing = None
        if body.id is not None:
            if body.id.casefold() in {t.casefold() for t in taken}:
                raise AlreadyExists(f"project/{body.id}")
            project_id = body.id
        else:
            project_id = suggest_project_id(
                folder,
                manifest_id=existing.manifest.id if existing else None,
                taken_ids=taken,
                flavor=self.fs.flavor,
                rules=self.rules,
            )
        reg_doc: dict[str, Any] = {"kind": "project", "id": project_id, "folder": folder}
        if body.labels:
            reg_doc["labels"] = list(body.labels)
        if exists:
            fields = body.model_fields_set
            manifest = initial_manifest(
                reg_doc,
                manifest_id=project_id,
                name=body.name,
                description=body.description if "description" in fields else None,
                flavor=self.fs.flavor,
            )
            values = manifest.model_dump(mode="json", exclude_unset=True)
            if body.settings is not None:
                values["settings"] = body.settings.model_dump(mode="json", exclude_unset=True)
            if body.attributes:
                values["attributes"] = copy.deepcopy(body.attributes)
            init_space(folder, manifest=ProjectManifest.model_validate(values), **self._options())
        stored = self.repository.create(reg_doc)
        self.spaces.close(project_id)
        return self._view(stored, self._conflicts())

    def _current(
        self, project_id: str
    ) -> tuple[StoredDefinition, str | None, ManifestRecord | None, str]:
        stored = self.repository.get(project_id)
        stored.model(ProjectRegistration)
        folder = self.resolve(stored.document)
        try:
            _, record = self._read(folder)
        except (ManifestInvalid, SpaceError, OSError):
            record = None
        version = combined_version(stored.version_hash, record.version if record else None)
        return stored, folder, record, version

    @staticmethod
    def _check_version(expected: str | None, current: str) -> None:
        if expected is not None and expected != current:
            raise VersionConflict(VersionConflictDetails(current_version_hash=current))

    @staticmethod
    def _clean_registration(document: Mapping[str, Any]) -> dict[str, Any]:
        doc = copy.deepcopy(dict(document))
        legacy = doc.pop("working_directory", None)
        if not doc.get("folder") and legacy:
            doc["folder"] = legacy
        for key in IGNORED_PROJECT_KEYS:
            doc.pop(key, None)
        return doc

    def update(
        self, project_id: str, body: ProjectUpdate, *, expected_version: str | None = None
    ) -> ProjectView:
        """고치기(요청에 쓴 필드만). 이름·설명·설정·속성은 매니페스트, 폴더·보관·라벨은 등록부.

        Raises:
            NotFound: 등록이 없다.
            VersionConflict: ``expected_version``(합친 해시)이 지금과 다르다(412).
            ProjectError: 폴더 겹침(409), 폴더 없음(409 ``project.folder_missing``).
            ManifestInvalid, ConfigReadonly: 매니페스트를 쓸 수 없다(409).
        """
        stored, folder, record, version = self._current(project_id)
        self._check_version(expected_version, version)
        fields = body.model_fields_set
        reg_doc = self._clean_registration(stored.document)
        changed = reg_doc != stored.document
        if "folder" in fields and body.folder is not None:
            new_folder, exists = self.normalize_folder(body.folder)
            self._reject_conflicts(new_folder, exclude=project_id, live_only=False)
            if exists:
                merged = self._merged(stored)
                init_space(
                    new_folder,
                    manifest=ProjectManifest.model_validate(
                        {
                            "id": record.manifest.id if record else project_id,
                            "name": merged.name,
                            "description": merged.description,
                            **(
                                {"settings": merged.settings.model_dump(mode="json")}
                                if merged.settings is not None
                                else {}
                            ),
                            "attributes": merged.attributes,
                        }
                    ),
                    **self._options(),
                )
            reg_doc["folder"] = new_folder
            folder = new_folder
            changed = True
            try:
                _, record = self._read(folder)
            except (ManifestInvalid, SpaceError, OSError):
                record = None
        if "archived" in fields and body.archived is not None:
            was = bool(stored.document.get("archived"))
            if was and not body.archived and folder is not None:
                self._reject_conflicts(folder, exclude=project_id, live_only=True)
            if body.archived != was:
                reg_doc["archived"] = body.archived
                if body.archived:
                    reg_doc["archived_at"] = self._clock()
                else:
                    reg_doc.pop("archived_at", None)
                changed = True
        if "labels" in fields and body.labels is not None:
            reg_doc["labels"] = list(body.labels)
            changed = True
        manifest_changes = self._manifest_changes(body)
        if manifest_changes:
            migrated = self._write_manifest(project_id, folder, reg_doc, manifest_changes)
            if migrated:
                for key in MANIFEST_KEYS:
                    reg_doc.pop(key, None)
                changed = True
        if changed and reg_doc != stored.document:
            self.repository.save(reg_doc, expected_version=stored.version_hash)
        self.spaces.close(project_id)
        return self.get_view(project_id)

    @staticmethod
    def _manifest_changes(body: ProjectUpdate) -> dict[str, Any]:
        """매니페스트에 쓸 바뀐 값(``settings``의 None = 지우기, 다른 None은 무시)."""
        out: dict[str, Any] = {}
        for name in ("name", "description", "settings", "attributes"):
            if name not in body.model_fields_set:
                continue
            value = getattr(body, name)
            if value is None and name != "settings":
                continue
            if value is not None and hasattr(value, "model_dump"):
                value = value.model_dump(mode="json", exclude_unset=True)
            out[name] = copy.deepcopy(value)
        return out

    def _write_manifest(
        self,
        project_id: str,
        folder: str | None,
        reg_doc: Mapping[str, Any],
        changes: Mapping[str, Any],
    ) -> bool:
        """매니페스트에 바뀐 값을 쓴다. 매니페스트가 없어 새로 만들었으면(옛 등록 옮김) True."""
        if folder is None or not Path(folder).is_dir():
            raise ProjectError(
                ErrorCodes.PROJECT_FOLDER_MISSING,
                "프로젝트 폴더가 없어 설정을 저장할 수 없습니다",
                ProjectFolderUnavailableDetails(
                    project_id=project_id,
                    status=KnownProjectStatuses.FOLDER_MISSING,
                    folder=folder,
                ).model_dump(mode="json", exclude_none=True),
            )
        space = self._open(folder)
        record = read_manifest(space)
        if not space.config_writable:
            raise ConfigReadonly("the project folder is read-only")
        if record is not None:
            base = record.manifest.model_dump(mode="json", exclude_unset=True)
        else:
            base = initial_manifest(
                reg_doc, manifest_id=project_id, flavor=self.fs.flavor
            ).model_dump(mode="json", exclude_unset=True)
        for key, value in changes.items():
            if value is None:
                base.pop(key, None)
            else:
                base[key] = value
        write_manifest(
            space,
            ProjectManifest.model_validate(base),
            expected_version=record.version if record else None,
        )
        return record is None

    def archive(self, project_id: str, *, expected_version: str | None = None) -> None:
        """등록 해제(보관). 폴더 내용·기록은 지우지 않는다(K33-4)."""
        stored, _, _, version = self._current(project_id)
        self._check_version(expected_version, version)
        if stored.document.get("archived"):
            return
        reg_doc = self._clean_registration(stored.document)
        reg_doc["archived"] = True
        reg_doc["archived_at"] = self._clock()
        self.repository.save(reg_doc, expected_version=stored.version_hash)
        self.spaces.close(project_id)

    # ------------------------------------------------------------ 매니페스트 다시 만들기·.gitignore

    def reset_manifest(self, project_id: str, body: ManifestResetRequest) -> ManifestResetResult:
        """깨진 매니페스트를 백업하고 새로 만든다(§PI.16 ③, 상태 ``manifest_invalid``일 때만).

        Raises:
            ProjectError: 매니페스트가 깨진 상태가 아니다(409 ``already_exists``).
            ConfigReadonly: 폴더에 쓸 수 없다.
        """
        view = self.get_view(project_id)
        folder = view.project.folder
        if view.status != KnownProjectStatuses.MANIFEST_INVALID or folder is None:
            raise ProjectError(
                ErrorCodes.ALREADY_EXISTS,
                "설정 파일이 깨진 상태가 아니라 다시 만들지 않습니다",
                {"project_id": project_id, "status": view.status},
            )
        space = self._open(folder)
        values: dict[str, Any] = {"id": project_id, "name": body.name}
        if body.description is not None:
            values["description"] = body.description
        backup = reset_manifest(space, ProjectManifest.model_validate(values))
        if backup is None:
            raise ProjectError(
                ErrorCodes.ALREADY_EXISTS,
                "옛 설정 파일이 없어 백업하지 않았습니다",
                {"project_id": project_id},
            )
        self.spaces.close(project_id)
        return ManifestResetResult(project=self.get_view(project_id), backup_path=str(backup))

    def append_gitignore(self, project_id: str) -> ProjectView:
        """``.gitignore``에 빠진 틀 줄만 끝에 덧붙인다(사용자가 누를 때만)."""
        view = self.get_view(project_id)
        folder = view.project.folder
        if folder is None or not Path(folder).is_dir():
            raise ProjectError(
                ErrorCodes.PROJECT_FOLDER_MISSING,
                "프로젝트 폴더가 없습니다",
                ProjectFolderUnavailableDetails(
                    project_id=project_id, status=view.status, folder=folder
                ).model_dump(mode="json", exclude_none=True),
            )
        append_gitignore(self._open(folder))
        return self.get_view(project_id)


__all__ = ["ProjectManager"]
