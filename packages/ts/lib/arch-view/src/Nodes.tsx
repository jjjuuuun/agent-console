import { Fragment, memo } from "react";
import type { ReactNode } from "react";
import type { Node, NodeProps } from "@xyflow/react";
import type { ArchitectureCellView, ArchitectureZone } from "@agent-console/contracts/architecture";
import { METRIC_COUNT, METRIC_ERRORS, resolveTone } from "./defaults";
import { useDiagram } from "./context";
import { metricPieces } from "./format";
import type { MetricText } from "./format";
import { cellAccessibleName, cellHasErrors } from "./model";
import type { ArchLevel, MetricKindSpec } from "./types";
import type { ArchViewMessages } from "./messages";

export type CellNodeData = { cellId: string } & Record<string, unknown>;
export type ZoneNodeData = { zone: ArchitectureZone } & Record<string, unknown>;

/** 위치 규칙: 영역 제목 기준선 좌표는 CSS가 정한다(§2.4). */
export const ZoneNode = memo(function ZoneNode({ data }: NodeProps<Node<ZoneNodeData>>) {
  const z = data.zone;
  return (
    <div className="ac-arch-zone" data-zone-id={z.id} data-zone-style={z.style ?? undefined} aria-hidden="true">
      {z.label ? <span className="ac-arch-zone-title">{z.label}</span> : null}
      {z.description ? <span className="ac-arch-zone-desc">{z.description}</span> : null}
    </div>
  );
});

function Icon({ name }: { name: "unknown" | "failed" }) {
  return <span className="ac-arch-icon" data-icon={name} aria-hidden="true" />;
}

/** 지표 줄 한 조각. 수집 안 됨은 "–", 추정은 "추정" 글자 + 점선 밑줄. */
export function MetricPiece({ piece, errorIcon }: { piece: MetricText; errorIcon?: boolean }) {
  const isErr = piece.name === METRIC_ERRORS && piece.value !== null && piece.value > 0;
  return (
    <span className="ac-arch-metric" data-status={piece.status} data-inferred={piece.inferred ? "" : undefined} data-error={isErr ? "" : undefined}>
      {isErr && errorIcon !== false ? <Icon name="failed" /> : null}
      {piece.text}
    </span>
  );
}

function summaryText(cell: ArchitectureCellView, pieces: MetricText[], messages: ArchViewMessages): string {
  if (cell.status === "not_collected") return messages.metricDash;
  const count = pieces.find((p) => p.name === METRIC_COUNT) ?? pieces[0];
  return count ? count.text : "";
}

function CellBody({ cell, level, mode }: { cell: ArchitectureCellView; level: ArchLevel; mode: "live" | "layout" }) {
  const ctx = useDiagram();
  const { messages } = ctx;
  const notCollected = cell.status === "not_collected";
  if (level === "summary" && mode === "live") {
    const pieces = metricPieces(cell.metrics, messages, { compact: true, kinds: ctx.metricKinds, ...(ctx.locale === undefined ? {} : { locale: ctx.locale }) });
    return (
      <span className="ac-arch-cell-sum" aria-hidden="true">
        {summaryText(cell, pieces, messages)}
      </span>
    );
  }
  const pieces = metricPieces(cell.metrics, messages, { kinds: ctx.metricKinds, ...(ctx.locale === undefined ? {} : { locale: ctx.locale }) });
  const highlighted = ctx.highlight.cells.has(cell.id);
  return (
    <>
      <span className="ac-arch-cell-title">
        <span className="ac-arch-cell-name">{cell.label}</span>
        {mode === "live" && (highlighted || cell.status === "partial") ? (
          <>
          {" "}
          <span className="ac-arch-badges">
            {highlighted ? <span className="ac-arch-badge" data-kind="event">{messages.badgeEvent}</span> : null}
            {highlighted && cell.status === "partial" ? " " : null}
            {cell.status === "partial" ? <span className="ac-arch-badge" data-kind="partial" title={cell.partial_reason ?? undefined}>{messages.badgePartial}</span> : null}
          </span>
          </>
        ) : null}
      </span>
      {" "}
      <span className="ac-arch-cell-desc" title={cell.description ?? undefined}>{cell.description ?? ""}</span>
      {" "}
      {mode === "live" ? (
        <span className="ac-arch-cell-metrics">
          {notCollected ? (
            <span className="ac-arch-metric" data-status="not_collected">
              <Icon name="unknown" />
              {messages.metricNotCollected}
            </span>
          ) : (
            pieces.map((p, i) => (
              <Fragment key={p.name}>
                {i > 0 ? " " : null}
                <MetricPiece piece={p} />
              </Fragment>
            ))
          )}
        </span>
      ) : (
        <span className="ac-arch-cell-metrics" />
      )}
    </>
  );
}

