"""스펙 저장소: `ac-store` `DefinitionStore` 위의 스펙·문서 틀 작업(design §6R.1.2·§6R.1.4).

새 저장소를 두지 않는다. 스펙·틀은 정의 종류(여러 파일 본문)라 버전 기록·`If-Match`·쓰기 전 검사
(비밀)·외부 변경 감지를 정의 저장소가 그대로 한다. 이 클래스는 SDD 규칙만 더한다.

- 만들기(틀 복사·빈 스펙·가져온 문서), 규칙·문서 목록 저장, 삭제
- 문서 본문 읽기·쓰기(본문 `If-Match` = 파일 sha256, 만들기만 `create_only`, 상태 `on_edit`)
- 문서 상태 전환(`transitions`의 `from`·`to`·`by`, 관문 `document_state`)
- 작업 고치기(최신 원문 재파싱 → 작업 키로 찾기 → 머리 줄 해시 비교 → 줄 하나 고치기, 관문
  `task_status`, 정의 저장 충돌이면 한 번 다시 시도)
- 보기·목록 요약, 틀 목록·틀로 저장

동기 API다(정의 저장소와 같음). 공간 고르기·비밀 검사 설정·WS 알림은 서버 모듈 몫이다.
"""

from __future__ import annotations

import copy
import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import ValidationError

from agent_console_conditions import ConditionOperator, builtin_operators
from agent_console_contracts import VersionConflictDetails
from agent_console_contracts.sdd import (
    DocumentStateInfo,
    EffectiveSyntax,
    KnownTransitionActors,
    ParsedTask,
    RunProfileSummary,
    SaveAsTemplateResult,
    SaveAsTemplateStatus,
    SddSettings,
    SddTaskChangedDetails,
    SpecDefinition,
    SpecDocument,
    SpecDocumentSummary,
    SpecIndex,
    SpecSummary,
    SpecSyntax,
    SpecTemplate,
    SpecTemplateSummary,
    SpecView,
    StageRef,
    TaskPatchResult,
    TemplateConflictPolicy,
)
from agent_console_store import (
    DefinitionCorrupt,
    DefinitionStore,
    NotFound,
    StoredDefinition,
    VersionConflict,
)

from ._check import check_rules
from ._compiled import CompiledSyntax, compile_syntax, line_hash, split_lines
from ._errors import (
    DocumentChangedError,
    DocumentExistsError,
    DocumentMissingError,
    SpecNotFoundError,
    TemplateExistsError,
    TransitionDeniedError,
)
from ._gates import gate_context, require_gates
from ._ids import slug_id, unique_id
from ._parse import find_task, parse_spec
from ._patch import TaskChangedError, patch_task
from ._syntax import document_state_infos, effective_syntax
from ._templates import blank_documents, instantiate, spec_to_template

__all__ = [
    "DocumentContent",
    "LoadedSpec",
    "SpecRepository",
    "StoredSpec",
]

_T = TypeVar("_T")
_ANY_STATE = "*"
_GATE_DOCUMENT = "document_state"
_GATE_TASK = "task_status"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class StoredSpec:
    """저장된 스펙(또는 문서 틀) 정의와 버전.

    Attributes:
        id: 정의 id.
        document: 저장된 문서 그대로(JSON 호환 dict, 모르는 키 포함).
        version_hash: 정의 버전(`If-Match`).
        saved_at: 마지막 저장 시각.
    """

    id: str
    document: dict[str, Any]
    version_hash: str
    saved_at: float | None

    @property
    def spec(self) -> SpecDefinition:
        return SpecDefinition.model_validate(self.document)

    @property
    def template(self) -> SpecTemplate:
        return SpecTemplate.model_validate(self.document)


@dataclass(frozen=True, slots=True)
class DocumentContent:
    """문서 본문 하나."""

    document_id: str
    file: str
    data: bytes
    content_hash: str

    @property
    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace")


@dataclass(frozen=True, slots=True)
class LoadedSpec:
    """읽고 파싱한 스펙 하나(보기·계획·추적·연동 맥락의 재료)."""

    stored: StoredSpec
    spec: SpecDefinition
    files: dict[str, bytes | None]
    syntax: EffectiveSyntax
    compiled: CompiledSyntax
    index: SpecIndex


