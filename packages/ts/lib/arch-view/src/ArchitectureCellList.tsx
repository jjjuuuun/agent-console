import type { ArchitectureCellView, ArchitectureEdgeView, ArchitectureMembership, ArchitectureView } from "@agent-console/contracts/architecture";
import { defaultMetricKinds, defaultTones, resolveTone } from "./defaults";
import { metricPieces } from "./format";
import { formatMessage, resolveMessages } from "./messages";
import type { ArchViewMessages } from "./messages";
import { cellAriaLabel, cellBlockedReason, edgeAriaLabel, edgeBlockedReason, highlightSets, sameSelection } from "./model";
import { MetricPiece } from "./Nodes";
import type { ArchSelection, BlockedReason, MetricKindSpec } from "./types";

export interface ArchitectureCellListProps {
  view: ArchitectureView;
  selection?: ArchSelection | null;
  highlight?: ArchitectureMembership | null;
  /** 선택 변경(같은 대상을 다시 누르면 null). */
  onSelect?: (selection: ArchSelection | null) => void;
  /** 걸러낼 수 없는 대상을 눌렀을 때(수집 안 됨·구조 연결). */
  onBlocked?: (target: ArchSelection, reason: BlockedReason) => void;
  tones?: Readonly<Record<string, string>>;
  metricKinds?: Readonly<Record<string, MetricKindSpec>>;
  messages?: Partial<ArchViewMessages>;
  className?: string;
}

/**
 * 칸 목록(§5.6): 그림과 같은 일을 목록으로 한다. 칸 행 수 = 칸 수, 연결 행 수 = 연결 수.
 * 행은 `aria-pressed` 버튼이다.
 */
