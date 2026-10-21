import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { joinClass } from "./Status";

/** 파일 트리에 보일 파일 하나. 도메인을 모른다: 경로와 오른쪽에 붙일 부가 표시만 있다. */
export interface FileTreeItem {
  /** `/`로 구분한 상대 경로(폴더는 경로에서 만든다) */
  path: string;
  /** 경로 오른쪽에 붙는 부가 표시(크기·배지 등) */
  trailing?: ReactNode;
  /** 앞에 붙는 표시(아이콘 등). 없으면 기본 문자 아이콘 */
  leading?: ReactNode;
}

export interface FileTreeProps {
  items: readonly FileTreeItem[];
  /** 접근성 이름(필수) */
  ariaLabel: string;
  /** `tree`(폴더로 묶음, 기본) | `flat`(전체 경로 한 줄씩) */
  view?: "tree" | "flat";
  /** 선택된 파일 경로(제어형) */
  selected?: string | null;
  /** Enter/클릭으로 파일을 고를 때 */
  onSelect?: (path: string) => void;
  className?: string;
}

interface Row {
  key: string;
  kind: "folder" | "file";
  /** 화면에 보이는 이름(트리: 마지막 구성요소, 평면: 전체 경로) */
  label: string;
  depth: number;
  parent: string | null;
  item?: FileTreeItem;
}

/** 경로 목록 → 폴더/파일 행(폴더 먼저, 이름순). 순수 함수. */
export function buildRows(items: readonly FileTreeItem[], view: "tree" | "flat", collapsed: ReadonlySet<string>): Row[] {
  if (view === "flat") {
    return items.map((item) => ({ key: item.path, kind: "file" as const, label: item.path, depth: 1, parent: null, item }));
  }
  interface Dir {
    name: string;
    key: string;
    dirs: Map<string, Dir>;
    files: FileTreeItem[];
  }
  const root: Dir = { name: "", key: "", dirs: new Map(), files: [] };
  for (const item of items) {
    const parts = item.path.split("/").filter((p) => p !== "");
    let dir = root;
    for (const part of parts.slice(0, -1)) {
      const key = dir.key === "" ? part : `${dir.key}/${part}`;
      let next = dir.dirs.get(part);
      if (!next) {
        next = { name: part, key, dirs: new Map(), files: [] };
        dir.dirs.set(part, next);
      }
      dir = next;
    }
    dir.files.push(item);
  }
  const rows: Row[] = [];
  const walk = (dir: Dir, depth: number, parent: string | null) => {
    for (const d of [...dir.dirs.values()].sort((a, b) => a.name.localeCompare(b.name))) {
      rows.push({ key: `dir:${d.key}`, kind: "folder", label: d.name, depth, parent });
      if (!collapsed.has(d.key)) walk(d, depth + 1, `dir:${d.key}`);
    }
    for (const f of [...dir.files].sort((a, b) => a.path.localeCompare(b.path))) {
      const name = f.path.split("/").filter((p) => p !== "").pop() ?? f.path;
      rows.push({ key: f.path, kind: "file", label: name, depth, parent });
      rows[rows.length - 1]!.item = f;
    }
  };
  walk(root, 1, null);
  return rows;
}

/**
 * 경로 배열을 트리(또는 평면 목록)로 보여 주는 `role="tree"`. 도메인을 모른다.
 * 키보드: `↑↓` 이동, `→` 폴더 펴기/첫 자식, `←` 폴더 접기/부모, `Enter`/`Space` 파일 선택·폴더 토글, `Home`/`End`.
 */
export function FileTree({ items, ariaLabel, view = "tree", selected, onSelect, className }: FileTreeProps) {
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [active, setActive] = useState<string | null>(null);
  const refs = useRef(new Map<string, HTMLDivElement>());
  const rows = useMemo(() => buildRows(items, view, collapsed), [items, view, collapsed]);
  const current = rows.some((r) => r.key === active) ? active : (rows[0]?.key ?? null);

  const focusRow = (key: string | undefined) => {
    if (key === undefined) return;
    setActive(key);
    refs.current.get(key)?.focus();
  };
  const folderPath = (row: Row) => row.key.slice(4);
  const toggle = (row: Row, open: boolean) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (open) next.delete(folderPath(row));
      else next.add(folderPath(row));
      return next;
    });

  const onKeyDown = (event: KeyboardEvent, row: Row, index: number) => {
    const isOpen = row.kind === "folder" && !collapsed.has(folderPath(row));
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        focusRow(rows[index + 1]?.key);
        break;
      case "ArrowUp":
        event.preventDefault();
        focusRow(rows[index - 1]?.key);
        break;
      case "Home":
        event.preventDefault();
        focusRow(rows[0]?.key);
        break;
      case "End":
        event.preventDefault();
        focusRow(rows[rows.length - 1]?.key);
        break;
      case "ArrowRight":
        event.preventDefault();
        if (row.kind === "folder") {
          if (!isOpen) toggle(row, true);
          else focusRow(rows[index + 1]?.key);
        }
        break;
      case "ArrowLeft":
        event.preventDefault();
        if (row.kind === "folder" && isOpen) toggle(row, false);
        else if (row.parent !== null) focusRow(row.parent);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        if (row.kind === "folder") toggle(row, !isOpen);
        else onSelect?.(row.key);
        break;
    }
  };

  return (
    <div role="tree" aria-label={ariaLabel} className={joinClass("ac-filetree", className)}>
      {rows.map((row, index) => {
        const isOpen = row.kind === "folder" && !collapsed.has(folderPath(row));
        return (
          <div
            key={row.key}
            ref={(el) => {
              if (el) refs.current.set(row.key, el);
              else refs.current.delete(row.key);
            }}
            role="treeitem"
            aria-level={row.depth}
            aria-selected={row.kind === "file" ? selected === row.key : undefined}
            aria-expanded={row.kind === "folder" ? isOpen : undefined}
            tabIndex={row.key === current ? 0 : -1}
            className="ac-filetree-row"
            data-kind={row.kind}
            data-path={row.kind === "folder" ? folderPath(row) : row.key}
            data-selected={row.kind === "file" && selected === row.key ? "true" : undefined}
            style={{ paddingInlineStart: `calc(var(--ac-space-2, 8px) + ${(row.depth - 1) * 16}px)` }}
            onFocus={() => setActive(row.key)}
            onKeyDown={(e) => onKeyDown(e, row, index)}
            onClick={() => {
              setActive(row.key);
              if (row.kind === "folder") toggle(row, !isOpen);
              else onSelect?.(row.key);
            }}
          >
            <span className="ac-filetree-mark" aria-hidden="true">
              {row.item?.leading ?? (row.kind === "folder" ? (isOpen ? "▾" : "▸") : "·")}
            </span>
            <span className="ac-filetree-label ac-ellipsis" title={row.item?.path ?? row.label}>
              {row.label}
            </span>
            {row.item?.trailing === undefined ? null : <span className="ac-filetree-trailing">{row.item.trailing}</span>}
          </div>
        );
      })}
    </div>
  );
}
