import { useState } from "react";
import { teamMessages as t } from "./messages";

export interface HintOneLineProps {
  /** 한 줄 요약(넘치면 말줄임) */
  short: string;
  /** 펼쳤을 때 전문 */
  full: string;
}

/** 안내 배너 안 내용: 한 줄 + [더 보기](펼치면 전문). 배너 틀(닫기)은 호출자(`HintBanner`)가 그린다. */
export function HintOneLine({ short, full }: HintOneLineProps) {
  const [open, setOpen] = useState(false);
  return (
    <span className="team-hint-line" data-open={open ? "true" : undefined}>
      <span className={open ? "team-hint-text" : "team-hint-text ac-ellipsis"}>{open ? full : short}</span>
      <button type="button" className="app-link-btn" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? t.layout.hintLess : t.layout.hintMore}
      </button>
    </span>
  );
}
