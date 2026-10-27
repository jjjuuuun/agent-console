import { useId } from "react";
import { ViewportPortal } from "@xyflow/react";
import { useDiagram } from "./context";
import { edgeAriaLabel, edgeBlockedReason } from "./model";
import type { EdgeModel } from "./model";

/** 선택·강조·상태가 정한 선 색(토큰 변수 이름). 화살촉도 같은 색으로 채운다. */
function strokeVar(m: EdgeModel, selected: boolean, highlighted: boolean): string {
  if (selected) return "--ac-edge-selected";
  if (highlighted) return "--ac-edge-active";
  if (m.state === "dead") return "--ac-edge-dead";
  if (m.state === "error") return "--ac-danger";
  return m.style.stroke;
}
function dashVar(m: EdgeModel): string | undefined {
  if (m.state === "dead") return "--ac-edge-pattern-2";
  if (m.state === "structural") return m.style.dash ?? "--ac-edge-pattern-1";
  return m.style.dash;
}

/**
 * 연결(꺾은선)과 라벨 칩을 칸 위 레이어에 그린다. `ViewportPortal`이라 캔버스 좌표계를 그대로 쓰고
 * 레이어는 영역 < 칸 < 연결 < 칩 순이다. 연결 시작·끝은 `points`가 이미 경계 6px 바깥이다.
 */
export function EdgeLayer({ models, width, height }: { models: readonly EdgeModel[]; width: number; height: number }) {
  const ctx = useDiagram();
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const markers = new Map<string, string>();
  const rows = models.map((m) => {
    const selected = ctx.selection?.kind === "edge" && ctx.selection.id === m.edge.id;
    const highlighted = ctx.highlight.edges.has(m.edge.id);
    const stroke = strokeVar(m, selected, highlighted);
    if (!markers.has(stroke)) markers.set(stroke, `ac-arch-mk-${uid}-${markers.size}`);
    return { m, selected, highlighted, stroke, dash: dashVar(m), marker: markers.get(stroke) as string };
  });
  const summary = ctx.level === "summary";
  return (
    <ViewportPortal>
      <div className="ac-arch-layer" style={{ width, height }}>
        <svg className="ac-arch-edges" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" focusable="false">
          <defs>
            {[...markers].map(([stroke, id]) => (
              <marker key={id} id={id} markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse">
                <path d="M1 1L11 6L1 11Z" style={{ fill: `var(${stroke})` }} />
              </marker>
            ))}
          </defs>
          {rows.map(({ m, selected, highlighted, stroke, dash, marker }) => (
            <g key={m.edge.id} className="ac-arch-edge" data-edge-id={m.edge.id} data-state={m.state} data-selected={selected ? "" : undefined} data-highlighted={highlighted ? "" : undefined}>
              <path className="ac-arch-edge-hit" d={m.d} onClick={() => ctx.activate({ kind: "edge", id: m.edge.id })} />
              <path
                className="ac-arch-edge-line"
                d={m.d}
                markerEnd={`url(#${marker})`}
                style={{ stroke: `var(${stroke})`, strokeDasharray: dash ? `var(${dash})` : undefined }}
              />
            </g>
          ))}
        </svg>
        {rows.map(({ m, selected, highlighted, stroke }) => {
          const e = m.edge;
          const blocked = edgeBlockedReason(e);
          return (
            <button
              key={e.id}
              type="button"
              className="ac-arch-chip"
              data-edge-id={e.id}
              data-state={m.state}
              data-level={ctx.level}
              data-selected={selected ? "" : undefined}
              data-highlighted={highlighted ? "" : undefined}
              data-blocked={blocked ?? undefined}
              aria-pressed={selected}
              aria-label={edgeAriaLabel(e, ctx.cellLabels, ctx.messages, { highlighted, kinds: ctx.metricKinds })}
              title={m.fit.labelClipped ? (e.label ?? undefined) : undefined}
              style={{ left: m.center[0], top: m.center[1], maxWidth: m.cap, ["--arch-stroke" as string]: `var(${stroke})` }}
              onClick={() => ctx.activate({ kind: "edge", id: e.id })}
            >
              {summary ? null : (
                <>
                  {highlighted ? <span className="ac-arch-chip-dot" aria-hidden="true" /> : null}
                  <span className="ac-arch-chip-label">{e.label ?? ""}</span>
                  {m.fit.count ? <b className="ac-arch-chip-count">{m.fit.count}</b> : null}
                  {m.errorText ? (
                    <span className="ac-arch-chip-err">
                      <span className="ac-arch-icon" data-icon="failed" aria-hidden="true" />
                      {m.fit.errorsIconOnly ? null : m.errorText}
                    </span>
                  ) : null}
                </>
              )}
            </button>
          );
        })}
      </div>
    </ViewportPortal>
  );
}
