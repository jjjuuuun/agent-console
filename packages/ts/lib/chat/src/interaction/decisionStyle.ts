import type { CSSProperties } from "react";

/** `tokens.md` 5.5 "결정 버튼 의미 토큰" 이름. 이 표의 이름만 색으로 인정한다(임의 CSS 색·모르는 이름은 무시). */
export const DECISION_COLOR_TOKENS = ["accent", "success", "danger", "warning", "info", "neutral"] as const;
export type DecisionColorToken = (typeof DECISION_COLOR_TOKENS)[number];

export interface DecisionHints {
  color?: string | null;
  icon?: string | null;
  dashed?: boolean | null;
}

export function isDecisionColorToken(v: unknown): v is DecisionColorToken {
  return typeof v === "string" && (DECISION_COLOR_TOKENS as readonly string[]).includes(v);
}

const TOKEN_VARS: Record<DecisionColorToken, { border: string; bg: string }> = {
  accent: { border: "--ac-accent", bg: "--ac-accent-bg" },
  success: { border: "--ac-success", bg: "--ac-success-bg" },
  danger: { border: "--ac-danger", bg: "--ac-danger-bg" },
  warning: { border: "--ac-warning", bg: "--ac-warning-bg" },
  info: { border: "--ac-info", bg: "--ac-info-bg" },
  neutral: { border: "--ac-border-strong", bg: "--ac-surface-3" },
};

/**
 * 결정 버튼 모양. `ui_hints`가 없으면 모두 같은 기본 스타일. 글자색은 항상 `--ac-text`.
 * 색이 지정되면 굵기 600 + 테두리 2px. 선택된 버튼은 힌트와 무관하게 2px accent 테두리.
 */
export function decisionButtonStyle(hints: DecisionHints | null | undefined, selected: boolean): { style: CSSProperties; dataColor?: DecisionColorToken } {
  const color = isDecisionColorToken(hints?.color) ? hints.color : undefined;
  const borderStyle = hints?.dashed ? "dashed" : "solid";
  let borderColor = "var(--ac-border-strong)";
  let borderWidth = 1;
  let background = "transparent";
  let fontWeight: CSSProperties["fontWeight"];
  if (color) {
    const vars = TOKEN_VARS[color];
    borderColor = `var(${vars.border})`;
    borderWidth = 2;
    background = `var(${vars.bg})`;
    fontWeight = 600;
  }
  if (selected) {
    borderColor = "var(--ac-accent)";
    borderWidth = 2;
  }
  // 단축 속성(border)을 쓰지 않는다: 점선 여부 같은 부분 변경이 안전하다.
  const style: CSSProperties = {
    color: "var(--ac-text)",
    background,
    borderWidth,
    borderStyle,
    borderColor,
    borderRadius: "var(--ac-radius-md)",
    padding: "var(--ac-space-1) var(--ac-space-3)",
    minHeight: "var(--ac-control-md, 28px)",
    fontFamily: "inherit",
    fontSize: "inherit",
    fontWeight,
    cursor: "pointer",
  };
  return { style, dataColor: color };
}
