import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { NodeRun } from "@agent-console/contracts";
import { Button, StatusChip } from "@agent-console/ui";
import { formatDuration } from "../../lib/format";
import { delegationMessages as dm } from "../delegation";
import { nodeRunKey, runOrdinalText } from "./nodeRuns";

export interface NodeRunListChild {
  runId: string;
  /** 자식 Run 짧은 id 문구(`r-7c1b`) */
  short: string;
}

export interface NodeRunListProps {
  /** 이 노드의 실행들(오래된 것 위) */
  runs: readonly NodeRun[];
  /** 보이는 실행의 키(`nodeRunKey`) */
  selectedKey: string;
  onSelect(key: string): void;
  /** 사용자가 `Home`/`End`로 처음·최신을 고르려는 경우를 구분하려고 최신 키를 따로 받는다 */
  statusLabel(status: string): string;
  /** 시작 시각 문구(`14:01:02`) */
  startedText(run: NodeRun): string;
  /** 호출자 노드 label(마지막 항목). 없으면 undefined */
  callerLabel(run: NodeRun): string | undefined;
  onSelectCaller?(run: NodeRun): void;
  /** 이 실행이 만든 자식 실행(여럿이면 `n개 ▾`) */
  childrenOf?(run: NodeRun): readonly NodeRunListChild[];
  onOpenChild?(runId: string): void;
  /** 응답 대기 중인 실행에서 [상호작용 탭에서 답하기] */
  onAnswer?(run: NodeRun): void;
  /** `End`: 최신 실행으로(고른 상태를 풀고 최신을 따라간다). 없으면 마지막 행을 고른다 */
  onLatest?(): void;
  /** 이 개수를 넘으면 보이는 행만 그린다(기본 50) */
  virtualAbove?: number;
  rowHeight?: number;
  viewportHeight?: number;
}

const OVERSCAN = 6;

/**
 * 실행 목록(노드·연결 탭, screen-delegation.md 3.3.1): 실행·상태·시작·소요·호출자·자식 실행. 행을 골라 "보이는 실행"으로 삼는다.
 * `role="grid"`, `↑↓` 행 이동, `Enter` 고정, `Home`/`End` 처음·최신. 행이 `virtualAbove`개를 넘으면 보이는 행만 그린다.
 * 어떤 행에도 자식이 없으면 자식 실행 열을 그리지 않는다.
 */
