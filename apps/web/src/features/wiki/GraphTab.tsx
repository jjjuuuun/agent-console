/**
 * 그래프 탭(screen-wiki §7): 도구줄(중심·깊이·토글·개수) + 링크 그래프 캔버스 + 연결 목록. 데이터는 서버 그래프(`GET …/graph`)이고,
 * 중심·깊이는 주소가 진실이다(`center`·`depth`). 중심이 없는 페이지면 전체로 되돌리고 안내한다. 링크 문법이 없으면 그래프를 그리지 않는다.
 * 페이지 경로·제목·링크 상태는 서버 값이고, 그래프·목록 그리기는 `@agent-console/wiki-view`가 한다.
 */
import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";
import { Banner, Button, EmptyState } from "@agent-console/ui";
import { LinkGraph, LinkList, type GraphNodeData } from "@agent-console/wiki-view";
import { ToneChip } from "@agent-console/markdown-doc";
import type { WikiGraph, WikiGraphNode } from "@agent-console/contracts/wiki";
import { useStorage } from "../../app/StorageContext";
import { ROUTE_ROLES, routePath } from "../library";
import { FailureBlock, ListSkeleton } from "./parts";
import { useWikiGraph } from "./useWikiTabsApi";
import { usePageList, useWikiSyntax } from "./useWikiApi";
import { GRAPH_LIST_ONLY_KEY, WIKI_GRAPH, WIKI_PARAMS, WIKI_STORAGE } from "./wikiConfig";
import type { WikiTabProps } from "./wikiTabs";
import { classifyWikiError } from "./wikiErrors";
import { wikiMessages as m } from "./messages";
import { wikiTabMessages } from "./tabMessages";

const g = wikiTabMessages.graph;
const GAP_TOKEN = "--ac-wiki-graph-gap";

/** 디자인 토큰(px 길이)을 읽는다. 읽을 수 없으면(문서 밖·테스트) undefined — 그래프가 기본 간격을 쓴다. */
function tokenPixels(name: string): number | undefined {
  if (typeof document === "undefined") return undefined;
  const n = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
  return Number.isFinite(n) && n > 0 ? n : undefined;
}
const P = WIKI_PARAMS;
const CURRENT = "current";
const ALL = "all";
const PICK = "page";

/** 토글(끊긴 대상·고아)에 맞게 그래프를 걸러낸다. 끊긴 대상을 빼면 그 노드에 닿는 선도 뺀다. 데이터 재질의는 없다. */
export function filterGraph(graph: WikiGraph, showBroken: boolean, showOrphan: boolean): WikiGraph {
  const nodes = (graph.nodes ?? []).filter((n) => showBroken || n.broken !== true).map((n): WikiGraphNode => (showOrphan || n.orphan !== true ? n : { ...n, orphan: false }));
  const keep = new Set(nodes.map((n) => n.path));
  return { ...graph, nodes, edges: (graph.edges ?? []).filter((e) => keep.has(e.from) && keep.has(e.to)) };
}

