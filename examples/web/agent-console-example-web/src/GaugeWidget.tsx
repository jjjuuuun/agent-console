import type { WidgetDescriptor, WidgetRenderProps } from "@agent-console/log-view";

const numberOption = (v: unknown, fallback: number): number => (typeof v === "number" && Number.isFinite(v) && v > 0 ? v : fallback);

/**
 * 첫 행의 값을 `options.max` 대비 비율로 보이는 게이지 본문. 값이 없으면(null) 0%가 아니라 "–"를 보인다.
 * `options.max`가 숫자가 아니면 기본 100.
 */
export function GaugeBody({ rows, title, options, formatters, messages }: WidgetRenderProps) {
  const value = rows[0]?.value;
  const max = numberOption(options["max"], 100);
  if (value == null) {
    return (
      <p role="group" aria-label={title} data-testid="gauge-empty">
        {messages.none}
      </p>
    );
  }
  return (
    <div role="group" aria-label={title}>
      <meter value={Math.min(value, max)} min={0} max={max} aria-label={title} />
      <span data-testid="gauge-value">{formatters.number(value)}</span>
    </div>
  );
}

/**
 * 대시보드 위젯 종류 하나(X21). 종류 id·제목·옵션 스키마는 이 객체의 데이터다.
 * `createWidgetRegistry(builtinWidgets, [gaugeWidget])`처럼 목록에 더하면 격자가 그린다.
 */
export const gaugeWidget: WidgetDescriptor = {
  kind: "example.gauge",
  title: "게이지",
  description: "지표 하나를 최대값 대비 막대로 보인다",
  queryShape: { groupBy: { min: 0, max: 0 } },
  optionsSchema: {
    type: "object",
    properties: { max: { type: "number", title: "최대값", exclusiveMinimum: 0, default: 100 } },
  },
  defaultSize: { w: 3, h: 2 },
  render: (props) => <GaugeBody {...props} />,
};
