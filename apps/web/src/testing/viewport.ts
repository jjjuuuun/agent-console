import { afterEach, beforeEach } from "vitest";

/**
 * 테스트 파일 전체의 뷰포트 폭을 정한다(happy-dom 기본은 1024). 반응형 분기(좁은 폭 드롭다운 등)가 아닌
 * 넓은 화면 동작을 확인하는 테스트가 쓴다. 끝나면 원래 폭으로 되돌린다.
 */
export function withViewportWidth(width: number): void {
  let before = 0;
  beforeEach(() => {
    before = window.innerWidth;
    window.innerWidth = width;
  });
  afterEach(() => {
    window.innerWidth = before;
  });
}
