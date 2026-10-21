/**
 * 앱 층이 서버 모듈에 거는 요구(모듈 id 또는 역할, 모두 만족해야 한다). 라우트·연동 부분·설정 섹션 데이터는 각자의 파일에 있고,
 * 여러 곳이 함께 보는 요구만 여기에 둔다. 사용자가 다르게 원하면 이 값만 고친다.
 */

/** 설정 문서(워크스페이스 설정)를 읽고 쓰는 기능. 꺼지면 설정 문서를 쓰는 폼·알림·단축키 덮어쓰기가 모두 빠진다. */
export const DOCUMENT_REQUIRES: readonly string[] = ["settings"];

/**
 * 다른 기능의 목록을 이름 해석용으로 읽는 곳이 부르기 전에 확인할 요구(모듈 id 또는 역할). 꺼져 있으면 그 목록은 부르지 않고
 * 빈 목록으로 두어 id 원문이 보인다. 사용자가 다르게 원하면 이 값만 고친다.
 */
export const LOOKUP_REQUIRES = {
  conversations: ["conversations"],
  agents: ["definitions:agent"],
  graphs: ["definitions:graph"],
} as const satisfies Record<string, readonly string[]>;

/**
 * 프로젝트 전환기·범위 필터·태그·범위 선택이 있으려면 서버에서 켜져 있어야 하는 역할(모듈 id가 아니라 역할).
 * 꺼져 있으면 프로젝트 UI는 통째로 사라지고 나머지 화면은 그대로 동작한다. 사용자가 다르게 원하면 이 값만 고친다.
 */
export const PROJECT_REQUIRES: readonly string[] = ["projects"];
