"""계약 수준 상수. 프로토콜 어휘이며 사용자 데이터(노드 타입·카테고리 등)가 아니다."""

from typing import Final

CONTRACTS_VERSION: Final = "0.12.1"
"""계약 전체 버전(`GET /bootstrap`의 contracts_version). 하위 모듈 버전(`CONTRACT_VERSIONS`) 중
하나라도 바뀌면 올린다(design §3R.3, modularity §3.6)."""

CONTRACT_SUBMODULES: Final = (
    "common",
    "resources",
    "logs",
    "definitions",
    "runs",
    "usage",
    "projects",
    "chat",
    "exports",
    "imports",
    "architecture",
    "memory",
    "modules",
)
"""기능별 계약 하위 모듈(아래 층 → 위 층 순). 모든 모델은 이 중 하나에 정의된다.

import 규칙(import-linter layers, 루트 `importlinter.rules.toml`): 위 층만 아래 층을 import한다.
`resources`·`logs`는 서로 모르고(둘 다 `common`만 쓴다, `definitions`가 둘을 쓴다),
`runs`·`usage`·`projects`는 서로 모르고(0.8.0: `projects`는 `definitions`까지만 쓴다),
`chat`·`exports`·`imports`·`architecture`도 서로 모른다(0.9.0: `architecture`는 `runs`의 조건·
`logs`의 이벤트·`definitions`의 이슈를 쓴다. 0.10.0: `memory`도 같은 층이고 `runs`의 조건·
`definitions`의 이슈만 쓴다). `modules`는 맨 위다.
TS 생성물도 같은 이름의 하위 경로(`@agent-console/contracts/<이름>`)로 나뉜다.
"""

CONTRACT_VERSIONS: Final[dict[str, str]] = {
    "common": "1.7.0",
    "resources": "1.1.0",
    "logs": "1.1.0",
    "definitions": "1.4.0",
    "runs": "1.5.0",
    "usage": "1.1.0",
    "projects": "3.1.0",
    "chat": "1.2.0",
    "exports": "1.0.0",
    "imports": "1.1.0",
    "architecture": "1.0.0",
    "memory": "1.1.0",
    "modules": "1.3.0",
}
"""계약 하위 모듈 → 버전(semver). 그 하위 모듈의 형식을 바꾸면 그 값을 올린다.
모듈은 쓰는 하위 모듈 버전을 `ModuleInfo.contracts`로 낸다. 0.5.0에서 1.0.0으로 시작했다
(`logs`는 0.6.0, `projects`는 0.8.0, `architecture`는 0.9.0, `memory`는 0.10.0에서
1.0.0으로 시작. `projects`는 0.11.0에서 2.0.0 — 프로젝트 = 로컬 폴더, 0.12.0에서 3.0.0 — 프로젝트
구성 = 폴더 안 사본, 0.12.1에서 3.1.0 — 프로젝트 기록 DB·폴더 확인 보강, design §PI)."""

USAGE_REPORT_PARTS: Final = ("windows", "tokens")
"""`GET /usage?parts=`의 알려진 부분 이름. windows = 창 스냅샷,
tokens = 토큰 집계(`UsageReport.rollups`). 생략 = 전부, 모르는 이름은 무시한다."""


LOG_EVENT_ORDERS: Final = ("asc", "desc")
"""로그 목록 필터 `order`의 값(design §4R.9). seq 기준 오름·내림차순, 기본 asc."""

LOG_PROJECT_UNGROUPED: Final = "~ungrouped"
"""로그 필터 `project`의 예약 값: 묶기 규칙에 맞지 않은 로그(design §4R.9). `~` 접두로 그룹 id와
겹치지 않는다. 0.11.0 deprecated(K33-15): 로그 필터 `project`는 등록 프로젝트 id를 받는다.
다음 major에서 삭제."""


