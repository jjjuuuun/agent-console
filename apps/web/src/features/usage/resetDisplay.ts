import { formatDateTime } from "../../lib/format";
import { usageMessages as u } from "./messages";
import { RESET_DATE_AFTER_SECONDS } from "./usageConfig";
import { formatRemaining } from "./usageLib";

/** 초기화 시각이 기준(`farAfterSeconds`)보다 먼 미래인가. */
export function isFarReset(resetsAt: number, nowSec: number, farAfterSeconds: number = RESET_DATE_AFTER_SECONDS): boolean {
  return resetsAt - nowSec > farAfterSeconds;
}

/**
 * 미래 `resets_at`의 표시 구절. 가까우면 남은 시간("초기화까지 2시간"), 기준보다 멀면 날짜("초기화 2026. 11. 30.").
 * 가까운 경우만 절대 시각이 따로 붙을 수 있게 `far`를 함께 돌려준다.
 * @param relative 남은 시간 문구 만들기 (예: `u.cards.resets`)
 * @param onDate 날짜 문구 만들기 (예: `u.cards.resetsOnDate`)
 */
export function formatResetsPhrase(
  resetsAt: number,
  nowSec: number,
  relative: (remaining: string) => string,
  onDate: (date: string) => string,
  farAfterSeconds: number = RESET_DATE_AFTER_SECONDS,
): { text: string; far: boolean } {
  if (isFarReset(resetsAt, nowSec, farAfterSeconds)) return { text: onDate(formatDateTime(resetsAt)), far: true };
  return { text: relative(formatRemaining(resetsAt - nowSec)), far: false };
}

/** 카드·팝오버용 자세한 구절: 가까우면 "초기화까지 2시간 (절대 시각)", 기준보다 멀면 날짜만. */
export function futureResetsText(resetsAt: number, nowSec: number): string {
  const p = formatResetsPhrase(resetsAt, nowSec, u.cards.resets, u.cards.resetsOnDate);
  return p.far ? p.text : `${p.text} ${u.cards.resetsAt(formatDateTime(resetsAt))}`;
}
