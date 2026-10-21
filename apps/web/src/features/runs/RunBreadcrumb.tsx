import { useState } from "react";
import { Link } from "react-router";
import { Popover } from "@agent-console/ui";
import { delegationMessages as dm } from "../delegation";

export interface BreadcrumbItem {
  id: string;
  /** 짧은 id(앞 6자, mono) */
  short: string;
  /** 팀 구성 이름(12px muted). 못 읽었으면 생략 */
  teamName?: string | undefined;
}

export interface RunBreadcrumbProps {
  /** 루트부터 현재까지. 마지막이 현재 화면 */
  items: readonly BreadcrumbItem[];
  hrefOf(id: string): string;
  /** 이 개수를 넘으면 앞쪽을 `…` 메뉴로 접는다(기본 5) */
  max?: number;
}

/**
 * 자식 실행의 위치: `루트 r-2f9a ▸ r-7c1b ▸ r-91d0`. 각 항목 아래에 팀 구성 이름. 항목이 많으면 앞쪽을 접는다.
 * 루트 실행(체인이 1개)이면 아무것도 그리지 않는다.
 */
export function RunBreadcrumb({ items, hrefOf, max = 5 }: RunBreadcrumbProps) {
  const [foldOpen, setFoldOpen] = useState(false);
  if (items.length < 2) return null;
  const folded = items.length > max ? items.slice(0, items.length - (max - 1)) : [];
  const shown = items.slice(folded.length);
  const render = (item: BreadcrumbItem, index: number, last: boolean) => {
    const isRoot = index === 0 && folded.length === 0;
    const label = isRoot ? dm.run.breadcrumb.root(item.short) : item.short;
    return (
      <span className="dlg-crumb">
        {last ? <span className="app-mono" title={item.id}>{label}</span> : <Link to={hrefOf(item.id)} className="app-mono" title={item.id}>{label}</Link>}
        {item.teamName ? <span className="dlg-crumb-sub ac-ellipsis" title={item.teamName}>{item.teamName}</span> : null}
      </span>
    );
  };
  return (
    <nav aria-label={dm.run.breadcrumb.label} className="dlg-crumbs">
      <ol>
        {folded.length > 0 ? (
          <li className="dlg-crumb-wrap">
            <Popover
              open={foldOpen}
              onOpenChange={setFoldOpen}
              panelLabel={dm.run.breadcrumb.more}
              renderTrigger={(props) => (
                <button {...props} type="button" className="ac-btn" data-variant="ghost" data-size="sm" aria-label={dm.run.breadcrumb.more} title={dm.run.breadcrumb.more}>…</button>
              )}
            >
              <ul className="dlg-crumb-fold">
                {folded.map((f, i) => (
                  <li key={f.id}>
                    <Link to={hrefOf(f.id)} className="app-mono" title={f.id} onClick={() => setFoldOpen(false)}>{i === 0 ? dm.run.breadcrumb.root(f.short) : f.short}</Link>
                    {f.teamName ? <span className="dlg-crumb-sub ac-ellipsis" title={f.teamName}> {f.teamName}</span> : null}
                  </li>
                ))}
              </ul>
            </Popover>
          </li>
        ) : null}
        {shown.map((item, i) => (
          <li key={item.id} className="dlg-crumb-wrap" aria-current={folded.length + i === items.length - 1 ? "page" : undefined}>
            {i > 0 || folded.length > 0 ? <span aria-hidden="true" className="ac-breadcrumb-sep"> ▸ </span> : null}
            {render(item, folded.length + i, folded.length + i === items.length - 1)}
          </li>
        ))}
      </ol>
    </nav>
  );
}