class ErrorCodes:
    """`ErrorInfo.code`의 알려진 값. 플러그인은 다른 코드를 쓸 수 있다."""

    BAD_REQUEST: Final = "bad_request"
    VALIDATION_FAILED: Final = "validation_failed"
    UNAUTHORIZED: Final = "unauthorized"
    FORBIDDEN: Final = "forbidden"
    NOT_FOUND: Final = "not_found"
    ALREADY_EXISTS: Final = "already_exists"
    VERSION_CONFLICT: Final = "version_conflict"
    VERSION_REQUIRED: Final = "version_required"
    PAYLOAD_TOO_LARGE: Final = "payload_too_large"
    INTERNAL: Final = "internal"
    CONVERSATION_BUSY: Final = "conversation_busy"
    INTERACTION_CLOSED: Final = "interaction_closed"
    RUN_NOT_RESUMABLE: Final = "run_not_resumable"
    """끊긴 실행을 이어 갈 수 없다(끊긴 Run이 아님·이미 이어 감·대화의 마지막 턴이 아님, §2R.10)."""
    FEATURE_UNAVAILABLE: Final = "feature_unavailable"
    """켜진 모듈 안에서 선택 포트가 없어 그 동작이 꺼져 있다.
    `details` = `FeatureUnavailableDetails{module, port}`."""
    NOT_READY: Final = "not_ready"
    """서버가 아직 준비되지 않았다(모듈 시작 훅이 끝나기 전·종료 중, `GET /health` 503, 3R.16).
    준비 신호 계약은 그대로다: `/health` 200 = 준비."""
    BACKEND_UNRESOLVED: Final = "backend.unresolved"
    """실행 백엔드가 정해지지 않은 노드가 있어 실행을 만들지 않았다(사전 점검, 0.8.0, HTTP 422).
    `details` = `BackendUnresolvedDetails{nodes, options}`, 해결 버튼은 `ErrorInfo.fix`."""
    BACKEND_PROBE_UNSUPPORTED: Final = "backend.probe_unsupported"
    """실행 백엔드가 연결 테스트를 지원하지 않는다(`capabilities.probe=false`, 0.8.0, HTTP 409,
    ux-overhaul §15.8). `details.backend` = 백엔드 id."""
    BACKEND_LOGIN_UNSUPPORTED: Final = "backend.login_unsupported"
    """실행 백엔드가 앱 화면 로그인을 지원하지 않는다(`capabilities.login=false`, 0.8.0, HTTP 409,
    F14). `details.backend` = 백엔드 id."""
    BACKEND_LOGIN_BUSY: Final = "backend.login_busy"
    """다른 로그인 세션이 진행 중이다(서버 전체 하나, 0.8.0, HTTP 409, F14).
    `details.session_id` = 진행 중인 세션 id, `details.backend` = 그 세션의 백엔드 id."""
    BACKEND_LOGOUT_UNSUPPORTED: Final = "backend.logout_unsupported"
    """실행 백엔드가 앱 화면 로그아웃을 지원하지 않는다(`capabilities.logout=false`, 0.8.0,
    HTTP 409, F14). `details.backend` = 백엔드 id."""
    BACKEND_SUBSCRIPTION_AUTH_DISABLED: Final = "backend.subscription_auth_disabled"
    """설치자 설정이 구독 인증을 꺼서 로그인을 시작하지 않았다(백엔드가 거절, 0.8.0, HTTP 409, F14).
    백엔드는 다른 거절 코드도 쓸 수 있다(열린 어휘, 이 표에 없으면 HTTP 400)."""
    BACKEND_LOGIN_SESSION_NOT_FOUND: Final = "backend.login_session_not_found"
    """로그인 세션이 없거나 보관 시간이 지났다(0.8.0, HTTP 404, F14)."""
    ARCHITECTURE_PROFILE_NOT_FOUND: Final = "architecture.profile_not_found"
    """구조도 프로필이 없다(id로 조회·투영, 0.9.0, HTTP 404). `details.profile` = 요청한 id.
    투영에서 다른 프로필로 대신 그릴 수 있으면 오류 대신
    안내(`architecture.profile_fallback`)를 단다."""
    ARCHITECTURE_SCOPE_TOO_LARGE: Final = "architecture.scope_too_large"
    """구조도 범위(또는 단독 투영 본문)의 이벤트 수가 설치자 상한을 넘어 투영하지 않았다(0.9.0,
    HTTP 422). `details` = `ArchitectureScopeTooLargeDetails{events, limit}`."""
    MEMORY_INVALID_KEY: Final = "memory.invalid_key"
    """메모리 키가 글자 규칙(빈 마디·`.`·`..`·앞뒤 `/`·제어 문자 금지, 최대 길이)에 맞지
    않다(0.10.0, HTTP 422)."""
    MEMORY_TOO_LARGE: Final = "memory.too_large"
    """메모리 본문·가져오기 묶음이 설치자 한도를 넘었다(0.10.0, HTTP 422). `details.limit`."""
    MEMORY_SECRET_REJECTED: Final = "memory.secret_rejected"
    """메모리 본문에 비밀 의심 값이 있어 쓰기를 거부했다(설정 비밀 처리 = 거부, 0.10.0, HTTP 422).
    본문·찾은 값은 응답에 싣지 않는다. `details` = `MemorySecretRejectedDetails{field, rules}`."""

    # ---- 5.7R.33(design §PI, 0.11.0): 프로젝트 = 로컬 폴더, 실행 사전 점검, 폴더 확인·탐색
    PROJECT_REQUIRED: Final = "project.required"
    """프로젝트 기능이 있는 조립에서 `project_id` 없이 실행·대화를 시작했다(HTTP 422).
    fix = [프로젝트 고르기]."""
    PROJECT_NOT_IMPORTED: Final = "project.not_imported"
    """실행 대상이 이 프로젝트에서 쓸 수 없다(HTTP 422). `details` =
    `ProjectNotImportedDetails{project_id, kind, id, in_library}`(0.12.0): 실행 대상이 그 프로젝트
    공간에 없다. `in_library` = 라이브러리에는 있음(화면 [가져와서 실행], K33-18)."""
    PROJECT_FOLDER_MISSING: Final = "project.folder_missing"
    """프로젝트 상태가 ready가 아니라 시작하지 않았다(폴더 없음·권한·미지정·겹침, HTTP 409).
    `details` = `ProjectFolderUnavailableDetails{project_id, status, folder?}`."""
    PROJECT_FOLDER_TAKEN: Final = "project.folder_taken"
    """같은 폴더가 이미 등록돼 있다(HTTP 409, K33-2). `details` =
    `ProjectFolderConflictDetails{project_id, archived}`."""
    PROJECT_FOLDER_OVERLAPS: Final = "project.folder_overlaps"
    """등록된 폴더와 겹친다(한쪽이 다른 쪽 안, HTTP 409, K33-2). `details` =
    `ProjectFolderConflictDetails{project_id, relation: parent|child}`."""
    PROJECT_OUTSIDE_FOLDER: Final = "project.outside_folder"
    """설정의 경로 값(`x-path` 필드)이 프로젝트 폴더 밖이다(HTTP 422, design §PI.5). `details` =
    `ProjectOutsideFolderDetails{project_id, folder, paths}`."""
    FOLDERS_REMOTE_DISABLED: Final = "folders.remote_disabled"
    """서버가 루프백이 아닌 주소에 묶여 폴더 확인·탐색·만들기를 열지 않았다(HTTP 403, design §PI.6).
    설치자 설정 `mod-projects.allow_remote_browse`로만 켠다."""
    # 폴더 작업 실패(`ac-local-folders` `FolderError.code`에 `folders.` 접두를 붙인 값).
    FOLDERS_EMPTY: Final = "folders.empty"
    FOLDERS_INVALID_PATH: Final = "folders.invalid_path"
    FOLDERS_RELATIVE: Final = "folders.relative"
    FOLDERS_FOREIGN_PATH: Final = "folders.foreign_path"
    """다른 OS 경로(예: 리눅스 서버에 Windows 드라이브 경로). 경로 제안은 하지 않는다."""
    FOLDERS_NO_HOME: Final = "folders.no_home"
    FOLDERS_OUTSIDE_ROOTS: Final = "folders.outside_roots"
    """탐색 범위(`browse_roots`) 밖(HTTP 403)."""
    FOLDERS_NOT_FOUND: Final = "folders.not_found"
    """목록을 볼 폴더가 없다(HTTP 404)."""
    FOLDERS_NOT_DIRECTORY: Final = "folders.not_directory"
    FOLDERS_NO_ACCESS: Final = "folders.no_access"
    FOLDERS_INVALID_NAME: Final = "folders.invalid_name"
    FOLDERS_EXISTS: Final = "folders.exists"
    """만들려는 폴더가 이미 있다(HTTP 409)."""
    FOLDERS_MISSING_PARENT: Final = "folders.missing_parent"
    FOLDERS_IO_ERROR: Final = "folders.io_error"
    """파일 시스템 오류(HTTP 500, 메시지에 경로 밖 정보 없음)."""

    # ---- 5.7R.33c2(design §PI.4·§PI.6, 0.12.0): 프로젝트 공간·복사·네이티브 폴더 대화상자
    PROJECT_NOT_FOUND: Final = "project.not_found"
    """정의·메모리 경로의 `?project=`(공간)나 복사 요청의 `SpaceRef`가 등록되지 않은 프로젝트를
    가리킨다(HTTP 404). `details.project_id`."""
    PROJECT_MANIFEST_INVALID: Final = "project.manifest_invalid"
    """폴더 매니페스트(`.agent-console/project.yaml`)를 읽을 수 없어 시작·쓰기를 하지 않았다
    (HTTP 409). `details` = `ProjectFolderUnavailableDetails{project_id, status, folder?}`."""
    PROJECT_CONFIG_READONLY: Final = "project.config_readonly"
    """프로젝트 폴더의 구성(`.agent-console/`)에 쓸 수 없어 가져오기·편집·메모리 쓰기를 하지
    않았다(HTTP 409, `ProjectView.config_writable = false`). `details.project_id`."""
    PROJECT_COPY_CONFLICT: Final = "project.copy_conflict"
    """복사 계획 뒤 원본 또는 대상이 바뀌었다. 보통 복사 결과 항목의 이슈
    (`CopyApplyItemResult.issue`)로 쓰고, 오류로 낼 때는 HTTP 409. `details.kind`·`details.id`."""
    FOLDERS_DIALOG_UNAVAILABLE: Final = "folders.dialog_unavailable"
    """네이티브 폴더 대화상자를 쓸 수 없다(제공자 없음·꺼짐·원격 바인딩, HTTP 409). 화면은 앱 안
    찾아보기로 간다. 선택 응답에서는 `FolderPickResult.status = unavailable`."""
    FOLDERS_DIALOG_BUSY: Final = "folders.dialog_busy"
    """다른 폴더 선택 창이 열려 있다(한 번에 하나, HTTP 409)."""
    FOLDERS_DIALOG_TIMEOUT: Final = "folders.dialog_timeout"
    """폴더 선택 창이 시간 상한 안에 닫히지 않았다(HTTP 409, 서버가 창 프로세스를 끝냄)."""

    # ---- 5.7R.33c3(design §PI.4.6·§PI.16, 0.12.1): 프로젝트 기록 DB·대화 이어 가기
    PROJECT_RECORDS_UNAVAILABLE: Final = "project.records_unavailable"
    """프로젝트 기록 DB(`<folder>/<config_dir>/records.sqlite3`)에 쓸 수 없어 대화·실행 시작이나
    기록 쓰기를 하지 않았다(HTTP 409). 앱 DB에 대신 쓰지 않는다(K33-31). `details` =
    `ProjectRecordsUnavailableDetails{project_id, reason, backup_path?}`(이유
    `KnownRecordsUnavailableReasons`). 실행 중에 폴더가 사라지면 그 Run의 `error.code`로도 쓴다."""
    CHAT_SESSION_UNAVAILABLE: Final = "chat.session_unavailable"
    """이 앱에 대화의 백엔드 세션 기록이 없어 이어 갈 수 없다(HTTP 409, design §PI.4.6.4).
    `details` = `{conversation_id, node_ids}`. 다시 보낼 때 `on_missing_session: "fresh"`면 그
    노드는 새 세션으로 시작한다."""


