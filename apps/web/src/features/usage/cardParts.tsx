import type { UsageWindowSnapshot } from "@agent-console/contracts";
import { Tooltip } from "@agent-console/ui";
import { usageMessages as t } from "./messages";
import { formatRatio, formatTokens, type WindowGroup } from "./usageLib";

/** 상태 값 → 라벨·톤·접근성 이름(메시지 표). 표에 없는 값은 원문. */
export function statusView(status: string | null | undefined) {
  if (status == null || status === "") return undefined;
  const known = t.status[status];
  return { label: known?.label ?? status, tone: known?.tone, aria: known?.aria };
}

export type ValueKind = "ratio" | "status" | "tokens" | "none";

export interface CardValue {
  kind: ValueKind;
  /** 헤드라인(`N% 사용` / 상태 라벨 / `사용률 없음` / 값 없음 문구) */
  headline: string;
  /** 접근성 이름에 쓰는 값 글자 */
  aria: string;
  /** 보조 줄의 `토큰 {n}` (비율이나 상태 옆에 토큰이 함께 올 때, 또는 토큰만 올 때) */
  tokensLine?: string;
  /** 칩으로 보일 상태(비율이 있을 때만; `success` 톤은 숨김) */
  chip?: { label: string; tone: NonNullable<ReturnType<typeof statusView>>["tone"] };
  /** 글자로 보이지 않고 ⓘ·스크린리더로만 가는 줄 */
  hidden: string[];
}

/** 스냅샷 하나의 표시 값(순수). 값을 지어내지 않고, 정보가 없는 줄은 `hidden`으로 모은다. */
export function describeValue(s: UsageWindowSnapshot, windowName: string, fellBack = false): CardValue {
  const st = statusView(s.status);
  const hidden: string[] = [];
  const tokensLine = s.used_tokens != null ? t.cards.tokens(formatTokens(s.used_tokens)) : undefined;
  let v: Omit<CardValue, "hidden">;
  if (s.used_ratio != null) {
    const headline = t.cards.headline(formatRatio(s.used_ratio));
    v = { kind: "ratio", headline, aria: headline, ...(tokensLine ? { tokensLine } : {}), ...(st && st.tone !== "success" ? { chip: { label: st.label, tone: st.tone } } : {}) };
  } else if (st) {
    v = { kind: "status", headline: st.label, aria: st.aria ? st.aria(windowName) : st.label, ...(tokensLine ? { tokensLine } : {}) };
    hidden.push(t.cards.hidden.statusOnly);
  } else if (tokensLine) {
    v = { kind: "tokens", headline: t.cards.noRatioHeadline, aria: `${t.cards.noRatioHeadline}, ${tokensLine}`, tokensLine };
    hidden.push(t.cards.hidden.noLimit);
  } else v = { kind: "none", headline: t.cards.noValue, aria: t.cards.noValue };
  if (s.resets_at == null || !Number.isFinite(s.resets_at)) hidden.push(t.cards.hidden.resetsUnknown);
  if (fellBack) hidden.push(t.cards.hidden.ruleFallback);
  return { ...v, hidden };
}

/** 정보 없는 줄을 접는 ⓘ. 줄이 없으면 아무것도 그리지 않는다. 글자는 툴팁(시각)과 `.ac-sr-only`(스크린리더)로 간다. */
export function InfoHint({ lines, placement = "top" }: { lines: readonly string[]; placement?: "top" | "bottom" }) {
  if (lines.length === 0) return null;
  return (
    <span className="usage-info">
      <Tooltip placement={placement} align="end" content={lines.map((l) => <span key={l} className="usage-info-line">{l}</span>)}>
        <button type="button" className="usage-info-btn" aria-label={t.cards.info}>
          <span aria-hidden="true">ⓘ</span>
        </button>
      </Tooltip>
      <span className="ac-sr-only">{lines.join(". ")}</span>
    </span>
  );
}

/** 격자 아래 기준 문구의 종류. 설정 순서가 있으면 configured, 아니면 공식 우선 규칙이 쓰였는지로 정한다. */
export function basisKind(groups: readonly WindowGroup[], hasOrder: boolean): "configured" | "recentOfficial" | "recent" {
  if (hasOrder) return "configured";
  return groups.some((g) => g.rule === "recent-official") ? "recentOfficial" : "recent";
}
