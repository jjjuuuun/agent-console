import { getAt } from "../../lib/jsonPointer";

/**
 * 팀 구성 데이터에서 읽는 config 키 위치(JSON Pointer). 화면 코드는 키 이름을 쓰지 않고 이 표만 본다
 * (screen-delegation.md 1.3, 서버 `ac-teams` `TeamConventions`와 같은 약속). 다른 키를 쓰는 플러그인이면 이 데이터만 바꾼다.
 */
export interface TeamConventions {
  /** 반복 연결 회차 한도: 연결 config 기준 */
  edgeIterationLimit: string;
  /** 위임 연결의 위임 방식 덮어쓰기: 연결 config 기준(명세 4키 밖 추가, 방식 칩 계산용) */
  edgeStrategy: string;
  /** 중첩 노드가 자식 팀 구성 버전을 고정하는 위치: 노드 config 기준 */
  nodePinVersion: string;
  /** 위임자 노드가 위임 방식별 설정(`{방식 id: 설정}`)을 두는 위치: 노드 config 기준(명세 4키 밖 추가, 방식 설정 폼용) */
  nodeDelegation: string;
  /** 반복 한도 팀·공통 층 값: 사용자 설정 묶음 기준 */
  settingsFlowMaxIterations: string;
  /** 노드 실행 총량 안내: 사용자 설정 묶음 기준 */
  settingsFlowMaxNodeRuns: string;
}

/** 기본 플러그인(`ac-nodes-core`) 스키마와 같은 위치. */
export const DEFAULT_TEAM_CONVENTIONS: TeamConventions = {
  edgeIterationLimit: "/max_iterations",
  edgeStrategy: "/strategy",
  nodePinVersion: "/version",
  nodeDelegation: "/delegation",
  settingsFlowMaxIterations: "/flow/max_iterations",
  settingsFlowMaxNodeRuns: "/flow/max_node_runs",
};

/** 위치의 값 중 비어 있지 않은 문자열만. */
export function stringAt(data: unknown, pointer: string): string | undefined {
  const v = getAt(data, pointer);
  return typeof v === "string" && v !== "" ? v : undefined;
}

/** 위치의 값 중 유한한 숫자만. */
export function numberAt(data: unknown, pointer: string): number | undefined {
  const v = getAt(data, pointer);
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}