HTTP_STATUS_BY_ERROR_CODE: Final[dict[str, int]] = {
    ErrorCodes.BAD_REQUEST: 400,
    ErrorCodes.VALIDATION_FAILED: 422,
    ErrorCodes.UNAUTHORIZED: 401,
    ErrorCodes.FORBIDDEN: 403,
    ErrorCodes.NOT_FOUND: 404,
    ErrorCodes.ALREADY_EXISTS: 409,
    ErrorCodes.VERSION_CONFLICT: 412,
    ErrorCodes.VERSION_REQUIRED: 428,
    ErrorCodes.PAYLOAD_TOO_LARGE: 413,
    ErrorCodes.INTERNAL: 500,
    ErrorCodes.CONVERSATION_BUSY: 409,
    ErrorCodes.INTERACTION_CLOSED: 409,
    ErrorCodes.RUN_NOT_RESUMABLE: 409,
    ErrorCodes.FEATURE_UNAVAILABLE: 409,
    ErrorCodes.NOT_READY: 503,
    ErrorCodes.BACKEND_UNRESOLVED: 422,
    ErrorCodes.BACKEND_PROBE_UNSUPPORTED: 409,
    ErrorCodes.BACKEND_LOGIN_UNSUPPORTED: 409,
    ErrorCodes.BACKEND_LOGIN_BUSY: 409,
    ErrorCodes.BACKEND_LOGOUT_UNSUPPORTED: 409,
    ErrorCodes.BACKEND_SUBSCRIPTION_AUTH_DISABLED: 409,
    ErrorCodes.BACKEND_LOGIN_SESSION_NOT_FOUND: 404,
    ErrorCodes.ARCHITECTURE_PROFILE_NOT_FOUND: 404,
    ErrorCodes.ARCHITECTURE_SCOPE_TOO_LARGE: 422,
    ErrorCodes.MEMORY_INVALID_KEY: 422,
    ErrorCodes.MEMORY_TOO_LARGE: 422,
    ErrorCodes.MEMORY_SECRET_REJECTED: 422,
    ErrorCodes.PROJECT_REQUIRED: 422,
    ErrorCodes.PROJECT_NOT_IMPORTED: 422,
    ErrorCodes.PROJECT_FOLDER_MISSING: 409,
    ErrorCodes.PROJECT_FOLDER_TAKEN: 409,
    ErrorCodes.PROJECT_FOLDER_OVERLAPS: 409,
    ErrorCodes.PROJECT_OUTSIDE_FOLDER: 422,
    ErrorCodes.FOLDERS_REMOTE_DISABLED: 403,
    ErrorCodes.FOLDERS_EMPTY: 422,
    ErrorCodes.FOLDERS_INVALID_PATH: 422,
    ErrorCodes.FOLDERS_RELATIVE: 422,
    ErrorCodes.FOLDERS_FOREIGN_PATH: 422,
    ErrorCodes.FOLDERS_NO_HOME: 422,
    ErrorCodes.FOLDERS_OUTSIDE_ROOTS: 403,
    ErrorCodes.FOLDERS_NOT_FOUND: 404,
    ErrorCodes.FOLDERS_NOT_DIRECTORY: 422,
    ErrorCodes.FOLDERS_NO_ACCESS: 422,
    ErrorCodes.FOLDERS_INVALID_NAME: 422,
    ErrorCodes.FOLDERS_EXISTS: 409,
    ErrorCodes.FOLDERS_MISSING_PARENT: 422,
    ErrorCodes.FOLDERS_IO_ERROR: 500,
    ErrorCodes.PROJECT_NOT_FOUND: 404,
    ErrorCodes.PROJECT_MANIFEST_INVALID: 409,
    ErrorCodes.PROJECT_CONFIG_READONLY: 409,
    ErrorCodes.PROJECT_COPY_CONFLICT: 409,
    ErrorCodes.FOLDERS_DIALOG_UNAVAILABLE: 409,
    ErrorCodes.FOLDERS_DIALOG_BUSY: 409,
    ErrorCodes.FOLDERS_DIALOG_TIMEOUT: 409,
    ErrorCodes.PROJECT_RECORDS_UNAVAILABLE: 409,
    ErrorCodes.CHAT_SESSION_UNAVAILABLE: 409,
}
"""알려진 오류 코드 → HTTP 상태. `If-Match` 불일치 = 412, `If-Match` 없음 = 428."""

