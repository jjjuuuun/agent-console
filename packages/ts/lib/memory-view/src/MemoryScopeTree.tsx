import type { MemoryScopeKindInfo, MemoryScopeRef, MemoryScopeSummary } from "@agent-console/contracts/memory";
import { useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { formatMessage, resolveMessages } from "./messages";
import { groupScopes, sameScope, scopeKey, scopeLabel, type ScopeGroup, type ScopeLabel, type ScopeNameResolvers } from "./scopes";

export interface MemoryScopeTreeProps {
  /** 범위 종류 목록(서버 병합 순서). */
  kinds: readonly MemoryScopeKindInfo[];
  /** 범위 요약. 프로젝트 거르기는 호출자가 `visibleScopes`로 먼저 한다. */
  scopes: readonly MemoryScopeSummary[];
  /** 선택한 범위. null = "모든 범위". */
  selected: MemoryScopeRef | null;
  onSelect: (scope: MemoryScopeRef | null) => void;
  /** 맥락 필드 이름 → 이름 풀기. 없으면 모든 id를 그대로 보인다. */
  resolvers?: ScopeNameResolvers;
  /** 펼친 종류 id 목록(제어). 생략하면 모두 펼침으로 시작하는 비제어. */
  openKinds?: readonly string[];
  onOpenKindsChange?: (open: string[]) => void;
  /** 프로젝트 거르기로 숨긴 범위 수와 "모두 보기" 콜백. 0이면 줄이 없다. */
  hiddenCount?: number;
  onShowHidden?: () => void;
  /** 범위 행 `⋯` 메뉴 동작. 셋 다 없으면 메뉴 단추가 없다. */
  onNewIn?: (scope: MemoryScopeRef) => void;
  onExportScope?: (scope: MemoryScopeRef) => void;
  onClearScope?: (scope: MemoryScopeRef) => void;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

type Row =
  | { type: "all"; id: string; level: 1 }
  | { type: "kind"; id: string; level: 1; group: ScopeGroup }
  | { type: "scope"; id: string; level: 2; group: ScopeGroup; scope: MemoryScopeSummary; label: ScopeLabel }
  | { type: "heading"; id: string };

/**
 * 범위 나무: 맨 위 "모든 범위" → 종류(서버 순서) → 범위(라벨 순). 쓸 수 없는 범위(알 수 없는·꺼진 종류)는 맨 아래에 모은다.
 * 범위 종류 이름·라벨은 전부 props 데이터다. 키보드: ↑↓ 이동, ←→ 접기/펼치기, Home/End, Enter/Space 선택.
 */
export function MemoryScopeTree({
  kinds, scopes, selected, onSelect, resolvers = {}, openKinds, onOpenKindsChange, hiddenCount = 0, onShowHidden,
  onNewIn, onExportScope, onClearScope, messages: custom, className,
}: MemoryScopeTreeProps) {
  const m = resolveMessages(custom);
  const grouped = useMemo(
    () => groupScopes(kinds, scopes, { labelOf: (s, k) => scopeLabel(s.scope, k, resolvers, s.kind_known !== false).text }),
    [kinds, scopes, resolvers],
  );
  const [innerOpen, setInnerOpen] = useState<string[] | undefined>(undefined);
  const open = openKinds ?? innerOpen;
  const setOpen = (next: string[]) => {
    setInnerOpen(next);
    onOpenKindsChange?.(next);
  };
  const isOpen = (kind: string) => (open === undefined ? true : open.includes(kind));
  const toggle = (kind: string) => {
    const all = [...grouped.groups, ...grouped.unavailable].map((g) => g.kind);
    const current = open ?? all;
    setOpen(current.includes(kind) ? current.filter((k) => k !== kind) : [...current, kind]);
  };

  const rows = useMemo(() => {
    const out: Row[] = [{ type: "all", id: "all", level: 1 }];
    const add = (g: ScopeGroup) => {
      out.push({ type: "kind", id: `kind:${g.kind}`, level: 1, group: g });
      if (!g.selfScope && isOpen(g.kind)) {
        for (const s of g.scopes) out.push({ type: "scope", id: `scope:${scopeKey(s.scope)}`, level: 2, group: g, scope: s, label: scopeLabel(s.scope, g.info, resolvers, g.state !== "unknown") });
      }
    };
    grouped.groups.forEach(add);
    if (grouped.unavailable.length > 0) {
      out.push({ type: "heading", id: "heading" });
      grouped.unavailable.forEach(add);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- isOpen은 open에 의존한다
  }, [grouped, resolvers, open]);

  const focusable = rows.filter((r): r is Exclude<Row, { type: "heading" }> => r.type !== "heading");
  const [focusId, setFocusId] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const selectedId = selected === null ? "all" : rowIdOfScope(selected, grouped.groups.concat(grouped.unavailable));
  const activeId = focusable.some((r) => r.id === focusId) ? focusId : focusable.some((r) => r.id === selectedId) ? selectedId : (focusable[0]?.id ?? null);
  const uid = useId();

  const focusRow = (id: string) => {
    setFocusId(id);
    queueMicrotask(() => rootRef.current?.querySelector<HTMLElement>(`[data-row-id="${CSS.escape(id)}"]`)?.focus());
  };
  const activate = (row: Exclude<Row, { type: "heading" }>) => {
    if (row.type === "all") onSelect(null);
    else if (row.type === "kind") {
      if (row.group.selfScope) onSelect({ kind: row.group.kind, id: "" });
      else toggle(row.group.kind);
    } else onSelect(row.scope.scope);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const target = (e.target as HTMLElement).closest<HTMLElement>("[data-row-id]");
    if (!target || e.target !== target) return;
    const idx = focusable.findIndex((r) => r.id === target.dataset["rowId"]);
    const row = focusable[idx];
    if (!row) return;
    const go = (i: number) => {
      const next = focusable[Math.max(0, Math.min(focusable.length - 1, i))];
      if (next) focusRow(next.id);
    };
    switch (e.key) {
      case "ArrowDown": e.preventDefault(); go(idx + 1); break;
      case "ArrowUp": e.preventDefault(); go(idx - 1); break;
      case "Home": e.preventDefault(); go(0); break;
      case "End": e.preventDefault(); go(focusable.length - 1); break;
      case "ArrowRight":
        if (row.type === "kind" && !row.group.selfScope) { e.preventDefault(); if (!isOpen(row.group.kind)) toggle(row.group.kind); else go(idx + 1); }
        break;
      case "ArrowLeft":
        if (row.type === "kind" && !row.group.selfScope && isOpen(row.group.kind)) { e.preventDefault(); toggle(row.group.kind); }
        else if (row.type === "scope") { e.preventDefault(); focusRow(`kind:${row.group.kind}`); }
        break;
      case "Enter": case " ": e.preventDefault(); activate(row); break;
      default:
    }
  };

  /** 같은 종류의 범위(둘 이상)가 전부 정의에서 지워졌으면 "삭제됨" 표지는 종류 행에 한 번만 단다. */
  const allDeletedKinds = new Set(
    [...grouped.groups, ...grouped.unavailable]
      .filter((g) => !g.selfScope && g.scopes.length > 1 && g.state !== "unknown" && g.scopes.every((s) => scopeLabel(s.scope, g.info, resolvers, true).deleted))
      .map((g) => g.kind),
  );

  const hasMenu = Boolean(onNewIn ?? onExportScope ?? onClearScope);
  const [menuFor, setMenuFor] = useState<string | null>(null);

  const countCell = (n: number): ReactNode => <span className="ac-mem-tree-count" data-zero={n === 0 ? "" : undefined}>{n}</span>;

  return (
    <div className={`ac-mem-root ac-mem-tree${className ? ` ${className}` : ""}`} ref={rootRef}>
      <div role="tree" aria-label={m["a11y.tree"]} onKeyDown={onKeyDown} className="ac-mem-tree-list">
        {rows.map((row) => {
          if (row.type === "heading") {
            return <div key={row.id} role="presentation" className="ac-mem-tree-heading">{m["scope.unavailableGroup"]}</div>;
          }
          const tabIndex = row.id === activeId ? 0 : -1;
          if (row.type === "all") {
            return (
              <div key={row.id} role="treeitem" aria-level={1} aria-selected={selected === null} data-row-id={row.id} tabIndex={tabIndex}
                className="ac-mem-tree-row" data-selected={selected === null ? "" : undefined} onClick={() => { setFocusId(row.id); onSelect(null); }}
                aria-label={`${m["scope.all"]}, ${formatMessage(m["scope.entries"] as string, { n: grouped.total })}`}>
                <span className="ac-mem-tree-label">{m["scope.all"]}</span>
                {countCell(grouped.total)}
              </div>
            );
          }
          if (row.type === "kind") {
            const g = row.group;
            const label = scopeLabel({ kind: g.kind, id: "" }, g.info, {}, g.state !== "unknown");
            const kindText = g.state === "unknown" ? g.kind : (g.info?.label ?? g.kind);
            const chips: string[] = [];
            if (g.state === "unknown") chips.push(m["scope.unknownKind"] as string);
            if (g.state === "disabled") chips.push(m["scope.disabledKind"] as string);
            if (allDeletedKinds.has(g.kind)) chips.push(m["scope.deleted"] as string);
            const ref: MemoryScopeRef = { kind: g.kind, id: "" };
            const isSel = g.selfScope && sameScope(selected, ref);
            const tip = g.state === "unknown" ? (m["scope.unknownKind.tip"] as string) : g.state === "disabled" ? (m["scope.disabledKind.tip"] as string) : (g.info?.description ?? undefined);
            return (
              <div key={row.id} role="treeitem" aria-level={1} aria-expanded={g.selfScope ? undefined : isOpen(g.kind)} aria-selected={g.selfScope ? isSel : undefined}
                data-row-id={row.id} tabIndex={tabIndex} className="ac-mem-tree-row ac-mem-tree-kind" data-selected={isSel ? "" : undefined} data-state={g.state}
                title={tip} onClick={() => { setFocusId(row.id); activate(row); }}
                aria-label={[`${label.text}`, formatMessage(m["scope.entries"] as string, { n: g.entries }), ...chips].join(", ")}>
                {g.selfScope ? <span className="ac-mem-tree-twisty" aria-hidden="true" /> : <span className="ac-mem-tree-twisty" aria-hidden="true" data-open={isOpen(g.kind) ? "" : undefined} />}
                {g.state === "unknown" ? <span className="ac-mem-icon ac-mem-icon-unknown" aria-hidden="true" /> : null}
                <span className="ac-mem-tree-label" data-mono={g.state === "unknown" ? "" : undefined}>{kindText}</span>
                {chips.map((c) => <span key={c} className="ac-mem-chip" data-tone="warning">{c}</span>)}
                {countCell(g.entries)}
              </div>
            );
          }
          const sel = sameScope(selected, row.scope.scope);
          const chips = [row.label.deleted ? (m["scope.deleted"] as string) : ""].filter(Boolean);
          const shownChips = allDeletedKinds.has(row.group.kind) ? [] : chips;
          const stateLabel = row.group.state === "unknown" ? (m["scope.unknownKind"] as string) : row.group.state === "disabled" ? (m["scope.disabledKind"] as string) : "";
          const menuOpen = menuFor === row.id;
          return (
            <div key={row.id} role="treeitem" aria-level={2} aria-selected={sel} data-row-id={row.id} tabIndex={tabIndex}
              className="ac-mem-tree-row ac-mem-tree-scope" data-selected={sel ? "" : undefined}
              title={row.label.text} onClick={() => { setFocusId(row.id); onSelect(row.scope.scope); }}
              aria-label={[row.label.text, formatMessage(m["scope.entries"] as string, { n: row.scope.entries }), ...chips, ...(stateLabel ? [stateLabel] : [])].join(", ")}>
              <span className="ac-mem-tree-label" data-mono={row.label.mono ? "" : undefined}>
                {row.label.parts.map((p, i) => (
                  <span key={i} className={p.mono ? "ac-mem-mono" : undefined}>{i > 0 ? " / " : ""}{p.text}</span>
                ))}
              </span>
              {shownChips.map((c) => <span key={c} className="ac-mem-chip" data-tone="warning"><span className="ac-mem-icon ac-mem-icon-unknown" aria-hidden="true" />{c}</span>)}
              {countCell(row.scope.entries)}
              {hasMenu && row.group.state === "ok" ? (
                <>
                  <button type="button" className="ac-mem-iconbtn ac-mem-tree-menu-btn" aria-haspopup="menu" aria-expanded={menuOpen} aria-controls={menuOpen ? `${uid}-menu` : undefined}
                    aria-label={formatMessage(m["scope.menu"] as string, { label: row.label.text })} title={formatMessage(m["scope.menu"] as string, { label: row.label.text })}
                    onClick={(e) => { e.stopPropagation(); setMenuFor(menuOpen ? null : row.id); }}
                    onKeyDown={(e) => { e.stopPropagation(); if (e.key === "Escape") setMenuFor(null); }}>
                    <span aria-hidden="true">⋯</span>
                  </button>
                  {menuOpen ? (
                    <div role="menu" id={`${uid}-menu`} className="ac-mem-menu" onKeyDown={(e) => { e.stopPropagation(); if (e.key === "Escape") setMenuFor(null); }}>
                      {onNewIn ? <button type="button" role="menuitem" onClick={(e) => { e.stopPropagation(); setMenuFor(null); onNewIn(row.scope.scope); }}>{m["scope.menu.newHere"]}</button> : null}
                      {onExportScope ? <button type="button" role="menuitem" onClick={(e) => { e.stopPropagation(); setMenuFor(null); onExportScope(row.scope.scope); }}>{m["scope.menu.exportScope"]}</button> : null}
                      {onClearScope ? <button type="button" role="menuitem" data-danger="" onClick={(e) => { e.stopPropagation(); setMenuFor(null); onClearScope(row.scope.scope); }}>{m["scope.menu.clear"]}</button> : null}
                    </div>
                  ) : null}
                </>
              ) : null}
            </div>
          );
        })}
      </div>
      {hiddenCount > 0 ? (
        <p className="ac-mem-tree-hidden">
          <span>{formatMessage(m["scope.hiddenOthers"] as string, { n: hiddenCount })}</span>{" "}
          {onShowHidden ? <button type="button" className="ac-mem-linkbtn" onClick={onShowHidden}>{m["scope.showAll"]}</button> : null}
        </p>
      ) : null}
    </div>
  );
}

function rowIdOfScope(scope: MemoryScopeRef, groups: readonly ScopeGroup[]): string {
  const g = groups.find((x) => x.kind === scope.kind);
  if (g?.selfScope) return `kind:${g.kind}`;
  return `scope:${scopeKey(scope)}`;
}
