import { useMemo, useState } from "react";
import { ApiError } from "@agent-console/api-client";
import type { Run } from "@agent-console/contracts";
import { Banner, Button, Dialog, Spinner, StatusChip } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { useApiQuery } from "../../app/queries";
import { describeError } from "../../app/errors";
import { chatMessages } from "./chatMessages";
import { anyRerunnable, defaultResumeSelection, hasRunningSelected, issuesByNode } from "./lib/resume";

const t = chatMessages.resume;

export interface ResumeDialogProps {
  open: boolean;
  runId: string;
  onClose: () => void;
  /** 새 Run이 시작되었다(턴 목록을 다시 읽는다) */
  onResumed: (run: Run) => void;
  /** 409/404처럼 목록이 낡았을 때 서버 메시지를 알린다 */
  onNotify: (message: string) => void;
}

/**
 * 끊긴 턴의 [이 지점부터 다시 실행] 다이얼로그. 노드 목록은 `GET /runs/{id}/resume-options`,
 * 다시 실행은 `POST /runs/{id}/resume`. 기본 선택·가능 여부는 서버 값(`rerunnable`, `status`)으로만 정한다.
 */
export function ResumeDialog({ open, runId, onClose, onResumed, onNotify }: ResumeDialogProps) {
  const { rest } = useApi();
  const options = useApiQuery(["chat", "resume-options", runId], (r) => r.getResumeOptions(runId), { enabled: open, gcTime: 0, staleTime: 0 });
  const nodes = options.data?.nodes ?? null;
  const loadError = options.isError ? describeError(options.error, t.loadFailed).message : null;
  const [picked, setPicked] = useState<ReadonlySet<string> | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const list = useMemo(() => nodes ?? [], [nodes]);
  // 사용자가 건드리기 전에는 서버 값으로 계산한 기본 선택
  const selected = picked ?? defaultResumeSelection(list);
  const canRun = selected.size > 0 && !busy;

  const toggle = (id: string, on: boolean) =>
    setPicked(() => {
      const next = new Set(selected);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  const allIds = list.filter((n) => n.rerunnable).map((n) => n.node_id);

  const run = async () => {
    if (!canRun) return;
    setBusy(true);
    setSubmitError(null);
    try {
      const started = await rest.resumeRun(runId, list.filter((n) => selected.has(n.node_id)).map((n) => n.node_id));
      onResumed(started);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        const byNode = issuesByNode(e.details);
        if (Object.keys(byNode).length > 0) {
          setRowErrors(byNode);
          setPicked(new Set([...selected].filter((id) => byNode[id] === undefined)));
        } else setSubmitError(describeError(e, t.failed).message);
      } else if (e instanceof ApiError && (e.status === 409 || e.status === 404)) {
        onNotify(describeError(e, t.failed).message);
        setPicked(null);
        setRowErrors({});
        void options.refetch();
      } else setSubmitError(describeError(e, t.failed).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      title={t.title}
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose} disabled={busy}>{t.cancel}</Button>
          {submitError !== null ? <Button onClick={() => void run()} disabled={!canRun}>{t.retry}</Button> : null}
          <Button variant="primary" loading={busy} disabled={!canRun} onClick={() => void run()} title="Ctrl+Enter">
            {busy ? t.running : t.run}
          </Button>
        </>
      }
    >
      <div
        className="chat-resume"
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            void run();
          } else if ((e.key === "a" || e.key === "A") && (e.ctrlKey || e.metaKey) && !(e.target as HTMLElement).matches("input[type='text'], textarea")) {
            e.preventDefault();
            setPicked(new Set(allIds));
          }
        }}
      >
        <p className="app-muted">{t.intro}</p>
        {options.isPending && loadError === null ? (
          <div role="status" aria-busy="true"><Spinner label={t.loading} /></div>
        ) : loadError !== null ? (
          <Banner tone="danger" actions={<Button size="sm" onClick={() => void options.refetch()}>{t.retry}</Button>}>{loadError}</Banner>
        ) : !anyRerunnable(list) ? (
          <p role="status" className="app-muted">{t.empty}</p>
        ) : (
          <>
            <ul className="chat-resume-list" aria-label={t.listLabel} style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "var(--ac-space-2)" }}>
              {list.map((n) => {
                const label = n.label ?? n.node_id;
                const statusText = t.nodeStatus[n.status] ?? t.nodeStatusFallback(n.status);
                const error = rowErrors[n.node_id];
                return (
                  <li key={n.node_id} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "var(--ac-space-2)" }}>
                    <label className="app-check" aria-disabled={!n.rerunnable || undefined}>
                      <input
                        type="checkbox"
                        checked={selected.has(n.node_id)}
                        disabled={!n.rerunnable || busy}
                        aria-describedby={n.rerunnable ? undefined : `resume-why-${n.node_id}`}
                        onChange={(e) => toggle(n.node_id, e.target.checked)}
                      />
                      <span>{label}</span>
                    </label>
                    <StatusChip status={n.status} label={statusText} />
                    {n.rerunnable ? null : (
                      <span id={`resume-why-${n.node_id}`} className="app-muted">
                        {t.notRerunnable} ({t.notRerunnableReason})
                      </span>
                    )}
                    {error === undefined ? null : <span role="alert" style={{ color: "var(--ac-danger)" }}>{error}</span>}
                  </li>
                );
              })}
            </ul>
            {hasRunningSelected(list, selected) ? <Banner tone="warning">{t.costWarning}</Banner> : null}
            <p className="app-muted lib-field-note">{t.upstreamNote}</p>
          </>
        )}
        {submitError === null ? null : <Banner tone="danger">{submitError}</Banner>}
      </div>
    </Dialog>
  );
}
