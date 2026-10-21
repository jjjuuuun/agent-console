import { useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";
import type { Run } from "@agent-console/contracts";
import { StatusChip, Tag } from "@agent-console/ui";
import { formatDateTime, formatElapsed, formatRelative } from "../../lib/format";
import { runStatusLabels, runsMessages as t } from "./messages";
import { WAITING_RUN_STATUS, CANCELLABLE_RUN_STATUSES } from "./runsConfig";
import { inputSummary, runDurationMs, totalTokens, formatTokensShort, truncate } from "./runsLib";

export interface RunsTableProps {
  runs: readonly Run[];
  /** 지금(ms). 상대 시각·진행 중 경과 계산용(주입) */
  nowMs: number;
  graphName(id: string): string | undefined;
  conversationTitle(id: string | null | undefined): string | undefined;
  /** 행을 열 때(Enter·클릭) */
  onOpen(run: Run): void;
  onCancel(run: Run): void;
  /** 경로 만들기(라우터에 의존하지 않도록 주입) */
  hrefs: { run(id: string): string; graph(id: string): string; conversation(id: string): string };
  /** 중첩 팀 자식 실행 표시: 자식 행(`↳`·`자식` 칩·`상위` 링크·`상위에 포함`)과 행 메뉴 항목. 없으면 일반 표 */
  nested?: { isChild(run: Run): boolean; hasChildren(run: Run): boolean; onShowChildren(run: Run): void };
}

/** 실행 목록 표(`role="grid"`: ↑↓ 이동, Enter 열기, Shift+F10 행 메뉴, Ctrl+Shift+X 취소). 데이터·콜백은 props. */
export function RunsTable({ runs, nowMs, graphName, conversationTitle, onOpen, onCancel, hrefs, nested }: RunsTableProps) {
  const [active, setActive] = useState(0);
  const [menu, setMenu] = useState<string | null>(null);
  const rows = useRef<(HTMLTableRowElement | null)[]>([]);
  const nowSec = nowMs / 1000;
  const cols = t.list.columns;

  const focusRow = (i: number) => {
    const next = Math.max(0, Math.min(runs.length - 1, i));
    setActive(next);
    rows.current[next]?.focus();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTableRowElement>, run: Run, i: number) => {
    if ((e.target as HTMLElement).closest("a,button,[role=menu]") !== null && e.key === "Enter") return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        focusRow(i + 1);
        break;
      case "ArrowUp":
        e.preventDefault();
        focusRow(i - 1);
        break;
      case "Home":
        e.preventDefault();
        focusRow(0);
        break;
      case "End":
        e.preventDefault();
        focusRow(runs.length - 1);
        break;
      case "Enter":
        e.preventDefault();
        onOpen(run);
        break;
      case "F10":
        if (e.shiftKey) {
          e.preventDefault();
          setMenu(run.id);
        }
        break;
      case "X":
        if (e.ctrlKey && e.shiftKey && CANCELLABLE_RUN_STATUSES.includes(run.status)) {
          e.preventDefault();
          onCancel(run);
        }
        break;
      case "Escape":
        setMenu(null);
        break;
      default:
    }
  };

  return (
    <table className="app-table runs-table" role="grid" aria-label={t.list.tableLabel}>
      <thead>
        <tr>
          <th scope="col">{cols.status}</th>
          <th scope="col">{cols.graph}</th>
          <th scope="col">{cols.source}</th>
          <th scope="col">{cols.started}</th>
          <th scope="col">{cols.elapsed}</th>
          <th scope="col">{cols.tokens}</th>
          <th scope="col"><span className="ac-sr-only">{cols.actions}</span></th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run, i) => {
          const waiting = run.status === WAITING_RUN_STATUS;
          const title = conversationTitle(run.conversation_id);
          const duration = runDurationMs(run, nowSec);
          const usage = run.totals;
          const total = totalTokens(usage);
          const summary = inputSummary(run.input, 60);
          const statusLabel = runStatusLabels[run.status] ?? run.status;
          const child = nested?.isChild(run) === true;
          return (
            <tr
              key={run.id}
              ref={(el) => {
                rows.current[i] = el;
              }}
              tabIndex={i === active ? 0 : -1}
              className="runs-row"
              data-waiting={waiting ? "true" : undefined}
              data-run-id={run.id}
              aria-label={`${run.id}, ${statusLabel}`}
              onFocus={() => setActive(i)}
              onDoubleClick={() => onOpen(run)}
              onKeyDown={(e) => onKeyDown(e, run, i)}
            >
              <td className="runs-cell-status">
                {child ? <span aria-hidden="true" className="app-muted">↳ </span> : null}
                <StatusChip status={run.status} kind="run" label={statusLabel} />
                {child ? <Tag className="runs-waiting-tag">{t.list.childChip}</Tag> : null}
              </td>
              <td className="ac-ellipsis">
                <Link to={hrefs.graph(run.graph_id)}>{graphName(run.graph_id) ?? t.list.unknownGraph}</Link>
              </td>
              <td className="ac-ellipsis" title={summary}>
                {child && run.parent_run_id ? (
                  <Link to={hrefs.run(run.parent_run_id)}>{t.list.parentLink(run.parent_run_id.slice(0, 6))}</Link>
                ) : run.conversation_id ? (
                  <Link to={hrefs.conversation(run.conversation_id)}>{title ?? (summary !== "" ? truncate(summary, 30) : run.conversation_id)}</Link>
                ) : (
                  <span className="app-muted">{t.list.directRun(t.list.origins[run.origin] ?? run.origin)}</span>
                )}
              </td>
              <td title={formatDateTime(run.created_at)}>{formatRelative(run.created_at, nowMs)}</td>
              <td className="ac-num">{duration === undefined ? "–" : formatElapsed(duration)}</td>
              <td
                className="ac-num"
                title={usage ? t.list.tokensTitle(formatTokensShort(usage.input_tokens), formatTokensShort(usage.output_tokens)) : undefined}
              >
                {formatTokensShort(total)}
                {child ? <Tag className="runs-waiting-tag" title={t.list.includedInParentHint}>{t.list.includedInParent}</Tag> : null}
              </td>
              <td className="runs-cell-menu">
                <RowMenu
                  run={run}
                  open={menu === run.id}
                  onToggle={(open) => setMenu(open ? run.id : null)}
                  onOpen={() => onOpen(run)}
                  onCancel={() => onCancel(run)}
                  hrefs={hrefs}
                  {...(nested ? { nested: { child, hasChildren: nested.hasChildren(run), onShowChildren: () => nested.onShowChildren(run) } } : {})}
                />
                {waiting ? <Tag className="runs-waiting-tag">{t.list.waitingBar}</Tag> : null}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function RowMenu({
  run,
  open,
  onToggle,
  onOpen,
  onCancel,
  hrefs,
  nested,
}: {
  nested?: { child: boolean; hasChildren: boolean; onShowChildren(): void };
  run: Run;
  open: boolean;
  onToggle(open: boolean): void;
  onOpen(): void;
  onCancel(): void;
  hrefs: RunsTableProps["hrefs"];
}) {
  const cancellable = CANCELLABLE_RUN_STATUSES.includes(run.status);
  return (
    <span className="runs-menu">
      <button type="button" className="ac-btn" data-variant="ghost" data-size="sm" aria-haspopup="menu" aria-expanded={open} aria-label={`${t.list.rowMenu}: ${run.id}`} onClick={() => onToggle(!open)}>
        ⋯
      </button>
      {open ? (
        <div role="menu" className="runs-menu-list" onKeyDown={(e) => e.key === "Escape" && onToggle(false)}>
          <button type="button" role="menuitem" onClick={() => (onToggle(false), onOpen())}>{t.list.open}</button>
          {nested?.child && run.parent_run_id ? <Link role="menuitem" to={hrefs.run(run.parent_run_id)}>{t.list.openParent}</Link> : null}
          {nested?.hasChildren ? <button type="button" role="menuitem" onClick={() => (onToggle(false), nested.onShowChildren())}>{t.list.showChildren}</button> : null}
          {run.conversation_id ? <Link role="menuitem" to={hrefs.conversation(run.conversation_id)}>{t.list.toConversation}</Link> : null}
          <Link role="menuitem" to={hrefs.graph(run.graph_id)}>{t.list.toGraph}</Link>
          {cancellable ? <button type="button" role="menuitem" onClick={() => (onToggle(false), onCancel())}>{t.list.cancel}</button> : null}
        </div>
      ) : null}
    </span>
  );
}
