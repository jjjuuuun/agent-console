import { IconButton } from "./Button";
import { Icon } from "./Icon";
import { joinClass } from "./Status";

/** 가운데 말줄임: 앞 `head`·뒤 `tail` 글자만 남기고 `…`로 잇는다. 이미 짧으면 그대로. */
export function middleEllipsis(value: string, head = 8, tail = 4): string {
  const chars = Array.from(value);
  if (chars.length <= head + tail + 1) return value;
  return `${chars.slice(0, head).join("")}…${chars.slice(chars.length - tail).join("")}`;
}

export interface MiddleEllipsisProps {
  value: string;
  head?: number;
  tail?: number;
  /** 있으면 복사 아이콘 버튼을 붙인다(접근성 이름). 전체 값을 클립보드에 복사. */
  copyLabel?: string;
  className?: string;
}

/** id·해시·경로용 가운데 말줄임 + 전체 값 툴팁(+ 선택 복사 버튼). 표현 전용. */
export function MiddleEllipsis({ value, head, tail, copyLabel, className }: MiddleEllipsisProps) {
  return (
    <span className={joinClass("ac-middle-ellipsis", className)}>
      <span className="ac-mono-wrap" title={value}>{middleEllipsis(value, head, tail)}</span>
      {copyLabel === undefined ? null : (
        <IconButton icon={<Icon name="copy" size={14} />} label={copyLabel} size="sm" variant="ghost" onClick={() => void navigator.clipboard?.writeText(value)} />
      )}
    </span>
  );
}
