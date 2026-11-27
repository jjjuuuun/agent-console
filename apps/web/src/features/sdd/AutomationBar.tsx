/**
 * 자동 진행 상태 줄(screen-sdd §10.2): "자동 진행 켜짐 · 진행 중 실행 n개 · 건너뜀 m개 [멈춤]" 또는 "멈춤 — 이유 [다시 시작]".
 * 표현 전용이다. 상태는 서버 값(`AutomationState`)이고 멈춤 이유 문구는 messages 표(모르는 이유는 원문). [멈춤]·[다시 시작]은 콜백으로 올린다.
 */
import { Button } from "@agent-console/ui";
import type { AutomationState } from "@agent-console/contracts/sdd";
import { useT } from "@agent-console/i18n";
import { useMaybeT, type MaybeTranslate } from "../../i18n/useMaybeT";

export interface AutomationBarProps {
  state: AutomationState;
  onStop: () => void;
  onResume: () => void;
  busy?: boolean;
  /** 폴더에 쓸 수 없는 등 조작이 막힌 이유 */
  blockedReason?: string | undefined;
}

export function stopReasonText(reason: string | null | undefined, tm: MaybeTranslate): string {
  if (reason === null || reason === undefined || reason === "") return "";
  return tm(`automation.reasons.${reason}`) ?? reason;
}

export function AutomationBar({ state, onStop, onResume, busy = false, blockedReason }: AutomationBarProps) {
  const t = useT("sdd");
  const tm = useMaybeT("sdd");
  const blocked = blockedReason !== undefined && blockedReason !== "";
  const stopped = !state.running;
  const skipped = state.skipped_keys ?? [];
  return (
    <div className="sdd-automation" role="status" data-testid="sdd-automation" data-running={state.running ? "" : undefined}>
      <span aria-hidden="true">⟳</span>
      <span>{stopped ? stopReasonText(state.stopped_reason, tm) === "" ? t("automation.stopped") : t("automation.stoppedWith", { reason: stopReasonText(state.stopped_reason, tm) }) : t("automation.status", { a: (state.active_runs ?? []).length, s: skipped.length })}</span>
      {skipped.length > 0 && stopped ? <span className="app-muted">{t("automation.skipped", { keys: skipped.join(", ") })}</span> : null}
      <Button size="sm" loading={busy} aria-disabled={blocked || undefined} title={blocked ? blockedReason : undefined} onClick={() => { if (!blocked) (stopped ? onResume : onStop)(); }}>
        {stopped ? t("automation.resume") : t("automation.stop")}
      </Button>
    </div>
  );
}
