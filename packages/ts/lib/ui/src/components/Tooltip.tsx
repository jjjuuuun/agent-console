import type { ReactNode } from "react";
import { joinClass } from "./Status";

export interface TooltipProps {
  /** 툴팁 내용(보통 라벨 + 단축키). 접근성 이름은 자식 버튼의 `aria-label`이 맡는다. */
  content: ReactNode;
  /** 표시 위치. 기본 아래. */
  placement?: "bottom" | "top";
  /** 가장자리 정렬. 화면 오른쪽 끝 버튼은 `end`. */
  align?: "center" | "start" | "end";
  children: ReactNode;
  className?: string;
}

/**
 * CSS만으로 만든 툴팁: 호버 400ms 뒤(`--ac-tip-delay`), 키보드 포커스(`:focus-visible`)는 즉시 보인다.
 * 장식이므로 `aria-hidden`이다. 자식이 스스로 접근성 이름을 가져야 한다.
 */
export function Tooltip({ content, placement = "bottom", align = "center", children, className }: TooltipProps) {
  return (
    <span className={joinClass("ac-tip-host", className)}>
      {children}
      <span className="ac-tip" aria-hidden="true" data-placement={placement} data-align={align}>
        {content}
      </span>
    </span>
  );
}
