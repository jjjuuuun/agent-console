/**
 * 자동 진행 상태 줄(screen-sdd §10.2): "자동 진행 켜짐 · 진행 중 실행 n개 · 건너뜀 m개 [멈춤]" 또는 "멈춤 — 이유 [다시 시작]".
 * 표현 전용이다. 상태는 서버 값(`AutomationState`)이고 멈춤 이유 문구는 messages 표(모르는 이유는 원문). [멈춤]·[다시 시작]은 콜백으로 올린다.
 */
import { Button } from "@agent-console/ui";
import type { AutomationState } from "@agent-console/contracts/sdd";
import { sddMessages as m } from "./messages";

export interface AutomationBarProps {
  state: AutomationState;
  onStop: () => void;
  onResume: () => void;
  busy?: boolean;
  /** 폴더에 쓸 수 없는 등 조작이 막힌 이유 */
  blockedReason?: string | undefined;
}

export function stopReasonText(reason: string | null | undefined): string {
  if (reason === null || reason === undefined || reason === "") return "";
  return m.automation.reasons[reason] ?? reason;
}

export function AutomationBar({ state, onStop, onResume, busy = false, blockedReason }: AutomationBarProps) {
  const blocked = blockedReason !== undefined && blockedReason !== "";
  const stopped = !state.running;
  const skipped = state.skipped_keys ?? [];
  return (
    <div className="sdd-automation" role="status" data-testid="sdd-automation" data-running={state.running ? "" : undefined}>
      <span aria-hidden="true">⟳</span>
      <span>{stopped ? m.automation.stopped(stopReasonText(state.stopped_reason)) : m.automation.status((state.active_runs ?? []).length, skipped.length)}</span>
      {skipped.length > 0 && stopped ? <span className="app-muted">{m.automation.skipped(skipped.join(", "))}</span> : null}
      <Button size="sm" loading={busy} aria-disabled={blocked || undefined} title={blocked ? blockedReason : undefined} onClick={() => { if (!blocked) (stopped ? onResume : onStop)(); }}>
        {stopped ? m.automation.resume : m.automation.stop}
      </Button>
    </div>
  );
}
