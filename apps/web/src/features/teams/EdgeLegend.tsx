import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import type { DelegationStrategyDescriptor, EdgeTypeDescriptor } from "@agent-console/contracts";
import { resolveEdgeStyle } from "@agent-console/graph-editor";
import { Button, Icon, useIconRegistry } from "@agent-console/ui";
import { useHint } from "../../app/hints";
import { SessionChip, attributeRows, edgeSessionOf, effectiveStrategyId, sessionOf } from "../delegation";
import { teamMessages } from "./messages";
import { latestById } from "./teamsLogic";

const m = teamMessages.sessions;
const HINT_MS = 8000;

export interface LegendRow {
  key: string;
  kind: EdgeTypeDescriptor;
  strategy: DelegationStrategyDescriptor | undefined;
  /** 선 샘플에 쓰는 유효 방식 id(위임 연결만) */
  strategyId: string | undefined;
  session: string | undefined;
}

/**
 * 범례 행 계산(순수 함수): 이 팀에서 쓰는 (연결 종류, 유효 방식) 쌍을 한 줄로 합치고, 나머지 종류는 종류 기본 방식으로 따로 모은다.
 * 종류·방식 이름은 모두 디스크립터 데이터다.
 */
export function legendRows(
  edges: readonly { id: string; kind: string; config?: Record<string, unknown> | undefined }[],
  edgeTypes: readonly EdgeTypeDescriptor[],
  strategies: readonly DelegationStrategyDescriptor[],
): { used: LegendRow[]; unused: LegendRow[] } {
  const kinds = latestById(edgeTypes);
  const byId = new Map(kinds.map((k) => [k.id, k]));
  const rowOf = (kind: EdgeTypeDescriptor, edge: { config?: Record<string, unknown> | undefined }): LegendRow => {
    const strategyId = effectiveStrategyId(edge as { config?: never }, kind);
    return { key: `${kind.id}\u0000${strategyId ?? ""}`, kind, strategyId, strategy: strategyId === undefined ? undefined : strategies.find((s) => s.id === strategyId), session: edgeSessionOf(edge as { config?: never }, kind, strategies) };
  };
  const used = new Map<string, LegendRow>();
  for (const e of edges) {
    const kind = byId.get(e.kind);
    if (kind === undefined) continue;
    const row = rowOf(kind, e);
    if (!used.has(row.key)) used.set(row.key, row);
  }
  const usedKinds = new Set([...used.values()].map((r) => r.kind.id));
  const unused = kinds.filter((k) => !usedKinds.has(k.id)).map((k) => rowOf(k, {}));
  return { used: [...used.values()], unused };
}

function Row({ row, strategies, renderIcon }: { row: LegendRow; strategies: readonly DelegationStrategyDescriptor[]; renderIcon: (name: string) => ReactNode }) {
  const style = resolveEdgeStyle(row.kind, strategies, { strategyId: row.strategyId ?? null });
  const icon = style.iconName === undefined ? null : renderIcon(style.iconName);
  return (
    <li className="ses-legend-row" data-legend-row="">
      <svg className="ses-legend-sample" viewBox="0 0 40 8" aria-hidden="true" focusable="false">
        <line x1="0" y1="4" x2="40" y2="4" style={{ ...(style.color === undefined ? {} : { stroke: style.color }), ...(style.dasharray === undefined ? {} : { strokeDasharray: style.dasharray }), ...(style.linecap === undefined ? {} : { strokeLinecap: style.linecap }) }} data-dash={style.dasharray ?? "none"} />
      </svg>
      {icon !== null ? <span aria-hidden="true">{icon}</span> : null}
      <span className="ses-legend-name" title={row.strategy === undefined ? row.kind.title : `${row.kind.title} · ${row.strategy.title}`}>
        {row.kind.title}
        {row.strategy !== undefined ? ` · ${row.strategy.title}` : ""}
      </span>
      <SessionChip value={row.session} />
    </li>
  );
}

