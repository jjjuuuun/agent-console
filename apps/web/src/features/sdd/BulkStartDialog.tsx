/**
 * 준비된 작업 한꺼번에 시작(screen-sdd §4.3). 준비된 작업 목록(체크로 가린다) + 동작 고르기(고른 작업들의 합집합, 연동 동작 라벨 그대로)
 * + 제출 뒤 작업별 결과(`started`·`blocked`·`failed`). 모두 시작하면 닫고 토스트, 하나라도 못 했으면 닫지 않고 이유를 보인다.
 * 동작 이름·연동 id는 서버 데이터다. 상한(`max_bulk_start`)은 서버 정보에서 받는다.
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import { KNOWN_TASK_ACTION_STATUSES } from "@agent-console/contracts/constants";
import { Banner, Button, Dialog, useToast } from "@agent-console/ui";
import type { ParsedTask, TaskActionResult } from "@agent-console/contracts/sdd";
import { ROUTE_ROLES, routePath } from "../library";
import { ListSkeleton } from "./parts";
import { sddKeys, useBulkActions, useSddSpace } from "./useSddApi";
import { useT } from "@agent-console/i18n";
import { SddToast } from "./SddToast";

export interface BulkStartDialogProps {
  open: boolean;
  onClose: () => void;
  specId: string;
  /** 시작할 수 있는 준비된 작업(끝나지 않은 것) */
  readyTasks: readonly ParsedTask[];
  /** 선택에 섞인 준비되지 않은 작업(목록에 muted로 보이고 제출 개수에서 빠진다) */
  skippedTasks?: readonly ParsedTask[];
  /** 한 번에 시작할 수 있는 상한(서버 한도). 모르면 undefined */
  limit?: number | undefined;
  /** 실행이 막힌 이유(있으면 제출 단추가 `aria-disabled`) */
  blockedReason?: string | undefined;
}