RUN_ORIGINS: Final = ("chat", "web", "api", "task", "resume")
"""`Run.origin`의 알려진 값. chat=채팅 대화의 한 턴,
web=웹 [실행] 버튼, api=외부 REST 호출(기본), task=작업 관리(Phase 6),
resume=끊긴 실행의 노드부터 다시 실행(`Run.resumed_from`, design §2R.10). 다른 값도 허용."""

WS_CLOSE_UNAUTHORIZED: Final = 4401
"""WS close 코드: 토큰 없음·불일치. 클라이언트는 재접속하지 않는다."""

WS_CLOSE_FORBIDDEN: Final = 4403
"""WS close 코드: Host·Origin 검사 실패. 클라이언트는 재접속하지 않는다."""

WS_AUTH_CLOSE_CODES: Final = (WS_CLOSE_UNAUTHORIZED, WS_CLOSE_FORBIDDEN)
"""인증·접근 거부로 닫은 close 코드 묶음. 다시 붙어도 같은 결과라 재접속하지 않는다."""


class KnownResourceSlots:
    """실행 묶음(`ResourceBundle.slots`)의 알려진 칸 이름. **문서 상수**다.

    목록·enum이 아니다. 플러그인은 다른 칸을 만들 수 있고, 백엔드는 받을 칸을
    `BackendCapabilities.resource_slots`로 선언한다. 스키마·TS 상수로 내보내지 않는다.

    값 형식(관례, 스키마로 강제하지 않음): 각 칸 값은 항목 목록이고 기본 combine은 `append`다.
    항목 모양은 기본 종류 플러그인(`ac-resources-core`) README를 참고한다.
    """

    INSTRUCTIONS: Final = "instructions"
    FILES: Final = "files"
    MCP_SERVERS: Final = "mcp_servers"
    TOOLS: Final = "tools"
    SKILLS: Final = "skills"
    HOOKS: Final = "hooks"
    RULES: Final = "rules"
    """경로 조건 지침. 항목은 경로 조건(glob 목록)과 본문을 담는다."""


