import { useMemo } from "react";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";

export interface HandoffCell {
  from: string;
  to: string;
  via?: string | null | undefined;
  count: number;
}

export interface HandoffMatrixViewProps {
  cells: readonly HandoffCell[];
  /** 셀 클릭/Enter: from·to(·via가 하나뿐일 때 via). */
  onCellClick?: (cell: { from: string; to: string; via?: string }) => void;
  labelFor?: (id: string) => string | undefined;
  viaLabelFor?: (via: string) => string | undefined;
  /** 서버가 자른 상한(셀 개수가 이 값이면 안내를 보인다). */
  limit?: number;
  loading?: boolean;
  messages?: DeepPartial<LogViewMessages>;
  ariaLabel?: string;
}

interface Agg {
  count: number;
  vias: Map<string, number>;
}

const byNameThenCount = (totals: Map<string, number>) => (a: string, b: string) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0) || (a < b ? -1 : a > b ? 1 : 0);

/**
 * 위임 행렬: 행 = 보낸 쪽, 열 = 받는 쪽, 셀 = 횟수. 순서는 합계 내림차순(동률은 이름순).
 * 숫자가 주 정보이고 배경 농도는 보조다. 같은 (from,to)는 `via`와 상관없이 합쳐 보이고 툴팁에 방식별 분해를 적는다.
 */
export function HandoffMatrixView(props: HandoffMatrixViewProps) {
  const { cells, onCellClick, labelFor, viaLabelFor, limit = 40, loading, ariaLabel } = props;
  const m = useMemo(() => mergeMessages(props.messages), [props.messages]);
  const model = useMemo(() => {
    const grid = new Map<string, Agg>();
    const rowT = new Map<string, number>();
    const colT = new Map<string, number>();
    let max = 0;
    for (const c of cells) {
      const k = `${c.from}\u0000${c.to}`;
      const a = grid.get(k) ?? { count: 0, vias: new Map() };
      a.count += c.count;
      if (c.via) a.vias.set(c.via, (a.vias.get(c.via) ?? 0) + c.count);
      grid.set(k, a);
      rowT.set(c.from, (rowT.get(c.from) ?? 0) + c.count);
      colT.set(c.to, (colT.get(c.to) ?? 0) + c.count);
      max = Math.max(max, a.count);
    }
    return { grid, rows: [...rowT.keys()].sort(byNameThenCount(rowT)), cols: [...colT.keys()].sort(byNameThenCount(colT)), max };
  }, [cells]);

  if (loading) return <p className="ac-lv-empty" role="status">{m.loading}</p>;
  if (cells.length === 0) return <p className="ac-lv-empty" role="status">{m.handoffEmpty}</p>;
  const label = (id: string) => labelFor?.(id) ?? id;
  return (
    <div className="ac-lv-handoff">
      <div className="ac-lv-scroll-xy">
        <table aria-label={ariaLabel ?? m.handoffMatrix}>
          <thead>
            <tr>
              <td />
              {model.cols.map((c) => (
                <th key={c} scope="col" className="ac-lv-ellipsis" title={label(c)}>
                  {label(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {model.rows.map((r) => (
              <tr key={r}>
                <th scope="row" className="ac-lv-ellipsis" title={label(r)}>
                  {label(r)}
                </th>
                {model.cols.map((c) => {
                  const a = model.grid.get(`${r}\u0000${c}`);
                  if (!a) return <td key={c} className="ac-lv-handoff-empty" />;
                  const tint = 8 + (a.count / Math.max(model.max, 1)) * 32;
                  const breakdown = [...a.vias].map(([v, n]) => `${viaLabelFor?.(v) ?? v} ${n}`).join(" · ");
                  const only = a.vias.size === 1 ? [...a.vias.keys()][0] : undefined;
                  return (
                    <td key={c} style={{ background: `color-mix(in srgb, var(--ac-accent) ${tint.toFixed(0)}%, var(--ac-surface-1))` }}>
                      <button
                        type="button"
                        className="ac-lv-handoff-cell ac-lv-num"
                        title={breakdown || undefined}
                        aria-label={fmt(m.handoffCell, { from: label(r), to: label(c), n: a.count })}
                        onClick={() => onCellClick?.(only ? { from: r, to: c, via: only } : { from: r, to: c })}
                      >
                        {a.count}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {cells.length >= limit ? <p className="ac-lv-muted">{fmt(m.handoffLimit, { n: limit })}</p> : null}
    </div>
  );
}
