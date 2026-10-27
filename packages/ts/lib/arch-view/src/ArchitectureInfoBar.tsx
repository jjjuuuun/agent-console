import type { ArchitectureCellView, ArchitectureEdgeView, ArchitectureGroupView, ArchitectureMetric, ArchitectureUnavailableView, ArchitectureView } from "@agent-console/contracts/architecture";
import { METRIC_COUNT, defaultMetricKinds } from "./defaults";
import { formatDurationMs, formatMetric, metricPieces } from "./format";
import { formatMessage, resolveMessages } from "./messages";
import type { ArchViewMessages } from "./messages";
import { sameSelection } from "./model";
import type { ArchSelection, MetricKindSpec } from "./types";

export interface ArchitectureInfoBarProps {
  view: ArchitectureView;
  /** 풀어 쓸 대상(포커스 대상이 있으면 그것, 없으면 선택). 없으면 안내 문구. */
  target: ArchSelection | null;
  /** 포커스만 있고 선택은 아닌 대상을 보여 주는 중이면 "미리보기"를 붙인다. */
  preview?: boolean;
  /** 지금 걸러 둔 대상(묶음 칩의 눌림 표시용). */
  selection?: ArchSelection | null;
  messages?: Partial<ArchViewMessages>;
  metricKinds?: Readonly<Record<string, MetricKindSpec>>;
  onSelect?: (selection: ArchSelection | null) => void;
  onDrill?: (cellId: string, group?: string | null) => void;
  className?: string;
}

function Longs({ metrics, messages, kinds }: { metrics: Readonly<Record<string, ArchitectureMetric>> | undefined; messages: ArchViewMessages; kinds: Readonly<Record<string, MetricKindSpec>> }) {
  const pieces = metricPieces(metrics, messages, { kinds });
  return (
    <>
      {pieces.map((p) => {
        const detail = metrics?.[p.name]?.detail;
        return (
          <span key={p.name} className="ac-arch-info-metric" data-status={p.status}>
            {p.long}
            {detail && detail.samples > 0 ? (
              <span className="ac-arch-info-detail">
                {" "}
                ({[
                  detail.avg_ms != null ? `${messages.metricAvg} ${formatDurationMs(detail.avg_ms, messages)}` : null,
                  detail.max_ms != null ? `${messages.metricMax} ${formatDurationMs(detail.max_ms, messages)}` : null,
                  formatMessage(messages.metricSamples, { n: detail.samples }),
                ].filter(Boolean).join(" · ")})
              </span>
            ) : null}
          </span>
        );
      })}
    </>
  );
}

const groupLabel = (g: ArchitectureGroupView, m: ArchViewMessages): string => g.label ?? g.key ?? m.noName;

/**
 * 선택 정보 줄(§5.4). 칸·연결·묶음·분류 안 됨 하나를 풀어 쓴다. 지표는 관측/추정/수집 안 됨을 글자로 구분하고 0으로 채우지 않는다.
 */
export function ArchitectureInfoBar({ view, target, preview, selection, messages: partial, metricKinds, onSelect, onDrill, className }: ArchitectureInfoBarProps) {
  const messages = resolveMessages(partial);
  const kinds = metricKinds ?? defaultMetricKinds;
  const cell = target && (target.kind === "cell" || target.kind === "group") ? (view.cells ?? []).find((c) => c.id === target.id) : undefined;
  const edge = target?.kind === "edge" ? (view.edges ?? []).find((e) => e.id === target.id) : undefined;
  const labels = Object.fromEntries((view.cells ?? []).map((c) => [c.id, c.label]));
  let body: React.ReactNode = <span className="ac-arch-info-hint">{messages.hintEmpty}</span>;

  if (target?.kind === "cell" && cell) body = <CellInfo cell={cell} view={view} messages={messages} kinds={kinds} selection={selection ?? null} onSelect={onSelect} onDrill={onDrill} />;
  else if (target?.kind === "edge" && edge) body = <EdgeInfo edge={edge} labels={labels} messages={messages} kinds={kinds} />;
  else if (target?.kind === "group" && cell) {
    const g = (cell.groups ?? []).find((x) => x.key === target.group);
    if (g) {
      body = (
        <>
          <strong className="ac-arch-info-name">{`${cell.label} › ${groupLabel(g, messages)}`}</strong>
          <span className="ac-arch-info-metrics"><Longs metrics={g.metrics} messages={messages} kinds={kinds} /></span>
        </>
      );
    }
  } else if (target?.kind === "unassigned" && view.unassigned) {
    body = (
      <>
        <strong className="ac-arch-info-name">{messages.listUnassigned}</strong>
        <span className="ac-arch-info-metrics"><Longs metrics={view.unassigned.metrics} messages={messages} kinds={kinds} /></span>
      </>
    );
  }
  return (
    <div className={["ac-arch-info", className].filter(Boolean).join(" ")} role="status" data-empty={body && target ? undefined : ""}>
      {preview && target ? <span className="ac-arch-info-preview">{messages.preview}</span> : null}
      {body}
    </div>
  );
}

