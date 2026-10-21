import type { HTMLAttributes } from "react";

/** 상태 종류. `run`이면 `data-status-kind="run"`을 달아 Run 상태 규칙(completed/paused/interrupted)이 적용된다. */
export type StatusKind = "node" | "run";

export interface StatusIconProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  /** 서버가 준 상태 문자열 그대로. 모르는 값은 tokens.css 폴백(점선 + 물음표)으로 그려진다. */
  status: string;
  kind?: StatusKind;
  /** 렌더 크기(px). 기본 16. 칩·패널에서는 14. */
  size?: 14 | 16;
  /** 접근성 이름(앱이 messages에서 전달). 없으면 장식으로 간주해 숨긴다. */
  label?: string;
}

/** 상태 아이콘. `data-status`만 달고 모양·색·애니메이션은 tokens.css가 정한다. */
export function StatusIcon({ status, kind = "node", size = 16, label, ...rest }: StatusIconProps) {
  const a11y = label === undefined ? { "aria-hidden": true } : { role: "img", "aria-label": label };
  return (
    <span
      {...rest}
      {...a11y}
      className={joinClass("ac-status-icon", rest.className)}
      data-status={status}
      data-status-kind={kind === "run" ? "run" : undefined}
      data-size={size === 14 ? "14" : undefined}
    />
  );
}

export interface StatusChipProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  status: string;
  kind?: StatusKind;
  /** 화면에 보일 한글 라벨(앱이 messages로 전달). 생략하면 상태 문자열 원문. */
  label?: string;
  /** 아이콘만 표시하고 라벨은 aria-label/title로. */
  compact?: boolean;
}

/** 상태 칩 = 아이콘 + 라벨 + tint. 라벨은 한 줄 말줄임이며 전체 값은 title로도 제공한다. */
export function StatusChip({ status, kind = "node", label, compact = false, ...rest }: StatusChipProps) {
  const text = label ?? status;
  return (
    <span
      title={text}
      {...rest}
      {...(compact ? { role: "img", "aria-label": text } : {})}
      className={joinClass("ac-status-chip", rest.className)}
      data-status={status}
      data-status-kind={kind === "run" ? "run" : undefined}
      data-compact={compact ? "true" : undefined}
    >
      <StatusIcon status={status} kind={kind} size={14} />
      {compact ? null : <span className="ac-status-chip-label ac-ellipsis">{text}</span>}
    </span>
  );
}

export function joinClass(...parts: Array<string | undefined | false>): string {
  return parts.filter(Boolean).join(" ");
}
