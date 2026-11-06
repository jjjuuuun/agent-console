/**
 * 오른쪽 패널(screen-wiki §6.9): 백링크 · 나가는 링크 · 기록 세그먼트. 데이터와 콜백은 props이고 표현은 `@agent-console/wiki-view`가 맡는다.
 * 링크 문법이 비어 있으면 백링크·나가는 링크 자리에 안내가 나온다(§12 "문법 없음"). 기록 저장소가 없어도 기록 탭은 보이고 안내가 나온다.
 */
import type { ReactNode } from "react";
import { ToneChip } from "@agent-console/markdown-doc";
import { OutlinksPanel, PageHistory, type WikiDisplay } from "@agent-console/wiki-view";
import type { WikiHistoryPage, WikiLink, WikiPageVersion, WikiPageView } from "@agent-console/contracts/wiki";
import { SIDE_TAB_DEFS } from "./wikiConfig";
import { wikiMessages as m } from "./messages";

export interface SidePaneProps {
  tab: string;
  onTab: (id: string) => void;
  /** 열린 페이지(없으면 빈 패널) */
  page: WikiPageView | undefined;
  /** 링크 문법이 없어 링크를 찾지 않는다 */
  noSyntax: boolean;
  /** 문법 없음 안내의 [규칙 열기] (규칙 탭이 있을 때만) */
  onOpenRules?: (() => void) | undefined;
  display: WikiDisplay;
  titleOf: (path: string) => string | undefined;
  onOpenPage: (path: string, anchor?: string | null) => void;
  onHoverLink: (link: WikiLink | null) => void;
  onLocateLink: (link: WikiLink) => void;
  onOpenLinkTarget: (link: WikiLink) => void;
  onCreateFromLink: (link: WikiLink) => void;
  schemeText?: ((link: WikiLink) => string | undefined) | undefined;
  readOnly: boolean;
  readOnlyReason: string | undefined;
  /** 기록. `unavailable`이면 기록 저장소가 없다(안내) */
  history: { data: WikiHistoryPage | undefined; unavailable: boolean; failed: boolean; loading: boolean };
  currentVersion: number | null;
  selectedVersion: number | null;
  onSelectVersion: (v: WikiPageVersion) => void;
  onCompareVersion: (v: WikiPageVersion) => void;
  onRestoreVersion: (v: WikiPageVersion) => void;
  onOpenRun?: ((runId: string, rootRunId: string | null) => void) | undefined;
  onOpenProjectSettings?: (() => void) | undefined;
  restoreDisabledReason: string | undefined;
  now: number;
  height?: number | string;
}

function NoSyntax({ onOpenRules }: { onOpenRules?: (() => void) | undefined }): ReactNode {
  return (
    <div className="wiki-nosyntax" role="note" data-testid="wiki-nosyntax">
      <strong>{m.page.noSyntaxTitle}</strong>
      <p className="app-muted">{m.page.noSyntaxBody}</p>
      {onOpenRules === undefined ? null : <button type="button" className="app-link-btn" onClick={onOpenRules}>{m.header.issuesOpen}</button>}
    </div>
  );
}

export function SidePane(p: SidePaneProps) {
  const backlinks = p.page?.backlinks ?? [];
  const links = p.page?.links ?? [];
  const versions = p.history.data?.items ?? [];
  const counts: Record<string, number | null> = { backlinks: p.noSyntax ? null : backlinks.length, outlinks: p.noSyntax ? null : links.length, history: p.history.unavailable ? null : p.history.data === undefined ? null : versions.length };
  return (
    <div className="wiki-side-pane" data-testid="wiki-side-pane" aria-label={m.side.label}>
      <div role="tablist" aria-label={m.side.label} className="wiki-segment">
        {SIDE_TAB_DEFS.map((t) => {
          const n = counts[t.id];
          return (
            <button key={t.id} type="button" role="tab" id={`wiki-side-tab-${t.id}`} aria-selected={p.tab === t.id} aria-controls="wiki-side-panel" className="wiki-segment-btn" onClick={() => p.onTab(t.id)}>
              {m.side.tabs[t.labelKey] ?? t.id}{n === null || n === undefined ? "" : ` ${n}`}
            </button>
          );
        })}
      </div>
      <div id="wiki-side-panel" role="tabpanel" aria-labelledby={`wiki-side-tab-${p.tab}`} className="wiki-side-body">
        {p.tab === "backlinks" ? (
          p.noSyntax ? <NoSyntax onOpenRules={p.onOpenRules} /> : backlinks.length === 0 ? (
            <div className="wiki-side-empty">
              <p className="app-muted">{m.side.backlinksNone}</p>
              {p.page?.page.orphan === true ? <ToneChip label={m.side.orphan} tone="warning" /> : null}
            </div>
          ) : (
            <ul className="wiki-backlinks" aria-label={m.side.tabs["backlinks"]}>
              {backlinks.map((b) => (
                <li key={b.path}>
                  <button type="button" className="wiki-backlink-row" aria-label={m.side.open(b.title !== undefined && b.title !== "" ? b.title : b.path)} onClick={() => p.onOpenPage(b.path)}>
                    <span className="wiki-backlink-title ac-ellipsis">{b.title !== undefined && b.title !== "" ? b.title : b.path}</span>
                    <span className="wiki-backlink-path ac-mono-wrap ac-ellipsis app-muted">{b.path}</span>
                    {b.count !== undefined && b.count >= 2 ? <span className="wiki-backlink-count app-muted">{m.side.count(b.count)}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          )
        ) : p.tab === "outlinks" ? (
          p.noSyntax ? <NoSyntax onOpenRules={p.onOpenRules} /> : (
            <OutlinksPanel
              content={p.page?.content ?? ""}
              links={links}
              display={p.display}
              titleOf={p.titleOf}
              onHover={p.onHoverLink}
              onLocate={p.onLocateLink}
              onOpen={p.onOpenLinkTarget}
              onCreate={p.onCreateFromLink}
              readOnly={p.readOnly}
              {...(p.readOnlyReason === undefined ? {} : { readOnlyReason: p.readOnlyReason })}
              {...(p.schemeText === undefined ? {} : { schemeText: p.schemeText })}
              {...(p.height === undefined ? {} : { height: p.height })}
            />
          )
        ) : p.history.failed && !p.history.unavailable ? (
          <p className="app-field-error" role="alert">{m.history.failed}</p>
        ) : p.history.loading && !p.history.unavailable ? (
          <p className="app-muted" role="status">{m.loading}</p>
        ) : (
          <PageHistory
            versions={versions}
            pruned={p.history.data?.pruned === true}
            currentVersion={p.currentVersion}
            selectedVersion={p.selectedVersion}
            display={p.display}
            unavailable={p.history.unavailable}
            {...(p.onOpenProjectSettings === undefined ? {} : { onOpenProjectSettings: p.onOpenProjectSettings })}
            onSelect={p.onSelectVersion}
            onCompare={p.onCompareVersion}
            onRestore={p.onRestoreVersion}
            {...(p.onOpenRun === undefined ? {} : { onOpenRun: p.onOpenRun })}
            {...(p.restoreDisabledReason === undefined ? {} : { restoreDisabledReason: p.restoreDisabledReason })}
            now={Math.floor(p.now / 1000)}
            {...(p.height === undefined ? {} : { height: p.height })}
          />
        )}
      </div>
    </div>
  );
}
