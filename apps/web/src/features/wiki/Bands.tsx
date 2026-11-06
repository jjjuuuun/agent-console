/** 본문 위 띠 목록(screen-wiki §6.7). 우선순위 순서로 받은 항목을 최대 2개 보이고 나머지는 `외 n건 [펼치기]`로 접는다. */
import { useState, type ReactNode } from "react";
import { Banner, Button, type Tone } from "@agent-console/ui";
import { wikiMessages as m } from "./messages";

export interface BandItem {
  id: string;
  tone: Tone;
  content: ReactNode;
  actions?: ReactNode;
  /** 서버가 준 상세 행(규칙 id + 메시지 등). 펼치면 보인다 */
  rows?: readonly { key: string; id?: string | null | undefined; message: string }[];
}

export function Bands({ items, max = 2 }: { items: readonly BandItem[]; max?: number }) {
  const [expanded, setExpanded] = useState(false);
  if (items.length === 0) return null;
  const shown = expanded ? items : items.slice(0, max);
  const hidden = items.length - shown.length;
  return (
    <div className="wiki-bands" data-testid="wiki-bands">
      {shown.map((b) => (
        <Banner key={b.id} tone={b.tone} role={b.tone === "danger" || b.tone === "warning" ? "alert" : "status"} actions={b.actions} data-band={b.id}>
          {b.content}
          {b.rows === undefined || b.rows.length === 0 ? null : (
            <ul className="wiki-band-rows">
              {b.rows.map((r) => (
                <li key={r.key}>{r.id === undefined || r.id === null || r.id === "" ? null : <code className="ac-mono">{r.id}</code>} <span>{r.message}</span></li>
              ))}
            </ul>
          )}
        </Banner>
      ))}
      {hidden > 0 ? (
        <p className="app-muted wiki-band-more">
          {m.band.more(hidden)}{" "}
          <Button size="sm" onClick={() => setExpanded(true)}>{m.band.expand}</Button>
        </p>
      ) : null}
    </div>
  );
}
