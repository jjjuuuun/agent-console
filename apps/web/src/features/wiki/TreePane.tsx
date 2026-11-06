/**
 * 왼쪽 트리 칸(screen-wiki §6.3): 거르기 입력 + 제목/경로 표시 전환 + `PageTree` + 아래 [최근 변경] 전환(지운 페이지의 [되돌리기]).
 * 폴더 열림 상태는 위키별로 저장한다(`localStorage`, 실패해도 동작). 폴더에는 이름 바꾸기·지우기가 없다(이번 단계 범위 밖).
 * 데이터와 콜백은 props다(페이지 목록·열림 상태 저장은 컨테이너가 한다).
 */
import { useEffect, useRef, useState } from "react";
import { Menu, Button, type MenuItemDef } from "@agent-console/ui";
import { AuthorChip, OpChip, PageTree, expandAllFolders, type TreeRow, type TreeTitleMode, type WikiDisplay } from "@agent-console/wiki-view";
import type { WikiChange, WikiPageSummary } from "@agent-console/contracts/wiki";
import { KNOWN_WIKI_CHANGE_OPS } from "@agent-console/contracts/constants";
import { formatRelative } from "../../lib/format";
import { wikiMessages as m } from "./messages";

export interface TreePaneProps {
  pages: readonly WikiPageSummary[];
  truncated: boolean;
  total: number | null;
  maxPages: number | null;
  selectedPath: string | null;
  dirtyPaths: ReadonlySet<string>;
  expanded: ReadonlySet<string>;
  onExpandedChange: (next: ReadonlySet<string>) => void;
  titleMode: TreeTitleMode;
  onTitleModeChange: (mode: TreeTitleMode) => void;
  display: WikiDisplay;
  onSelect: (path: string) => void;
  onRename: (path: string) => void;
  onDelete: (path: string) => void;
  onNewHere: (folder: string) => void;
  onCopyPath: (path: string) => void;
  /** 쓰기를 막는 이유(읽기 전용). 있으면 새 페이지·이름 바꾸기·지우기 메뉴가 비활성 */
  blockedReason?: string | undefined;
  /** 최근 변경 목록(보이는 동안만 읽는다) */
  changes: { items: readonly WikiChange[]; hasMore: boolean; loading: boolean; failed: boolean; loadMore: () => void };
  onShowRecent: (shown: boolean) => void;
  recentShown: boolean;
  /** 지운 페이지 행의 [되돌리기]. 기록 저장소가 없거나 읽기 전용이면 undefined(버튼 없음) */
  onRestoreDeleted?: ((change: WikiChange) => void) | undefined;
  /** 쓴 주체 칩의 실행 링크 */
  onOpenRun?: ((runId: string, rootRunId: string | null) => void) | undefined;
  now: number;
  /** 트리로 포커스를 옮기는 단축키(`Alt+T`)용 */
  filterRef?: React.Ref<HTMLInputElement>;
}

interface Menu2 {
  row: TreeRow;
  x: number;
  y: number;
}

