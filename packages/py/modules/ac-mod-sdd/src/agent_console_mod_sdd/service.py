"""스펙 서비스: 공간 고르기·사용자 설정·연동·검증 출처·비밀 검사·변경 알림을
묶는다(``sdd.service``).

``ac-sdd``의 순수 함수·저장소 위에 서버 몫만 더한다(design §6R.3 ``mod-sdd``):

- 공간: 요청의 공간 이름(``?project=``) → ``SddScope``(저장소·파일 접근·쓰기 가능·스펙 폴더). 이름이
  없으면 단독 루트(``standalone_root``). 이름이 왔는데 ``sdd.spaces``가 없으면 409
  ``sdd.spaces_unavailable``(앱 workspace에 대신 만들지 않는다).
- 문서 틀: 공간 이름이 없으면 앱 라이브러리(``definitions.store``, 공용 구성)의 틀을 읽는다.
  라이브러리가 없으면 단독 루트의 틀.
- 연동(X43)·검증 출처(X42)는 포트·플러그인에서 부를 때마다 모은다(늦게 켜진 제공자도 보인다).
- 능력(``SddCapabilities``)은 포트 유무로 계산한다(웹이 모듈 id를 몰라도 된다).

실행·프로젝트를 모른다. 공간 이름은 불투명 문자열이다.
"""

from __future__ import annotations

import asyncio
import posixpath
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from agent_console_conditions import ConditionOperator
from agent_console_contracts import ErrorCodes, Issue, LabelDisplay, SpaceRef
from agent_console_contracts.sdd import (
    AutomationState,
    KnownTaskLinkKinds,
    ParsedTask,
    RunProfile,
    SddCapabilities,
    SddChanged,
    SddInfo,
    SddLimits,
    SddSettings,
    SpecIssue,
    SpecRules,
    SpecView,
    TaskLink,
    VerificationResult,
)
from agent_console_sdd import (
    AutomationControl,
    LoadedSpec,
    LocalSpecFiles,
    ProfileChecker,
    SpecContext,
    SpecFiles,
    TaskIntegration,
    VerificationContext,
    VerificationSource,
)
from agent_console_secret_rules import SecretRules, default_rules
from agent_console_store import DefinitionKind, DefinitionStore

from .cache import CachedSpecRepository, ParseCache
from .config import parse_sdd_settings, section_of
from .errors import SpaceError
from .ports import SddSpace, SddSpaces
from .secrets import SCAN_OFF, scan_text
from .settings import SddModuleSettings


def _first(path: str) -> str:
    return path.strip("/").split("/", 1)[0]


@dataclass(frozen=True)
class SddScope:
    """요청 하나가 쓰는 공간.

    Attributes:
        name: 공간 이름(단독 루트면 None).
        repository: 그 공간의 스펙 저장소(파싱 캐시 포함).
        files: 폴더 안만 읽고 쓰는 파일 접근(없으면 가져오기·내보내기 꺼짐).
        writable: 쓸 수 있나(``SddInfo.writable``).
        spec_root: 스펙 폴더(폴더 기준 상대 경로, ``SddInfo.spec_root``).
        reserved: 가져오기·내보내기에서 쓸 수 없는 첫 구성요소(저장소 폴더).
        max_doc_bytes: 문서 본문 한도(모르면 None).
    """

    name: str | None
    repository: CachedSpecRepository
    files: SpecFiles | None
    writable: bool
    spec_root: str
    reserved: tuple[str, ...]
    max_doc_bytes: int | None = None


@dataclass
class SddPorts:
    """서비스가 부를 때마다 읽는 바깥 의존(포트 등). 모두 선택이다."""

    spaces: Callable[[], SddSpaces | None] = lambda: None
    library: Callable[[], DefinitionStore | None] = lambda: None
    integrations: Callable[[], Sequence[TaskIntegration]] = lambda: ()
    sources: Callable[[], Sequence[VerificationSource]] = lambda: ()
    plugin_sources: Callable[[], Sequence[VerificationSource]] = lambda: ()
    workspace_settings: Callable[[], Any] = lambda: None
    secret_rules: Callable[[], SecretRules | None] = lambda: None
    operators: Callable[[], Mapping[str, ConditionOperator]] | None = None
    publish: Callable[[SddChanged], None] = lambda _payload: None
    loopback: Callable[[], bool] = lambda: True


