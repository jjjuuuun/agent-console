import { joinClass } from "./Status";

export interface TrustBadgeProps {
  /** 신뢰 등급 문자열(열린 값). 스타일이 아는 값은 색·아이콘이 달라지고, 모르는 값은 중립 배지로 보인다. */
  trust: string;
  /** 표시 문구. 앱이 messages 표에서 골라 넘긴다. 비어 있으면 `trust` 원문을 보인다. */
  label?: string;
  className?: string;
}

/** 신뢰 등급 배지. 색 단독이 아니라 아이콘·테두리 모양·텍스트를 함께 쓴다(tokens.md 5.3). 등급 목록을 코드에 두지 않는다. */
export function TrustBadge({ trust, label, className }: TrustBadgeProps) {
  const text = label === undefined || label === "" ? trust : label;
  return (
    <span className={joinClass("ac-trust", className)} data-trust={trust} title={text === trust ? undefined : trust}>
      <span className="ac-trust-icon" aria-hidden="true" />
      <span className="ac-ellipsis">{text}</span>
    </span>
  );
}
