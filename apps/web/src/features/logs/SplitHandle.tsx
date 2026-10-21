import { useRef, type KeyboardEvent, type PointerEvent } from "react";

export interface SplitHandleProps {
  /** 조절되는 패널의 현재 크기(px). vertical이면 오른쪽 패널의 폭, horizontal이면 위쪽 패널의 높이 */
  size: number;
  min: number;
  max: number;
  onChange(next: number): void;
  label: string;
  /** 키보드 한 번에 움직이는 px */
  step?: number;
  /**
   * `vertical`(기본): 세로 분리선, 패널이 오른쪽에 있다(왼쪽으로 끌면 커진다, `←`가 키운다).
   * `horizontal`: 가로 분리선, 패널이 위에 있다(아래로 끌면 커진다, `↓`가 키운다).
   */
  orientation?: "vertical" | "horizontal";
}

/** 분리선(패널 크기 조절): 포인터로 끌거나 포커스 뒤 방향키(기본 16px 단위). `role="separator"` + 현재 값. */
export function SplitHandle({ size, min, max, onChange, label, step = 16, orientation = "vertical" }: SplitHandleProps) {
  const start = useRef<{ p: number; s: number } | null>(null);
  const horizontal = orientation === "horizontal";
  const clamp = (n: number) => Math.min(max, Math.max(min, n));
  const down = (e: PointerEvent<HTMLDivElement>) => {
    start.current = { p: horizontal ? e.clientY : e.clientX, s: size };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const move = (e: PointerEvent<HTMLDivElement>) => {
    const s = start.current;
    if (s === null) return;
    const delta = horizontal ? e.clientY - s.p : s.p - e.clientX;
    onChange(clamp(s.s + delta));
  };
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    const grow = horizontal ? "ArrowDown" : "ArrowLeft";
    const shrink = horizontal ? "ArrowUp" : "ArrowRight";
    if (e.key === grow) {
      e.preventDefault();
      onChange(clamp(size + step));
    } else if (e.key === shrink) {
      e.preventDefault();
      onChange(clamp(size - step));
    }
  };
  return (
    <div
      role="separator"
      aria-orientation={horizontal ? "horizontal" : "vertical"}
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={size}
      tabIndex={0}
      className={horizontal ? "logs-split logs-split-h" : "logs-split"}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={() => (start.current = null)}
      onKeyDown={key}
    />
  );
}
