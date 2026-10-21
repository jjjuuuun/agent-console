import { delegationMessages as t } from "./messages";

/**
 * 서버 값(0부터)을 사람이 세는 번호로 바꾸는 종류. 시도(`attempt`)는 서버 값이 이미 1부터라 여기에 없다
 * (명세는 "0이 아니면 시도 n+1"이지만 엔진이 1부터 세어 그대로 쓴다. 5R.17 보고).
 */
export type OrdinalKind = "iteration" | "call";

/**
 * 회차·호출·시도 번호의 화면 문구. 서버 값은 0부터이고 화면은 1부터 센다(D1). **+1 변환은 이 함수 한 곳**이다.
 * JSON·URL·이벤트 payload·테스트 픽스처는 서버 값 그대로 쓴다.
 */
export function formatRunOrdinal(value: number, kind: OrdinalKind): string {
  const n = Math.max(0, Math.trunc(value)) + 1;
  if (kind === "call") return t.run.call(n);
  return t.run.iteration(n);
}

/** 번호만(문구 없이) 화면 값으로. 배지 `#3`·`×2`처럼 조각을 직접 만들 때. */
export function displayNumber(value: number): number {
  return Math.max(0, Math.trunc(value)) + 1;
}