export interface EdgeLegendProps {
  edges: readonly { id: string; kind: string; config?: Record<string, unknown> | undefined }[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  strategies: readonly DelegationStrategyDescriptor[];
  renderIcon: (name: string) => ReactNode;
  /** 디스크립터 읽기 실패 시 [다시 시도] */
  onRetry?: () => void;
}

/**
 * 캔버스 아래 [연결 범례] 버튼과 비모달 팝오버(위쪽으로 열림). 선 샘플은 편집기가 쓰는 `resolveEdgeStyle` 결과를 그대로 그리고,
 * 세션 칩 설명은 디스크립터에 나온 세션 값마다 한 줄이다. `Esc`로 닫고 포커스는 버튼으로 돌아간다.
 */
export function EdgeLegend({ edges, edgeTypes, strategies, renderIcon, onRetry }: EdgeLegendProps) {
  const [open, setOpen] = useState(false);
  const [unusedOpen, setUnusedOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const hint = useHint("edge-legend");
  const [hintShown, setHintShown] = useState(true);
  const registry = useIconRegistry();
  useEffect(() => {
    if (!hint.visible) return;
    const timer = setTimeout(() => setHintShown(false), HINT_MS);
    return () => clearTimeout(timer);
  }, [hint.visible]);
  const rows = useMemo(() => legendRows(edges, edgeTypes, strategies), [edges, edgeTypes, strategies]);
  // 세션 값 설명: 디스크립터(방식·연결 종류)에 나온 값마다 한 줄. 문구가 있는 값만 보인다
  const sessionValues = useMemo(() => {
    const seen = new Set<string>();
    for (const s of strategies) {
      const v = sessionOf(s);
      if (v !== undefined) seen.add(v);
    }
    for (const k of latestById(edgeTypes)) if (typeof k.session === "string" && k.session !== "") seen.add(k.session);
    return [...seen].flatMap((v) => {
      const cell = attributeRows({ session: v })[0];
      return cell === undefined || cell.unknownValue ? [] : [{ value: v, text: cell.long }];
    });
  }, [strategies, edgeTypes]);
  const empty = rows.used.length + rows.unused.length === 0;
  const close = () => {
    setOpen(false);
    button.current?.focus();
  };
  return (
    <span className="ses-legend-wrap" onKeyDown={(e) => { if (e.key === "Escape" && open) { e.stopPropagation(); close(); } }}>
      <Button ref={button} size="sm" aria-expanded={open} aria-controls={open ? panelId : undefined} onClick={() => { setOpen((v) => !v); hint.dismiss(); }}>
        {registry.has("list") ? <Icon name="list" size={14} /> : null} {m.legendButton}
      </Button>
      {hint.visible && hintShown && !open ? (
        <span className="app-muted ses-legend-hint" role="status">
          {m.legendHint}{" "}
          <button type="button" className="app-link-btn" onClick={hint.dismiss}>{m.legendClose}</button>
        </span>
      ) : null}
      {open ? (
        <div className="ses-legend" id={panelId} role="dialog" aria-label={m.legendTitle}>
          {empty ? (
            <>
              <p className="app-muted">{m.legendEmpty}</p>
              {onRetry !== undefined ? <Button size="sm" onClick={onRetry}>{m.legendRetry}</Button> : null}
            </>
          ) : (
            <>
              {rows.used.length > 0 ? (
                <section aria-label={m.legendUsed}>
                  <span className="lib-field-label">{m.legendUsed}</span>
                  <ul className="ses-legend-list">{rows.used.map((r) => <Row key={r.key} row={r} strategies={strategies} renderIcon={renderIcon} />)}</ul>
                </section>
              ) : null}
              {rows.unused.length > 0 ? (
                <section>
                  <button type="button" className="app-link-btn" aria-expanded={unusedOpen} onClick={() => setUnusedOpen((v) => !v)}>
                    {m.legendUnused(rows.unused.length)} {unusedOpen ? "▾" : "▸"}
                  </button>
                  {unusedOpen ? <ul className="ses-legend-list">{rows.unused.map((r) => <Row key={r.key} row={r} strategies={strategies} renderIcon={renderIcon} />)}</ul> : null}
                </section>
              ) : null}
              {sessionValues.length > 0 ? (
                <section aria-label={m.legendSessions}>
                  <span className="lib-field-label">{m.legendSessions}</span>
                  <ul className="ses-legend-list">
                    {sessionValues.map((s) => (
                      <li key={s.value} className="ses-legend-row">
                        <SessionChip value={s.value} />
                        <span className="ses-legend-name">{s.text}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </span>
  );
}
