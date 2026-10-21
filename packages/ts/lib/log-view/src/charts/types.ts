/** 차트 어댑터의 라이브러리 중립 입력. 차트 라이브러리 타입은 이 폴더 밖으로 나가지 않는다. */
export interface ChartSeries {
  key: string;
  label: string;
  /** CSS 색(토큰 변수 가능). */
  color: string;
  /** SVG stroke-dasharray. 비면 실선. */
  dash?: string;
}

export interface LineChartProps {
  /** x축 라벨(시간 차원 값 등). */
  xLabels: readonly string[];
  series: readonly ChartSeries[];
  /** series.key -> x 순서의 값(null = 값 없음, 선을 끊는다). */
  values: Readonly<Record<string, readonly (number | null)[]>>;
  width: number;
  height: number;
  formatValue?: (n: number) => string;
  ariaLabel: string;
}
