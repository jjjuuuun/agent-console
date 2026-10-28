import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactElement } from "react";

import { Icon } from "./icons";
import type { Translate } from "./messages";
import { cells } from "./middleEllipsis";
import { collapseCrumbs, splitPath } from "./pathSegments";
import type { FolderCreateFn, FolderEntryData, FolderListFn, FolderListingData, FolderRootData } from "./types";
import { useAfter } from "./useAfter";
import { useElementCells } from "./useElementCells";
import { useVirtualList } from "./useVirtualList";

export interface FolderBrowserProps {
  /** 요소 id 접두. */
  id: string;
  t: Translate;
  /** 탐색 시작 위치(서버가 준다). 시작 위치 화면의 항목. */
  roots: readonly FolderRootData[];
  /** 처음 보여 줄 폴더. null이면 시작 위치 목록. */
  startPath: string | null;
  list: FolderListFn;
  /** 없으면 [새 폴더]를 그리지 않는다. */
  createFolder?: FolderCreateFn;
  /** 폴더로 들어갔다(더블클릭·Enter·→·빵부스러기·새 폴더 성공). 앱이 입력 칸을 이 경로로 바꾼다. */
  onNavigate?: (path: string) => void;
  /** [이 폴더 선택]. */
  onSelect?: (path: string) => void;
  /** Esc. */
  onClose?: () => void;
  /** `nearest_existing`에서 시작했을 때 안내에 넣을 경로. 폴더로 들어가면 사라진다. */
  nearestNote?: string | null;
  disabled?: boolean;
  defaultShowHidden?: boolean;
  /** 행 높이(px). 토큰 `--ac-browse-row-h`(32)와 같아야 한다. */
  rowHeightPx?: number;
  /** 로딩 표시를 미루는 시간(ms). 기본 150. */
  loadingDelayMs?: number;
  autoFocus?: boolean;
}

interface Row {
  key: string;
  name: string;
  path: string;
  hidden: boolean;
  link: boolean;
  locked: boolean;
  projectName: string | null;
}

type Load = { status: "loading" | "ready" | "error"; data: FolderListingData | null };
type Loaded = { key: string; status: "ready" | "error"; data: FolderListingData | null };

const INVALID_NAME = /[\\/:]/;

function toRow(e: FolderEntryData): Row {
  return {
    key: e.path, name: e.name, path: e.path, hidden: e.hidden === true, link: e.link === true, locked: e.locked === true,
    projectName: e.project_id ? (e.project_name ?? e.project_id) : null,
  };
}

/**
 * 폴더 찾아보기 패널: 빵부스러기, 숨김 토글, 새 폴더, 가상 목록(listbox), 로딩·빈·잘림·오류 상태.
 * 서버 호출(`list`·`createFolder`)은 props로 주입받는다. 현재 위치는 `onNavigate`로 알린다.
 */
