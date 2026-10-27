import { defaultEdgeLegendKeys, defaultEdgeStyles, resolveEdgeStyle } from "./defaults";
import { resolveMessages } from "./messages";
import type { ArchViewMessages } from "./messages";
import type { EdgeStyleSpec } from "./types";

export interface ArchitectureLegendProps {
  messages?: Partial<ArchViewMessages>;
  /** 범례 견본에 쓸 연결 모양. 기본은 X24 기본표. */
  edgeStyles?: Readonly<Record<string, EdgeStyleSpec>>;
  /** 견본으로 보일 연결 style 이름. 생략하면 `edgeStyles`의 모든 이름. */
  edgeStyleNames?: readonly string[];
  /** 연결 style 이름 → 범례 글자. 없으면 기본 문구 표, 그것도 없으면 이름 그대로. */
  edgeLegend?: Readonly<Record<string, string>>;
  id?: string;
  className?: string;
}

function Line({ spec, state }: { spec: EdgeStyleSpec; state?: "dead" | "error" }) {
  const stroke = state === "error" ? "--ac-danger" : state === "dead" ? "--ac-edge-dead" : spec.stroke;
  const dash = state === "dead" ? "--ac-edge-pattern-2" : spec.dash;
  return (
    <svg className="ac-arch-swatch-line" width="40" height="12" viewBox="0 0 40 12" aria-hidden="true" focusable="false">
      <path d="M2 6H28" style={{ stroke: `var(${stroke})`, strokeDasharray: dash ? `var(${dash})` : undefined }} className="ac-arch-edge-line" />
      <path d="M27 1L37 6L27 11Z" style={{ fill: `var(${stroke})` }} />
    </svg>
  );
}

/**
 * 범례(§2.6). 견본은 실제 칸·연결과 같은 CSS 클래스·데이터 속성으로 그리므로 모양이 바뀌면 함께 바뀐다.
 */
export function ArchitectureLegend({ messages: partial, edgeStyles = defaultEdgeStyles, edgeStyleNames, edgeLegend, id, className }: ArchitectureLegendProps) {
  const m = resolveMessages(partial);
  const names = edgeStyleNames ?? Object.keys(edgeStyles);
  return (
    <ul id={id} className={["ac-arch-legend", className].filter(Boolean).join(" ")}>
      {names.map((n) => (
        <li key={n} data-legend={`edge:${n}`}>
          <Line spec={resolveEdgeStyle(n, edgeStyles)} />
          <span>{edgeLegend?.[n] ?? (defaultEdgeLegendKeys[n] ? m[defaultEdgeLegendKeys[n] as keyof ArchViewMessages] : n)}</span>
        </li>
      ))}
      <li data-legend="not_collected"><span className="ac-arch-cell ac-arch-swatch" data-status="not_collected" aria-hidden="true" /><span>{m.legendNotCollected}</span></li>
      <li data-legend="partial"><span className="ac-arch-badge" data-kind="partial">{m.badgePartial}</span><span>{m.legendPartial}</span></li>
      <li data-legend="estimate"><span className="ac-arch-metric" data-inferred="">{m.metricInferred}</span><span>{m.legendInferred}</span></li>
      <li data-legend="error"><span className="ac-arch-cell ac-arch-swatch" data-errors="" aria-hidden="true" /><span>{m.legendError}</span></li>
      <li data-legend="selected"><span className="ac-arch-cell ac-arch-swatch" data-selected="" aria-hidden="true" /><span>{m.legendSelected}</span></li>
      <li data-legend="highlighted"><span className="ac-arch-cell ac-arch-swatch" data-highlighted="" aria-hidden="true" /><span>{m.legendHighlighted}</span></li>
      <li data-legend="zone"><span className="ac-arch-zone ac-arch-swatch-zone" data-zone-style="runtime" aria-hidden="true" /><span>{m.legendZone}</span></li>
    </ul>
  );
}