export function GraphTab({ wikiId, view, summary, params, setParams, goTab, hasTab, openNewPage, ctx }: WikiTabProps) {
  const navigate = useNavigate();
  const storage = useStorage();
  const idBase = useId();
  const syntaxQ = useWikiSyntax(wikiId);
  const pagesQ = usePageList(wikiId);
  const [selected, setSelected] = useState<string | null>(null);
  const [showBroken, setShowBroken] = useState(true);
  const [showOrphan, setShowOrphan] = useState(true);
  const [listOnly, setListOnlyState] = useState(() => storage.get(GRAPH_LIST_ONLY_KEY) === "true");
  const [picking, setPicking] = useState(false);
  const gap = useMemo(() => tokenPixels(GAP_TOKEN), []);

  const links = syntaxQ.data?.syntax?.links;
  const noSyntax = syntaxQ.data !== undefined && (syntaxQ.data.empty === true || (links ?? []).length === 0);

  const centerParam = params.get(P.center);
  const mode = centerParam === null ? CURRENT : centerParam === "" ? ALL : PICK;
  const lastPage = storage.get(WIKI_STORAGE.lastPage(wikiId));
  const home = view.wiki.home;
  const currentPath = lastPage ?? (typeof home === "string" && home !== "" ? home : undefined);
  const wanted = mode === ALL ? undefined : mode === PICK ? (centerParam ?? undefined) : currentPath;
  const depthParam = params.get(P.depth);
  const depth = depthParam === WIKI_GRAPH.all ? undefined : WIKI_GRAPH.depths.includes(Number(depthParam)) ? Number(depthParam) : WIKI_GRAPH.defaultDepth;

  const firstQ = useWikiGraph(wikiId, { center: wanted, depth: wanted === undefined ? undefined : depth }, !noSyntax);
  const firstMissing =
    wanted !== undefined &&
    ((firstQ.data !== undefined && !(firstQ.data.nodes ?? []).some((n) => n.path === wanted && n.broken !== true)) || (firstQ.isError && classifyWikiError(firstQ.error, "").kind === "pageNotFound"));
  const allQ = useWikiGraph(wikiId, {}, !noSyntax && firstMissing);
  const q = firstMissing ? allQ : firstQ;
  const center = firstMissing ? undefined : wanted;

  const graph = useMemo(() => (q.data === undefined ? undefined : filterGraph(q.data, showBroken, showOrphan)), [q.data, showBroken, showOrphan]);

  const update = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    mutate(next);
    setParams(next, { replace: true });
  };
  const setCenter = (value: string | null) => update((n) => (value === null ? n.delete(P.center) : n.set(P.center, value)));
  const setDepth = (value: string) => update((n) => n.set(P.depth, value));
  const setListOnly = (on: boolean) => {
    setListOnlyState(on);
    storage.set(GRAPH_LIST_ONLY_KEY, String(on));
  };

  const openNode = (node: Pick<GraphNodeData, "path" | "broken" | "scheme">) => {
    if (node.broken) {
      if (!ctx.readOnly) openNewPage({ path: node.path });
      return;
    }
    if (node.scheme) return;
    goTab("page", { [P.path]: node.path });
  };
  const centerNode = (path: string) => {
    const node = (q.data?.nodes ?? []).find((n) => n.path === path);
    if (node === undefined || node.broken === true || node.scheme) return;
    setCenter(path);
  };
  const openSettings = () => void navigate(routePath(ROUTE_ROLES.settings));

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const t = e.target as HTMLElement;
    if (e.altKey || e.ctrlKey || e.metaKey || t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA") return;
    if (e.key === "l" || e.key === "L") {
      setListOnly(!listOnly);
    } else if ((e.key === "+" || e.key === "-" || e.key === "=") && center !== undefined) {
      const steps = WIKI_GRAPH.depths;
      const at = Math.max(0, steps.indexOf(depth ?? WIKI_GRAPH.defaultDepth));
      const next = steps[(at + (e.key === "-" ? steps.length - 1 : 1)) % steps.length];
      if (next !== undefined) setDepth(String(next));
    }
  };

  let body;
  if (noSyntax) {
    body = (
      <div className="wiki-state" data-testid="wiki-graph-nosyntax" role="note">
        <h2 className="wiki-state-title">{m.page.noSyntaxTitle}</h2>
        <p className="app-muted">{m.page.noSyntaxBody}</p>
        <div className="wiki-toolbar">
          {hasTab("rules") ? <Button onClick={() => goTab("rules")}>{g.openRules}</Button> : null}
          <Button onClick={openSettings}>{g.openSettings}</Button>
        </div>
      </div>
    );
  } else if (q.isPending) {
    body = <ListSkeleton rows={6} />;
  } else if (q.isError || graph === undefined) {
    body = <FailureBlock error={q.error} title={g.loadFailed} onRetry={() => void q.refetch()} />;
  } else if ((q.data?.nodes ?? []).length === 0 && summary?.pages === 0) {
    body = <div className="wiki-state" data-testid="wiki-graph-empty"><EmptyState title={g.empty} /></div>;
  } else {
    const noLinks = (graph.edges ?? []).length === 0 && (graph.nodes ?? []).length > 0;
    body = (
      <>
        {firstMissing && wanted !== undefined ? <Banner tone="info" data-testid="wiki-graph-center-missing">{g.centerMissing(wanted)}</Banner> : null}
        {noLinks ? <Banner tone="info">{g.noLinks}</Banner> : null}
        <div className="wiki-graph-body" data-list-only={listOnly || undefined}>
          {listOnly ? null : (
            <div className="wiki-graph-canvas" data-testid="wiki-graph-canvas">
              <LinkGraph
                graph={graph}
                centerPath={center ?? null}
                selectedPath={selected}
                onSelect={setSelected}
                onOpen={openNode}
                onCenter={centerNode}
                height="fill"
                {...(gap === undefined ? {} : { gap })}
              />
            </div>
          )}
          <div className="wiki-graph-list">
            <LinkList
              graph={graph}
              centerPath={center ?? null}
              selectedPath={selected}
              onSelect={setSelected}
              onOpen={(node) => openNode({ path: node.path, broken: node.broken === true, scheme: node.scheme ?? null })}
              onCenter={centerNode}
              height="100%"
            />
          </div>
        </div>
      </>
    );
  }

  const nodeCount = graph?.nodes?.length;
  const truncated = q.data?.truncated === true;
  const total = q.data?.total;
  const pages = pagesQ.data?.items ?? [];
  const pickListId = `${idBase}-pages`;
  const depthValue = depth === undefined ? WIKI_GRAPH.all : String(depth);
  const toolbarOff = noSyntax;

  return (
    <div className="wiki-graph" data-testid="wiki-graph" onKeyDown={onKeyDown}>
      {toolbarOff ? null : (
        <div className="wiki-graph-toolbar" role="group" aria-label={g.toolbar}>
          <label className="wiki-inline">
            <span className="wiki-label">{g.center}</span>
            <select
              className="wiki-input wiki-select"
              value={firstMissing ? ALL : mode}
              onChange={(e) => {
                const v = e.target.value;
                setPicking(false);
                if (v === CURRENT) setCenter(null);
                else if (v === ALL) setCenter("");
                else if (centerParam === null || centerParam === "") setPicking(true);
              }}
            >
              <option value={CURRENT}>{g.centerCurrent}{currentPath === undefined ? "" : ` · ${currentPath}`}</option>
              <option value={ALL}>{g.centerAll}</option>
              <option value={PICK}>{mode === PICK && centerParam !== null ? centerParam : g.centerPick}</option>
            </select>
          </label>
          {picking ? (
            <>
              <input
                className="wiki-input wiki-pick"
                list={pickListId}
                aria-label={g.pickLabel}
                placeholder={g.pickPlaceholder}
                onChange={(e) => {
                  const hit = pages.find((p) => p.path === e.target.value);
                  if (hit !== undefined) {
                    setPicking(false);
                    setCenter(hit.path);
                  }
                }}
              />
              <datalist id={pickListId}>
                {pages.map((p) => <option key={p.path} value={p.path}>{p.title ?? ""}</option>)}
              </datalist>
            </>
          ) : null}
          <div role="group" aria-label={g.depth} className="wiki-segment">
            {WIKI_GRAPH.depths.map((n) => (
              <button key={n} type="button" className="wiki-segment-btn" aria-pressed={depthValue === String(n)} disabled={center === undefined} onClick={() => setDepth(String(n))}>{n}</button>
            ))}
            <button type="button" className="wiki-segment-btn" aria-pressed={depthValue === WIKI_GRAPH.all} disabled={center === undefined} onClick={() => setDepth(WIKI_GRAPH.all)}>{g.depthAll}</button>
          </div>
          <label className="wiki-inline"><input type="checkbox" checked={showBroken} onChange={(e) => setShowBroken(e.target.checked)} />{g.showBroken}</label>
          <label className="wiki-inline"><input type="checkbox" checked={showOrphan} onChange={(e) => setShowOrphan(e.target.checked)} />{g.showOrphan}</label>
          <label className="wiki-inline"><input type="checkbox" checked={listOnly} onChange={(e) => setListOnly(e.target.checked)} />{g.listOnly}</label>
          <span className="wiki-spacer" />
          {nodeCount === undefined ? null : <span className="app-muted" role="status">{g.count(nodeCount)}</span>}
          {truncated ? <ToneChip tone="warning" label={typeof total === "number" && nodeCount !== undefined ? g.truncated(nodeCount, total) : g.truncatedNoTotal} /> : null}
        </div>
      )}
      <div className="wiki-graph-main">{body}</div>
    </div>
  );
}
