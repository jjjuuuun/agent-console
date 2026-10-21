import type { LogSourceInfo } from "@agent-console/contracts";
import { formatBytes } from "../../lib/bytes";
import { formatRelative } from "../../lib/format";
import { logsMessages as t } from "./messages";

/** 출처 상태 줄의 종류(`screen-logs.md` 6.2). */
export type SourceStatusKind = "off" | "unsaved" | "before" | "ok" | "error" | "scanning";

export interface SourceStatusView {
  kind: SourceStatusKind;
  /** 칩 문구(없으면 칩 없음) */
  chip: string | undefined;
  /** 칩 옆 설명 문장들(이미 한글) */
  parts: string[];
  /** 오류 코드 원문(오류일 때) */
  code: string | undefined;
  /** 남은 양 안내(있을 때) */
  pending: string | undefined;
  /** 오류일 때 서버 코드에 대응하는 문장(없으면 일반 안내) */
  errorText: string | undefined;
}

export interface SourceStatusInput {
  info: LogSourceInfo;
  /** 설정 폼에서 현재 유효한 켜짐 값(저장 전 포함) */
  enabled: boolean;
  /** 저장 전 변경이 있는지(스위치가 서버 값과 다름) */
  dirty?: boolean;
  scanning?: boolean;
  nowMs: number;
  /** `messages.logs.error.<code>` 같은 코드별 문장 사전(없으면 일반 안내) */
  errorMessages?: Readonly<Record<string, string>>;
}

/** 출처 하나의 상태 줄 데이터. 오류 코드·남은 양은 서버 값을 그대로 쓴다. */
export function describeSourceStatus({ info, enabled, dirty = false, scanning = false, nowMs, errorMessages = t.settings.sources.errorMessages }: SourceStatusInput): SourceStatusView {
  const s = t.sourceStatus;
  const status = info.status;
  const base = { chip: undefined, parts: [], code: undefined, pending: undefined, errorText: undefined };
  // 끄는 변경도 저장 전이면 그렇게 알린다(자동 켜짐을 끄는 경우 등).
  if (!enabled) return { ...base, kind: "off", parts: dirty ? [s.off, s.unsaved] : [s.off] };
  if (scanning) return { ...base, kind: "scanning", parts: [s.scanning] };
  if (dirty) return { ...base, kind: "unsaved", parts: [s.unsaved] };
  if (status?.error_code != null) {
    const code = status.error_code;
    return { ...base, kind: "error", chip: s.error, code, errorText: errorMessages[code] ?? s.noServerMessage, parts: status.last_scan_at != null ? [s.lastScan(formatRelative(status.last_scan_at, nowMs))] : [] };
  }
  if (status?.last_scan_at == null) return { ...base, kind: "before", chip: s.beforeScan, parts: [s.scanBeforeHint] };
  const pending = status.pending_bytes != null && status.pending_bytes > 0 ? s.pending(formatBytes(status.pending_bytes)) : undefined;
  return { ...base, kind: "ok", chip: s.ok, parts: [s.lastScan(formatRelative(status.last_scan_at, nowMs)), ...(status.refs != null ? [s.refs(status.refs)] : [])], pending };
}

/** 한 줄 요약(빈 상태 B의 출처별 줄). */
export function sourceStatusLine(info: LogSourceInfo, nowMs: number): string {
  const v = describeSourceStatus({ info, enabled: info.enabled, nowMs });
  return [v.chip, v.code, ...v.parts, v.pending].filter((x): x is string => x !== undefined && x !== "").join(" · ");
}
