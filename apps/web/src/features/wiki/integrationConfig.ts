/**
 * 다른 화면과의 연결 표(`docs/design/screen-wiki.md` §11). 수치·저장소 키만 있고 위키 이름·동작 이름·모듈 id는 없다.
 * 위젯 이름(`wiki-ref`)은 서버 스키마가 정하는 데이터이므로 앱 조립 층(`links/configWidgets`)의 등록 표에 있다.
 */

/** 실행 상세 "고친 위키 페이지 N" 칩과 팝오버. */
export const RUN_CHANGES = {
  /** 한 번에 받는 변경 수 = 칩 숫자 상한("100+") */
  cap: 100,
  /** 팝오버 행 높이(px) */
  rowHeight: 40,
  /** 팝오버 최대 높이 */
  maxHeight: "min(400px, 60vh)",
  /** 실행 중 실시간 알림 뒤 다시 세기까지 모으는 시간(ms) */
  debounceMs: 1000,
} as const;

/** 메모리 항목 → 위키 새 페이지. */
export const PROMOTE = {
  /** 마지막으로 쓴 위키를 프로젝트별로 기억하는 localStorage 접두(뒤에 프로젝트 id) */
  lastWikiStorage: "ac.wiki.lastwiki.",
  /** 제목(본문 첫 줄) 최대 글자 수 */
  titleMax: 80,
  /** 토스트 표시 시간(ms) */
  toastMs: 8000,
} as const;

/** 위키 고르기 위젯. */
export const WIKI_REF = {
  /** 목록 질의 재사용 시간(ms) */
  staleMs: 15_000,
} as const;
