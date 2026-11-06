import "@agent-console/wiki-view/styles.css";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon, Popover } from "@agent-console/ui";
import { OpChip, VirtualList } from "@agent-console/wiki-view";
import type { WikiChange, WikiChangePage, WikiSummary } from "@agent-console/contracts/wiki";
import { useApi } from "../../app/ApiContext";
import { useNow } from "../../app/useNow";
import { formatRelative } from "../../lib/format";
import { RUN_CHANGES } from "./integrationConfig";
import { wikiLinkMessages as t } from "./integrationMessages";
import { WIKI_PARAMS, buildWikiDisplay } from "./wikiConfig";
import { wikiPagePath, wikiPath } from "./wikiPaths";
import "./integration.css";

export interface RunWikiChangesProps {
  /** 실행 id(루트 실행이면 하위 실행의 쓰기까지 서버가 합쳐 준다) */
  runId: string;
  /** 실행의 프로젝트(공간). 없으면 단독 공간 */
  projectId: string | null;
  /** 실행 중이면 위키 변경 알림이 올 때마다(1초 디바운스) 다시 센다 */
  active: boolean;
}

/** 칩 숫자: 상한에 닿으면 "100+". */
export function changeCountText(count: number, hasMore: boolean, cap = RUN_CHANGES.cap): string {
  return hasMore || count >= cap ? `${cap}+` : String(count);
}

const display = buildWikiDisplay();
const keyOf = (runId: string, projectId: string | null) => ["wiki", projectId ?? "", "run-changes", runId] as const;

/**
 * 실행 상세 요약 줄의 "고친 위키 페이지 N" 칩과 목록 팝오버(screen-wiki.md 11.2). 변경이 없거나 못 읽으면 아무것도 그리지 않는다.
 * 위키를 가로지르는 한 번의 요청(`author_run`)이고, 행은 그 위키 페이지(해당 버전 비교)로 가는 링크다. 지워진 페이지는 위키 화면으로 가는 링크 + 설명이다.
 */
export function RunWikiChanges({ runId, projectId, active }: RunWikiChangesProps) {
  const { wiki, ws } = useApi();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const now = useNow(open, 30_000);
  const changes = useQuery<WikiChangePage, Error>({
    queryKey: keyOf(runId, projectId),
    queryFn: () => wiki(projectId).listSpaceWikiChanges({ authorRun: runId, limit: RUN_CHANGES.cap }),
    retry: false,
    meta: { silentBackgroundError: true },
  });
  const names = useQuery<WikiSummary[], Error>({
    queryKey: ["wiki", projectId ?? "", "wikis", "run-changes"],
    queryFn: () => wiki(projectId).listWikis(),
    enabled: (changes.data?.items?.length ?? 0) > 0,
    retry: false,
    meta: { silentBackgroundError: true },
  });
  useEffect(() => {
    if (!active) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const sub = ws.subscribeWiki(() => {
      timer ??= setTimeout(() => {
        timer = undefined;
        void qc.invalidateQueries({ queryKey: keyOf(runId, projectId) });
      }, RUN_CHANGES.debounceMs);
    });
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      sub.unsubscribe();
    };
  }, [active, ws, qc, runId, projectId]);
  const items = changes.data?.items ?? [];
  if (items.length === 0) return null;
  const nameOf = (id: string) => names.data?.find((w) => w.id === id)?.name || id;
  const count = changeCountText(items.length, (changes.data?.next_cursor ?? null) !== null);
  return (
    <span className="wiki-runchanges">
      <Popover
        open={open}
        onOpenChange={setOpen}
        panelLabel={t.runChanges.listLabel}
        panelClassName="wiki-runchanges-panel"
        renderTrigger={(p) => (
          <button {...p} type="button" className="wiki-runchip" title={t.runChanges.tip}>
            <Icon name="wiki" size={12} />
            <span>{t.runChanges.chip(count)}</span>
          </button>
        )}
      >
        <VirtualList
          items={items}
          rowHeight={RUN_CHANGES.rowHeight}
          maxHeight={RUN_CHANGES.maxHeight}
          ariaLabel={t.runChanges.listLabel}
          getKey={(c, i) => `${c.wiki}/${c.path}/${c.version}/${i}`}
          renderRow={(c, ctx) => <ChangeRow key={ctx.index} change={c} wikiName={nameOf(c.wiki)} style={ctx.style} nowMs={now} />}
        />
      </Popover>
    </span>
  );
}

function ChangeRow({ change, wikiName, style, nowMs }: { change: WikiChange; wikiName: string; style: React.CSSProperties; nowMs: number }) {
  const gone = change.op === "delete";
  const to = gone ? wikiPath(change.wiki) : wikiPagePath(change.wiki, change.path, { [WIKI_PARAMS.tab]: "page", [WIKI_PARAMS.version]: change.version });
  return (
    <div role="listitem" className="wiki-runchange" style={style}>
      <OpChip op={change.op} display={display} size="dense" />
      <span className="wiki-runchange-wiki ac-ellipsis" title={change.wiki}>{wikiName}</span>
      <Link className="wiki-runchange-path ac-ellipsis" to={to} title={gone ? t.runChanges.deletedTip : change.path} aria-label={gone ? undefined : t.runChanges.open(wikiName, change.path)}>
        {change.path}
      </Link>
      <span className="wiki-runchange-time app-muted">{formatRelative(change.at, nowMs)}</span>
    </div>
  );
}
