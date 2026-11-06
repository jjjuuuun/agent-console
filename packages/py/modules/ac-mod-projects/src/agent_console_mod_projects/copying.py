"""공간 사이 복사(design §PI.4.2 K33-6·K33-17)와 옛 프로젝트 전용 정의 정리 계획(§PI.8).

공간 = 라이브러리(``definitions.store``, ``SpaceRef.project_id`` null) 또는 프로젝트 폴더의
사본 공간.
계획·판정 규칙은 순수 패키지 ``ac-projects``(``copy_plan``·``apply_decisions``·``apply_renames``)가
하고 여기서는 저장소를 읽고 쓴다.

- 사본에는 원본 id·버전·시각을 쓰지 않는다(정의 파일·매니페스트 어디에도). 대상 버전 기록 메시지에만
  ``가져옴: <공간> <종류>/<id> @<버전 앞 7자>``를 남긴다.
- 옛 범위 필드(``project``)는 사본에서 뺀다.
- 리소스 본문 파일(여러 파일·단일 본문)도 함께 복사한다.
- 쓰기 전에 대상 공간의 비밀 규칙으로 모든 문서를 검사하고, 하나라도 걸리면 아무것도 쓰지 않고
  422(``SecretRejected``, 위치만).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_console_contracts import (
    CopyApplyItemResult,
    CopyApplyRequest,
    CopyApplyResult,
    CopyItem,
    CopyKindInfo,
    CopyPlan,
    CopyPlanRequest,
    ErrorCodes,
    Issue,
    KnownCopyStatuses,
    KnownIssueCodes,
    SpaceRef,
)
from agent_console_project_space import (
    ConfigReadonly,
    SecretFinding,
    SecretRejected,
    read_manifest,
    scan_secrets,
)
from agent_console_projects import (
    LEGACY_SCOPE_FIELD,
    References,
    RewriteReferences,
    SourceDefinition,
    apply_decisions,
    apply_renames,
    copy_plan,
    legacy_items,
    renames_of,
    without_scope_field,
)
from agent_console_secret_rules import SecretRules
from agent_console_store import (
    AlreadyExists,
    DefinitionKind,
    DefinitionStore,
    NotFound,
    StoreError,
    VersionConflict,
)

from .definitions import read_definitions
from .errors import ProjectError
from .spaces import ProjectSpaceCache

type DefinitionId = tuple[str, str]

LIBRARY_LABEL = "library"
"""라이브러리 공간 표시 이름(버전 기록 메시지)."""


@dataclass(frozen=True)
class Space:
    """복사 한쪽 공간."""

    label: str
    store: DefinitionStore
    kinds: tuple[str, ...] | None
    rules: SecretRules
    writable: bool = True


class _LazySource(Mapping[DefinitionId, SourceDefinition]):
    """원본 공간 정의를 필요할 때만 읽는 매핑(키 = 지금 색인)."""

    def __init__(self, store: DefinitionStore, index: Mapping[DefinitionId, str]) -> None:
        self._store = store
        self._index = index
        self._cache: dict[DefinitionId, SourceDefinition] = {}

    def __getitem__(self, key: DefinitionId) -> SourceDefinition:
        if key not in self._index:
            raise KeyError(key)
        if key not in self._cache:
            stored = self._store.get(*key)
            name = stored.document.get("name")
            self._cache[key] = SourceDefinition(
                stored.document, stored.version_hash, name if isinstance(name, str) else ""
            )
        return self._cache[key]

    def __iter__(self) -> Iterator[DefinitionId]:
        return iter(self._index)

    def __len__(self) -> int:
        return len(self._index)


def space_index(
    store: DefinitionStore, kinds: Iterable[str] | None = None
) -> dict[DefinitionId, str]:
    """공간의 (종류, id) → 버전 해시. 읽을 수 없는 정의는 뺀다."""
    out: dict[DefinitionId, str] = {}
    allowed = set(kinds) if kinds is not None else None
    for kind in store.kinds():
        if allowed is not None and kind not in allowed:
            continue
        try:
            ids = store.list_ids(kind)
        except StoreError:
            continue
        for def_id in ids:
            try:
                out[(kind, def_id)] = store.get(kind, def_id).version_hash
            except (StoreError, ValueError):
                continue
    return out


@dataclass(frozen=True)
class Body:
    """정의의 본문(여러 파일 또는 단일 본문)."""

    files: dict[str, bytes] | None = None
    content: bytes | None = None


def read_body(store: DefinitionStore, kind: str, def_id: str) -> Body | None:
    """본문 파일을 읽는다(종류가 본문을 쓰지 않으면 None)."""
    try:
        listed = store.list_files(kind, def_id)
    except ValueError:
        listed = None
    if listed is not None:
        return Body(files={f.path: store.read_file(kind, def_id, f.path) for f in listed})
    try:
        data = store.read_content(kind, def_id)
    except ValueError:
        return None
    return Body(content=data) if data is not None else None


def write_body(
    store: DefinitionStore,
    kind: str,
    def_id: str,
    body: Body,
    *,
    version: str,
    message: str,
) -> None:
    """본문을 대상에 쓴다(여러 파일은 원본과 정확히 같게 — 대상에만 있던 파일은 지움)."""
    if body.files is not None:
        try:
            current = [f.path for f in store.list_files(kind, def_id)]
        except (ValueError, NotFound):
            current = []
        changes: dict[str, bytes | None] = {p: None for p in current if p not in body.files}
        changes.update(body.files)
        if changes:
            store.write_files(kind, def_id, changes, expected_version=version, message=message)
    elif body.content is not None:
        store.write_content(kind, def_id, body.content, expected_version=version, message=message)


def combine_rewriters(rewriters: Sequence[RewriteReferences]) -> RewriteReferences | None:
    """여러 참조 고치기를 차례로 적용하는 하나(없으면 None)."""
    if not rewriters:
        return None

    def rewrite(
        kind: str, document: Mapping[str, Any], renames: Mapping[DefinitionId, str]
    ) -> Mapping[str, Any]:
        out: Mapping[str, Any] = document
        for item in rewriters:
            out = item(kind, out, renames)
        return out

    return rewrite


def _keep(
    _kind: str, document: Mapping[str, Any], _renames: Mapping[DefinitionId, str]
) -> Mapping[str, Any]:
    return document


class CopyService:
    """공간 사이 복사.

    Args:
        library: 라이브러리 정의 저장소(없으면 None — 라이브러리가 낀 복사는 ``unavailable()``).
        spaces: 프로젝트 공간 캐시.
        known: 등록 id가 있는지(없으면 404 ``project.not_found``).
        references: 참조 추출(없으면 None).
        rewriters: 참조 고치기(없으면 빈 목록).
        library_rules: 라이브러리로 쓸 때의 비밀 규칙.
        unavailable: 라이브러리 저장소가 없을 때 던질 예외를 만든다.
        messages: 문구 바꾸기.
        kind_info: 아는 정의 종류(기본 종류 + 종류 기여 X44, ``library``·``portable`` 값). 복사
            대화상자 메타데이터(``kinds``·``items``)가 쓴다. 없으면 두 목록이 빈다.
    """

    def __init__(
        self,
        *,
        library: Callable[[], DefinitionStore | None],
        spaces: ProjectSpaceCache,
        known: Callable[[str], bool],
        references: Callable[[], References | None],
        rewriters: Callable[[], Sequence[RewriteReferences]],
        library_rules: Callable[[], SecretRules],
        unavailable: Callable[[], Exception],
        messages: Mapping[str, str] | None = None,
        kind_info: Callable[[], Sequence[DefinitionKind]] = lambda: (),
    ) -> None:
        self._library = library
        self._kind_info = kind_info
        self._spaces = spaces
        self._known = known
        self._references = references
        self._rewriters = rewriters
        self._library_rules = library_rules
        self._unavailable = unavailable
        self._messages = dict(messages or {})

    # ------------------------------------------------------------ 공간

    def space(self, ref: SpaceRef, *, target: bool) -> Space:
        """``SpaceRef`` → 공간. 대상이면 매니페스트가 읽혀야 하고(409) 쓸 수 있어야 한다(409)."""
        if ref.project_id is None:
            store = self._library()
            if store is None:
                raise self._unavailable()
            return Space(LIBRARY_LABEL, store, None, self._library_rules())
        if not self._known(ref.project_id):
            raise ProjectError(
                ErrorCodes.PROJECT_NOT_FOUND,
                f"프로젝트를 찾을 수 없습니다: {ref.project_id}",
                {"project_id": ref.project_id},
            )
        space = self._spaces.open(ref.project_id)
        if target:
            read_manifest(space)  # 깨졌으면 409 project.manifest_invalid
        return Space(
            f"project:{ref.project_id}",
            space.definitions,
            space.portable_kinds,
            space.secret_rules,
            space.config_writable,
        )

    # ------------------------------------------------------------ 종류·목록(복사 대화상자)

    def kinds(self, ref: SpaceRef) -> list[CopyKindInfo]:
        """그 공간에 있는 정의 종류 중 복사에 쓸 수 있는 것(싱글턴·모르는 종류 제외, 저장소 순서).

        ``library``·``portable``은 종류 값 그대로라 화면이 방향(공용 → 프로젝트는 ``portable``,
        프로젝트 → 공용은 ``library``)으로 거른다. 종류 이름을 모르는 화면도 같은 목록을 쓴다.
        """
        space = self.space(ref, target=False)
        info = {k.name: k for k in self._kind_info()}
        present = space.kinds if space.kinds is not None else tuple(space.store.kinds())
        out: list[CopyKindInfo] = []
        for name in present:
            kind = info.get(name)
            if kind is None or kind.is_singleton:
                continue
            out.append(CopyKindInfo(kind=name, library=kind.library, portable=kind.is_portable))
        return out

    def items(self, ref: SpaceRef, kind: str | None = None) -> list[CopyItem]:
        """그 공간의 정의 목록(본문 없음, 종류 순 → 저장소 요약 순). ``kind``를 주면 그 종류만.

        Raises:
            ProjectError: ``kind``가 이 공간의 복사 종류가 아니다(404 ``not_found``).
        """
        space = self.space(ref, target=False)
        names = [k.kind for k in self.kinds(ref)]
        if kind is not None:
            if kind not in names:
                raise ProjectError(
                    ErrorCodes.NOT_FOUND,
                    f"이 공간에서 복사할 수 없는 종류입니다: {kind}",
                    {"kind": kind},
                )
            names = [kind]
        out: list[CopyItem] = []
        for name in names:
            try:
                summaries = space.store.summaries(name)
            except StoreError:
                continue
            out.extend(
                CopyItem(
                    kind=name,
                    id=s.id,
                    name=s.name,
                    description=s.description,
                    saved_at=s.saved_at,
                )
                for s in summaries
            )
        return out

    def _pair(self, source: SpaceRef, target: SpaceRef) -> tuple[Space, Space]:
        if source.project_id == target.project_id:
            raise ProjectError(ErrorCodes.BAD_REQUEST, "원본과 대상 공간이 같습니다")
        return self.space(source, target=False), self.space(target, target=True)

    # ------------------------------------------------------------ 계획

    def plan(self, request: CopyPlanRequest) -> CopyPlan:
        """복사 계획(아무것도 쓰지 않음)."""
        src, dst = self._pair(request.source, request.target)
        return self._plan(src, dst, request.items, request.include_references)

    def _plan(
        self,
        src: Space,
        dst: Space,
        items: Iterable[Any],
        include_references: bool,
    ) -> CopyPlan:
        source_index = space_index(src.store, src.kinds)
        target_index = space_index(dst.store, dst.kinds)
        return copy_plan(
            items,
            _LazySource(src.store, source_index),
            target_index,
            references=self._references(),
            include_references=include_references,
            kinds=dst.kinds if dst.kinds is not None else dst.store.kinds(),
            messages=self._messages,
        )

    def legacy_plan(self, project_id: str) -> CopyPlan:
        """옛 프로젝트 전용 정의(라이브러리의 ``project`` 필드 = 이 id) → 이 프로젝트 공간 계획."""
        src, dst = self._pair(SpaceRef(project_id=None), SpaceRef(project_id=project_id))
        keys = legacy_items(read_definitions(src.store), project_id)
        return self._plan(src, dst, keys, True)

    # ------------------------------------------------------------ 적용

    def apply(self, request: CopyApplyRequest) -> CopyApplyResult:
        """고른 동작을 적용한다(항목별 결과, 계획 뒤에 바뀐 항목만 ``conflict``).

        Raises:
            ConfigReadonly: 대상 프로젝트 폴더에 쓸 수 없다(409).
            SecretRejected: 쓸 문서에 평문 비밀이 있다(422, 아무것도 쓰지 않음).
        """
        src, dst = self._pair(request.source, request.target)
        source_index = space_index(src.store, src.kinds)
        target_index = space_index(dst.store, dst.kinds)
        decisions = apply_decisions(
            request.items,
            source_index=source_index,
            target_index=target_index,
            messages=self._messages,
        )
        writes = [d for d in decisions if d.writes]
        if writes and not dst.writable:
            raise ConfigReadonly("the target project folder is read-only")
        docs = {d.key: without_scope_field(src.store.get(d.kind, d.id).document) for d in writes}
        renames = renames_of(decisions)
        rewrite = combine_rewriters(list(self._rewriters()))
        out_docs = apply_renames(docs, renames, rewrite_references=rewrite or _keep)
        self._scan(dst, out_docs.values())
        target_of = {d.key: (d.kind, d.target_id) for d in writes}
        results: list[CopyApplyItemResult] = []
        applied: list[DefinitionId] = []
        for decision in decisions:
            result = decision.result()
            if decision.writes:
                key = target_of[decision.key]
                try:
                    self._write(
                        src,
                        dst,
                        decision.kind,
                        decision.id,
                        key[1],
                        out_docs[key],
                        overwrite=decision.status == KnownCopyStatuses.OVERWRITTEN,
                        source_version=source_index[decision.key],
                    )
                except (VersionConflict, AlreadyExists):
                    result = result.model_copy(
                        update={
                            "status": KnownCopyStatuses.CONFLICT,
                            "issue": Issue(
                                severity="warning",
                                code=KnownIssueCodes.PROJECT_COPY_CONFLICT,
                                message=(
                                    f"{decision.kind}/{decision.id}이(가) 쓰는 중에 바뀌었습니다"
                                ),
                                details={
                                    "kind": decision.kind,
                                    "id": decision.id,
                                    "reason": "target_changed",
                                },
                            ),
                        }
                    )
                else:
                    applied.append(decision.key)
                    if decision.key in renames and rewrite is None:
                        result = result.model_copy(
                            update={
                                "issue": Issue(
                                    severity="info",
                                    code=KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE,
                                    message=(
                                        "참조를 고칠 수 없어 이 묶음 안의 참조는 옛 id 그대로입니다"
                                    ),
                                    details={"kind": decision.kind, "id": decision.id},
                                )
                            }
                        )
            elif decision.status == KnownCopyStatuses.REUSED:
                applied.append(decision.key)
            results.append(result)
        self._after_source(src, request, applied, source_index)
        return CopyApplyResult(items=results)

    def _scan(self, dst: Space, documents: Iterable[Mapping[str, Any]]) -> None:
        findings: list[SecretFinding] = []
        for doc in documents:
            prefix = f"/{doc.get('kind', '')}/{doc.get('id', '')}"
            findings += [
                SecretFinding(prefix + f.path, f.reason) for f in scan_secrets(dst.rules, doc)
            ]
        if findings:
            raise SecretRejected(tuple(findings))

    @staticmethod
    def _write(
        src: Space,
        dst: Space,
        kind: str,
        source_id: str,
        target_id: str,
        document: Mapping[str, Any],
        *,
        overwrite: bool,
        source_version: str,
    ) -> None:
        message = f"가져옴: {src.label} {kind}/{source_id} @{source_version[:7]}"
        body = read_body(src.store, kind, source_id)
        if overwrite:
            current = dst.store.get(kind, target_id).version_hash
            stored = dst.store.save(kind, document, expected_version=current, message=message)
        else:
            stored = dst.store.create(kind, document, message=message)
        if body is not None:
            write_body(
                dst.store, kind, target_id, body, version=stored.version_hash, message=message
            )

    def _after_source(
        self,
        src: Space,
        request: CopyApplyRequest,
        applied: Sequence[DefinitionId],
        source_index: Mapping[DefinitionId, str],
    ) -> None:
        """원본 정리: ``remove_source``면 지우고, 아니면 이 대상을 가리키던 옛 범위 필드만
        지운다."""
        target_id = request.target.project_id
        for key in applied:
            try:
                stored = src.store.get(*key)
            except StoreError:
                continue
            if request.remove_source:
                try:
                    src.store.delete(key[0], key[1], expected_version=stored.version_hash)
                except StoreError:
                    continue
            elif (
                src.label == LIBRARY_LABEL
                and target_id is not None
                and stored.document.get(LEGACY_SCOPE_FIELD) == target_id
            ):
                try:
                    src.store.save(
                        key[0],
                        without_scope_field(stored.document),
                        expected_version=stored.version_hash,
                        message=f"project: {target_id} -> (프로젝트로 복사함)",
                    )
                except StoreError:
                    continue


__all__ = [
    "LIBRARY_LABEL",
    "Body",
    "CopyService",
    "Space",
    "combine_rewriters",
    "read_body",
    "space_index",
    "write_body",
]