class SddService:
    """스펙 서비스(포트 ``sdd.service`` 구현).

    Args:
        options: 설치자 설정.
        standalone: 단독 루트 정의 저장소(스펙·틀 종류 등록).
        kinds: (스펙 종류, 문서 틀 종류).
        ports: 바깥 의존.
        standalone_max_bytes: 단독 저장소 문서 본문 한도(보고용).
    """

    def __init__(
        self,
        options: SddModuleSettings,
        *,
        standalone: DefinitionStore,
        kinds: tuple[DefinitionKind, DefinitionKind],
        ports: SddPorts | None = None,
        standalone_max_bytes: int | None = None,
    ) -> None:
        self.options = options
        self.standalone = standalone
        self.spec_kind, self.template_kind = kinds
        self.ports = ports or SddPorts()
        self.cache = ParseCache(options.parse_cache_entries)
        self._standalone_max = standalone_max_bytes

    # ------------------------------------------------------------ 설정·규칙
    def settings_and_issues(self) -> tuple[SddSettings, list[Issue]]:
        """지금 사용자 설정 ``sdd``(깨진 부분은 뺀 값)와 형식 문제."""
        try:
            raw = section_of(self.ports.workspace_settings())
        except Exception:  # 설정을 못 읽어도 스펙 화면은 동작한다
            raw = None
        return parse_sdd_settings(raw)

    def settings(self) -> SddSettings:
        return self.settings_and_issues()[0]

    def warnings(self) -> list[Issue]:
        """``server.warnings``: 사용자 설정 형식 문제."""
        return self.settings_and_issues()[1]

    def rules(self) -> SecretRules:
        """비밀 의심 규칙(포트 → 없으면 기본)."""
        try:
            found = self.ports.secret_rules()
        except Exception:
            found = None
        return found if isinstance(found, SecretRules) else default_rules()

    def operators(self) -> Mapping[str, ConditionOperator] | None:
        return self.ports.operators() if self.ports.operators is not None else None

    def secret_mode(self) -> str:
        return self.settings().secret_scan

    def secret_findings(self, text: str, *, document: str | None = None) -> list[Issue]:
        """글의 비밀 의심 위치(설정이 ``off``면 빈 목록, 값 없음)."""
        if self.secret_mode() == SCAN_OFF:
            return []
        return list(scan_text(self.rules(), text, document=document))

    def document_findings(self, text: str, *, document: str) -> list[SpecIssue]:
        if self.secret_mode() == SCAN_OFF:
            return []
        return scan_text(self.rules(), text, document=document)

    def label_key(self, name: str) -> str:
        """실행 라벨 키(설치자 접두 + 이름)."""
        return self.options.run_label_prefix + name

    def label_display(self) -> list[LabelDisplay]:
        """실행 라벨 표시 규칙(접두 적용, 형식이 틀린 항목은 뺀다)."""
        out: list[LabelDisplay] = []
        for rule in self.options.label_rules():
            try:
                out.append(LabelDisplay.model_validate(rule))
            except ValidationError:
                continue
        return out

    # ------------------------------------------------------------ 공간
    def _repository(
        self, store: DefinitionStore, *, space_key: str, directory: str, templates: DefinitionStore
    ) -> CachedSpecRepository:
        self._ensure_kinds(store)
        return CachedSpecRepository(
            store,
            spec_kind=self.spec_kind.name,
            template_kind=self.template_kind.name,
            operators=self.operators(),
            settings=self.settings,
            directory=directory,
            max_tasks=self.options.max_tasks,
            timeout_ms=float(self.options.parse_timeout_ms),
            template_store=templates,
            cache=self.cache,
            space_key=space_key,
        )

    def _ensure_kinds(self, store: DefinitionStore) -> None:
        known = set(store.kinds())
        register = getattr(store, "register_kind", None)
        for kind in (self.spec_kind, self.template_kind):
            if kind.name not in known and callable(register):
                register(kind)

    def library(self) -> DefinitionStore | None:
        """앱 라이브러리 저장소(문서 틀 종류가 있을 때만)."""
        try:
            store = self.ports.library()
        except Exception:
            return None
        if store is None or self.template_kind.name not in store.kinds():
            return None
        return store

    def scope(self, space: str | None) -> SddScope:
        """공간 이름 → 공간(None·빈 값 = 단독 루트).

        Raises:
            SpaceError: 제공자가 없다(``sdd.spaces_unavailable``)·모르는
            공간(``project.not_found``)·
                열 수 없다(제공자 예외의 ``code``).
        """
        if not space:
            return self._standalone_scope()
        provider = self.ports.spaces()
        if provider is None:
            raise SpaceError(
                ErrorCodes.SDD_SPACES_UNAVAILABLE,
                space,
                "프로젝트 연동이 꺼져 있어 이 프로젝트의 스펙을 열 수 없습니다.",
            )
        try:
            opened: SddSpace = provider.open(space)
        except LookupError:
            raise SpaceError(
                ErrorCodes.PROJECT_NOT_FOUND, space, "프로젝트를 찾을 수 없습니다."
            ) from None
        except Exception as exc:
            code = getattr(exc, "code", None)
            raise SpaceError(
                str(code) if isinstance(code, str) and code else ErrorCodes.INTERNAL,
                space,
                "프로젝트 공간을 열 수 없습니다.",
            ) from exc
        store_dir = str(getattr(opened, "config_dir", "") or "").strip("/")
        spec_root = (
            posixpath.join(store_dir, self.options.spec_dir)
            if store_dir
            else (self.options.spec_dir.strip("/"))
        )
        reserved = (
            (_first(store_dir),)
            if store_dir
            else (_first(self.options.spec_dir), _first(self.options.template_dir))
        )
        repo = self._repository(
            opened.store, space_key=space, directory=spec_root, templates=opened.store
        )
        limit = getattr(opened, "max_content_bytes", None)
        return SddScope(
            name=space,
            repository=repo,
            files=opened.files,
            writable=bool(opened.config_writable),
            spec_root=spec_root,
            reserved=reserved,
            max_doc_bytes=limit if isinstance(limit, int) else None,
        )

    def _standalone_scope(self) -> SddScope:
        templates = self.library() or self.standalone
        root = getattr(self.standalone, "root", None)
        files: SpecFiles | None = None
        if root is not None:
            files = LocalSpecFiles(root)
        spec_root = self.options.spec_dir.strip("/")
        repo = self._repository(
            self.standalone, space_key="", directory=spec_root, templates=templates
        )
        return SddScope(
            name=None,
            repository=repo,
            files=files,
            writable=True,
            spec_root=spec_root,
            reserved=(_first(self.options.spec_dir), _first(self.options.template_dir)),
            max_doc_bytes=self._standalone_max,
        )

    def template_target(self, ref: SpaceRef | None) -> tuple[DefinitionStore, SpaceRef]:
        """틀로 저장 대상(None·라이브러리 = 앱 라이브러리, 프로젝트 = 그 공간 저장소).

        Raises:
            SpaceError: 라이브러리가 없다(``feature_unavailable``)·공간을 열 수 없다.
        """
        if ref is None or ref.project_id is None:
            library = self.library()
            if library is None:
                raise SpaceError(
                    ErrorCodes.FEATURE_UNAVAILABLE,
                    "",
                    "공용 구성(정의 기능)이 꺼져 있어 라이브러리에 틀을 저장할 수 없습니다.",
                )
            return library, SpaceRef()
        scope = self.scope(ref.project_id)
        return scope.repository.store, SpaceRef(project_id=ref.project_id)

    # ------------------------------------------------------------ 연동·검증
    def integrations(self) -> list[TaskIntegration]:
        try:
            return list(self.ports.integrations())
        except Exception:
            return []

    def automation(self) -> AutomationControl | None:
        for item in self.integrations():
            if isinstance(item, AutomationControl):
                return item
        return None

    def verification_sources(self) -> list[tuple[VerificationSource, Mapping[str, Any]]]:
        """쓸 검증 출처와 옵션: 포트 출처(설정에서 끈 것 제외) + 설정에서 켠 플러그인 출처."""
        configured = {s.id: s for s in self.settings().verification_sources}
        out: list[tuple[VerificationSource, Mapping[str, Any]]] = []
        seen: set[str] = set()
        try:
            ported = list(self.ports.sources())
        except Exception:
            ported = []
        for source in ported:
            setting = configured.get(source.id)
            if source.id in seen or (setting is not None and not setting.enabled):
                continue
            seen.add(source.id)
            out.append((source, dict(setting.options) if setting else {}))
        try:
            plugins = list(self.ports.plugin_sources())
        except Exception:
            plugins = []
        for source in plugins:
            setting = configured.get(source.id)
            if source.id in seen or setting is None or not setting.enabled:
                continue
            seen.add(source.id)
            out.append((source, dict(setting.options)))
        return out

    def capabilities(self, scope: SddScope) -> SddCapabilities:
        integrations = self.integrations()
        runs = any(
            KnownTaskLinkKinds.RUN in tuple(getattr(i, "link_kinds", ()) or ())
            for i in integrations
        )
        return SddCapabilities(
            runs=runs,
            templates=self.library() is not None,
            verification=bool(self.verification_sources()),
            automation=self.automation() is not None,
            import_export=scope.files is not None,
        )

    def info(self, scope: SddScope) -> SddInfo:
        return SddInfo(
            spec_root=scope.spec_root,
            writable=scope.writable,
            limits=SddLimits(
                max_bulk_start=self.options.max_bulk_start,
                max_tasks=self.options.max_tasks,
                max_doc_bytes=scope.max_doc_bytes,
            ),
            capabilities=self.capabilities(scope),
            label_display=self.label_display(),
        )

    def context(self, scope: SddScope, loaded: LoadedSpec) -> SpecContext:
        return SpecContext(
            space=scope.name,
            spec=loaded.spec,
            index=loaded.index,
            syntax=loaded.syntax,
            version_hash=loaded.stored.version_hash,
            directory=scope.repository.spec_directory(loaded.spec.id),
            files=scope.files,
        )

    async def links(self, ctx: SpecContext, tasks: Sequence[ParsedTask]) -> list[TaskLink]:
        """모든 연동의 작업 연결(연동 하나가 실패해도 나머지는 쓴다)."""
        found: list[TaskLink] = []
        for item in self.integrations():
            try:
                found.extend(await item.links(ctx, tasks))
            except Exception:
                continue
        return found

    async def results(self, ctx: SpecContext) -> list[VerificationResult]:
        found: list[VerificationResult] = []
        for source, options in self.verification_sources():
            try:
                found.extend(await source.collect(VerificationContext(spec=ctx, options=options)))
            except Exception:
                continue
        return found

    async def profile_issues(
        self, ctx: SpecContext, profiles: Sequence[RunProfile]
    ) -> list[SpecIssue]:
        """``ProfileChecker`` 연동의 실행 프로필 검사(없으면 검사하지 않는다, design §6R.4)."""
        out: list[SpecIssue] = []
        for item in self.integrations():
            if not isinstance(item, ProfileChecker):
                continue
            for profile in profiles:
                try:
                    out.extend(await item.check_profile(ctx, profile))
                except Exception:
                    continue
        return out

    async def automation_state(self, ctx: SpecContext) -> AutomationState | None:
        control = self.automation()
        if control is None:
            return None
        try:
            return control.automation_state(ctx)
        except Exception:
            return None

    async def view(self, scope: SddScope, spec_id: str) -> SpecView:
        """스펙 보기 + 작업 연결·프로필 검사·자동 진행 상태."""
        repo = scope.repository
        view = repo.view(spec_id)
        loaded = repo.load(spec_id)
        ctx = self.context(scope, loaded)
        tasks = await self.with_links(ctx, list(loaded.index.tasks))
        issues = list(view.issues)
        issues.extend(await self.profile_issues(ctx, view.spec.rules.run_profiles or ()))
        return view.model_copy(
            update={
                "index": loaded.index.model_copy(update={"tasks": tasks}),
                "issues": issues,
                "automation_state": await self.automation_state(ctx),
            }
        )

    def task_issues(self, ctx: SpecContext, tasks: Sequence[ParsedTask]) -> list[SpecIssue]:
        """연동의 선택 메서드 ``task_issues(ctx, tasks) -> list[SpecIssue]``가 낸 작업 이슈.

        예: 실행 결과를 상태에 반영하지 못함 ``sdd.status_not_applied``(6R.15). X43 프로토콜 밖
        선택 능력이다(``link_kinds``와 같은 방식)."""
        found: list[SpecIssue] = []
        for item in self.integrations():
            method = getattr(item, "task_issues", None)
            if not callable(method):
                continue
            try:
                found.extend(i for i in method(ctx, tasks) if isinstance(i, SpecIssue))
            except Exception:
                continue
        return found

    async def with_links(self, ctx: SpecContext, tasks: list[ParsedTask]) -> list[ParsedTask]:
        if not tasks:
            return tasks
        links = await self.links(ctx, tasks)
        extra = self.task_issues(ctx, tasks)
        if not links and not extra:
            return tasks
        by_key: dict[str, list[TaskLink]] = {}
        for link in links:
            if link.task_key:
                by_key.setdefault(link.task_key, []).append(link)
        issues_by_key: dict[str, list[SpecIssue]] = {}
        for issue in extra:
            if issue.task_key:
                issues_by_key.setdefault(issue.task_key, []).append(issue)
        out: list[ParsedTask] = []
        for t in tasks:
            update: dict[str, Any] = {}
            if t.key in by_key:
                update["links"] = [*t.links, *by_key[t.key]]
            if t.key in issues_by_key:
                update["issues"] = [*t.issues, *issues_by_key[t.key]]
            out.append(t.model_copy(update=update) if update else t)
        return out

    def rules_profiles(self, raw: Mapping[str, Any]) -> list[RunProfile]:
        try:
            return list(SpecRules.model_validate(raw).run_profiles or ())
        except ValidationError:
            return []

    # ------------------------------------------------------------ 알림
    def notify(
        self,
        space: str | None,
        spec_id: str,
        *,
        version_hash: str | None = None,
        automation: bool = False,
        deleted: bool = False,
    ) -> None:
        """WS ``sdd.changed``를 낸다(본문 없음)."""
        try:
            ref = SpaceRef(project_id=space) if space else SpaceRef()
        except ValidationError:
            ref = SpaceRef()
        self.ports.publish(
            SddChanged(
                space=ref,
                spec_id=spec_id,
                version_hash=version_hash,
                automation=automation,
                deleted=deleted,
            )
        )

    def on_saved(self, item: Any) -> None:
        """정의 저장 알림(``definitions.saved``) → 스펙 종류면 ``sdd.changed``."""
        if getattr(item, "kind", None) != self.spec_kind.name:
            return
        spec_id = getattr(item, "id", None)
        if not isinstance(spec_id, str) or not spec_id:
            return
        space = getattr(item, "space", None)
        self.notify(
            space if isinstance(space, str) else None,
            spec_id,
            version_hash=getattr(item, "version_hash", None),
        )


async def gather_actions(
    integrations: Sequence[TaskIntegration], ctx: SpecContext, task: ParsedTask
) -> list[Any]:
    """모든 연동의 작업 동작(연동 하나가 실패해도 나머지는 쓴다)."""
    found: list[Any] = []
    results = await asyncio.gather(
        *(i.actions(ctx, task) for i in integrations), return_exceptions=True
    )
    for item in results:
        if isinstance(item, BaseException):
            continue
        found.extend(item)
    return found


__all__ = ["SddPorts", "SddScope", "SddService", "gather_actions"]