export function ArchitectureCellList({ view, selection = null, highlight = null, onSelect, onBlocked, tones = defaultTones, metricKinds = defaultMetricKinds, messages: partial, className }: ArchitectureCellListProps) {
  const messages = resolveMessages(partial);
  const hl = highlightSets(highlight);
  const cells = view.cells ?? [];
  const edges = view.edges ?? [];
  const labels = Object.fromEntries(cells.map((c) => [c.id, c.label]));
  const press = (target: ArchSelection, reason: BlockedReason | null) => {
    if (reason) onBlocked?.(target, reason);
    else onSelect?.(sameSelection(selection, target) ? null : target);
  };
  const unassigned = view.unassigned;
  return (
    <div className={["ac-arch-list", className].filter(Boolean).join(" ")}>
      <h3 className="ac-arch-list-head">{formatMessage(messages.listCells, { n: cells.length })}</h3>
      <ul className="ac-arch-list-rows" aria-label={formatMessage(messages.listCells, { n: cells.length })}>
        {cells.map((c) => (
          <li key={c.id}>
            <CellRow cell={c} messages={messages} tones={tones} kinds={metricKinds} selected={selection?.kind === "cell" && selection.id === c.id} highlighted={hl.cells.has(c.id)} onPress={() => press({ kind: "cell", id: c.id }, cellBlockedReason(c))} />
          </li>
        ))}
      </ul>
      <h3 className="ac-arch-list-head">{formatMessage(messages.listEdges, { n: edges.length })}</h3>
      <ul className="ac-arch-list-rows" aria-label={formatMessage(messages.listEdges, { n: edges.length })}>
        {edges.map((e) => (
          <li key={e.id}>
            <EdgeRow edge={e} labels={labels} messages={messages} kinds={metricKinds} selected={selection?.kind === "edge" && selection.id === e.id} highlighted={hl.edges.has(e.id)} onPress={() => press({ kind: "edge", id: e.id }, edgeBlockedReason(e))} />
          </li>
        ))}
      </ul>
      {unassigned || (view.unavailable ?? []).length > 0 ? (
        <ul className="ac-arch-list-rows ac-arch-list-extra" aria-label={messages.listUnassigned}>
          {unassigned ? (
            <li>
              <button type="button" className="ac-arch-row" data-selected={selection?.kind === "unassigned" ? "" : undefined} aria-pressed={selection?.kind === "unassigned"} onClick={() => press({ kind: "unassigned", id: "" }, null)}>
                <span className="ac-arch-row-name">{messages.listUnassigned}</span>
                <span className="ac-arch-row-metrics">{metricPieces(unassigned.metrics, messages, { kinds: metricKinds }).map((p) => <MetricPiece key={p.name} piece={p} />)}</span>
              </button>
            </li>
          ) : null}
          {(view.unavailable ?? []).map((u, i) => (
            <li key={`${u.cell ?? ""}-${u.item}-${i}`} className="ac-arch-row" data-static="">
              <span className="ac-arch-row-name">{formatMessage(messages.unavailableItem, { item: u.item, reason: u.reason || messages.notCollectedHelp })}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function CellRow({ cell, messages, tones, kinds, selected, highlighted, onPress }: { cell: ArchitectureCellView; messages: ArchViewMessages; tones: Readonly<Record<string, string>>; kinds: Readonly<Record<string, MetricKindSpec>>; selected: boolean; highlighted: boolean; onPress: () => void }) {
  const pieces = cell.status === "not_collected" ? [] : metricPieces(cell.metrics, messages, { kinds });
  return (
    <button
      type="button"
      className="ac-arch-row"
      data-cell-id={cell.id}
      data-status={cell.status}
      data-selected={selected ? "" : undefined}
      data-highlighted={highlighted ? "" : undefined}
      aria-pressed={selected}
      aria-label={cellAriaLabel(cell, messages, { highlighted, kinds })}
      style={{ ["--cell-tone" as string]: `var(${resolveTone(cell.tone, tones)})` }}
      onClick={onPress}
    >
      <span className="ac-arch-cell-band" aria-hidden="true" />
      <span className="ac-arch-row-name">{cell.label}</span>
      <span className="ac-arch-row-metrics" aria-hidden="true">
        {cell.status === "not_collected" ? <span className="ac-arch-metric" data-status="not_collected">{messages.metricNotCollected}</span> : pieces.map((p) => <MetricPiece key={p.name} piece={p} />)}
      </span>
      {cell.status === "partial" ? <span className="ac-arch-badge" data-kind="partial" aria-hidden="true">{messages.badgePartial}</span> : null}
      {highlighted ? <span className="ac-arch-badge" data-kind="event" aria-hidden="true">{messages.badgeEvent}</span> : null}
    </button>
  );
}

function EdgeRow({ edge, labels, messages, kinds, selected, highlighted, onPress }: { edge: ArchitectureEdgeView; labels: Record<string, string>; messages: ArchViewMessages; kinds: Readonly<Record<string, MetricKindSpec>>; selected: boolean; highlighted: boolean; onPress: () => void }) {
  const pieces = edge.kind === "observed" && edge.status !== "not_collected" ? metricPieces(edge.metrics, messages, { kinds }) : [];
  return (
    <button
      type="button"
      className="ac-arch-row"
      data-edge-id={edge.id}
      data-state={edge.kind === "structural" ? "structural" : edge.status === "not_collected" ? "dead" : "observed"}
      data-selected={selected ? "" : undefined}
      data-highlighted={highlighted ? "" : undefined}
      aria-pressed={selected}
      aria-label={edgeAriaLabel(edge, labels, messages, { highlighted, kinds })}
      onClick={onPress}
    >
      <span className="ac-arch-row-name">{edge.label || edge.id}</span>
      <span className="ac-arch-row-flow" aria-hidden="true">{formatMessage(messages.flow, { from: labels[edge.from] ?? edge.from, to: labels[edge.to] ?? edge.to })}</span>
      <span className="ac-arch-row-metrics" aria-hidden="true">
        {edge.kind === "structural" ? <span className="ac-arch-metric">{messages.edgeStructural}</span> : edge.status === "not_collected" ? <span className="ac-arch-metric" data-status="not_collected">{messages.metricNotCollected}</span> : pieces.map((p) => <MetricPiece key={p.name} piece={p} />)}
      </span>
    </button>
  );
}
