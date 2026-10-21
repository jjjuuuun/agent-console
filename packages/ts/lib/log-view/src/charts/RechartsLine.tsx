import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import type { LineChartProps } from "./types";

/** recharts 꺾은선(지연 로드 대상). 이 파일만 recharts를 import한다. */
export default function RechartsLine({ xLabels, series, values, width, height, formatValue, ariaLabel }: LineChartProps) {
  const data = xLabels.map((x, i) => {
    const point: Record<string, string | number | null> = { x };
    for (const s of series) point[s.key] = values[s.key]?.[i] ?? null;
    return point;
  });
  return (
    <LineChart width={width} height={height} data={data} role="img" aria-label={ariaLabel} accessibilityLayer>
      <CartesianGrid stroke="var(--ac-chart-grid, var(--ac-border))" strokeDasharray="3 3" />
      <XAxis dataKey="x" tick={{ fontSize: 12, fill: "var(--ac-chart-axis-text, var(--ac-text-muted))" }} />
      <YAxis tick={{ fontSize: 12, fill: "var(--ac-chart-axis-text, var(--ac-text-muted))" }} width={48} tickFormatter={formatValue} />
      <Tooltip formatter={(v) => (typeof v === "number" && formatValue ? formatValue(v) : String(v))} />
      {series.map((s) => (
        <Line key={s.key} type="linear" dataKey={s.key} name={s.label} stroke={s.color} strokeDasharray={s.dash} dot={{ r: 2 }} connectNulls={false} isAnimationActive={false} />
      ))}
    </LineChart>
  );
}
