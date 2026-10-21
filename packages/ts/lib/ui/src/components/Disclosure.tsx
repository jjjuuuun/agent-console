import { useRef, useState, type ReactNode } from "react";
import { joinClass } from "./Status";

export interface DisclosureProps {
  summary: ReactNode;
  children?: ReactNode;
  /** 제어형 열림. 생략하면 비제어. */
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

/** 접힘 블록(`<details>` 기반). 요약 줄은 Enter/Space로 토글된다. 제어/비제어. */
export function Disclosure({ summary, children, open, defaultOpen = false, onOpenChange, className }: DisclosureProps) {
  const [inner, setInner] = useState(defaultOpen);
  const current = open ?? inner;
  const ref = useRef<HTMLDetailsElement>(null);
  return (
    <details ref={ref} className={joinClass("ac-disclosure", className)} open={current} data-open={current ? "true" : "false"}>
      <summary
        className="ac-disclosure-summary"
        onClick={(event) => {
          // 브라우저 기본 토글 대신 상태를 직접 관리해 제어형에서 어긋나지 않게 한다.
          event.preventDefault();
          if (open === undefined) setInner(!current);
          onOpenChange?.(!current);
          // 제어형에서 부모가 값을 바꾸지 않으면 DOM 상태도 그대로 둔다(기본 토글을 막지 못하는 환경 대비).
          if (ref.current) ref.current.open = open === undefined ? !current : open;
        }}
      >
        {summary}
      </summary>
      <div className="ac-disclosure-body">{children}</div>
    </details>
  );
}
