import type { WikiPageSummary } from "@agent-console/contracts/wiki";
import { useMemo, useState, type KeyboardEvent } from "react";
import { isComposingEvent, useDomId } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";
import { allFolders, buildTree, type TreeRow, type TreeTitleMode } from "./tree";
import { VirtualList } from "./VirtualList";

export interface PageTreeProps {
  pages: readonly WikiPageSummary[];
  /** 지금 열린 페이지 경로. 그 상위 폴더는 항상 펼쳐진다. */
  selectedPath?: string | null;
  /** 펼친 폴더(제어형). 저장(localStorage 등)은 호출자가 한다. */
  expanded: ReadonlySet<string>;
  onExpandedChange: (next: ReadonlySet<string>) => void;
  /** 거르기 글(경로·제목 부분 일치, 클라이언트). 비어 있지 않으면 모두 펼친다. */
  filter?: string;
  titleMode?: TreeTitleMode;
  /** 저장 안 된 편집이 있는 페이지 경로들 */
  dirtyPaths?: ReadonlySet<string>;
  /** 행을 고르거나 Enter. */
  onSelect?: (path: string) => void;
  /** F2 / 메뉴: 이름 바꾸기·옮기기. 폴더에는 걸지 않는다. */
  onRename?: (path: string) => void;
  /** Delete: 지우기. 폴더에는 걸지 않는다. */
  onDelete?: (path: string) => void;
  /** Shift+F10·ContextMenu 키·우클릭. 폴더 행도 받는다. */
  onContextMenu?: (row: TreeRow, anchor: HTMLElement) => void;
  /** 페이지 목록이 상한에서 잘렸다. `total`이 있으면 개수를 밝힌다. */
  truncated?: boolean;
  total?: number | null;
  /** 상한 개수(안내 문구용). 모르면 생략. */
  maxPages?: number | null;
  rowHeight?: number;
  height?: number | string;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 새 펼침 집합: 폴더 하나를 뒤집는다. */
function toggled(set: ReadonlySet<string>, key: string): ReadonlySet<string> {
  const next = new Set(set);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

/**
 * 페이지 트리(가상 목록, `role="tree"`). 폴더 먼저·한국어 숫자 정렬, 끊긴 링크·고아·저장 안 됨·첫 페이지는 아이콘 + 이름(`aria-label`)이다.
 * 키보드: ↑↓ Home End 이동, → 펼침/자식으로, ← 접힘/부모로, Enter 선택, F2 이름 바꾸기, Delete 지우기, Shift+F10 메뉴.
 */
export function PageTree({
  pages, selectedPath = null, expanded, onExpandedChange, filter = "", titleMode = "title", dirtyPaths, onSelect, onRename, onDelete, onContextMenu,
  truncated = false, total = null, maxPages = null, rowHeight = 28, height, messages, className,
}: PageTreeProps) {
  const t = resolveMessages(messages);
  const base = useDomId();
  const rows = useMemo(
    () => buildTree(pages, { expanded, filter, titleMode, ...(selectedPath ? { revealPath: selectedPath } : {}) }),
    [pages, expanded, filter, titleMode, selectedPath],
  );
  const selectedIndex = rows.findIndex((r) => r.kind === "page" && r.key === selectedPath);
  const [active, setActive] = useState<number>(-1);
  const shown = active >= 0 && active < rows.length ? active : selectedIndex >= 0 ? selectedIndex : rows.length > 0 ? 0 : -1;
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const rowId = (i: number) => `${base}-r${i}`;
  const parentIndex = (i: number): number => {
    const depth = rows[i]!.depth;
    for (let j = i - 1; j >= 0; j -= 1) if (rows[j]!.kind === "folder" && rows[j]!.depth < depth) return j;
    return -1;
  };
  const choose = (i: number) => {
    const row = rows[i];
    if (!row) return;
    setActive(i);
    if (row.kind === "folder") onExpandedChange(toggled(expanded, row.key));
    else onSelect?.(row.key);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (rows.length === 0 || isComposingEvent(e)) return;
    const cur = shown;
    const row = rows[cur];
    const move = (to: number) => {
      e.preventDefault();
      setActive(Math.min(Math.max(0, to), rows.length - 1));
    };
    switch (e.key) {
      case "ArrowDown": return move(cur + 1);
      case "ArrowUp": return move(cur - 1);
      case "Home": return move(0);
      case "End": return move(rows.length - 1);
      case "ArrowRight":
        if (row?.kind === "folder") {
          e.preventDefault();
          if (!row.expanded) onExpandedChange(toggled(expanded, row.key));
          else if (cur + 1 < rows.length && rows[cur + 1]!.depth > row.depth) setActive(cur + 1);
        }
        return;
      case "ArrowLeft":
        if (row?.kind === "folder" && row.expanded && filter.trim() === "") {
          e.preventDefault();
          onExpandedChange(toggled(expanded, row.key));
        } else if (row && row.depth > 0) {
          const p = parentIndex(cur);
          if (p >= 0) move(p);
        }
        return;
      case "Enter":
        if (row) {
          e.preventDefault();
          choose(cur);
        }
        return;
      case "F2":
        if (row?.kind === "page" && onRename) {
          e.preventDefault();
          onRename(row.key);
        }
        return;
      case "Delete":
        if (row?.kind === "page" && onDelete) {
          e.preventDefault();
          onDelete(row.key);
        }
        return;
      case "ContextMenu":
        if (row && onContextMenu && anchorEl) {
          e.preventDefault();
          onContextMenu(row, anchorEl.querySelector<HTMLElement>(`#${rowId(cur)}`) ?? anchorEl);
        }
        return;
      default:
        if (e.key === "F10" && e.shiftKey && row && onContextMenu && anchorEl) {
          e.preventDefault();
          onContextMenu(row, anchorEl.querySelector<HTMLElement>(`#${rowId(cur)}`) ?? anchorEl);
        }
    }
  };

  const note = truncated
    ? total !== null && total !== undefined && maxPages !== null
      ? formatMessage(t["tree.truncated.total"], { total, max: maxPages })
      : t["tree.truncated"]
    : null;

  return (
    <div className={`ac-wk-root ac-wk-tree${className ? ` ${className}` : ""}`} ref={setAnchorEl} style={height !== undefined ? { height } : undefined}>
      {note ? <p className="ac-wk-banner" data-tone="info" role="status">{note}</p> : null}
      {rows.length === 0 ? (
        <p className="ac-wk-muted ac-wk-empty" role="status">{filter.trim() !== "" ? t["tree.noMatch"] : t["tree.empty"]}</p>
      ) : (
        <VirtualList
          items={rows}
          rowHeight={rowHeight}
          role="tree"
          ariaLabel={t["tree.label"] ?? ""}
          tabIndex={0}
          activeDescendant={shown >= 0 ? rowId(shown) : undefined}
          activeIndex={shown}
          onKeyDown={onKeyDown}
          getKey={(r) => `${r.kind}:${r.key}`}
          className="ac-wk-tree-list"
          renderRow={(row, ctx) => {
            const isPage = row.kind === "page";
            const page = row.page;
            const broken = page?.broken_links ?? 0;
            const dirty = isPage && dirtyPaths?.has(row.key) === true;
            const stateLabels: string[] = [];
            if (page?.home) stateLabels.push(t["tree.home"] ?? "");
            if (page?.orphan) stateLabels.push(t["tree.orphan"] ?? "");
            if (broken > 0) stateLabels.push(formatMessage(t["tree.broken"], { n: broken }));
            if (dirty) stateLabels.push(t["tree.dirty"] ?? "");
            const aria = isPage ? [row.name, ...stateLabels].join(", ") : formatMessage(t["tree.folder"], { name: row.name, n: row.count ?? 0 });
            return (
              <div
                id={rowId(ctx.index)}
                role="treeitem"
                aria-level={row.depth + 1}
                aria-setsize={ctx.setSize}
                aria-posinset={ctx.posInSet}
                aria-label={aria}
                aria-expanded={row.kind === "folder" ? row.expanded === true : undefined}
                aria-selected={isPage ? row.key === selectedPath : undefined}
                data-kind={row.kind}
                data-active={ctx.index === shown || undefined}
                className="ac-wk-tree-row"
                style={{ ...ctx.style, paddingInlineStart: 8 + row.depth * 16 }}
                title={isPage ? `${row.name}\n${row.key}` : row.key}
                onClick={() => choose(ctx.index)}
                onContextMenu={(e) => {
                  if (!onContextMenu) return;
                  e.preventDefault();
                  setActive(ctx.index);
                  onContextMenu(row, e.currentTarget);
                }}
              >
                {row.kind === "folder" ? (
                  <>
                    <span className="ac-wk-twisty" data-open={row.expanded || undefined} aria-hidden="true" />
                    <span className="ac-wk-icon" data-icon="folder" aria-hidden="true" />
                    <span className="ac-wk-ellipsis ac-wk-grow">{row.name}</span>
                    {!row.expanded ? <span className="ac-wk-muted ac-wk-num" aria-hidden="true">{row.count}</span> : null}
                  </>
                ) : (
                  <>
                    <span className="ac-wk-twisty" aria-hidden="true" />
                    <span className="ac-wk-icon" data-icon={page?.orphan ? "page-orphan" : "page"} aria-hidden="true" />
                    <span className="ac-wk-ellipsis ac-wk-grow">{row.name}</span>
                    {page?.home ? <span className="ac-wk-icon" data-icon="home" aria-hidden="true" /> : null}
                    {broken > 0 ? (
                      <span className="ac-wk-state" data-tone="danger" aria-hidden="true">
                        <span className="ac-wk-icon" data-icon="link-broken" />
                        {broken}
                      </span>
                    ) : null}
                    {dirty ? <span className="ac-wk-dot" aria-hidden="true" /> : null}
                  </>
                )}
              </div>
            );
          }}
        />
      )}
    </div>
  );
}

/** 모두 펼치기에 쓸 폴더 목록(호출자가 `onExpandedChange`에 넘긴다). */
export function expandAllFolders(pages: readonly WikiPageSummary[]): ReadonlySet<string> {
  return new Set(allFolders(pages));
}
