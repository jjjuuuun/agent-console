import type { TaskLink, TraceMatrix as TraceMatrixData, TraceRow } from "@agent-console/contracts/sdd";
import { useMemo, useRef, useState } from "react";
import { codeDisplay, type CodeDisplayTable } from "./display";
import { useVirtualRows } from "./hooks";
import { formatMessage, messageOr, resolveMessages } from "./messages";
import { filterTraceRows, gapLabelKey, hasGaps, verificationLabelKey } from "./trace";
import { ToneChip } from "./ToneChip";

export const TRACE_ROW_HEIGHT = 32;

export interface TraceMatrixProps {
  matrix: TraceMatrixData;
  /** 빈 곳 코드 → `{tone, label, hint}`. 표에 없으면 경고 톤 + 코드 원문(또는 `gap.<코드>` 문구). 앱 데이터다. */
  gapDisplay?: CodeDisplayTable;
  /** 검증 결과 코드 → `{tone, label}`. 표에 없으면 중립 + 원문. */
  verificationDisplay?: CodeDisplayTable;
  onOpenTask?: (taskKey: string, row: TraceRow) => void;
  onOpenRequirement?: (row: TraceRow) => void;
  /** 실행 연동이 있을 때만 실행 열을 그린다. 기본 true */
  showRuns?: boolean;
  /** 검증 출처가 있을 때만 검증 열을 그린다. 기본 true */
  showVerification?: boolean;
  openableKinds?: readonly string[];
  onOpenLink?: (link: TaskLink) => void;
  /** 빈 곳만 보기(제어형). 없으면 안에서 관리 */
  onlyGaps?: boolean;
  onOnlyGapsChange?: (value: boolean) => void;
  height?: number | "fill";
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 요구 ↔ 작업 ↔ 실행 ↔ 검증 추적 표(가상 목록). 빈 곳만 걸러 볼 수 있고, 작업·요구는 눌러서 이동한다. */
export function TraceMatrix(props: TraceMatrixProps) {
  const {
    matrix, gapDisplay, verificationDisplay, onOpenTask, onOpenRequirement, showRuns = true, showVerification = true, openableKinds = [], onOpenLink,
    onlyGaps, onOnlyGapsChange, height = "fill", messages, className,
  } = props;
  const text = resolveMessages(messages);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [innerOnly, setInnerOnly] = useState(false);
  const only = onlyGaps ?? innerOnly;
  const allRows = useMemo(() => matrix.rows ?? [], [matrix.rows]);
  const rows = useMemo(() => filterTraceRows(allRows, only), [allRows, only]);
  const virtual = useVirtualRows({ count: rows.length, rowHeight: TRACE_ROW_HEIGHT, scrollRef });
  const root = `ac-sdd-root${className ? ` ${className}` : ""}`;
  const orphans = matrix.orphans;
  const orphanNotes = [
    orphans?.tasks_without_requirements?.length ? formatMessage(text["trace.orphan.tasks"], { n: orphans.tasks_without_requirements.length }) : "",
    orphans?.unknown_requirement_refs?.length ? formatMessage(text["trace.orphan.unknownRefs"], { n: orphans.unknown_requirement_refs.length }) : "",
    orphans?.unknown_task_links?.length ? formatMessage(text["trace.orphan.unknownLinks"], { n: orphans.unknown_task_links.length }) : "",
  ].filter((s) => s !== "");

  if (allRows.length === 0) {
    return (
      <div className={`${root} ac-sdd-empty`} role="status" data-state="empty">
        <p className="ac-sdd-empty-title">{text["trace.empty.title"]}</p>
        <p className="ac-sdd-muted">{text["trace.empty.body"]}</p>
      </div>
    );
  }
  const gapChip = (code: string) => {
    const d = codeDisplay(code, gapDisplay, "warning", messageOr(text, gapLabelKey(code), code));
    return <ToneChip key={code} label={d.label} tone={d.tone} title={d.hint ?? d.label} />;
  };

  return (
    <div className={`${root} ac-sdd-trace`} style={{ height: height === "fill" ? "100%" : height }}>
      <div className="ac-sdd-toolbar">
        <label className="ac-sdd-check">
          <input
            type="checkbox"
            checked={only}
            onChange={(e) => {
              setInnerOnly(e.target.checked);
              onOnlyGapsChange?.(e.target.checked);
            }}
          />
          {text["trace.filter.gaps"]}
        </label>
        {orphanNotes.length > 0 ? (
          <span className="ac-sdd-muted" role="status" title={text["trace.orphans"]}>
            {orphanNotes.join(" · ")}
          </span>
        ) : null}
      </div>
      <div ref={scrollRef} className="ac-sdd-scroll" style={{ flex: 1 }}>
        <ul className="ac-sdd-vlist" role="list" aria-label={text["trace.table"]} style={{ height: virtual.getTotalSize() }}>
          {virtual.getVirtualItems().map((item) => {
            const row = rows[item.index] as TraceRow;
            const gaps = row.gaps ?? [];
            const tasks = row.tasks ?? [];
            const v = row.verification ? codeDisplay(row.verification.status, verificationDisplay, "neutral", messageOr(text, verificationLabelKey(row.verification.status), row.verification.status)) : null;
            return (
              <li
                key={row.id}
                className="ac-sdd-vrow ac-sdd-trace-row"
                data-gaps={hasGaps(row) || undefined}
                style={{ transform: `translateY(${item.start}px)`, height: TRACE_ROW_HEIGHT }}
                aria-setsize={rows.length}
                aria-posinset={item.index + 1}
                aria-label={formatMessage(text["trace.row"], { id: row.id, tasks: tasks.length, gaps: gaps.length > 0 ? gaps.join(", ") : text["trace.noGaps"] })}
              >
                {onOpenRequirement ? (
                  <button type="button" className="ac-sdd-link ac-sdd-trace-req" aria-label={formatMessage(text["trace.openRequirement"], { id: row.id })} onClick={() => onOpenRequirement(row)}>
                    <span className="ac-sdd-mono">{row.id}</span> <span className="ac-sdd-ellipsis">{row.title}</span>
                  </button>
                ) : (
                  <span className="ac-sdd-trace-req">
                    <span className="ac-sdd-mono">{row.id}</span> <span className="ac-sdd-ellipsis">{row.title}</span>
                  </span>
                )}
                <span className="ac-sdd-trace-tasks">
                  {tasks.map((key) =>
                    onOpenTask ? (
                      <button key={key} type="button" className="ac-sdd-link ac-sdd-mono" aria-label={formatMessage(text["trace.openTask"], { key })} onClick={() => onOpenTask(key, row)}>
                        {key}
                      </button>
                    ) : (
                      <span key={key} className="ac-sdd-mono">{key}</span>
                    ),
                  )}
                </span>
                {showRuns ? (
                  <span className="ac-sdd-trace-runs">
                    {(row.runs ?? []).map((link) => {
                      const k = `${link.integration}:${link.kind}:${link.ref}`;
                      return onOpenLink && openableKinds.includes(link.kind) ? (
                        <button key={k} type="button" className="ac-sdd-link ac-sdd-mono" onClick={() => onOpenLink(link)}>
                          {link.ref}
                        </button>
                      ) : (
                        <span key={k} className="ac-sdd-mono">{link.ref}</span>
                      );
                    })}
                  </span>
                ) : null}
                {showVerification ? <span className="ac-sdd-trace-ver">{v ? <ToneChip label={v.label} tone={v.tone} /> : <span className="ac-sdd-muted">{text["trace.noVerification"]}</span>}</span> : null}
                <span className="ac-sdd-trace-gaps">{gaps.map(gapChip)}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