class KnownIssueCodes:
    """알려진 검증 이슈 코드(`Issue.code`) 일부(design §2R.2 #14). **문서 상수**다.

    목록·enum이 아니다. 이슈를 내는 쪽(패키지·플러그인)은 다른 코드를 쓸 수 있고,
    화면은 코드가 아니라 `severity`·`message`·`path`·`suggestions`로 그린다.
    값을 손으로 복사하지 않도록 이름 → 코드 표를 스키마 `x-constants.KNOWN_ISSUE_CODES`(TS 상수
    `KNOWN_ISSUE_CODES`)로 내보낸다(5.2R.3 후속). 표에 없는 코드도 그대로 유효하다.
    """

    LIMITS_NOT_ENFORCED: Final = "limits.not_enforced"
    """`limits`에 값이 있는데 노드의 실행 백엔드가 그 항목을 강제하지 못한다.
    path = `/limits/<필드>`. 필드와 `EnforceCapabilities` 항목은 같은 키 이름으로 대응한다."""
    RESOURCE_SLOT_UNSUPPORTED: Final = "resource.slot_unsupported"
    """붙인 리소스가 채우는 실행 묶음 칸을 백엔드가 받지 않는다(또는 설정으로 꺼져 있다)."""
    RESOURCE_SLOT_SESSION_SHARED: Final = "resource.slot_session_shared"
    """위임받는 노드(서브에이전트 자리)의 묶음 칸이 대상별로 나뉘지 않고 위임자 세션에 합쳐진다
    (`BackendCapabilities.subagent_slots`에 없는 칸). `details.slot` = 칸 이름."""
    SECRET_PLAIN_FOUND: Final = "secret.plain_found"
    """정의에 평문 비밀로 의심되는 값이 있다(`ServerInfo.warnings`). 값은 담지 않는다.
    `details.kind` = 정의 종류 이름, `details.id` = 정의 id, `Issue.path` = 정의 문서 기준
    JSON Pointer."""
    LOGS_SOURCE_FAILED: Final = "logs.source_failed"
    """로그 출처 하나의 발견·읽기가 실패했다(다른 출처는 계속 수집). `details.source` = 출처 id,
    `details.error_code` = 출처 상태의 오류 코드(design §4R.4)."""
    LOGS_REDACTION_UNAVAILABLE: Final = "logs.redaction_unavailable"
    """비밀 의심 가림을 줄 수 없어 로그 색인을 가리지 않고 저장한다(가림 규칙 포트 없음)."""
    LOGS_STORAGE_MEMORY: Final = "logs.storage_memory"
    """로그 색인을 둘 DB가 없어 메모리에 둔다(재시작하면 사라짐, design §4R.5)."""
    LOGS_UNKNOWN_CLASSIFIER: Final = "logs.unknown_classifier"
    """출처 설정이 고른 분류기 id가 등록돼 있지 않다. `details.source`·`details.classifier`."""

    # ---- 5R(design §5R.8, 0.7.0): 반복·조건·혼합 위임·중첩 팀
    FLOW_MAX_ITERATIONS_INVALID: Final = "flow.max_iterations_invalid"
    """사이클 연결의 유효 최대 반복(엣지 config → `flow.max_iterations` → 디스크립터 `cycle`)이
    없거나 1 미만이다. 엣지 이슈, path = `/max_iterations`."""
    FLOW_MAX_NODE_RUNS_EXCEEDED: Final = "flow.max_node_runs_exceeded"
    """실행 하나의 노드 실행 수가 `flow.max_node_runs`를 넘어 Run이 실패했다(`ErrorInfo.code`로도
    쓴다). `details.limit`. 화면은 서버 `message`를 그대로 보인다(설정 경로 필드는 없다)."""
    CONDITION_UNKNOWN_OPERATOR: Final = "condition.unknown_operator"
    """조건 항목의 연산자가 등록돼 있지 않다(warning, 실행 시 그 항목은 거짓). `details.op`."""
    CONDITION_INVALID_VALUE: Final = "condition.invalid_value"
    """조건 항목의 값이 연산자 `value_schema`에 맞지 않다(error). `details.op`."""
    TEAM_MIXED_STRATEGIES: Final = "team.mixed_strategies"
    """한 위임자의 대상이 서로 다른 위임 방식이고 그중 composable이 아닌 방식이 있다."""
    TEAM_RECURSIVE: Final = "team.recursive"
    """중첩 팀이 자기 자신 또는 순환으로 자기를 다시 넣는다. `details.path` = 팀 구성 id 경로."""
    TEAM_NESTING_EXCEEDED: Final = "team.nesting_exceeded"
    """중첩 팀 깊이가 `delegation.max_nesting`을 넘는다. `details.limit`."""
    TEAM_TEAM_NOT_FOUND: Final = "team.team_not_found"
    """중첩 팀 노드가 가리키는 팀 구성(또는 고정한 버전)이 없다."""
    TEAM_CHILD_NO_ENTRY: Final = "team.child_no_entry"
    """중첩 팀의 자식 팀 구성에 입구가 없다(자식 검증 결과 요약)."""
    DELEGATION_DEPTH_EXCEEDED: Final = "delegation.depth_exceeded"
    """위임 깊이가 위임 방식 `max_depth`·설정 `delegation.max_depth` 중 작은 값을 넘는다
    (검증·실행 둘 다)."""

    # ---- 5.2R(design §5.2R.3 #4, 0.8.0): 백엔드 사전 점검·프로젝트 범위
    BACKEND_UNRESOLVED: Final = "backend.unresolved"
    """백엔드를 쓰는 노드의 실행 백엔드가 층 어디에도 정해지지 않았다(노드 이슈로도, 실행 거부 오류
    코드 `ErrorCodes.BACKEND_UNRESOLVED`로도 쓴다). `fix`로 [노드에서 지정]·[기본값으로 지정]."""
    PROJECT_SHARED_USES_PROJECT: Final = "project.shared_uses_project"
    """(0.11.0부터 내지 않음, K33-5) 공용 정의가 프로젝트 전용 정의를 쓴다(warning).
    `details.project`·`details.kind`·`details.id` = 참조된 정의."""
    PROJECT_CROSS_PROJECT: Final = "project.cross_project"
    """(0.11.0부터 내지 않음, K33-5) 프로젝트 P 전용 정의가 다른 프로젝트 Q 전용 정의를 쓴다."""
    PROJECT_UNKNOWN: Final = "project.unknown"
    """정의·실행이 없는 프로젝트 id를 가리킨다(info, 공용·프로젝트 층 없음으로 취급)."""
    PROJECT_REFERENCES_UNAVAILABLE: Final = "project.references_unavailable"
    """참조 추출이 없어(예: 정의 모듈이 꺼짐) 참조 규칙(`project.shared_uses_project`·
    `project.cross_project`)을 보지 못했다(info)."""
    PROJECT_DEFINITIONS_UNAVAILABLE: Final = "project.definitions_unavailable"
    """정의 읽기가 없어(예: 정의 모듈이 꺼짐) 프로젝트 범위 검사·옮기기 계획을 하지 못했다(info)."""

    # ---- 5.7R(design §5.7R.5, 0.10.0): 공유 메모리·에이전트 도구 공급자(X30)·구조도 검사(M-4)
    # 메모리 도구 실패 사유 코드(`memory.<MemoryEventPayload.status>`, 도구 결과 `is_error`).
    MEMORY_DENIED: Final = "memory.denied"
    """접근 설정이 그 범위·동작을 허용하지 않는다."""
    MEMORY_NOT_FOUND: Final = "memory.not_found"
    """그 범위에 그 키가 없다."""
    MEMORY_CONFLICT: Final = "memory.conflict"
    """`if_version`이 현재 버전과 다르다(도구 결과에 현재 버전을 알린다)."""
    MEMORY_TOO_LARGE: Final = "memory.too_large"
    """본문이 크기 한도를 넘는다(REST 오류 `ErrorCodes.MEMORY_TOO_LARGE`와 같은 값)."""
    MEMORY_SECRET_REJECTED: Final = "memory.secret_rejected"
    """본문에 비밀 의심 값이 있어 거부했다(REST 오류와 같은 값)."""
    MEMORY_RATE_LIMITED: Final = "memory.rate_limited"
    """실행당 쓰기 한도·속도 한도를 넘었다."""
    MEMORY_SCOPE_UNAVAILABLE: Final = "memory.scope_unavailable"
    """범위 id 틀이 이 실행에서 빈 값이라 그 범위를 쓸 수 없다(예: 프로젝트 없이 실행)."""
    MEMORY_INVALID_KEY: Final = "memory.invalid_key"
    """키가 글자 규칙에 맞지 않다(REST 오류와 같은 값)."""
    MEMORY_UNKNOWN_SCOPE_KIND: Final = "memory.unknown_scope_kind"
    """메모리 접근 설정·항목이 목록에 없는 범위 종류를 가리킨다(warning). `details.kind`."""
    MEMORY_SETTINGS_INVALID: Final = "memory.settings_invalid"
    """설정 섹션 memory의 일부가 형식에 맞지 않아 그 부분을 빼고 읽었다(`ServerInfo.warnings`).
    `Issue.path` = 섹션 기준 경로."""
    MEMORY_STORAGE_MEMORY: Final = "memory.storage_memory"
    """메모리 항목을 둘 DB가 없어 프로세스 메모리에 둔다(재시작하면 사라짐,
    `ServerInfo.warnings`)."""
    MEMORY_SEARCH_FALLBACK: Final = "memory.search_fallback"
    """전문 검색(SQLite FTS5 trigram)을 쓸 수 없어 단순 포함 검색으로 찾는다
    (`ServerInfo.warnings`)."""
    TOOLS_PROVIDER_FAILED: Final = "tools.provider_failed"
    """에이전트 도구 공급자가 예외를 내어 그 공급자를 건너뛰었다. `details.provider`."""
    TOOLS_DUPLICATE_NAME: Final = "tools.duplicate_name"
    """공급한 도구 이름이 이미 있는 도구와 겹쳐 뒤의 것(공급자 도구)을 뺐다. `details.name`·
    `details.provider`."""
    TOOLS_BACKEND_CAPABILITY_MISSING: Final = "tools.backend_capability_missing"
    """실행 백엔드가 플랫폼 도구(host tools)를 받지 못해 공급 도구를 뺐다(실행은 계속).
    `details.backend`·`details.provider`."""
    ARCHITECTURE_CONDITION_PATH_UNLISTED: Final = "architecture.condition_path_unlisted"
    """구조도 프로필 조건이 목록 본문에 없는 경로(예: 상세 전용 경로)를 봐서 맞지 않는다(warning,
    M-4). `details.prefix` = 걸린 경로 접두."""

    # ---- 5.7R.33(design §PI, 0.11.0): 프로젝트 = 로컬 폴더. 값은 `ErrorCodes`의 같은 이름과 같다
    # (실행 거부 오류 코드로도, 사전 점검·검증 이슈 코드로도 쓴다).
    PROJECT_REQUIRED: Final = "project.required"
    PROJECT_NOT_IMPORTED: Final = "project.not_imported"
    """`details.in_library` = 라이브러리에는 있음(0.12.0, K33-18)."""
    PROJECT_FOLDER_MISSING: Final = "project.folder_missing"
    PROJECT_FOLDER_TAKEN: Final = "project.folder_taken"
    PROJECT_FOLDER_OVERLAPS: Final = "project.folder_overlaps"
    PROJECT_OUTSIDE_FOLDER: Final = "project.outside_folder"
    FOLDERS_REMOTE_DISABLED: Final = "folders.remote_disabled"
    SETTINGS_IGNORED_KEY: Final = "settings.ignored_key"
    """설정에 이제 쓰지 않는 키가 있어 읽고 무시했다(info, 서버 시작은 막지 않음). 예:
    `projects.new_definition_scope`(§PI.8), `logs.projects`(K33-15). `details.key` = 설정 경로."""
    LOGS_NO_PROJECTS: Final = "logs.no_projects"
    """등록된 프로젝트가 없어 로그를 수집하지 않는다(info, design §PI.5)."""

    # ---- 5.7R.33c2(design §PI.4·§PI.6, 0.12.0). 값은 `ErrorCodes`의 같은 이름과 같다.
    PROJECT_NOT_FOUND: Final = "project.not_found"
    PROJECT_MANIFEST_INVALID: Final = "project.manifest_invalid"
    PROJECT_CONFIG_READONLY: Final = "project.config_readonly"
    PROJECT_COPY_CONFLICT: Final = "project.copy_conflict"
    """복사 결과 항목의 이슈(`CopyApplyItemResult.issue`, status conflict)."""
    PROJECT_MEMORY_NETWORK_FS: Final = "project.memory_network_fs"
    """(deprecated, 0.12.1) `PROJECT_NETWORK_FS`의 옛 이름. 서버는 새 이름만 낸다. 화면·도구는 두
    이름을 같은 뜻으로 읽는다. 다음 major에서 삭제."""
    FOLDERS_DIALOG_UNAVAILABLE: Final = "folders.dialog_unavailable"
    FOLDERS_DIALOG_BUSY: Final = "folders.dialog_busy"
    FOLDERS_DIALOG_TIMEOUT: Final = "folders.dialog_timeout"

    # ---- 5.7R.33c3(design §PI.4.6·§PI.16, 0.12.1). 앞 둘은 `ErrorCodes`의 같은 이름과 같다.
    PROJECT_RECORDS_UNAVAILABLE: Final = "project.records_unavailable"
    """`ProjectView.records_issue`로도 쓴다(기록 DB를 쓸 수 없는 이유, `details.reason`)."""
    CHAT_SESSION_UNAVAILABLE: Final = "chat.session_unavailable"
    PROJECT_NETWORK_FS: Final = "project.network_fs"
    """프로젝트 폴더가 네트워크 파일 시스템이라 SQLite 잠금(메모리·기록 DB)을 믿을 수 없다(info,
    `ProjectView.issues`, 감지할 수 있을 때만, K33-22). `details.files` = 영향받는 파일 이름
    (예: `memory.sqlite3`·`records.sqlite3`). 오류 코드가 아니다. 0.12.0의
    `project.memory_network_fs`를 일반화했다."""
    PROJECT_GITIGNORE_OUTDATED: Final = "project.gitignore_outdated"
    """앱이 만든 `.gitignore` 틀에 지금 틀의 줄이 빠져 있다(info, `ProjectView.issues`). 사용자가
    [덧붙이기]를 누를 때만 빠진 줄을 끝에 더한다. `details.lines` = 빠진 줄. 오류 코드가 아니다."""
    RUN_OTHER_HOST: Final = "run.other_host"
    """끝나지 않은 Run이 다른 앱(`Run.host_id`가 이 앱과 다름)의 것이다(info, 다른 앱에서 실행 중
    또는 그 앱이 비정상 종료). 이 앱은 복구하지 않고, 사용자가 [끊긴 것으로 표시]를 누를 때만
    바꾼다(design §PI.4.6.5). `details.host_id`. 오류 코드가 아니다."""