export function NodeRunList(p: NodeRunListProps) {
  const rowH = p.rowHeight ?? 32;
  const viewport = p.viewportHeight ?? 320;
  const virtual = p.runs.length > (p.virtualAbove ?? 50);
  const scroller = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const hasChild = useMemo(() => p.runs.some((r) => (p.childrenOf?.(r).length ?? 0) > 0), [p]);
  const selectedIndex = Math.max(0, p.runs.findIndex((r) => nodeRunKey(r) === p.selectedKey));
  const start = virtual ? Math.max(0, Math.floor(scrollTop / rowH) - OVERSCAN) : 0;
  const end = virtual ? Math.min(p.runs.length, Math.ceil((scrollTop + viewport) / rowH) + OVERSCAN) : p.runs.length;
  const [focusIndex, setFocusIndex] = useState<number | null>(null);

  // 선택한 행이 보이게 스크롤(가상 목록에서 행이 없을 수 있으므로 위치로 계산)
  useEffect(() => {
    const el = scroller.current;
    if (!virtual || el === null) return;
    const top = selectedIndex * rowH;
    if (top < el.scrollTop) el.scrollTop = top;
    else if (top + rowH > el.scrollTop + viewport) el.scrollTop = top + rowH - viewport;
  }, [virtual, selectedIndex, rowH, viewport]);
  useEffect(() => {
    if (focusIndex === null) return;
    scroller.current?.querySelector<HTMLElement>(`[data-index="${focusIndex}"]`)?.focus();
  }, [focusIndex, start, end]);

  const move = (to: number) => {
    const next = Math.max(0, Math.min(p.runs.length - 1, to));
    const run = p.runs[next];
    if (run === undefined) return;
    p.onSelect(nodeRunKey(run));
    setFocusIndex(next);
  };
  const onKey = (e: KeyboardEvent<HTMLTableRowElement>, index: number) => {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        move(index + 1);
        break;
      case "ArrowUp":
        e.preventDefault();
        move(index - 1);
        break;
      case "Home":
        e.preventDefault();
        move(0);
        break;
      case "End":
        e.preventDefault();
        if (p.onLatest) {
          p.onLatest();
          setFocusIndex(p.runs.length - 1);
        } else move(p.runs.length - 1);
        break;
      case "Enter": {
        e.preventDefault();
        const run = p.runs[index];
        if (run !== undefined) p.onSelect(nodeRunKey(run));
        break;
      }
      default:
    }
  };
  const columns = 5 + (hasChild ? 1 : 0);
  const visible = p.runs.slice(start, end);
  return (
    <div className="dlg-runlist-wrap" ref={scroller} style={virtual ? { maxHeight: viewport } : undefined} onScroll={virtual ? (e) => setScrollTop(e.currentTarget.scrollTop) : undefined}>
      <table className="dlg-runlist" role="grid" aria-label={dm.run.list.label} aria-rowcount={p.runs.length + 1}>
        <thead>
          <tr>
            <th scope="col">{dm.run.list.colRun}</th>
            <th scope="col">{dm.run.list.colStatus}</th>
            <th scope="col">{dm.run.list.colStarted}</th>
            <th scope="col">{dm.run.list.colElapsed}</th>
            <th scope="col">{dm.run.list.colCaller}</th>
            {hasChild ? <th scope="col">{dm.run.list.colChild}</th> : null}
          </tr>
        </thead>
        <tbody>
          {virtual && start > 0 ? <tr aria-hidden="true" style={{ height: start * rowH }}><td colSpan={columns} /></tr> : null}
          {visible.map((run, i) => {
            const index = start + i;
            const key = nodeRunKey(run);
            const selected = key === p.selectedKey;
            const caller = p.callerLabel(run);
            const kids = p.childrenOf?.(run) ?? [];
            const waiting = run.status === "waiting";
            return (
              <tr
                key={key}
                data-index={index}
                role="row"
                aria-rowindex={index + 2}
                aria-selected={selected}
                tabIndex={selected ? 0 : -1}
                onClick={() => p.onSelect(key)}
                onKeyDown={(e) => onKey(e, index)}
                style={{ height: rowH }}
              >
                <td role="gridcell" title={runOrdinalText(run, p.runs)}>{runOrdinalText(run, p.runs)}</td>
                <td role="gridcell">
                  <StatusChip status={run.status} label={waiting ? `⏸ ${dm.run.list.waiting}` : p.statusLabel(run.status)} />
                  {waiting && p.onAnswer ? (
                    <> <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); p.onAnswer?.(run); }}>{dm.run.list.answer}</Button></>
                  ) : null}
                </td>
                <td role="gridcell" className="ac-num">{p.startedText(run)}</td>
                <td role="gridcell" className="ac-num">{run.duration_ms == null ? "–" : formatDuration(run.duration_ms)}</td>
                <td role="gridcell">
                  {caller === undefined ? (
                    "–"
                  ) : p.onSelectCaller ? (
                    <button type="button" className="dlg-from-chip" onClick={(e) => { e.stopPropagation(); p.onSelectCaller?.(run); }}>{caller}</button>
                  ) : (
                    caller
                  )}
                </td>
                {hasChild ? (
                  <td role="gridcell">
                    {kids.length === 0 ? (
                      "–"
                    ) : kids.length === 1 ? (
                      <button type="button" className="app-link-btn app-mono" onClick={(e) => { e.stopPropagation(); p.onOpenChild?.(kids[0]!.runId); }}>{kids[0]!.short} ↗</button>
                    ) : (
                      <span title={kids.map((k) => k.short).join(", ")}>{dm.run.list.childMany(kids.length)}</span>
                    )}
                  </td>
                ) : null}
              </tr>
            );
          })}
          {virtual && end < p.runs.length ? <tr aria-hidden="true" style={{ height: (p.runs.length - end) * rowH }}><td colSpan={columns} /></tr> : null}
        </tbody>
      </table>
    </div>
  );
}
