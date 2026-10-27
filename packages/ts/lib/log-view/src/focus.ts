/**
 * 로그 화면의 주요 조절 장치로 포커스를 옮기는 공개 API. 앱이 log-view 내부 클래스 이름을
 * `querySelector`로 직접 읽지 않게 한다(클래스는 이 파일 안에서만 안다).
 */

/** 포커스 대상: 필터 줄의 첫 단추, 필터 추가 단추, 분류 칩 줄의 첫 칩 */
export type LogFocusTarget = "filterBar" | "addFilter" | "categoryChips";

const SELECTORS: Record<LogFocusTarget, string> = {
  filterBar: ".ac-lv-filterbar button",
  addFilter: ".ac-lv-addwrap button",
  categoryChips: ".ac-lv-catchips button",
};

export interface FocusLogControlOptions {
  /** 찾을 범위(기본 `document`) */
  root?: ParentNode;
  /** true면 포커스 대신 누른다(필터 추가 메뉴 열기) */
  activate?: boolean;
}

/**
 * 대상 조절 장치로 포커스를 옮긴다(또는 `activate`면 누른다).
 * @returns 대상을 찾았으면 true
 */
export function focusLogControl(target: LogFocusTarget, options: FocusLogControlOptions = {}): boolean {
  const root = options.root ?? document;
  const el = root.querySelector<HTMLElement>(SELECTORS[target]);
  if (el === null) return false;
  if (options.activate === true) el.click();
  else el.focus();
  return true;
}