function Unavailable({ items, messages }: { items: readonly ArchitectureUnavailableView[]; messages: ArchViewMessages }) {
  if (items.length === 0) return null;
  return (
    <ul className="ac-arch-info-unavail">
      {items.map((u, i) => (
        <li key={`${u.item}-${i}`}>{formatMessage(messages.unavailableItem, { item: u.item, reason: u.reason || messages.notCollectedHelp })}</li>
      ))}
    </ul>
  );
}

function CellInfo({ cell, view, messages, kinds, selection, onSelect, onDrill }: { cell: ArchitectureCellView; view: ArchitectureView; messages: ArchViewMessages; kinds: Readonly<Record<string, MetricKindSpec>>; selection: ArchSelection | null; onSelect?: (s: ArchSelection | null) => void; onDrill?: (cellId: string, group?: string | null) => void }) {
  const own = [...(cell.unavailable ?? []), ...(view.unavailable ?? []).filter((u) => u.cell === cell.id && !(cell.unavailable ?? []).some((x) => x.item === u.item))];
  return (
    <>
      <strong className="ac-arch-info-name">{cell.label}</strong>
      {cell.description ? <span className="ac-arch-info-desc">{cell.description}</span> : null}
      <span className="ac-arch-info-metrics">
        {cell.status === "not_collected" ? <span className="ac-arch-info-metric" data-status="not_collected">{`${messages.metricNotCollected} — ${messages.notCollectedHelp}`}</span> : <Longs metrics={cell.metrics} messages={messages} kinds={kinds} />}
      </span>
      {cell.status === "partial" && cell.partial_reason ? <span className="ac-arch-info-partial">{formatMessage(messages.ariaPartial, { reason: cell.partial_reason })}</span> : null}
      <Unavailable items={own} messages={messages} />
      {(cell.groups ?? []).length > 0 || cell.groups_rest ? (
        <span className="ac-arch-info-groups">
          {(cell.groups ?? []).map((g) => {
            const sel: ArchSelection = { kind: "group", id: cell.id, group: g.key };
            const count = g.metrics?.[METRIC_COUNT];
            const text = count ? formatMetric(count, messages, { name: METRIC_COUNT, compact: true }).text : "";
            return (
              <button
                key={g.key ?? "__none"}
                type="button"
                className="ac-arch-group-chip"
                aria-pressed={sameSelection(selection, sel)}
                onClick={() => onSelect?.(sameSelection(selection, sel) ? null : sel)}
                onDoubleClick={() => (g.drill ? onDrill?.(cell.id, g.key) : undefined)}
              >
                {groupLabel(g, messages)}
                {text ? <b>{` ${text}`}</b> : null}
              </button>
            );
          })}
          {cell.groups_rest ? <span className="ac-arch-group-rest">{formatMessage(messages.groupOthers, { n: cell.groups_rest.groups })}</span> : null}
        </span>
      ) : null}
      {cell.drillable && onDrill ? (
        <button type="button" className="ac-arch-info-drill" onClick={() => onDrill(cell.id)}>
          {messages.drill}
        </button>
      ) : null}
    </>
  );
}

function EdgeInfo({ edge, labels, messages, kinds }: { edge: ArchitectureEdgeView; labels: Record<string, string>; messages: ArchViewMessages; kinds: Readonly<Record<string, MetricKindSpec>> }) {
  return (
    <>
      <strong className="ac-arch-info-name">{edge.label || edge.id}</strong>
      <span className="ac-arch-info-desc">{formatMessage(messages.flow, { from: labels[edge.from] ?? edge.from, to: labels[edge.to] ?? edge.to })}</span>
      <span className="ac-arch-info-kind">{edge.kind === "structural" ? messages.edgeStructural : messages.edgeObserved}</span>
      {edge.kind === "observed" ? (
        <span className="ac-arch-info-metrics">
          {edge.status === "not_collected" ? <span className="ac-arch-info-metric" data-status="not_collected">{`${messages.metricNotCollected} — ${messages.notCollectedHelp}`}</span> : <Longs metrics={edge.metrics} messages={messages} kinds={kinds} />}
        </span>
      ) : null}
    </>
  );
}
