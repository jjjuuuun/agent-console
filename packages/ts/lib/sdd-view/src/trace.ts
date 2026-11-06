import type { TraceRow } from "@agent-console/contracts/sdd";

/** 빈 곳 코드 → 문구 키(`gap.<코드>`). 표에 없으면 호출자가 코드 원문을 쓴다. */
export function gapLabelKey(code: string): string {
  return `gap.${code}`;
}

/** 검증 결과 코드 → 문구 키(`verification.<코드>`). */
export function verificationLabelKey(code: string): string {
  return `verification.${code}`;
}

/** 빈 곳이 있는 행인가. */
export function hasGaps(row: Pick<TraceRow, "gaps">): boolean {
  return (row.gaps ?? []).length > 0;
}

/** 빈 곳만 남긴다(`onlyGaps`가 거짓이면 그대로). 순서는 유지한다. */
export function filterTraceRows(rows: readonly TraceRow[], onlyGaps: boolean): TraceRow[] {
  return onlyGaps ? rows.filter(hasGaps) : [...rows];
}
