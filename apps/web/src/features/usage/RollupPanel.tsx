import { useMemo, useState } from "react";
import { Button, Tabs, Tag } from "@agent-console/ui";
import { formatCount } from "../../lib/format";
import { usageMessages as t } from "./messages";
import { aggregateRollup, barRatio, type RollupDimension, type RollupLine } from "./usageLib";

export interface RollupPanelProps {
  /** 기간 안으로 이미 걸러진 서버 집계 행에서 만든 줄(차원별로 다시 합친 것) */
  linesByView: Readonly<Record<string, readonly RollupLine[]>>;
  /** 보기 목록(차원 id). 표시 이름은 messages.rollup.views */
  views: readonly RollupDimension[];
  view: RollupDimension;
  onViewChange(v: RollupDimension): void;
  /** 기간 선택지 id 목록과 현재 값 */
  periods: readonly string[];
  period: string;
  onPeriodChange(p: string): void;
  /** 차원 값 → 표시 이름 */
  nameOf(dimension: RollupDimension, value: string | null): string;
  loading?: boolean;
}

function dayLabel(value: string | null): string {
  if (value === null) return t.rollup.unnamed;
  const m = /^\d{4}-(\d{2})-(\d{2})$/.exec(value);
  return m ? `${Number(m[1])}/${Number(m[2])}` : value;
}

/** 토큰 집계: 가로 막대 리스트(일 보기는 세로 막대) + 표 보기. 막대 색은 중립이며 의미 색이 없다. */
export function RollupPanel(p: RollupPanelProps) {
  const [asTable, setAsTable] = useState(false);
  const { linesByView, view } = p;
  const lines = useMemo(() => linesByView[view] ?? [], [linesByView, view]);
  const max = useMemo(() => lines.reduce((m, l) => Math.max(m, l.total ?? 0), 0), [lines]);
  const name = (l: RollupLine) => (p.view === "day" ? dayLabel(l.value) : p.nameOf(p.view, l.value));

  const cell = (l: RollupLine) => (
    <>
      {l.precision.length > 0 ? <Tag title={l.precision.join(" / ")}>{t.rollup.totalOnly}</Tag> : null}
      {l.costUsd !== undefined ? <Tag title={t.rollup.costSession}>{t.rollup.cost(String(l.costUsd))} · {t.rollup.costSession}</Tag> : null}
    </>
  );

  return (
    <section className="usage-rollup" aria-labelledby="usage-rollup-title">
      <div className="usage-rollup-head">
        <h2 id="usage-rollup-title" className="app-block-title">{t.rollup.title}</h2>
        <label className="runs-filter">
          <span className="app-muted">{t.rollup.period}</span>
          <select value={p.period} onChange={(e) => p.onPeriodChange(e.target.value)}>
            {p.periods.map((id) => (
              <option key={id} value={id}>{t.rollup.periods[id] ?? id}</option>
            ))}
          </select>
        </label>
        <Button size="sm" aria-pressed={asTable} onClick={() => setAsTable(!asTable)}>{asTable ? t.rollup.asBars : t.rollup.asTable}</Button>
      </div>
      <Tabs
        ariaLabel={t.rollup.view}
        activeId={p.view}
        onChange={(id) => p.onViewChange(id as RollupDimension)}
        tabs={p.views.map((v) => ({ id: v, label: t.rollup.views[v] ?? v, content: null }))}
      />
      {lines.length === 0 ? (
        <p className="app-muted" role="status">{p.loading ? t.rollup.empty : t.rollup.empty}</p>
      ) : asTable ? (
        <table className="app-table" aria-label={t.rollup.tableLabel}>
          <thead>
            <tr>
              <th scope="col">{t.rollup.columns.name}</th>
              <th scope="col">{t.rollup.columns.total}</th>
              <th scope="col">{t.rollup.columns.input}</th>
              <th scope="col">{t.rollup.columns.output}</th>
              <th scope="col">{t.rollup.columns.note}</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.key}>
                <th scope="row" className="ac-ellipsis">{name(l)}</th>
                <td className="ac-num">{formatCount(l.total)}</td>
                <td className="ac-num">{l.input === undefined ? t.rollup.noSplit : formatCount(l.input)}</td>
                <td className="ac-num">{l.output === undefined ? t.rollup.noSplit : formatCount(l.output)}</td>
                <td>{cell(l)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : p.view === "day" ? (
        <ul className="usage-columns" aria-label={t.rollup.barsLabel}>
          {lines.slice(-31).map((l) => (
            <li key={l.key} title={`${name(l)}: ${formatCount(l.total)}`}>
              <span className="usage-col-bar" style={{ height: `${Math.round(barRatio(l.total, max) * 100)}%` }} role="img" aria-label={`${name(l)} ${formatCount(l.total)}`} />
              <span className="usage-col-label ac-num">{name(l)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="usage-bars" aria-label={t.rollup.barsLabel}>
          {lines.map((l) => (
            <li key={l.key} className="usage-bar-row">
              <span className="usage-bar-name ac-ellipsis" title={name(l)}>{name(l)}</span>
              <span className="usage-bar-track"><span className="usage-bar-fill" style={{ width: `${Math.round(barRatio(l.total, max) * 100)}%` }} /></span>
              <span className="ac-num usage-bar-total">{formatCount(l.total)}</span>
              <span className="app-muted usage-bar-split">
                {l.input !== undefined || l.output !== undefined ? `${t.rollup.input} ${l.input === undefined ? t.rollup.noSplit : formatCount(l.input)} · ${t.rollup.output} ${l.output === undefined ? t.rollup.noSplit : formatCount(l.output)}` : t.rollup.noSplit}
              </span>
              <span>{cell(l)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="app-muted usage-note">{t.rollup.note}</p>
    </section>
  );
}

/** 보기별 줄을 한 번에 만든다(순수 헬퍼). */
export function buildLinesByView(rows: Parameters<typeof aggregateRollup>[0], views: readonly RollupDimension[]): Record<string, RollupLine[]> {
  return Object.fromEntries(views.map((v) => [v, aggregateRollup(rows, v)]));
}
