import { joinClass } from "./Status";

export interface GaugeProps {
  /** 0~1. 없으면 "값 없음" 상태(0%를 그리지 않는다). */
  value?: number;
  size?: "md" | "lg";
  /** 오래된 값: 빗금 + 불투명도 .6. */
  stale?: boolean;
  /** 접근성 이름. */
  label: string;
  /** 값 없음일 때 보이는 문구. */
  noValueLabel: string;
  /** 접근성용 값 텍스트(예: "42%"). 생략하면 퍼센트를 계산한다. */
  valueText?: string;
  className?: string;
}

/** 사용률 게이지. 색은 값에 따라 바뀌지 않는다(`--ac-gauge-fill` 고정). `role=meter`는 값이 있을 때만. */
export function Gauge({ value, size = "md", stale = false, label, noValueLabel, valueText, className }: GaugeProps) {
  const hasValue = typeof value === "number" && Number.isFinite(value);
  if (!hasValue) {
    return (
      <div className={joinClass("ac-gauge", className)} data-size={size} data-no-value="true" role="img" aria-label={`${label}: ${noValueLabel}`}>
        <span className="ac-gauge-none" aria-hidden="true">{noValueLabel}</span>
      </div>
    );
  }
  const clamped = Math.min(1, Math.max(0, value));
  return (
    <div
      className={joinClass("ac-gauge", className)}
      data-size={size}
      data-stale={stale ? "true" : undefined}
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={clamped}
      aria-valuetext={valueText ?? `${Math.round(clamped * 100)}%`}
    >
      <div className="ac-gauge-fill" style={{ width: `${clamped * 100}%` }} />
    </div>
  );
}
