/**
 * 프로젝트 실행을 막는 서버 신호의 표(데이터). 서버가 `feature_unavailable`을 `details.port`와 함께 준다.
 * 모듈 id는 쓰지 않고 포트 이름으로만 안다.
 */
export const RUNS_BLOCK_PORTS: ReadonlySet<string> = new Set(["runs.scopes"]);
