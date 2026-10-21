/**
 * 실행 화면의 앱 기본값(데이터). 화면 코드는 이 값을 읽기만 하고, 사용자가 다르게 원하면 이 표만 바꾼다.
 * 노드 타입·연결 종류·에이전트 이름은 여기에 없다(서버 데이터). 아래 문자열은 계약이 정한 상태·이벤트 어휘다.
 */

/** 목록에서 "활성"으로 보는 Run 상태(경과 시간 갱신·폴링 대상). */
export const ACTIVE_RUN_STATUSES: readonly string[] = ["queued", "running", "waiting"];

/** 취소 버튼을 보이는 Run 상태. */
export const CANCELLABLE_RUN_STATUSES: readonly string[] = ["queued", "running", "waiting"];

/** 응답 대기를 뜻하는 Run 상태(왼쪽 막대·요약 문구). */
export const WAITING_RUN_STATUS = "waiting";

/** 중단(서버 재시작) 상태. 배너 문구용. */
export const INTERRUPTED_RUN_STATUS = "interrupted";

export interface PeriodOption {
  id: string;
  /** 지금부터 이 초 이전까지. null이면 제한 없음 */
  seconds: number | null;
}

/** 기간 선택지(화면 선택이며 설정이 아니다). 첫 항목이 아닌 `DEFAULT_PERIOD`가 기본. */
export const PERIOD_OPTIONS: readonly PeriodOption[] = [
  { id: "24h", seconds: 24 * 3600 },
  { id: "7d", seconds: 7 * 24 * 3600 },
  { id: "30d", seconds: 30 * 24 * 3600 },
  { id: "all", seconds: null },
];
export const DEFAULT_PERIOD = "7d";

/** 서버에 요청할 실행 목록 개수 상한. */
export const RUN_LIST_LIMIT = 200;
/** 활성 실행이 있을 때 목록을 다시 읽는 간격(ms). */
export const RUN_LIST_POLL_MS = 5000;
/** 이벤트가 오고 나서 trace·스냅샷을 다시 읽기까지의 디바운스(ms). */
export const RUN_REFETCH_DEBOUNCE_MS = 500;

/** 관측(hook·MCP) 탭이 모으는 이벤트 type 접두. 설정 `observe`가 수집 범위를 정한다. */
export const OBSERVE_PREFIXES: readonly string[] = ["hook.", "mcp."];

/** 연속 텍스트 조각 이벤트(한 행으로 합친다). */
export const TEXT_DELTA_EVENT = "agent.text_delta";
export const SUBAGENT_START_EVENT = "agent.subagent_started";
export const SUBAGENT_STOP_EVENT = "agent.subagent_stopped";
export const EDGE_TRAVERSED_EVENT = "edge.traversed";
export const EDGE_SKIPPED_EVENT = "edge.skipped";
/** 이 접두의 이벤트가 오면 상호작용 목록을 다시 읽는다. */
export const INTERACTION_EVENT_PREFIX = "interaction.";
/** 이 접두의 이벤트가 오면 Run 스냅샷(상태·NodeRun)을 즉시 다시 읽는다. */
export const SNAPSHOT_EVENT_PREFIXES: readonly string[] = ["run.", "node."];

/** 서브에이전트 종료 payload `status` → 노드 상태 표시 값. 모르는 값은 그대로 보인다. */
export const SUBAGENT_STOP_STATUS: Readonly<Record<string, string>> = {
  completed: "succeeded",
  failed: "failed",
  stopped: "cancelled",
};
/** 서브에이전트가 시작된 상태. */
export const SUBAGENT_RUNNING_STATUS = "running";

/** 엣지 스케줄링 중 순번 배지를 달지 않는 값(입구·답변). 값은 연결 종류 디스크립터의 `scheduling`. */
export const NO_ORDER_SCHEDULING: readonly string[] = ["entry", "exit"];

/** 이벤트 목록 한 번에 그리는 행 수(스크롤 시 더 보기). */
export const EVENT_PAGE_SIZE = 200;

/** 30초 이상 이벤트가 없을 때 "마지막 이벤트 n초 전"을 보이는 기준. */
export const EVENT_IDLE_SECONDS = 30;

/** "실패만" 필터가 비교하는 span 상태 값. */
export const FAILED_STATUS = "failed";