class KnownSuggestionIds:
    """알려진 이슈 제안 id(`IssueSuggestion.id`) 일부. **문서 상수**다.

    목록·enum이 아니다. 제안을 내는 쪽은 다른 id(예: 그래프 자동 고침의 생성 id)를 쓸 수 있다.
    화면이 특정 제안을 알아보고 동작을 붙여야 하는 id만 둔다. 이름 → id 표를 스키마
    `x-constants.KNOWN_SUGGESTION_IDS`(TS 상수 `KNOWN_SUGGESTION_IDS`)로 내보낸다.
    """

    PROJECT_MOVE_TO_SHARED: Final = "project.move_to_shared"
    """[공용으로 옮기기]. 빈 patch이고, 옮길 정의는 이슈 `details`의 `kind`·`id`(`details.move`에도
    같음). 범위 경고 `project.shared_uses_project`·`project.cross_project`에 붙는다."""


class KnownInteractionKinds:
    """기본 플러그인이 등록하는 상호작용 종류 id(design §R14.3). **문서 상수**다.

    목록·enum이 아니다. 특정 종류를 여는 코드(예: 백엔드 어댑터)만 이 값을 쓴다.
    엔진·서버·웹은 종류 이름을 모른다. 스키마·TS 상수로 내보내지 않는다.
    """

    QUESTION: Final = "question"
    TOOL_PERMISSION: Final = "tool_permission"
    REVIEW: Final = "review"


