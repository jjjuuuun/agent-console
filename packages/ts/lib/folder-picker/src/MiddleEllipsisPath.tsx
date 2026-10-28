import { useRef, type ReactElement } from "react";

import { middleEllipsis } from "./middleEllipsis";
import { useElementCells } from "./useElementCells";

export interface MiddleEllipsisPathProps {
  path: string;
  className?: string;
  /** 한 칸 폭(px). 기본 7.5. */
  cellWidthPx?: number;
}

/**
 * 경로를 칸 수에 맞춰 가운데 줄여 한 줄로 보인다(mono). 전체 경로는 툴팁(`title`)과 시각적으로 숨긴 텍스트로 남는다.
 * 측정 전에는 CSS 끝 줄임(`ac-ellipsis`)이며 측정 뒤에도 안전망으로 남긴다.
 */
export function MiddleEllipsisPath({ path, className, cellWidthPx }: MiddleEllipsisPathProps): ReactElement {
  const ref = useRef<HTMLSpanElement>(null);
  const cells = useElementCells(ref, cellWidthPx);
  const shown = cells === null ? path : middleEllipsis(path, cells);
  return (
    <span ref={ref} className={`ac-fp-path${className ? ` ${className}` : ""}`} title={path}>
      <span className="ac-fp-path-text ac-ellipsis" aria-hidden="true">{shown}</span>
      <span className="ac-fp-sr">{path}</span>
    </span>
  );
}
