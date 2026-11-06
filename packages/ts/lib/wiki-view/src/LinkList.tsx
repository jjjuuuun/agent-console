import type { WikiGraph, WikiGraphNode } from "@agent-console/contracts/wiki";
import { useCallback, useMemo, useState, type KeyboardEvent } from "react";
import { isComposingEvent, useDomId } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";
import { VirtualList } from "./VirtualList";

export interface LinkListProps {
  graph: WikiGraph;
  centerPath?: string | null;
  /** 제어형 선택(그래프와 서로 강조). */
  selectedPath?: string | null;
  onSelect?: (path: string) => void;
  /** 행 클릭·Enter: 그 노드 열기 */
  onOpen?: (node: WikiGraphNode) => void;
  /** Shift+Enter: 중심으로 삼기 */
  onCenter?: (path: string) => void;
  /** 거르기 글(제어형). 생략하면 안에서 관리하는 입력을 그린다. */
  filter?: string;
  onFilterChange?: (filter: string) => void;
  rowHeightGroup?: number;
  rowHeightChild?: number;
  height?: number | string;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

type Row =
  | { kind: "group"; key: string; node: WikiGraphNode; open: boolean; outCount: number; inCount: number }
  | { kind: "out" | "in"; key: string; node: WikiGraphNode; other: WikiGraphNode | undefined; otherPath: string; count: number; parent: string };

const collator = new Intl.Collator("ko", { numeric: true, sensitivity: "base" });

/**
 * 연결 목록 = 그래프와 같은 정보를 글로 보이는 가상 목록. 노드마다 접히는 그룹(제목 + 현재·고아·끊긴 칩), 아래에 `→ 나가는`·`← 들어오는` 행.
 * 중심 먼저, 나머지 제목 오름차순. 거르기는 제목·경로 부분 일치(클라이언트). 잘렸으면 맨 아래 안내.
 */
export function LinkList({
  graph, centerPath = null, selectedPath = null, onSelect, onOpen, onCenter, filter, onFilterChange, rowHeightGroup = 32, rowHeightChild = 28, height, messages, className,
}: LinkListProps) {
  const t = resolveMessages(messages);
  const base = useDomId();
  const [innerFilter, setInnerFilter] = useState("");
  const query = (filter ?? innerFilter).trim().toLowerCase();
  const [closed, setClosed] = useState<ReadonlySet<string>>(new Set());
  const [active, setActive] = useState(0);

  const rows = useMemo<Row[]>(() => {
    const byPath = new Map((graph.nodes ?? []).map((n) => [n.path, n] as const));
    const outs = new Map<string, Array<{ to: string; count: number }>>();
    const ins = new Map<string, Array<{ from: string; count: number }>>();
    for (const e of graph.edges ?? []) {
      if (!byPath.has(e.from) || !byPath.has(e.to)) continue;
      (outs.get(e.from) ?? outs.set(e.from, []).get(e.from)!).push({ to: e.to, count: e.count ?? 1 });
      (ins.get(e.to) ?? ins.set(e.to, []).get(e.to)!).push({ from: e.from, count: e.count ?? 1 });
    }
    const title = (n: WikiGraphNode) => (n.title && n.title !== "" ? n.title : n.path);
    const nodes = [...byPath.values()]
      .filter((n) => query === "" || n.path.toLowerCase().includes(query) || (n.title ?? "").toLowerCase().includes(query))
      .sort((a, b) => (a.path === centerPath ? -1 : b.path === centerPath ? 1 : collator.compare(title(a), title(b)) || collator.compare(a.path, b.path)));
    const out: Row[] = [];
    for (const n of nodes) {
      const o = outs.get(n.path) ?? [];
      const i = ins.get(n.path) ?? [];
      const open = !closed.has(n.path);
      out.push({ kind: "group", key: `g:${n.path}`, node: n, open, outCount: o.length, inCount: i.length });
      if (!open) continue;
      for (const e of o) out.push({ kind: "out", key: `o:${n.path}>${e.to}`, node: n, other: byPath.get(e.to), otherPath: e.to, count: e.count, parent: n.path });
      for (const e of i) out.push({ kind: "in", key: `i:${n.path}<${e.from}`, node: n, other: byPath.get(e.from), otherPath: e.from, count: e.count, parent: n.path });
    }
    return out;
  }, [graph, centerPath, query, closed]);

  const heightOf = useCallback((r: Row) => (r.kind === "group" ? rowHeightGroup : rowHeightChild), [rowHeightGroup, rowHeightChild]);
  const shown = Math.min(Math.max(active, 0), Math.max(rows.length - 1, 0));
  const rowId = (i: number) => `${base}-r${i}`;
  const toggle = (path: string) =>
    setClosed((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  const activate = (i: number, shift: boolean) => {
    const r = rows[i];
    if (!r) return;
    setActive(i);
    const target = r.kind === "group" ? r.node : (r.other ?? undefined);
    const path = r.kind === "group" ? r.node.path : r.otherPath;
    onSelect?.(path);
    if (shift) onCenter?.(path);
    else if (target) onOpen?.(target);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (rows.length === 0 || isComposingEvent(e)) return;
    const go = (to: number) => {
      e.preventDefault();
      setActive(Math.min(Math.max(0, to), rows.length - 1));
    };
    const r = rows[shown]!;
    switch (e.key) {
      case "ArrowDown": return go(shown + 1);
      case "ArrowUp": return go(shown - 1);
      case "Home": return go(0);
      case "End": return go(rows.length - 1);
      case "ArrowRight":
        if (r.kind === "group" && !r.open) {
          e.preventDefault();
          toggle(r.node.path);
        }
        return;
      case "ArrowLeft":
        if (r.kind === "group" && r.open) {
          e.preventDefault();
          toggle(r.node.path);
        }
        return;
      case "Enter":
        e.preventDefault();
        activate(shown, e.shiftKey);
        return;
      default:
    }
  };

  const filterValue = filter ?? innerFilter;
  const nodeCount = graph.nodes?.length ?? 0;
  return (
    <div className={`ac-wk-root ac-wk-linklist${className ? ` ${className}` : ""}`} style={{ display: "flex", flexDirection: "column", ...(height !== undefined ? { height } : {}) }}>
      <input
        type="search"
        className="ac-wk-input"
        aria-label={t["linklist.filter"]}
        placeholder={t["linklist.filter"]}
        value={filterValue}
        onChange={(e) => {
          setInnerFilter(e.target.value);
          onFilterChange?.(e.target.value);
        }}
      />
      {nodeCount === 0 ? (
        <p className="ac-wk-muted ac-wk-empty" role="status">{t["linklist.empty"]}</p>
      ) : rows.length === 0 ? (
        <p className="ac-wk-muted ac-wk-empty" role="status">{t["linklist.noMatch"]}</p>
      ) : (
        <VirtualList
          items={rows}
          rowHeight={heightOf}
          role="tree"
          ariaLabel={t["linklist.label"] ?? ""}
          tabIndex={0}
          activeDescendant={rowId(shown)}
          activeIndex={shown}
          onKeyDown={onKeyDown}
          getKey={(r) => r.key}
          renderRow={(r, ctx) => {
            const style = ctx.style;
            if (r.kind === "group") {
              const n = r.node;
              const isCenter = n.path === centerPath;
              return (
                <div
                  id={rowId(ctx.index)}
                  role="treeitem"
                  aria-level={1}
                  aria-expanded={r.open}
                  aria-selected={n.path === selectedPath}
                  data-kind="group"
                  data-active={ctx.index === shown || undefined}
                  className="ac-wk-row ac-wk-lrow"
                  style={style}
                  title={n.path}
                  onClick={() => activate(ctx.index, false)}
                >
                  <button
                    type="button"
                    tabIndex={-1}
                    className="ac-wk-iconbtn"
                    aria-label={formatMessage(r.open ? t["linklist.collapse"] : t["linklist.expand"], { title: n.title || n.path })}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggle(n.path);
                    }}
                  >
                    <span className="ac-wk-twisty" data-open={r.open || undefined} aria-hidden="true" />
                  </button>
                  <span className="ac-wk-ellipsis ac-wk-grow">{n.title && n.title !== "" ? n.title : n.path}</span>
                  {isCenter ? <span className="ac-wk-badge" data-tone="info">{t["linklist.center"]}</span> : null}
                  {n.orphan ? <span className="ac-wk-badge" data-tone="warning">{t["linklist.orphan"]}</span> : null}
                  {n.broken ? <span className="ac-wk-badge" data-tone="danger">{t["linklist.broken"]}</span> : null}
                </div>
              );
            }
            const other = r.other;
            const otherTitle = other && other.title && other.title !== "" ? other.title : r.otherPath;
            return (
              <div
                id={rowId(ctx.index)}
                role="treeitem"
                aria-level={2}
                aria-selected={r.otherPath === selectedPath}
                data-kind={r.kind}
                data-active={ctx.index === shown || undefined}
                className="ac-wk-row ac-wk-lrow"
                style={{ ...style, paddingInlineStart: 36 }}
                title={r.otherPath}
                onClick={() => activate(ctx.index, false)}
              >
                <span aria-hidden="true">{r.kind === "out" ? "→" : "←"}</span>
                <span className="sr-only ac-wk-sr">{r.kind === "out" ? t["linklist.out"] : t["linklist.in"]}</span>
                <span className="ac-wk-ellipsis ac-wk-grow">{otherTitle}</span>
                {other?.broken ? <span className="ac-wk-badge" data-tone="danger">{t["linklist.broken"]}</span> : null}
                {r.count >= 2 ? <span className="ac-wk-muted ac-wk-num">×{r.count}</span> : null}
              </div>
            );
          }}
        />
      )}
      {graph.truncated ? <p className="ac-wk-muted ac-wk-footnote">{t["linklist.truncated"]}</p> : null}
    </div>
  );
}
