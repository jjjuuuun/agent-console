import type { BackendProbeResult } from "@agent-console/contracts";
import { Banner } from "@agent-console/ui";
import { messages as m } from "../../app/messages";
import { FixButtons } from "../../app/fix";
import { formatRelative } from "../../lib/format";
import type { ProbeView } from "./hooks";

export interface ProbeResultBlockProps {
  probe: Pick<ProbeView, "result" | "requestError" | "finishedAtMs" | "running">;
  nowMs: number;
}

function detailLines(result: BackendProbeResult): string[] {
  return Object.entries(result.details ?? {}).map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`);
}

/** 연결 테스트 결과: 성공은 한 줄 + 확인 정보, 실패는 ① 무슨 일 ② 해결 버튼 ③ 접힌 상세. 비밀 값은 서버가 걸러 준 문장만 쓴다. */
export function ProbeResultBlock({ probe, nowMs }: ProbeResultBlockProps) {
  const t = m.backendReadiness;
  if (probe.running) return null;
  const { result, requestError } = probe;
  if (result === null && requestError === null) return null;
  const when = formatRelative(probe.finishedAtMs === null ? null : probe.finishedAtMs / 1000, nowMs);
  if (requestError !== null) {
    return (
      <Banner tone="danger" aria-label={t.probeResultLabel} data-testid="probe-result">
        <strong>{t.probeFailedTitle}</strong>
        <p className="app-muted">{t.probeRequestFailed}</p>
        <details className="app-details">
          <summary>{t.probeDetails}</summary>
          <pre className="ac-pre">{requestError.message}</pre>
        </details>
      </Banner>
    );
  }
  if (result === null) return null;
  if (result.ok) {
    const lines = detailLines(result);
    const seconds = result.latency_ms == null ? null : (result.latency_ms / 1000).toFixed(1);
    return (
      <Banner tone="success" aria-label={t.probeResultLabel} data-testid="probe-result">
        <strong>{seconds === null ? t.probeOkNoTime : t.probeOk(seconds)}</strong>
        {result.message ? <p className="app-muted">{result.message}</p> : null}
        {lines.length > 0 ? <ul className="app-readiness-details">{lines.map((l) => <li key={l}>{l}</li>)}</ul> : null}
        <p className="app-muted">{t.probeCheckedAt(when)}</p>
      </Banner>
    );
  }
  const lines = [...(result.reason ? [`${t.probeReason}: ${result.reason}`] : []), ...detailLines(result)];
  return (
    <Banner tone="danger" aria-label={t.probeResultLabel} data-testid="probe-result">
      <strong>{result.message || t.probeFailedTitle}</strong>
      <FixButtons fix={{ actions: result.fixes ?? [] }} />
      {lines.length > 0 ? (
        <details className="app-details">
          <summary>{t.probeDetails}</summary>
          <pre className="ac-pre">{lines.join("\n")}</pre>
        </details>
      ) : null}
    </Banner>
  );
}