/**
 * 칸 단추 안에 보이는 글자를 `CellBody`와 같은 순서로 이어 붙인다(접근 이름이 그 글자를 포함하도록, WCAG 2.5.3).
 * 요약 배율에서는 숫자만 보이지만 접근 이름은 배율과 상관없이 같도록 전체 글자를 쓰고, 요약 숫자가 거기 없으면 덧붙인다.
 */
function cellVisibleText(cell: ArchitectureCellView, level: ArchLevel, highlighted: boolean, messages: ArchViewMessages, kinds: Readonly<Record<string, MetricKindSpec>> | undefined, locale: string | undefined): string {
  const loc = locale === undefined ? {} : { locale };
  const pieces = metricPieces(cell.metrics, messages, { kinds, ...loc });
  const parts = [cell.label];
  if (highlighted) parts.push(messages.badgeEvent);
  if (cell.status === "partial") parts.push(messages.badgePartial);
  if (cell.description) parts.push(cell.description);
  if (cell.status === "not_collected") parts.push(messages.metricNotCollected);
  else parts.push(...pieces.map((p) => p.text));
  const full = parts.join(" ");
  // 요약 배율에서도 이름이 같도록(§13-8) 전체 배율 이름에도 같은 숫자 낱말을 넣는다
  if (level !== "summary" && cell.status === "not_collected") return full;
  const sum = summaryText(cell, metricPieces(cell.metrics, messages, { compact: true, kinds, ...loc }), messages);
  // 접근 이름 비교는 낱말 단위라(axe label-content-name-mismatch) "5회" 안의 "5"는 보이는 "5"로 치지 않는다 — 낱말로 없으면 덧붙인다
  return sum === "" || full.split(/\s+/).includes(sum) ? full : `${full} ${sum}`;
}

export const CellNode = memo(function CellNode({ data }: NodeProps<Node<CellNodeData>>) {
  const ctx = useDiagram();
  const cell = ctx.cells[data.cellId];
  if (!cell) return null;
  const { messages, level, mode } = ctx;
  const tone = resolveTone(cell.tone, ctx.tones);
  const selected = ctx.selection?.kind === "cell" && ctx.selection.id === cell.id;
  const highlighted = ctx.highlight.cells.has(cell.id);
  const renderer = cell.view && Object.prototype.hasOwnProperty.call(ctx.cellRenderers, cell.view) ? ctx.cellRenderers[cell.view] : undefined;
  const body: ReactNode = <CellBody cell={cell} level={level} mode={mode} />;
  const tip = [cell.label, cell.description, cell.partial_reason].filter(Boolean).join(" — ");
  return (
    <button
      type="button"
      className="ac-arch-cell"
      data-cell-id={cell.id}
      data-status={mode === "live" ? cell.status : "observed"}
      data-level={level}
      data-selected={selected ? "" : undefined}
      data-highlighted={highlighted && mode === "live" ? "" : undefined}
      data-errors={mode === "live" && cellHasErrors(cell) ? "" : undefined}
      aria-pressed={selected}
      aria-label={mode === "live" ? cellAccessibleName(cell, cellVisibleText(cell, level, highlighted, messages, ctx.metricKinds, ctx.locale), messages, { highlighted, kinds: ctx.metricKinds, ...(ctx.locale === undefined ? {} : { locale: ctx.locale }) }) : cell.label}
      title={tip}
      style={{ ["--cell-tone" as string]: `var(${tone})` }}
      onClick={() => ctx.activate({ kind: "cell", id: cell.id })}
      onDoubleClick={() => (cell.drillable ? ctx.drill(cell.id) : undefined)}
    >
      <span className="ac-arch-cell-band" aria-hidden="true" />
      {renderer ? renderer({ cell, level, messages, defaultBody: body }) : body}
    </button>
  );
});

