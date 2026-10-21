import { useMemo } from "react";
import type { HandoffCount, HandoffMatrix } from "@agent-console/contracts";
import { runsMessages as t } from "./messages";

export interface HandoffMatrixViewProps {
  matrix: HandoffMatrix;
  /** 에이전트 id 또는 노드 id → 표시 이름 */
  nameOf(id: string): string;
  /** 연결 종류 id 또는 span 종류 → 표시 이름(모르면 원문) */
  methodOf(kind: string): string;
  /** 칸을 눌렀을 때(해당 조합이 있는 실행 목록으로) */
  onSelectCell?(cell: { from: string; to: string }): void;
}

interface Cell {
  from: string;
  to: string;
  count: number;
  methods: { kind: string; count: number }[];
}

/** 행 = 넘기는 쪽, 열 = 받는 쪽, 칸 = 횟수. 색 강도는 보조이고 숫자가 주다. */
export function buildCells(cells: readonly HandoffCount[]): { rows: string[]; cols: string[]; byKey: Map<string, Cell>; max: number } {
  const rows = [...new Set(cells.map((c) => c.source))];
  const cols = [...new Set(cells.map((c) => c.target))];
  const byKey = new Map<string, Cell>();
  let max = 0;
  for (const c of cells) {
    const key = `${c.source}\u0000${c.target}`;
    const cell = byKey.get(key) ?? { from: c.source, to: c.target, count: 0, methods: [] };
    cell.count += c.count;
    cell.methods.push({ kind: c.kind ?? "", count: c.count });
    byKey.set(key, cell);
    max = Math.max(max, cell.count);
  }
  return { rows, cols, byKey, max };
}

export function HandoffMatrixView({ matrix, nameOf, methodOf, onSelectCell }: HandoffMatrixViewProps) {
  const cells = useMemo(() => matrix.cells ?? [], [matrix.cells]);
  const { rows, cols, byKey, max } = useMemo(() => buildCells(cells), [cells]);
  if (cells.length === 0) return <p className="app-muted app-pad" role="status">{t.handoffs.empty}</p>;
  return (
    <div className="runs-handoffs">
      <p className="app-muted">{t.handoffs.runs(matrix.runs ?? 0)}</p>
      <div className="runs-handoffs-scroll">
        <table className="app-table runs-matrix" role="table" aria-label={t.handoffs.tableLabel}>
          <thead>
            <tr>
              <th scope="col">{t.handoffs.corner}</th>
              {cols.map((c) => (
                <th key={c} scope="col" className="ac-ellipsis" title={c}>{nameOf(c)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r}>
                <th scope="row" className="ac-ellipsis" title={r}>{nameOf(r)}</th>
                {cols.map((c) => {
                  const cell = byKey.get(`${r}\u0000${c}`);
                  if (cell === undefined) return <td key={c} className="runs-matrix-empty"><span className="ac-sr-only">0</span></td>;
                  const detail = cell.methods.map((m) => `${m.kind === "" ? t.common.unknown : methodOf(m.kind)} ${m.count}`).join(" · ");
                  const label = t.handoffs.cellLabel(nameOf(r), nameOf(c), cell.count);
                  const tint = `color-mix(in srgb, var(--ac-accent) ${Math.round((cell.count / Math.max(1, max)) * 40)}%, transparent)`;
                  return (
                    <td key={c} className="ac-num runs-matrix-cell" style={{ background: tint }} title={detail}>
                      {onSelectCell ? (
                        <button type="button" className="app-link-btn" aria-label={`${label}. ${detail}`} onClick={() => onSelectCell({ from: r, to: c })}>
                          {cell.count}
                        </button>
                      ) : (
                        <span aria-label={`${label}. ${detail}`}>{cell.count}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
