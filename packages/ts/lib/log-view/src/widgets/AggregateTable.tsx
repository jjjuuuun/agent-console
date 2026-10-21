import { useMemo, useState } from "react";
import type { LogAggregateRow } from "@agent-console/contracts/logs";
import type { LogViewMessages } from "../messages";
import type { ColumnSpec, Formatters } from "../types";

export interface AggregateTableProps {
  rows: readonly LogAggregateRow[];
  groupBy: readonly string[];
  metricLabel?: string;
  /** 없으면 `keys..., value` 기본 열. */
  columns?: readonly ColumnSpec<LogAggregateRow>[];
  /** 최대 행 수(넘으면 하단 안내). */
  limit?: number;
  /** 값 열 머리 클릭 정렬(현재 행 한정, 클라이언트). */
  sortable?: boolean;
  ariaLabel: string;
  messages: LogViewMessages;
  formatters: Formatters;
}

/** 집계 결과 표. 값이 null이면 0이 아니라 "–". 표로 보기·`table` 위젯이 함께 쓴다. */
export function AggregateTable(props: AggregateTableProps) {
  const { rows, groupBy, metricLabel, columns, limit, sortable = false, ariaLabel, messages: m, formatters } = props;
  const [dir, setDir] = useState<"asc" | "desc" | null>(null);
  const sorted = useMemo(() => {
    if (!dir) return rows;
    const sign = dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      if (a.value == null && b.value == null) return 0;
      if (a.value == null) return 1;
      if (b.value == null) return -1;
      return (a.value - b.value) * sign;
    });
  }, [rows, dir]);
  const shown = limit != null ? sorted.slice(0, limit) : sorted;
  const cols: readonly ColumnSpec<LogAggregateRow>[] =
    columns ??
    [
      ...groupBy.map((g): ColumnSpec<LogAggregateRow> => ({ id: g, header: g, width: "minmax(0,1fr)", render: (r) => r.keys?.[g] ?? m.none })),
      { id: "value", header: metricLabel ?? "value", width: 120, align: "end", render: (r) => (r.value == null ? m.none : formatters.number(r.value)) },
    ];
  const valueCol = cols[cols.length - 1];
  return (
    <div className="ac-lv-aggtable">
      <table aria-label={ariaLabel}>
        <thead>
          <tr>
            {cols.map((c) => {
              const isValue = sortable && c === valueCol;
              return (
                <th key={c.id} scope="col" data-align={c.align ?? "start"} aria-sort={isValue ? (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none") : undefined}>
                  {isValue ? (
                    <button type="button" className="ac-lv-linkbtn" onClick={() => setDir(dir === "desc" ? "asc" : "desc")}>
                      {c.header}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {shown.map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c.id} data-align={c.align ?? "start"} className="ac-lv-ellipsis" title={typeof c.render?.(r) === "string" ? (c.render(r) as string) : undefined}>
                  {c.render ? c.render(r) : (r.keys?.[c.id] ?? m.none)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {limit != null && rows.length > limit ? <p className="ac-lv-muted">{m.widgetMoreHidden.replace("{n}", String(rows.length - limit))}</p> : null}
    </div>
  );
}