class KnownUsageTrust:
    """사용량 출처 신뢰 등급(`UsageSourceDescriptor.trust`)의 알려진 값.

    **문서 상수**다.

    목록·enum이 아니다. 서드파티 출처 플러그인은 다른 등급 문자열을 선언할 수 있고, 화면은 모르는
    값을 기본 배지로 보인다. 스키마·TS 상수로 내보내지 않는다.
    """

    OFFICIAL: Final = "official"
    """공식 SDK 타입·공식 문서가 보장하는 값."""
    OBSERVED: Final = "observed"
    """공식 경로에서 관측했지만 갱신 조건이 제한적인 값."""
    ESTIMATED: Final = "estimated"
    """로컬 집계 등으로 추정한 값(분모 없음 등)."""
    UNOFFICIAL: Final = "unofficial"
    """비공개 엔드포인트 등 공식 보장이 없는 값."""


class KnownModuleStatus:
    """`ModuleInfo.status`의 알려진 값. **문서 상수**다.

    목록·enum이 아니다. 호스트 구현이 다른 상태를 낼 수 있고 화면은 모르는 값을 그대로 보인다.
    스키마·TS 상수로 내보내지 않는다.
    """

    ACTIVE: Final = "active"
    DISABLED: Final = "disabled"
    """설정·명령행으로 끔."""
    UNSATISFIED: Final = "unsatisfied"
    """필수 포트를 줄 모듈이 없음(`reason`에 빠진 포트)."""
    FAILED: Final = "failed"
    """로드·시작 실패(`reason`은 비밀을 가린 메시지)."""
    CONFLICT: Final = "conflict"
    """같은 단일 포트를 둘 이상이 제공(`modules.bindings`로 고른다)."""