def _stored(found: StoredDefinition) -> StoredSpec:
    return StoredSpec(
        id=found.id,
        document=found.document,
        version_hash=found.version_hash,
        saved_at=found.saved_at,
    )


class SpecRepository:
    """스펙·문서 틀 저장소(정의 저장소 하나 = 공간 하나).

    Args:
        store: 정의 저장소. `spec_kind`·`template_kind` 종류가 등록돼 있어야
        한다(`definition_kinds`).
        spec_kind: 스펙 정의 종류 이름(호출자 데이터).
        template_kind: 문서 틀 정의 종류 이름(호출자 데이터).
        operators: 조건 연산자(관문·규칙 검사). None이면 `ac-conditions` 기본 연산자.
        settings: 사용자 설정 섹션 `sdd`(값 또는 부를 때마다 읽는 함수). None이면 기본값.
        default_syntax: 패키지 기본 문법 대신 쓸 것(테스트·다른 기본 데이터).
        blank_documents: 틀 없이 만든 스펙의 문서 목록. None이면 패키지 기본 데이터.
        directory: 스펙 문서 폴더의 앞부분(프로젝트 폴더 기준 상대 경로, 예: 공간의 스펙 폴더).
            스펙 하나의 폴더 = `<directory>/<스펙 id>`.
        template_store: 문서 틀을 읽고 쓰는 저장소(`template_kind` 등록). None이면 `store`.
            스펙과 틀이 다른 저장소에 있을 때 준다(예: 단독 공간 스펙 + 앱 라이브러리 틀).
        max_tasks: 파싱 작업 수 상한. timeout_ms: 문서 하나 파싱 시간 상한.
        clock: 상태 바꾼 기록 시각(초).
    """

    def __init__(
        self,
        store: DefinitionStore,
        *,
        spec_kind: str,
        template_kind: str,
        operators: Mapping[str, ConditionOperator] | None = None,
        settings: SddSettings | Callable[[], SddSettings] | None = None,
        default_syntax: SpecSyntax | None = None,
        blank_documents: Sequence[SpecDocument] | None = None,
        directory: str = "",
        max_tasks: int | None = None,
        timeout_ms: float | None = None,
        clock: Callable[[], float] = time.time,
        template_store: DefinitionStore | None = None,
    ) -> None:
        self.store = store
        self.template_store: DefinitionStore = (
            template_store if template_store is not None else store
        )
        self.spec_kind = spec_kind
        self.template_kind = template_kind
        self.operators: Mapping[str, ConditionOperator] = (
            operators
            if operators is not None
            else {op.descriptor.id: op for op in builtin_operators()}
        )
        self._settings = settings
        self._default_syntax = default_syntax
        self._blank = list(blank_documents) if blank_documents is not None else None
        self.directory = directory.strip("/")
        self._max_tasks = max_tasks
        self._timeout_ms = timeout_ms
        self._clock = clock

    # ------------------------------------------------------------------ 공용
    def settings(self) -> SddSettings:
        """지금 사용자 설정(주입한 값 또는 함수 결과)."""
        value = self._settings() if callable(self._settings) else self._settings
        return value or SddSettings()

    def syntax(self, spec: SpecDefinition | SpecTemplate | None) -> EffectiveSyntax:
        """스펙 규칙 → 사용자 설정 → 패키지 기본으로 합친 유효 문법."""
        return effective_syntax(
            spec.rules if spec is not None else None,
            self.settings(),
            default=self._default_syntax,
        )

    def spec_directory(self, spec_id: str) -> str:
        """스펙 문서 폴더(프로젝트 폴더 기준 상대 경로)."""
        return f"{self.directory}/{spec_id}" if self.directory else spec_id

    def _store_for(self, kind: str) -> DefinitionStore:
        return self.template_store if kind == self.template_kind else self.store

    def _get(self, kind: str, id: str, what: str) -> StoredSpec:
        try:
            return _stored(self._store_for(kind).get(kind, id))
        except NotFound:
            raise SpecNotFoundError(what, id) from None

    def _files(
        self, kind: str, id: str, documents: Sequence[SpecDocument]
    ) -> dict[str, bytes | None]:
        out: dict[str, bytes | None] = {}
        for doc in documents:
            try:
                out[doc.file] = self.store.read_file(kind, id, doc.file)
            except NotFound:
                out[doc.file] = None
        return out

    def _all_files(self, kind: str, id: str) -> dict[str, bytes]:
        store = self._store_for(kind)
        return {f.path: store.read_file(kind, id, f.path) for f in store.list_files(kind, id)}

    @staticmethod
    def _retry(fn: Callable[[], _T]) -> _T:
        """정의 저장 충돌(`VersionConflict`)이면 처음부터 한 번 다시 한다(design §6R.1.4)."""
        try:
            return fn()
        except VersionConflict:
            return fn()

    # ------------------------------------------------------------------ 스펙 읽기
    def list_ids(self) -> list[str]:
        return self.store.list_ids(self.spec_kind)

    def get(self, spec_id: str) -> StoredSpec:
        """스펙 정의. 없으면 `SpecNotFoundError`."""
        return self._get(self.spec_kind, spec_id, "spec")

    def read_files(self, spec_id: str) -> dict[str, bytes | None]:
        """스펙 문서 본문(문서 `file` → 내용, 없으면 None)."""
        stored = self.get(spec_id)
        return self._files(self.spec_kind, spec_id, stored.spec.documents)

    def load(self, spec_id: str) -> LoadedSpec:
        """스펙을 읽고 파싱한다."""
        stored = self.get(spec_id)
        spec = stored.spec
        files = self._files(self.spec_kind, spec_id, spec.documents)
        syntax = self.syntax(spec)
        compiled = compile_syntax(syntax)
        index = parse_spec(
            spec, files, compiled, max_tasks=self._max_tasks, timeout_ms=self._timeout_ms
        )
        return LoadedSpec(stored, spec, files, syntax, compiled, index)

    def view(self, spec_id: str, *, graphs: Sequence[str] | None = None) -> SpecView:
        """스펙 보기(`SpecView`: 정의·파싱 결과·풀린 라벨·규칙 검사 이슈). 자동 진행 상태는 서버가
        연동에서 채운다."""
        loaded = self.load(spec_id)
        spec = loaded.spec
        return SpecView(
            spec=spec,
            index=loaded.index,
            version_hash=loaded.stored.version_hash,
            directory=self.spec_directory(spec_id),
            task_statuses=loaded.syntax.statuses,
            document_states=document_state_infos(spec.rules.document_states),
            issues=check_rules(
                spec.rules,
                operators=self.operators,
                documents=spec.documents,
                settings=self.settings(),
                graphs=graphs,
                default_syntax=self._default_syntax,
            ),
        )

    def summaries(self) -> list[SpecSummary]:
        """스펙 목록 요약(읽을 수 없는 정의는 건너뛴다)."""
        out: list[SpecSummary] = []
        for spec_id in self.list_ids():
            try:
                loaded = self.load(spec_id)
            except (SpecNotFoundError, DefinitionCorrupt, ValidationError):
                continue
            out.append(self._summary(loaded))
        return out

    def _summary(self, loaded: LoadedSpec) -> SpecSummary:
        spec = loaded.spec
        infos = {s.id: s for s in document_state_infos(spec.rules.document_states)}
        docs: list[SpecDocumentSummary] = []
        for d in spec.documents:
            info: DocumentStateInfo | None = infos.get(d.state) if d.state else None
            docs.append(
                SpecDocumentSummary(
                    id=d.id,
                    title=d.title,
                    state=d.state,
                    state_label=info.label if info else d.state,
                    tone=info.tone if info else None,
                )
            )
        counts: dict[str, int] = {}
        done = loaded.compiled.done_ids
        for t in loaded.index.tasks:
            counts[t.status] = counts.get(t.status, 0) + 1
        stage = next((s for s in loaded.index.stages if s.done < s.total), None)
        return SpecSummary(
            id=spec.id,
            name=spec.name,
            description=spec.description,
            directory=self.spec_directory(spec.id),
            documents=docs,
            task_counts=counts,
            tasks_total=len(loaded.index.tasks),
            tasks_done=sum(1 for t in loaded.index.tasks if t.status in done),
            ready=sum(1 for t in loaded.index.tasks if t.ready),
            current_stage=StageRef(id=stage.id, title=stage.title) if stage else None,
            updated_at=loaded.stored.saved_at,
            issues=sum(1 for i in loaded.index.issues if i.severity == "error"),
        )

    # ------------------------------------------------------------------ 스펙 쓰기
    def _new_id(self, kind: str, name: str, id: str | None) -> str:
        if id is not None:
            return id
        return unique_id(name, self.store.list_ids(kind), fallback=slug_id(kind, fallback="item"))

    def _create(
        self, kind: str, document: dict[str, Any], files: Mapping[str, bytes], message: str
    ) -> StoredSpec:
        created = self.store.create(kind, document, message=message)
        if not files:
            return _stored(created)
        try:
            saved = self.store.write_files(
                kind,
                created.id,
                dict(files),
                expected_version=created.version_hash,
                message=message,
            )
        except BaseException:
            self.store.delete(kind, created.id)
            raise
        return _stored(saved)

    def create(
        self,
        *,
        name: str,
        id: str | None = None,
        template: str | None = None,
        documents: Sequence[SpecDocument] | None = None,
        contents: Mapping[str, bytes] | None = None,
        description: str | None = None,
        message: str | None = None,
    ) -> StoredSpec:
        """새 스펙을 만든다.

        - `template`(같은 공간의 문서 틀 id): 틀의 문서·규칙·본문을 복사(`instantiate`). 스펙 파일에
          틀 id를 쓰지 않고 버전 기록 메시지에만 `틀에서 만듦: <종류>/<id> @<버전 앞 7자>`.
        - `documents`(+ `contents`): 그 문서로(폴더에서 가져오기). 규칙은 비운다.
        - 둘 다 없으면 빈 스펙(`blank_documents`, 규칙 비움 — 사용자 설정·패키지 기본 문법을 따름).

        Raises:
            SpecNotFoundError: 틀이 없다. AlreadyExists: 같은 id가 있다(`ac-store`).
        """
        spec_id = self._new_id(self.spec_kind, name, id)
        if template is not None:
            tpl = self._get(self.template_kind, template, "template")
            draft = instantiate(
                tpl.document,
                self._all_files(self.template_kind, template),
                kind=self.spec_kind,
                id=spec_id,
                name=name,
                description=description,
            )
            note = (
                message or f"틀에서 만듦: {self.template_kind}/{template} @{tpl.version_hash[:7]}"
            )
            return self._create(self.spec_kind, draft.document, draft.files, note)
        docs = list(documents) if documents is not None else (self._blank or blank_documents())
        raw: dict[str, Any] = {
            "documents": [d.model_dump(mode="json", by_alias=True, exclude_none=True) for d in docs]
        }
        draft = instantiate(
            raw,
            dict(contents or {}),
            kind=self.spec_kind,
            id=spec_id,
            name=name,
            description=description,
        )
        return self._create(self.spec_kind, draft.document, draft.files, message or "만듦")

    def save(
        self,
        document: SpecDefinition | Mapping[str, Any],
        *,
        expected_version: str,
        message: str = "",
    ) -> StoredSpec:
        """스펙 정의(규칙·문서 목록)를 저장한다(`If-Match`)."""
        raw = (
            document.model_dump(mode="json", by_alias=True, exclude_none=True)
            if isinstance(document, SpecDefinition)
            else dict(document)
        )
        raw.setdefault("kind", self.spec_kind)
        return _stored(
            self.store.save(self.spec_kind, raw, expected_version=expected_version, message=message)
        )

    def delete(self, spec_id: str, *, expected_version: str | None = None) -> None:
        """스펙 정의와 본문 파일을 지운다(실행 기록은 그대로)."""
        try:
            self.store.delete(self.spec_kind, spec_id, expected_version=expected_version)
        except NotFound:
            raise SpecNotFoundError("spec", spec_id) from None

    # ------------------------------------------------------------------ 문서 본문
    def _document(self, spec: SpecDefinition, doc_id: str) -> SpecDocument:
        for d in spec.documents:
            if d.id == doc_id:
                return d
        raise SpecNotFoundError("document", doc_id)

    def read_document(self, spec_id: str, doc_id: str) -> DocumentContent:
        """문서 본문. 파일이 없으면 `DocumentMissingError`(읽기로 파일을 만들지 않는다, Q4)."""
        doc = self._document(self.get(spec_id).spec, doc_id)
        try:
            data = self.store.read_file(self.spec_kind, spec_id, doc.file)
        except NotFound:
            raise DocumentMissingError(doc.id, doc.file) from None
        return DocumentContent(doc.id, doc.file, data, _sha(data))

    def write_document(
        self,
        spec_id: str,
        doc_id: str,
        data: bytes | str,
        *,
        expected_hash: str | None = None,
        create_only: bool = False,
        by: str = KnownTransitionActors.HUMAN,
        message: str = "문서 수정",
    ) -> tuple[StoredSpec, DocumentContent]:
        """문서 본문을 쓴다.

        Args:
            expected_hash: 화면이 읽은 본문 sha256(`If-Match`). 다르면 `DocumentChangedError`.
                None이면 검사하지 않는다.
            create_only: 파일이 없을 때만 만든다(`If-None-Match: *`). 있으면 `DocumentExistsError`.
            by: 상태 `on_edit`로 상태를 되돌릴 때 기록할 쪽.

        문서의 지금 상태에 `on_edit: {to}`가 있고 본문이 바뀌었으면 그 상태로 바꾼다(전환
        규칙·관문을
        보지 않는 데이터 규칙). 작업 고치기(`patch_task`)는 `on_edit`를 적용하지 않는다.

        Returns:
            (저장 뒤 정의, 저장한 본문).
        """
        payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)

        def attempt() -> tuple[StoredSpec, DocumentContent]:
            stored = self.get(spec_id)
            spec = stored.spec
            doc = self._document(spec, doc_id)
            try:
                current: bytes | None = self.store.read_file(self.spec_kind, spec_id, doc.file)
            except NotFound:
                current = None
            if create_only and current is not None:
                raise DocumentExistsError(doc.id, _sha(current))
            if expected_hash is not None and (current is None or _sha(current) != expected_hash):
                raise DocumentChangedError(doc.id, None if current is None else _sha(current))
            saved = _stored(
                self.store.write_files(
                    self.spec_kind,
                    spec_id,
                    {doc.file: payload},
                    expected_version=stored.version_hash,
                    message=message,
                )
            )
            if current != payload:
                saved = self._apply_on_edit(saved, doc_id, by)
            return saved, DocumentContent(doc.id, doc.file, payload, _sha(payload))

        return self._retry(attempt)

    def _apply_on_edit(self, stored: StoredSpec, doc_id: str, by: str) -> StoredSpec:
        spec = stored.spec
        doc = self._document(spec, doc_id)
        state = doc.state or spec.rules.initial_document_state
        target = None
        for s in spec.rules.document_states or ():
            if s.id == state and s.on_edit is not None:
                target = s.on_edit.to
        if target is None or target == state:
            return stored
        return self._write_state(stored, doc_id, target, by=by, note=None, run_id=None)

    # ------------------------------------------------------------------ 문서 상태
    def _write_state(
        self,
        stored: StoredSpec,
        doc_id: str,
        to: str,
        *,
        by: str,
        note: str | None,
        run_id: str | None,
    ) -> StoredSpec:
        raw = copy.deepcopy(stored.document)
        change: dict[str, Any] = {"by": by, "at": self._clock()}
        if run_id is not None:
            change["run_id"] = run_id
        if note:
            change["note"] = note
        for item in raw.get("documents") or ():
            if isinstance(item, dict) and item.get("id") == doc_id:
                item["state"] = to
                item["state_changed"] = change
        return _stored(
            self.store.save(
                self.spec_kind,
                raw,
                expected_version=stored.version_hash,
                message=f"문서 상태: {doc_id} → {to} ({by})",
            )
        )

    def change_document_state(
        self,
        spec_id: str,
        doc_id: str,
        to: str,
        *,
        by: str,
        note: str | None = None,
        run_id: str | None = None,
        expected_version: str | None = None,
    ) -> StoredSpec:
        """문서 상태를 바꾼다(정의 저장 — 버전 기록이 승인 이력이 된다).

        전환 규칙: `transitions` 중 `from`이 지금 상태(없으면 `initial_document_state`)이거나
        `*`이고
        `to`가 같은 것. 없으면, 또는 있어도 `by`에 그 쪽이 없으면 `TransitionDeniedError`. 그다음
        `document_state` 관문을 평가한다(맥락 `change = {document, from, to, by}`, 막히면
        `GateBlockedError`).

        Args:
            by: 바꾸는 쪽(`KnownTransitionActors` — human·run·agent, 열린 문자열).
            expected_version: 주면 정의 버전이 같아야 한다(`VersionConflict`). 생략하면 최신에 적용
                (충돌이면 한 번 다시 시도).
        """

        def attempt() -> StoredSpec:
            stored = self.get(spec_id)
            if expected_version is not None and stored.version_hash != expected_version:
                raise VersionConflict(
                    VersionConflictDetails(
                        current_version_hash=stored.version_hash, saved_at=stored.saved_at
                    )
                )
            spec = stored.spec
            doc = self._document(spec, doc_id)
            current = doc.state or spec.rules.initial_document_state
            matches = [
                t
                for t in spec.rules.transitions or ()
                if t.to == to and (t.from_ == _ANY_STATE or t.from_ == current)
            ]
            if not any(by in t.by for t in matches):
                raise TransitionDeniedError(doc_id, current, to, by)
            require_gates(
                spec.rules,
                _GATE_DOCUMENT,
                gate_context(
                    spec, change={"document": doc_id, "from": current, "to": to, "by": by}
                ),
                operators=self.operators,
            )
            return self._write_state(stored, doc_id, to, by=by, note=note, run_id=run_id)

        if expected_version is not None:
            return attempt()
        return self._retry(attempt)

    # ------------------------------------------------------------------ 작업 고치기
    def patch_task(
        self,
        spec_id: str,
        key: str,
        *,
        expected_line_hash: str,
        status: str | None = None,
        fields: Mapping[str, str | None] | None = None,
        by: str = KnownTransitionActors.HUMAN,
        message: str | None = None,
    ) -> TaskPatchResult:
        """작업 머리 줄 하나를 고친다(K6R-5).

        최신 원문을 다시 파싱해 작업 키로 줄을 찾고, 그 줄 해시가 `expected_line_hash`와 같을 때만
        상태 표시 문자·필드를 고쳐 저장한다. 다른 줄이 바뀌었어도 이 줄이 같으면 통과한다. 상태를
        바꾸면
        먼저 `task_status` 관문을 평가한다(맥락 `task` + `change = {from, to, by}`).

        Raises:
            TaskChangedError: 그 줄이 바뀌었거나 작업이 없다(`sdd.task_changed`, 409 — `current`에
            최신
                줄).
            GateBlockedError: 관문이 막았다.
            TaskPatchError: 값이 문법에 맞지 않는다(모르는 상태 등).
        """

        def attempt() -> TaskPatchResult:
            loaded = self.load(spec_id)
            task = find_task(loaded.index, key)
            if task is None:
                raise TaskChangedError(SddTaskChangedDetails(task_key=key))
            if task.line_hash != expected_line_hash:
                raise TaskChangedError(self._changed(loaded, task))
            if status is not None:
                require_gates(
                    loaded.spec.rules,
                    _GATE_TASK,
                    gate_context(
                        loaded.spec,
                        loaded.index,
                        task=task,
                        change={"from": task.status, "to": status, "by": by},
                    ),
                    operators=self.operators,
                )
            doc = self._document(loaded.spec, task.document)
            raw = loaded.files.get(doc.file)
            text = (raw or b"").decode("utf-8", errors="replace")
            new_text = patch_task(text, task, syntax=loaded.compiled, status=status, fields=fields)
            payload = new_text.encode("utf-8")
            saved = self.store.write_files(
                self.spec_kind,
                spec_id,
                {doc.file: payload},
                expected_version=loaded.stored.version_hash,
                message=message or f"작업 {key} 고침 ({by})",
            )
            files = dict(loaded.files)
            files[doc.file] = payload
            index = parse_spec(
                loaded.spec,
                files,
                loaded.compiled,
                max_tasks=self._max_tasks,
                timeout_ms=self._timeout_ms,
            )
            updated = find_task(index, key) or task
            return TaskPatchResult(
                task=updated, version_hash=saved.version_hash, content_hash=_sha(payload)
            )

        return self._retry(attempt)

    @staticmethod
    def _changed(loaded: LoadedSpec, task: ParsedTask) -> SddTaskChangedDetails:
        doc = next((d for d in loaded.spec.documents if d.id == task.document), None)
        raw = loaded.files.get(doc.file) if doc else None
        lines = split_lines((raw or b"").decode("utf-8", errors="replace"))
        line = lines[task.line - 1].rstrip("\r\n") if 0 < task.line <= len(lines) else None
        return SddTaskChangedDetails(
            task_key=task.key,
            line_hash=task.line_hash if line is None else line_hash(line),
            line=task.line,
            text=line,
        )

    # ------------------------------------------------------------------ 문서 틀
    def template_ids(self) -> list[str]:
        return self.template_store.list_ids(self.template_kind)

    def get_template(self, template_id: str) -> StoredSpec:
        """문서 틀 정의. 없으면 `SpecNotFoundError`."""
        return self._get(self.template_kind, template_id, "template")

    def template_files(self, template_id: str) -> dict[str, bytes]:
        """문서 틀 본문 폴더의 파일 전부."""
        self.get_template(template_id)
        return self._all_files(self.template_kind, template_id)

    def template_summaries(
        self, *, graphs: Sequence[str] | None = None
    ) -> list[SpecTemplateSummary]:
        """이 공간의 문서 틀 목록(정의 모듈이 꺼져도 동작, §6R.18 Q2)."""
        out: list[SpecTemplateSummary] = []
        for tid in self.template_ids():
            try:
                tpl = self.get_template(tid).template
            except (SpecNotFoundError, DefinitionCorrupt, ValidationError):
                continue
            out.append(
                SpecTemplateSummary(
                    id=tpl.id,
                    name=tpl.name,
                    description=tpl.description,
                    documents=tpl.documents,
                    run_profiles=[
                        RunProfileSummary(id=p.id, title=p.title, graph=p.graph, purpose=p.purpose)
                        for p in tpl.rules.run_profiles or ()
                    ],
                    issues=check_rules(
                        tpl.rules,
                        operators=self.operators,
                        documents=tpl.documents,
                        settings=self.settings(),
                        graphs=graphs,
                        default_syntax=self._default_syntax,
                    ),
                )
            )
        return out

    def save_as_template(
        self,
        spec_id: str,
        *,
        name: str,
        id: str | None = None,
        include_content: bool = False,
        on_conflict: TemplateConflictPolicy = "fail",
        target: DefinitionStore | None = None,
    ) -> SaveAsTemplateResult:
        """스펙 → 문서 틀(§6R.18 Q8). `target` 저장소(기본 = 이 공간의 틀 저장소)에 저장한다.

        겹침: `fail` = `TemplateExistsError`, `overwrite` = 덮어씀(본문 파일도 정확히 같게),
        `rename` =
        `-2`… 새 id. 버전 기록 메시지에만 `스펙에서 만듦: <종류>/<id>`. 결과의 `target`은 호출자가
        채운다(공간 이름은 서버만 안다).
        """
        stored = self.get(spec_id)
        dest = target if target is not None else self.template_store
        taken = dest.list_ids(self.template_kind)
        template_id = id or slug_id(name, fallback=slug_id(self.template_kind, fallback="item"))
        status: SaveAsTemplateStatus = "created"
        if template_id in taken:
            if on_conflict == "fail":
                raise TemplateExistsError(template_id)
            if on_conflict == "rename":
                template_id = unique_id(template_id, taken, fallback=template_id)
                status = "renamed"
            else:
                status = "overwritten"
        files = self._all_files(self.spec_kind, spec_id)
        draft = spec_to_template(
            stored.document,
            files,
            kind=self.template_kind,
            id=template_id,
            name=name,
            include_content=include_content,
        )
        note = f"스펙에서 만듦: {self.spec_kind}/{spec_id}"
        if status == "overwritten":
            current = dest.get(self.template_kind, template_id)
            saved = dest.save(
                self.template_kind,
                draft.document,
                expected_version=current.version_hash,
                message=note,
            )
            existing = [f.path for f in dest.list_files(self.template_kind, template_id)]
            changes: dict[str, bytes | None] = {p: None for p in existing if p not in draft.files}
            changes.update(draft.files)
            if changes:
                dest.write_files(
                    self.template_kind,
                    template_id,
                    changes,
                    expected_version=saved.version_hash,
                    message=note,
                )
        else:
            created = dest.create(self.template_kind, draft.document, message=note)
            if draft.files:
                try:
                    dest.write_files(
                        self.template_kind,
                        template_id,
                        draft.files,
                        expected_version=created.version_hash,
                        message=note,
                    )
                except BaseException:
                    dest.delete(self.template_kind, template_id)
                    raise
        return SaveAsTemplateResult(template_id=template_id, status=status)