export function BulkStartDialog({ open, onClose, specId, readyTasks, skippedTasks = [], limit, blockedReason }: BulkStartDialogProps) {
  const t = useT("sdd");
  const space = useSddSpace();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [picked, setPicked] = useState<ReadonlySet<string> | null>(null);
  const [actionKey, setActionKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<readonly TaskActionResult[] | null>(null);

  const keys = useMemo(() => readyTasks.map((t) => t.key), [readyTasks]);
  const selected = picked ?? new Set(limit === undefined ? keys : keys.slice(0, limit));
  const chosen = keys.filter((k) => selected.has(k));
  const bulk = useBulkActions(specId, chosen, open);
  const actions = bulk.data?.actions ?? [];
  const usable = actions.filter((a) => (a.disabled ?? null) === null);
  const actionId = (a: { integration: string; id: string }) => `${a.integration}\u0000${a.id}`;
  const current = usable.find((a) => actionId(a) === actionKey) ?? usable[0];
  const overLimit = limit !== undefined && chosen.length > limit;
  const blocked = (blockedReason !== undefined && blockedReason !== "") || chosen.length === 0 || current === undefined || overLimit;
  // 시작하면 준비 목록에서 빠지므로, 시작 때의 제목을 따로 보관해 결과 줄에서 쓴다.
  const [titles, setTitles] = useState<ReadonlyMap<string, string | undefined>>(new Map());
  const titleOf = (key: string) => titles.get(key) ?? readyTasks.find((t) => t.key === key)?.title ?? key;

  const toggle = (key: string, on: boolean) => {
    const next = new Set(selected);
    if (on) next.add(key);
    else next.delete(key);
    setPicked(next);
  };

  const submit = async () => {
    if (blocked || current === undefined || busy) return;
    setBusy(true);
    setError(null);
    setTitles(new Map(readyTasks.map((t) => [t.key, t.title] as const)));
    try {
      const res = await space.client.bulkStartTasks(specId, { task_keys: chosen as [string, ...string[]], action: { integration: current.integration, id: current.id } });
      const items = res.items ?? [];
      void qc.invalidateQueries({ queryKey: sddKeys.root });
      const ok = items.filter((i) => i.status === KNOWN_TASK_ACTION_STATUSES.STARTED).length;
      if (items.length > 0 && ok === items.length) {
        onClose();
        toast({ tone: "success", text: <SddToast render={(t) => t("bulk.allStarted", { count: ok })} />, durationMs: 8000, action: { label: <SddToast render={(t) => t("bulk.openRuns")} />, onClick: () => void navigate(routePath(ROUTE_ROLES.runs)) } });
      } else {
        setResults(items);
      }
    } catch (e) {
      setError(e instanceof ApiError && e.message !== "" ? e.message : t("bulk.failedAll"));
    } finally {
      setBusy(false);
    }
  };

  const okCount = (results ?? []).filter((i) => i.status === KNOWN_TASK_ACTION_STATUSES.STARTED).length;

  return (
    <Dialog
      open={open}
      title={t("bulk.title", { n: readyTasks.length + skippedTasks.length, m: chosen.length })}
      onClose={onClose}
      actions={
        results === null ? (
          <>
            <Button onClick={onClose}>{t("cancel")}</Button>
            <Button variant="primary" loading={busy} aria-disabled={blocked || undefined} title={blockedReason} onClick={() => void submit()}>
              {busy ? t("bulk.starting") : t("bulk.submit", { m: chosen.length })}
            </Button>
          </>
        ) : (
          <Button onClick={onClose}>{t("bulk.close")}</Button>
        )
      }
    >
      <div className="sdd-form" data-testid="sdd-bulk">
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        {overLimit ? <Banner tone="warning">{t("bulk.limit", { count: limit as number })}</Banner> : null}
        {results === null ? (
          <>
            <fieldset className="sdd-field" disabled={busy}>
              <legend className="sdd-label">{t("bulk.action")}</legend>
              {bulk.isPending && chosen.length > 0 ? <ListSkeleton rows={2} /> : null}
              {bulk.isSuccess && usable.length === 0 ? <p className="app-muted" role="status">{t("bulk.actionNone")}</p> : null}
              <div className="sdd-radios">
                {actions.map((a) => {
                  const disabled = (a.disabled ?? null) !== null;
                  return (
                    <label key={actionId(a)} className="sdd-radio" data-checked={current !== undefined && actionId(current) === actionId(a) ? "" : undefined}>
                      <input type="radio" name="sdd-bulk-action" disabled={disabled} checked={current !== undefined && actionId(current) === actionId(a)} onChange={() => setActionKey(actionId(a))} />
                      <span className="sdd-radio-body">
                        <span className="sdd-radio-title ac-ellipsis">{a.label}</span>
                        {disabled ? <span className="app-muted">{a.disabled?.message}</span> : null}
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <fieldset className="sdd-field" disabled={busy}>
              <legend className="sdd-label">{t("bulk.tasks")}</legend>
              <ul className="sdd-files" aria-label={t("bulk.tasks")}>
                {readyTasks.map((t) => (
                  <li key={t.key} className="sdd-bulk-row">
                    <label className="ac-choice">
                      <input type="checkbox" checked={selected.has(t.key)} onChange={(e) => toggle(t.key, e.target.checked)} />
                      <span className="sdd-mono">{t.key}</span>
                      <span className="ac-ellipsis">{t.title ?? t.key}</span>
                    </label>
                  </li>
                ))}
                {skippedTasks.map((task) => (
                  <li key={task.key} className="sdd-bulk-row app-muted" data-skipped="">
                    <span className="sdd-mono">{task.key}</span> <span className="ac-ellipsis">{task.title ?? task.key}</span> <span>{t("bulk.skipped")}</span>
                  </li>
                ))}
              </ul>
            </fieldset>
            <p className="sdd-note">{t("bulk.hint")}</p>
          </>
        ) : (
          <>
            <p role="status">{t("bulk.summary", { m: results.length, ok: okCount })}</p>
            <ul className="sdd-files" aria-label={t("bulk.tasks")}>
              {results.map((r, idx) => {
                const key = r.task_key ?? `#${idx}`;
                const started = r.status === KNOWN_TASK_ACTION_STATUSES.STARTED;
                const runId = r.run_id ?? undefined;
                return (
                  <li key={key} className="sdd-bulk-row" data-result={r.status}>
                    <span className="sdd-mono">{key}</span> <span className="ac-ellipsis">{titleOf(key)}</span>{" "}
                    {started ? (
                      <>
                        <span>{t("bulk.started")}</span>{" "}
                        {runId === undefined ? null : <button type="button" className="app-link-btn" onClick={() => void navigate(`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(runId)}`)}>{t("bulk.openRun")}</button>}
                      </>
                    ) : (
                      <span className="sdd-danger-note" role="alert">{r.issue?.message ?? r.status}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </Dialog>
  );
}
