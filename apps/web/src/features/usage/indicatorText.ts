import { usageIndicatorMessages as t, usageMessages as u } from "./messages";
import { formatResetsPhrase } from "./resetDisplay";
import { INDICATOR_TONES } from "./usageConfig";
import type { IndicatorItem } from "./usageLib";

/** 1234 -> "1.2k", 3_835_480_500 -> "3.8G" (토큰 수 짧은 표기). */
export function compactCount(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1).replace(/\.0$/, "")}G`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(n);
}

/** 항목의 값 글자(블록 모양). 값이 없으면 "–". */
export function itemValueText(item: IndicatorItem, mode: string): string {
  switch (item.kind) {
    case "ratio":
      return mode === "used" ? t.usedText(item.used ?? 0) : t.remainingText(item.remaining ?? 0);
    case "status":
      return u.status[item.status ?? ""]?.label ?? item.status ?? u.common.none;
    case "tokens":
      return `토큰 ${compactCount(item.tokens ?? 0)}`;
    default:
      return u.common.none;
  }
}

/** 레일(좁은) 모양의 값 글자: 퍼센트 숫자만, 상태는 점. */
export function itemRailValue(item: IndicatorItem, mode: string): string {
  switch (item.kind) {
    case "ratio":
      return `${mode === "used" ? Math.min(100, item.used ?? 0) : (item.remaining ?? 0)}%`;
    case "status":
      return "●";
    case "tokens":
      return compactCount(item.tokens ?? 0);
    default:
      return u.common.none;
  }
}

/** 항목 하나를 한 구절로(스크린리더·제목용). */
export function itemSpoken(item: IndicatorItem, mode: string, nowSec: number): string {
  if (item.kind === "none") return t.itemOther(item.name, item.observed ? u.cards.noValue : t.notObserved);
  if (item.kind === "status") return t.itemOther(item.name, `${itemValueText(item, mode)}, ${u.cards.noRatio}`);
  if (item.kind === "tokens") return t.itemOther(item.name, `${itemValueText(item, mode)} ${t.tokensDetail}`);
  const resets = item.reset === "future" && item.resetsAt != null ? formatResetsPhrase(item.resetsAt, nowSec, u.cards.resets, u.cards.resetsOnDate).text : "";
  return t.itemRatio(item.name, mode === "used" ? t.spokenUsed(item.used ?? 0) : t.spokenRemaining(item.remaining ?? 0), resets);
}

/** 항목의 표식 문장들(오래됨·초기화 지남·규칙 적용). */
export function itemFlags(item: IndicatorItem): string[] {
  const out: string[] = [];
  if (item.stale) out.push(t.stale);
  if (item.reset === "passed") out.push(t.resetsPassed);
  if (item.overLimit) out.push(t.overLimit(item.used ?? 0));
  // 정상 톤(글리프 없음)은 낭독하지 않는다: 항상 켜진 기본 규칙이 매 항목에 소음이 되지 않게
  if (item.rule && INDICATOR_TONES[item.rule.tone]?.glyph !== "") out.push(t.ruleApplied(Math.round(item.rule.at * 100), t.tones[item.rule.tone] ?? item.rule.tone));
  return out;
}

/** 링크 `aria-label`: 모든 표시 항목을 한 문장으로. */
export function indicatorAriaLabel(items: readonly IndicatorItem[], mode: string, nowSec: number, extra: readonly string[] = []): string {
  const body = items.map((i) => [itemSpoken(i, mode, nowSec), ...itemFlags(i)].join(". ")).join(". ");
  return `${t.summary(body)}. ${[...extra, t.openLabel].join(". ")}`;
}

/** 문서 제목 끝에 붙일 짧은 글. 사용률 값이 아니면 null. */
export function titleSuffixOf(item: IndicatorItem | undefined, mode: string): string | null {
  if (item === undefined || item.kind !== "ratio") return null;
  return `${item.name} ${mode === "used" ? Math.min(100, item.used ?? 0) : (item.remaining ?? 0)}%`;
}