export function TreePane({ filterRef, ...p }: TreePaneProps) {
  const [filter, setFilter] = useState("");
  const [menu, setMenu] = useState<Menu2 | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const blocked = p.blockedReason !== undefined && p.blockedReason !== "";

  useEffect(() => {
    if (menu === null) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent && e.key !== "Escape") return;
      if (e instanceof MouseEvent && menuRef.current?.contains(e.target as Node)) return;
      setMenu(null);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    const id = requestAnimationFrame(() => menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus());
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
      cancelAnimationFrame(id);
    };
  }, [menu]);

  const items = (row: TreeRow): MenuItemDef[] => {
    if (row.kind === "folder") {
      return [
        { id: "new", label: m.tree.menu.newHere, disabled: blocked, onSelect: () => p.onNewHere(row.key) },
        { id: "expand", label: m.tree.menu.expandAll, onSelect: () => p.onExpandedChange(expandAllFolders(p.pages)) },
        { id: "collapse", label: m.tree.menu.collapseAll, onSelect: () => p.onExpandedChange(new Set()) },
      ];
    }
    return [
      { id: "open", label: m.tree.menu.open, onSelect: () => p.onSelect(row.key) },
      { id: "rename", label: m.tree.menu.rename, disabled: blocked, onSelect: () => p.onRename(row.key) },
      { id: "delete", label: m.tree.menu.delete, danger: true, disabled: blocked, onSelect: () => p.onDelete(row.key) },
      { id: "copy", label: m.tree.menu.copyPath, onSelect: () => p.onCopyPath(row.key) },
    ];
  };

  return (
    <div className="wiki-tree-pane" data-testid="wiki-tree-pane">
      {p.recentShown ? null : (
        <div className="wiki-tree-top">
          <input
            ref={filterRef}
            type="search"
            className="wiki-input wiki-tree-filter"
            aria-label={m.tree.filter}
            placeholder={m.tree.filter}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <select className="wiki-input wiki-tree-mode" aria-label={m.tree.titleMode} value={p.titleMode} onChange={(e) => p.onTitleModeChange(e.target.value === "path" ? "path" : "title")}>
            <option value="title">{m.tree.byTitle}</option>
            <option value="path">{m.tree.byPath}</option>
          </select>
        </div>
      )}
      <div className="wiki-tree-body">
        {p.recentShown ? (
          <RecentList {...p} />
        ) : p.pages.length === 0 ? (
          <p className="app-muted wiki-tree-empty">{m.tree.empty}</p>
        ) : (
          <PageTree
            pages={p.pages}
            selectedPath={p.selectedPath}
            expanded={p.expanded}
            onExpandedChange={p.onExpandedChange}
            filter={filter}
            titleMode={p.titleMode}
            dirtyPaths={p.dirtyPaths}
            onSelect={p.onSelect}
            onRename={blocked ? undefined : p.onRename}
            onDelete={blocked ? undefined : p.onDelete}
            onContextMenu={(row, anchor) => {
              const r = anchor.getBoundingClientRect();
              setMenu({ row, x: r.left + 24, y: r.bottom });
            }}
            truncated={p.truncated}
            total={p.total}
            maxPages={p.maxPages}
            height="100%"
          />
        )}
      </div>
      <div className="wiki-tree-foot">
        <Button size="sm" aria-pressed={p.recentShown} onClick={() => p.onShowRecent(!p.recentShown)}>
          {p.recentShown ? m.tree.recentBack : `${m.tree.recent} ▸`}
        </Button>
      </div>
      {menu === null ? null : (
        <div ref={menuRef} className="ac-popover wiki-ctx" role="presentation" style={{ position: "fixed", left: menu.x, top: menu.y }} aria-label={m.tree.menuLabel}>
          <Menu items={items(menu.row)} onClose={() => setMenu(null)} />
        </div>
      )}
    </div>
  );
}

function RecentList(p: Omit<TreePaneProps, "filterRef">) {
  const del: string = KNOWN_WIKI_CHANGE_OPS.DELETE;
  if (p.changes.loading && p.changes.items.length === 0) return <p className="app-muted wiki-tree-empty" role="status">{m.loading}</p>;
  if (p.changes.failed) return <p className="app-field-error wiki-tree-empty" role="alert">{m.changes.failed}</p>;
  if (p.changes.items.length === 0) return <p className="app-muted wiki-tree-empty">{m.tree.recentEmpty}</p>;
  return (
    <ul className="wiki-recent" aria-label={m.tree.recent}>
      {p.changes.items.map((c, i) => (
        <li key={`${c.path}:${c.version}:${i}`} className="wiki-recent-row">
          <button type="button" className="wiki-recent-open ac-mono-wrap" title={c.path} onClick={() => p.onSelect(c.path)}>{c.path}</button>
          <span className="wiki-recent-meta">
            <OpChip op={c.op} display={p.display} size="dense" />
            <span className="app-muted">{formatRelative(c.at, p.now)}</span>
            <AuthorChip author={c.author} display={p.display} size="dense" {...(p.onOpenRun === undefined ? {} : { onOpenRun: p.onOpenRun })} />
            {c.op === del && p.onRestoreDeleted !== undefined ? <button type="button" className="app-link-btn" onClick={() => p.onRestoreDeleted?.(c)}>{m.tree.deletedUndo}</button> : null}
          </span>
        </li>
      ))}
      {p.changes.hasMore ? <li><Button size="sm" onClick={p.changes.loadMore}>{m.tree.recentMore}</Button></li> : null}
    </ul>
  );
}

