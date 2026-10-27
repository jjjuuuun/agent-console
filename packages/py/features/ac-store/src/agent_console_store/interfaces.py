"""저장소 인터페이스(Protocol)와 값 객체. 도메인 코드는 이 모듈만 알면 된다."""

from __future__ import annotations

import builtins
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from agent_console_contracts import (
    DefinitionVersion,
    ErrorInfo,
    Interaction,
    InteractionStatus,
    NodeRun,
    ResourceFile,
    Run,
    RunEvent,
    RunEventBase,
    RunStatus,
)

from .kinds import DefinitionKind

M = TypeVar("M", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class StoredDefinition:
    """저장된 정의 문서와 그 버전. `document`는 JSON 호환 dict(모르는 필드 포함)."""

    kind: str
    id: str
    document: dict[str, Any]
    version_hash: str
    saved_at: float | None = None

    def model(self, cls: type[M]) -> M:
        """문서를 계약 모델로 검증해 돌려준다."""
        return cls.model_validate(self.document)


@dataclass(frozen=True, slots=True)
class DefinitionSummary:
    """목록용 요약(본문 없음). `counts`는 종류의 `count_fields` 길이."""

    kind: str
    id: str
    name: str
    description: str
    labels: list[str]
    version_hash: str
    saved_at: float | None
    counts: dict[str, int] = field(default_factory=dict)
    has_content: bool = False
    """종류가 본문 파일을 쓰고 문서가 본문을 가리키면 True."""
    extra: dict[str, str] = field(default_factory=dict)
    """종류의 `summary_fields`에서 복사한 문자열 필드(예: 리소스의 `type`)."""
    attributes: dict[str, Any] = field(default_factory=dict)
    """문서의 최상위 `attributes`(객체일 때만, 복사본). 없거나 객체가 아니면 빈 dict."""


class VersionRepository(Protocol):
    """정의 버전 스냅샷 이력(R2.5). (kind, id, version_hash)가 키다.

    본문 파일이 있는 정의는 저장마다 파일 내용도 **내용 주소 blob**(sha256)으로 남긴다.
    같은 내용은 한 번만 저장되고 여러 버전이 공유한다(design §2R.3).
    """

    def record(
        self,
        kind: str,
        id: str,
        version_hash: str,
        content: Mapping[str, Any],
        *,
        saved_at: float,
        message: str = "",
        files: Mapping[str, bytes] | None = None,
    ) -> None:
        """스냅샷을 저장한다. 같은 키가 있으면 내용과 시각을 갱신한다(멱등).

        Args:
            files: 경로 -> 본문 내용. 주면 그 버전의 본문 스냅샷을 이 값으로 바꾼다(빈 dict =
                본문 없음). None이면 기존 본문 스냅샷을 그대로 둔다.
        """
        ...

    def saved_at(self, kind: str, id: str, version_hash: str) -> float | None:
        """그 버전의 저장 시각. 기록이 없으면 None."""
        ...

    def list(self, kind: str, id: str) -> list[DefinitionVersion]:
        """최신순 목록. `content`는 담지 않는다."""
        ...

    def get(self, kind: str, id: str, version_hash: str) -> DefinitionVersion | None:
        """한 버전(`content` 포함). 없으면 None."""
        ...

    def files(self, kind: str, id: str, version_hash: str) -> dict[str, str] | None:
        """그 버전의 본문 스냅샷(경로 -> sha256). 버전이 없거나 본문을 남기지 않았으면 None
        (본문이 없는 정의는 빈 dict)."""
        ...

    def blob_size(self, sha256: str) -> int | None:
        """blob의 바이트 수. 없으면 None."""
        ...

    def read_blob(self, sha256: str) -> bytes | None:
        """blob 내용. 없으면 None."""
        ...

    def trim(self, kind: str, id: str, *, keep: int, protect: Collection[str] = ()) -> int:
        """가장 오래된 버전부터 지워 `keep`개만 남기고 지운 개수를 돌려준다.

        `protect`의 해시는 지우지 않고 `keep`개에 **포함**한다(현재 버전 등). 보호 대상이 `keep`보다
        많으면 그만큼 남는다. 구현이 Run이 참조하는 그래프 버전을 알면 그것도 보호한다. 지운
        버전의 blob은 `prune_blobs`가 정리한다.
        """
        ...

    def prune_blobs(self) -> int:
        """어떤 버전도 참조하지 않는 blob을 지우고 개수를 돌려준다."""
        ...


class DefinitionStore(Protocol):
    """정의(graph, agent, settings 등) 저장소. 종류는 `DefinitionKind`로 등록한다.

    예외: `NotFound`, `AlreadyExists`, `VersionRequired`, `VersionConflict`,
    `InvalidIdentifier`, 모델 검증 실패는 `pydantic.ValidationError`.
    """

    def kinds(self) -> list[str]:
        """등록된 종류 이름."""
        ...

    def register_kind(self, kind: DefinitionKind) -> None:
        """종류를 추가한다(코드 수정 없이 새 정의 종류 지원). 이름이 겹치면 `ValueError`."""
        ...

    def list_ids(self, kind: str) -> list[str]: ...

    def get(self, kind: str, id: str) -> StoredDefinition:
        """현재 문서. 없으면 `NotFound`."""
        ...

    def create(
        self, kind: str, document: Mapping[str, Any] | BaseModel, *, message: str = ""
    ) -> StoredDefinition:
        """새 정의. 같은 id가 있으면 `AlreadyExists`. id는 문서의 `id` 필드(싱글턴은 종류 이름)."""
        ...

    def save(
        self,
        kind: str,
        document: Mapping[str, Any] | BaseModel,
        *,
        expected_version: str | None = None,
        message: str = "",
    ) -> StoredDefinition:
        """기존 정의를 덮어쓴다(싱글턴은 없으면 만든다).

        `require_version` 종류는 `expected_version`이 없으면 `VersionRequired`,
        현재 해시와 다르면 `VersionConflict`. 저장마다 버전 스냅샷을 남긴다.
        """
        ...

    def delete(self, kind: str, id: str, *, expected_version: str | None = None) -> None:
        """삭제. 버전 이력은 남긴다(과거 Run의 `graph_version` 조회용). `expected_version`을 주면
        지금 버전과 같아야 한다(다르면 `VersionConflict`)."""
        ...

    def summaries(self, kind: str) -> list[DefinitionSummary]:
        """목록용 요약(id 순). 읽을 수 없는 파일은 건너뛴다."""
        ...

    def list_versions(self, kind: str, id: str) -> list[DefinitionVersion]:
        """버전 목록(최신순, `content` 없음)."""
        ...

    def get_version(self, kind: str, id: str, version_hash: str) -> DefinitionVersion:
        """한 버전(`content` 포함). 없으면 `NotFound`."""
        ...

    def read_content(self, kind: str, id: str) -> bytes | None:
        """본문 파일 내용. 종류가 본문을 쓰지 않거나 문서가 본문을 가리키지 않거나 파일이 없으면
        None. 정의가 없으면 `NotFound`, 경로가 정의 폴더 밖이면 `DefinitionCorrupt`."""
        ...

    def write_content(
        self,
        kind: str,
        id: str,
        data: bytes,
        *,
        file: str | None = None,
        media_type: str | None = None,
        expected_version: str | None = None,
        message: str = "본문 수정",
    ) -> StoredDefinition:
        """본문 파일을 쓰고(원자적) 새 버전을 남긴다. 버전 해시에는 본문이 들어간다.

        Args:
            file: 본문 파일의 상대 경로. 문서에 이미 있으면 생략한다. 바꾸면 이전 파일은 지운다.
            media_type: 문서의 `content.media_type`를 바꿀 때만.
            expected_version: `require_version` 종류는 필수(`VersionRequired`·`VersionConflict`).

        Raises:
            NotFound: 정의가 없다.
            InvalidContentPath: 경로가 정의 폴더 밖이거나 형식이 틀렸거나, 문서에도 인자에도 없다.
            ValueError: 종류가 본문을 쓰지 않는다.
        """
        ...

    # ---- 여러 파일 본문 (`DefinitionKind.multi_file`, design §2R.3) ----------------
    def list_files(self, kind: str, id: str) -> list[ResourceFile]:
        """본문 폴더의 파일 목록(경로 순). 링크·이름 규칙에 어긋난 파일은 건너뛴다.
        정의가 없으면 `NotFound`, 종류가 여러 파일을 쓰지 않으면 `ValueError`."""
        ...

    def read_file(self, kind: str, id: str, path: str) -> bytes:
        """본문 파일 하나. 없으면 `NotFound`, 경로가 틀리면 `InvalidContentPath`."""
        ...

    def write_file(
        self,
        kind: str,
        id: str,
        path: str,
        data: bytes,
        *,
        expected_version: str | None = None,
        message: str = "파일 수정",
    ) -> StoredDefinition:
        """파일 하나를 쓰고 새 버전을 남긴다(`write_files`의 한 건짜리)."""
        ...

    def delete_file(
        self,
        kind: str,
        id: str,
        path: str,
        *,
        expected_version: str | None = None,
        message: str = "파일 삭제",
    ) -> StoredDefinition:
        """파일 하나를 지우고 새 버전을 남긴다. 파일이 없으면 `NotFound`."""
        ...

    def write_files(
        self,
        kind: str,
        id: str,
        changes: Mapping[str, bytes | None],
        *,
        expected_version: str | None = None,
        message: str = "파일 수정",
    ) -> StoredDefinition:
        """여러 파일을 **한 버전**으로 바꾼다(`None` = 지움). 모든 검사를 마친 뒤에 쓴다.

        Raises:
            NotFound: 정의가 없다.
            VersionRequired, VersionConflict: If-Match 규칙(`require_version` 종류).
            InvalidContentPath: 경로 규칙 위반, 파일/폴더 이름 충돌, 대소문자만 다른 이름 충돌.
            ContentTooLarge: 결과 총량이 한도(`max_content_bytes`)를 넘는다.
            ValueError: 종류가 여러 파일을 쓰지 않는다.
        """
        ...

    def list_version_files(self, kind: str, id: str, version_hash: str) -> list[ResourceFile]:
        """그 버전의 본문 스냅샷 목록. 버전이 없거나 스냅샷이 없으면(0003 이전 버전) `NotFound`."""
        ...

    def read_version_file(self, kind: str, id: str, version_hash: str, path: str) -> bytes:
        """그 버전의 본문 파일 하나. 없으면 `NotFound`."""
        ...

    def restore_version(
        self,
        kind: str,
        id: str,
        version_hash: str,
        *,
        expected_version: str | None = None,
        message: str = "",
    ) -> StoredDefinition:
        """그 버전의 문서와 본문을 현재로 되돌리는 **새 버전**을 만든다(본문 파일은 스냅샷과
        정확히 같아진다: 없던 파일은 지움). 비밀·검증 검사는 하지 않는다 -- 호출자가
        `get_version`으로 먼저 본다. 본문 스냅샷이 없는 버전은 문서만 되돌리고 본문은
        그대로 둔다. 버전이 없으면 `NotFound`."""
        ...

    def prune_blobs(self) -> int:
        """어떤 버전도 쓰지 않는 본문 blob을 지운다."""
        ...

    def orphan_bodies(self, kind: str) -> list[str]:
        """정의 문서는 없는데 본문 폴더만 남은 id(저장 도중 종료 등으로 생긴 고아)."""
        ...

    def prune_orphan_bodies(self, kind: str) -> list[str]:
        """고아 본문 폴더를 지우고 그 id를 돌려준다. 정의가 있는 폴더는 건드리지 않는다."""
        ...


class RunRepository(Protocol):
    """Run과 NodeRun 기록."""

    def save(self, run: Run) -> None:
        """Run을 저장한다(없으면 만들고 있으면 전체 교체)."""
        ...

    def get(self, run_id: str) -> Run | None: ...

    def list(
        self,
        *,
        graph_id: str | None = None,
        status: Iterable[RunStatus] | None = None,
        parent_run_id: str | None = None,
        conversation_id: str | None = None,
        agent: str | None = None,
        resumed_from: str | None = None,
        root_run_id: str | None = None,
        project_id: str | None = None,
        root_only: bool = False,
        limit: int | None = None,
    ) -> list[Run]:
        """최신 생성순(created_at 내림차순). 주어진 조건은 모두 만족해야 한다(AND).

        `parent_run_id`는 직접 자식, `root_run_id`는 그 루트 아래 모든 자손(자식·손자…, 루트 자신은
        제외)이다. 루트 Run의 `root_run_id`는 null이다(design §5R.10).

        `project_id`는 `Run.project_id`가 같은 Run만(불투명 문자열), `root_only`가 참이면
        루트 Run(`root_run_id`가 null)만이다. `limit`은 이 두 조건을 건 뒤에 적용된다
        (자식 Run이 limit을 먹지 않는다).

        `resumed_from`은 그 Run을 이어 간 Run들이다(이미 이어 갔는지 확인).

        `agent`는 그 에이전트(정의 id)가 `actor`로 남긴 이벤트가 있는 Run이다.
        """
        ...

    def save_node_run(self, node_run: NodeRun) -> None:
        """NodeRun을 저장한다. 키 = (run_id, node_id, attempt, iteration, call), 있으면 교체.

        `call`은 위임자가 부른 회차(스케줄로 실행되면 0)다. 계보 `runs`가 없는 SQLite에서는 `call`이
        키에 들어가지 못한다(SqliteRunRepository 설명).
        """
        ...

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        """시작 시각, node_id, attempt, iteration 순(시작 전은 뒤)."""
        ...

    def interrupt_unfinished(
        self, *, ended_at: float, error: ErrorInfo | None = None
    ) -> builtins.list[str]:
        """종료되지 않은 Run(queued/running/paused/waiting)을 `interrupted`로 바꾸고 id를 돌려준다.
        (열린 상호작용은 건드리지 않는다. `InteractionRepository.close_pending`으로 따로 닫는다.)

        서버가 재시작할 때 이전 프로세스의 Run을 정리하는 용도다.
        """
        ...

    def delete(self, run_id: str) -> bool:
        """Run과 딸린 NodeRun, 이벤트, 라우팅 결정, 상호작용을 지운다. 있었으면 True."""
        ...


class EventRepository(Protocol):
    """RunEvent 저장(일반형). 같은 (run_id, seq)는 한 번만 저장된다."""

    def append(self, event: RunEventBase) -> bool:
        """저장하면 True. 같은 `event_id`가 이미 있으면 False(멱등).
        같은 (run_id, seq)에 다른 `event_id`면 `EventConflict`."""
        ...

    def append_many(self, events: Sequence[RunEventBase]) -> int:
        """한 트랜잭션으로 저장하고 새로 저장된 개수를 돌려준다."""
        ...

    def list(
        self,
        run_id: str,
        *,
        since_seq: int = 0,
        limit: int | None = None,
        actor: str | None = None,
        type_prefix: str | None = None,
    ) -> list[RunEvent]:
        """`seq > since_seq`인 이벤트를 seq 오름차순으로.

        `actor`는 정확히 같은 값, `type_prefix`는 `type`이 그 문자열로 시작하는 것(대소문자 구분).
        """
        ...

    def last_seq(self, run_id: str) -> int:
        """저장된 마지막 seq. 없으면 0."""
        ...

    def latest_by_type(
        self,
        type: str,
        *,
        run_id: str | None = None,
        actor: str | None = None,
        limit: int = 1,
    ) -> builtins.list[RunEvent]:
        """그 `type`의 최근 이벤트 `limit`개(ts 내림차순, 같으면 run_id·seq 내림차순).

        `run_id`를 생략하면 모든 Run에서 찾는다(예: 창별 최신 `usage.rate_limit`).
        """
        ...

    def list_by_actor(
        self,
        actor: str,
        *,
        since: float | None = None,
        type_prefix: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[RunEvent]:
        """한 에이전트가 낸 이벤트를 Run 가로질러 최신순(ts 내림차순)으로(최근 활동)."""
        ...


class InteractionRepository(Protocol):
    """상호작용(design §R14.4). payload·response는 호출자가 비밀을 가린 뒤 넘긴다."""

    def save(self, interaction: Interaction) -> bool:
        """pending 상태로 새로 만들거나 pending 행을 갱신한다.

        이미 닫힌 행은 덮어쓰지 않는다(늦게 도착한 저장이 응답을 되살리지 못하게). 저장했으면 True.
        """
        ...

    def get(self, interaction_id: str) -> Interaction | None: ...

    def list(
        self,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        status: InteractionStatus | Iterable[InteractionStatus] | None = None,
        root_run_id: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Interaction]:
        """`created_at` 오름차순(같으면 id). 조건은 AND.

        `root_run_id`는 그 루트 Run과 아래 모든 자식 Run의 상호작용이다(`root_run_id or run_id`
        기준으로 모으기, design §5R.10).
        """
        ...

    def close(
        self,
        interaction_id: str,
        *,
        status: InteractionStatus,
        closed_at: float,
        response: dict[str, Any] | None = None,
        answered_by: str | None = None,
        close_reason: str | None = None,
    ) -> Interaction:
        """pending -> 닫힘. `status='pending'` 조건부 갱신이라 동시에 호출하면 하나만 성공한다.

        Raises:
            NotFound: 없다.
            InteractionClosed: 이미 닫혀 있다(`.interaction`이 먼저 닫은 쪽의 상태).
            ValueError: `status`가 닫힌 상태가 아니다.
        """
        ...

    def close_pending(
        self,
        *,
        status: InteractionStatus,
        closed_at: float,
        run_id: str | None = None,
        answered_by: str | None = "system",
        close_reason: str | None = None,
    ) -> builtins.list[Interaction]:
        """대기 중인 것을 `expired`·`cancelled`로 닫고(`run_id` 없으면 전체) 닫은 것을 돌려준다.

        Raises:
            ValueError: `status`가 `expired`·`cancelled`가 아니다.
        """
        ...

    def pending_counts(self, conversation_ids: Iterable[str] | None = None) -> dict[str, int]:
        """대화 id -> 대기 중인 상호작용 수(0인 대화는 빠진다). 대화 목록 배지용."""
        ...
