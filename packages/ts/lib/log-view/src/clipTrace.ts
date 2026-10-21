import type { Trace, TraceSpan } from "@agent-console/contracts";

/**
 * 위임 흐름을 재생 시각까지 자른다(순수 함수, `trace-view`를 import하지 않고 계약 `Trace` 타입만 쓴다).
 * - `time`(epoch 초) 이전에 시작한 span만 남긴다. 시작 시각을 모르는 span은 뺀다.
 * - 아직 끝나지 않은 span(끝 시각이 없거나 `time` 이후)은 `status="running"`·`ended_at=null`로 바꾼다.
 * - 양 끝 span이 모두 남은 링크만 남긴다. 원본은 바꾸지 않는다.
 * `time`이 null/undefined면(재생 위치가 끝) 원본을 그대로 돌려준다.
 */
export function clipTraceAt(trace: Trace, time: number | null | undefined): Trace {
  if (time == null) return trace;
  const spans: TraceSpan[] = [];
  for (const s of trace.spans ?? []) {
    if (s.started_at == null || s.started_at > time) continue;
    const open = s.ended_at == null || s.ended_at > time;
    spans.push(open ? { ...s, status: "running", ended_at: null } : s);
  }
  const ids = new Set(spans.map((s) => s.id));
  const links = (trace.links ?? []).filter((l) => ids.has(l.source) && ids.has(l.target));
  return { ...trace, spans, links };
}