export function FolderBrowser(props: FolderBrowserProps): ReactElement {
  const { id, t, roots, startPath, list, createFolder, onNavigate, onSelect, onClose, nearestNote, disabled, defaultShowHidden = false, rowHeightPx = 32, loadingDelayMs = 150, autoFocus = true } = props;
  const [location, setLocation] = useState<string | null>(startPath);
  const [hidden, setHidden] = useState(defaultShowHidden);
  const [loaded, setLoaded] = useState<Loaded>({ key: "", status: "ready", data: null });
  const [reload, setReload] = useState(0);
  const [active, setActive] = useState(0);
  const [noteOn, setNoteOn] = useState(true);
  const [creating, setCreating] = useState<{ name: string; error: string | null; busy: boolean } | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const newInputRef = useRef<HTMLInputElement>(null);
  const cameFrom = useRef<string | null>(null);
  const typeahead = useRef({ text: "", at: 0 });

  // 목록 읽기: 위치·숨김·다시 시도가 바뀌면 이전 요청을 취소하고 새로 읽는다. 오래된 응답은 버린다.
  // "읽는 중"은 상태로 저장하지 않고, 마지막으로 도착한 응답의 key가 현재 key와 다른지로 구한다.
  // `list`가 매 렌더 새 함수여도 다시 읽지 않도록 최신 값만 ref로 든다.
  const listRef = useRef(list);
  useLayoutEffect(() => {
    listRef.current = list;
  });
  const loadKey = `${location ?? ""}\u0000${hidden ? 1 : 0}\u0000${reload}`;
  useEffect(() => {
    if (location === null) return;
    const ctl = new AbortController();
    listRef.current({ path: location, hidden }, ctl.signal).then(
      (data) => {
        if (!ctl.signal.aborted) setLoaded({ key: loadKey, status: "ready", data });
      },
      () => {
        if (!ctl.signal.aborted) setLoaded((prev) => ({ key: loadKey, status: "error", data: prev.data }));
      },
    );
    return () => ctl.abort();
  }, [location, hidden, reload, loadKey]);

  const load: Load = location === null ? { status: "ready", data: null } : loaded.key === loadKey ? { status: loaded.status, data: loaded.data } : { status: "loading", data: loaded.data };
  const rows: Row[] = useMemo(() => {
    if (location === null) return roots.map((r) => ({ key: r.path, name: r.label, path: r.path, hidden: false, link: false, locked: false, projectName: null }));
    return load.data ? load.data.entries.map(toRow) : [];
  }, [location, roots, load.data]);

  // 새 목록이 오면 활성 행을 정한다: 상위로 올라왔으면 방금 있던 폴더, 아니면 첫 행.
  useEffect(() => {
    if (load.status === "loading") return;
    const idx = cameFrom.current ? rows.findIndex((r) => r.path === cameFrom.current) : -1;
    cameFrom.current = null;
    setActive(idx >= 0 ? idx : 0);
    if (idx < 0) scrollRef.current?.scrollTo?.({ top: 0 });
  }, [rows, load.status]);

  const virtual = useVirtualList({ count: rows.length, rowHeight: rowHeightPx, scrollRef, keepIndex: active });
  useEffect(() => {
    if (rows.length === 0) return;
    try {
      virtual.scrollToIndex(Math.min(active, rows.length - 1), { align: "auto" });
    } catch {
      /* 레이아웃이 없는 환경 */
    }
  }, [active, rows.length, virtual]);

  useEffect(() => {
    if (autoFocus) scrollRef.current?.focus();
  }, [autoFocus]);

  const go = useCallback(
    (path: string | null) => {
      setNoteOn(false);
      setCreating(null);
      setMoreOpen(false);
      setLocation(path);
      if (path !== null) onNavigate?.(path);
    },
    [onNavigate],
  );
  const enter = (row: Row | undefined) => {
    if (!row || row.locked || disabled) return;
    go(row.path);
  };
  const up = () => {
    if (location === null) return;
    cameFrom.current = location;
    go(load.data?.parent ?? null);
  };

  const showSkeleton = useAfter(load.status === "loading" && load.data === null && location !== null, loadingDelayMs);
  const showProgress = useAfter(load.status === "loading" && load.data !== null, loadingDelayMs);

  const optionId = (i: number) => `${id}-opt-${i}`;
  const move = (next: number) => setActive(Math.max(0, Math.min(rows.length - 1, next)));

  const startNew = () => {
    if (!createFolder || location === null || disabled) return;
    setCreating({ name: "", error: null, busy: false });
    queueMicrotask(() => newInputRef.current?.focus());
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const k = e.key;
    const pageSize = Math.max(1, Math.floor((scrollRef.current?.clientHeight || 280) / rowHeightPx) - 1);
    if (k === "Escape") {
      e.stopPropagation();
      onClose?.();
      return;
    }
    if (e.ctrlKey && e.shiftKey && (k === "N" || k === "n")) {
      e.preventDefault();
      startNew();
      return;
    }
    if (k === "ArrowDown") move(active + 1);
    else if (k === "ArrowUp" && !e.altKey) move(active - 1);
    else if (k === "Home") move(0);
    else if (k === "End") move(rows.length - 1);
    else if (k === "PageDown") move(active + pageSize);
    else if (k === "PageUp") move(active - pageSize);
    else if (k === "Enter" || k === "ArrowRight") enter(rows[active]);
    else if (k === "ArrowLeft" || k === "Backspace" || (k === "ArrowUp" && e.altKey)) up();
    else if (k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && !e.nativeEvent.isComposing) {
      const now = Date.now();
      const ta = typeahead.current;
      ta.text = now - ta.at > 700 ? k : ta.text + k;
      ta.at = now;
      const needle = ta.text.toLowerCase();
      const from = ta.text.length === 1 ? active + 1 : active;
      const order = [...rows.keys()].map((i) => (from + i) % Math.max(rows.length, 1));
      const hit = order.find((i) => rows[i]!.name.toLowerCase().startsWith(needle));
      if (hit !== undefined) setActive(hit);
      return;
    } else return;
    e.preventDefault();
  };

  const submitNew = async () => {
    if (!creating || !createFolder || location === null || creating.busy) return;
    const name = creating.name.trim();
    if (name === "" || name === "." || name === ".." || INVALID_NAME.test(name)) {
      setCreating({ ...creating, error: t("folder.new.error.invalid") });
      return;
    }
    setCreating({ ...creating, busy: true, error: null });
    try {
      const res = await createFolder({ parent: load.data?.path ?? location, name }, new AbortController().signal);
      if (res.ok) go(res.path);
      else {
        const msg = res.message ?? (res.code === "exists" ? t("folder.new.error.exists") : res.code === "invalid_name" ? t("folder.new.error.invalid") : t("folder.new.error.failed"));
        setCreating((c) => (c ? { ...c, busy: false, error: msg } : c));
      }
    } catch {
      setCreating((c) => (c ? { ...c, busy: false, error: t("folder.new.error.failed") } : c));
    }
  };

  // 빵부스러기
  const navCells = useElementCells(navRef);
  const crumbs = useMemo(() => {
    const base: { label: string; path: string | null }[] = [{ label: t("folder.browse.roots"), path: null }];
    if (location !== null) for (const s of splitPath(load.data?.path ?? location)) base.push(s);
    return base;
  }, [location, load.data, t]);
  const collapsed = collapseCrumbs(crumbs, navCells ?? Number.POSITIVE_INFINITY, cells);

  const renderCrumb = (c: { label: string; path: string | null }, last: boolean) => (
    <li key={`${c.path ?? "roots"}`} className="ac-fp-crumb">
      <button type="button" className="ac-fp-crumb-btn" aria-current={last ? "location" : undefined} disabled={disabled} onClick={() => go(c.path)}>{c.label}</button>
    </li>
  );
  const shownLast = crumbs[crumbs.length - 1];

  const total = rows.length;
  const activeRow = rows[active];

  return (
    <div className="ac-fp-root ac-fp-browser" id={id} data-busy={load.status === "loading" ? "true" : undefined}>
      <div className="ac-fp-browser-head">
        <nav ref={navRef} className="ac-fp-nav" aria-label={t("folder.browse.breadcrumb")}>
          <ol className="ac-fp-crumbs">
            {collapsed.hidden.length === 0
              ? crumbs.map((c) => renderCrumb(c, c === shownLast))
              : (
                <>
                  {collapsed.head.map((c) => renderCrumb(c, false))}
                  <li className="ac-fp-crumb ac-fp-more">
                    <button type="button" className="ac-fp-crumb-btn" aria-haspopup="menu" aria-expanded={moreOpen} aria-label={t("folder.browse.breadcrumb_more")} onClick={() => setMoreOpen((o) => !o)} onKeyDown={(e) => { if (e.key === "Escape") setMoreOpen(false); }}>
                      <Icon name="more" />
                    </button>
                    {moreOpen ? (
                      <ul className="ac-fp-more-menu" role="menu" onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); setMoreOpen(false); } }}>
                        {collapsed.hidden.map((c) => (
                          <li key={c.path ?? "roots"} role="none">
                            <button type="button" role="menuitem" className="ac-fp-menuitem" onClick={() => go(c.path)}>{c.label}</button>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                  {collapsed.tail.map((c) => renderCrumb(c, c === shownLast))}
                </>
              )}
          </ol>
        </nav>
        <label className="ac-fp-check">
          <input type="checkbox" checked={hidden} disabled={disabled} onChange={(e) => setHidden(e.target.checked)} />
          <span>{t("folder.browse.hidden")}</span>
        </label>
        {createFolder ? (
          <button type="button" className="ac-fp-btn" data-size="sm" disabled={disabled || location === null} onClick={startNew}>{t("folder.browse.new")}</button>
        ) : null}
      </div>

      {nearestNote && noteOn ? <p className="ac-fp-note">{t("folder.check.nearest_note", { path: nearestNote })}</p> : null}
      <div className="ac-fp-progress" data-on={showProgress ? "true" : undefined} aria-hidden="true" />

      {creating ? (
        <div className="ac-fp-newrow">
          <div className="ac-fp-newline">
            <Icon name="folder" />
            <input
              ref={newInputRef}
              className="ac-fp-input ac-fp-newinput"
              value={creating.name}
              aria-label={t("folder.browse.new_name")}
              aria-invalid={creating.error ? "true" : undefined}
              aria-describedby={creating.error ? `${id}-newerr` : undefined}
              disabled={creating.busy}
              spellCheck={false}
              onChange={(e) => setCreating({ ...creating, name: e.target.value, error: null })}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void submitNew();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  e.stopPropagation();
                  setCreating(null);
                  scrollRef.current?.focus();
                }
              }}
            />
          </div>
          {creating.error ? <p id={`${id}-newerr`} className="ac-fp-newerr" role="alert">{creating.error}</p> : null}
        </div>
      ) : null}

      <div className="ac-fp-body">
        {load.status === "error" ? (
          <div className="ac-fp-state" role="alert">
            <p>{t("folder.browse.error")}</p>
            <button type="button" className="ac-fp-btn" data-size="sm" onClick={() => setReload((n) => n + 1)}>{t("folder.browse.retry")}</button>
          </div>
        ) : null}
        {load.status !== "error" && showSkeleton ? (
          <div className="ac-fp-skeleton" aria-busy="true" aria-label={t("folder.browse.loading")}>
            {Array.from({ length: 6 }, (_, i) => <span key={i} className="ac-fp-skel-row" />)}
          </div>
        ) : null}
        {load.status === "ready" && total === 0 ? <p className="ac-fp-state ac-fp-empty">{t("folder.browse.empty")}</p> : null}
        <div
          ref={scrollRef}
          className="ac-fp-list"
          role="listbox"
          tabIndex={0}
          aria-label={t("folder.browse.list")}
          aria-activedescendant={total > 0 && activeRow ? optionId(active) : undefined}
          aria-busy={load.status === "loading" ? "true" : undefined}
          hidden={load.status === "error" || total === 0}
          onKeyDown={onKeyDown}
        >
          <div role="presentation" className="ac-fp-list-inner" style={{ height: virtual.getTotalSize() }}>
            {virtual.getVirtualItems().map((v) => {
              const row = rows[v.index];
              if (!row) return null;
              const isActive = v.index === active;
              return (
                <div
                  key={row.key}
                  id={optionId(v.index)}
                  role="option"
                  className="ac-fp-row"
                  aria-selected={isActive}
                  aria-disabled={row.locked ? "true" : undefined}
                  aria-setsize={total}
                  aria-posinset={v.index + 1}
                  data-active={isActive ? "true" : undefined}
                  data-hidden={row.hidden ? "true" : undefined}
                  data-locked={row.locked ? "true" : undefined}
                  title={row.locked ? t("folder.browse.locked") : row.link ? t("folder.browse.link") : undefined}
                  style={{ height: rowHeightPx, transform: `translateY(${v.start}px)` }}
                  onClick={() => { setActive(v.index); scrollRef.current?.focus(); }}
                  onDoubleClick={() => enter(row)}
                >
                  <Icon name={row.locked ? "folder-lock" : "folder"} />
                  <span className="ac-fp-name ac-ellipsis">{row.name}</span>
                  {row.link ? <span className="ac-fp-link" aria-hidden="true">↗</span> : null}
                  {row.link ? <span className="ac-fp-sr">{t("folder.browse.link")}</span> : null}
                  {row.locked ? <span className="ac-fp-sr">{t("folder.browse.locked")}</span> : null}
                  {row.projectName ? <span className="ac-fp-chip ac-ellipsis">{t("folder.browse.registered", { name: row.projectName })}</span> : null}
                </div>
              );
            })}
          </div>
        </div>
        {load.data?.truncated ? <p className="ac-fp-truncated">{t("folder.browse.truncated", { n: load.data.entries.length })}</p> : null}
      </div>

      <div className="ac-fp-browser-foot">
        <span className="ac-fp-hint">{t("folder.browse.hint")}</span>
        <button type="button" className="ac-fp-btn" data-variant="primary" data-size="sm" disabled={disabled || location === null} onClick={() => location !== null && onSelect?.(location)}>
          {t("folder.browse.select")}
        </button>
      </div>
    </div>
  );
}
