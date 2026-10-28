/** 완전 삭제 확인(체크를 해야 켜진다, 기본 포커스는 [취소])과 범위 비우기(2단계: 범위 이름 입력). */
import { useRef, useState } from "react";
import { Banner, Button, Choice, Dialog } from "@agent-console/ui";
import type { MemoryEntry, MemoryEntrySummary, MemoryScopeRef, MemoryScopeSummary } from "@agent-console/contracts/memory";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { relativeTime } from "./format";
import { MEMORY_LIMITS } from "./memoryConfig";
import { memoryMessages as t } from "./messages";

export interface PurgeDialogProps {
  entry: MemoryEntry | MemoryEntrySummary;
  scopeLabel: string;
  /** 지울 버전 수(모르면 항목 버전 수로 센다) */
  versions: number;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function PurgeDialog({ entry, scopeLabel, versions, busy, onCancel, onConfirm }: PurgeDialogProps) {
  const [ok, setOk] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog
      open
      size="md"
      title={t.purge.title}
      onClose={onCancel}
      initialFocus={cancelRef}
      actions={
        <>
          <Button ref={cancelRef} onClick={onCancel}>{t.cancel}</Button>
          <Button variant="danger" disabled={!ok} loading={busy} onClick={onConfirm}>{t.purge.submit}</Button>
        </>
      }
    >
      <Banner tone="danger">{t.purge.body(versions)}</Banner>
      <p className="mem-purge-summary">{t.purge.summary(entry.key, scopeLabel, relativeTime(entry.updated_at))}</p>
      <Choice checked={ok} onChange={(e) => setOk(e.target.checked)}>{t.purge.confirm}</Choice>
    </Dialog>
  );
}

export interface ClearScopeDialogProps {
  scope: MemoryScopeRef;
  summary: MemoryScopeSummary | undefined;
  label: string;
  onClose: () => void;
  /** 끝났다(일부 실패 포함) — 표·나무를 다시 읽게 한다 */
  onDone: () => void;
}

type Phase = { step: 1 } | { step: 2 } | { step: 3; done: number; total: number; failed: string[]; finished: boolean };

/** 범위의 항목을 차례로 완전 삭제한다(지운 항목·보관 포함). 중간에 [중지]할 수 있고 실패는 사유 목록으로 남긴다. */
export function ClearScopeDialog({ scope, summary, label, onClose, onDone }: ClearScopeDialogProps) {
  const { rest } = useApi();
  const [phase, setPhase] = useState<Phase>({ step: 1 });
  const [typed, setTyped] = useState("");
  const stop = useRef(false);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const total = summary?.entries ?? 0;
  const archived = summary?.archived ?? 0;

  const run = async () => {
    stop.current = false;
    setPhase({ step: 3, done: 0, total, failed: [], finished: false });
    let done = 0;
    const failed: string[] = [];
    const failedIds = new Set<string>();
    let cursor: string | null = null;
    let planned = total;
    try {
      // 지우면서 처음부터 다시 읽는다(쪽 커서가 흔들리지 않게 한 쪽씩 지우고 새로 질의).
      for (;;) {
        if (stop.current) break;
        const page = await rest.listMemoryEntries({ scopes: [scope], includeArchived: true, includeDeleted: true, limit: MEMORY_LIMITS.clearPageSize, cursor });
        const items = page.items ?? [];
        planned = Math.max(planned, done + failed.length + items.length);
        if (items.length === 0) break;
        let progressed = false;
        for (const item of items) {
          if (stop.current) break;
          if (failedIds.has(item.id)) continue;
          try {
            await rest.purgeMemoryEntry(item.id);
            done += 1;
            progressed = true;
          } catch (e) {
            failedIds.add(item.id);
            failed.push(`${item.key}: ${describeError(e, t.toast.failed).message}`);
          }
          setPhase({ step: 3, done, total: planned, failed: [...failed], finished: false });
        }
        // 지운 만큼 줄어든 목록을 처음부터 다시 읽는다. 하나도 못 지웠으면 같은 쪽을 반복하지 않는다.
        cursor = null;
        if (!progressed) break;
      }
    } catch (e) {
      failed.push(describeError(e, t.toast.failed).message);
    }
    setPhase({ step: 3, done, total: planned, failed, finished: true });
    onDone();
  };

  const finished = phase.step === 3 && phase.finished;
  return (
    <Dialog
      open
      size="md"
      title={t.clear.title}
      onClose={phase.step === 3 && !finished ? () => undefined : onClose}
      initialFocus={cancelRef}
      actions={
        phase.step === 1 ? (
          <>
            <Button ref={cancelRef} onClick={onClose}>{t.cancel}</Button>
            <Button variant="danger" onClick={() => setPhase({ step: 2 })}>{t.clear.next}</Button>
          </>
        ) : phase.step === 2 ? (
          <>
            <Button ref={cancelRef} onClick={onClose}>{t.cancel}</Button>
            <Button variant="danger" disabled={typed !== label} onClick={() => void run()}>{t.clear.submit}</Button>
          </>
        ) : finished ? (
          <Button ref={cancelRef} variant="primary" onClick={onClose}>{t.close}</Button>
        ) : (
          <Button ref={cancelRef} onClick={() => (stop.current = true)}>{t.clear.stop}</Button>
        )
      }
    >
      {phase.step === 1 ? (
        <>
          <Banner tone="danger">{t.clear.step1(label, total, archived)}</Banner>
          <p className="mem-help">{t.clear.note}</p>
        </>
      ) : null}
      {phase.step === 2 ? (
        <div className="mem-field">
          <label htmlFor="mem-clear-type" className="mem-label">{t.clear.typeLabel}</label>
          <input id="mem-clear-type" className="mem-input" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
          <span className="mem-help mem-mono">{label}</span>
        </div>
      ) : null}
      {phase.step === 3 ? (
        <div role="status" aria-live="polite">
          <p>{t.clear.progress(phase.done, phase.total)}</p>
          {phase.failed.length > 0 ? (
            <>
              <p className="mem-error">{t.clear.partial(phase.done, phase.failed.length)}</p>
              <ul className="mem-issue-list">{phase.failed.slice(0, 10).map((f, i) => <li key={i}>{f}</li>)}</ul>
            </>
          ) : null}
        </div>
      ) : null}
    </Dialog>
  );
}
