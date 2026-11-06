/**
 * 위키 화면 › 페이지 탭(screen-wiki §6): 트리 · 가운데(보기/편집/비교/기록 버전) · 오른쪽 패널(백링크·나가는 링크·기록).
 * 선택한 페이지·모드·절·버전은 주소가 진실이다. 저장은 낙관적 갱신이 아니라 서버 응답으로 닫고(`If-Match`·`If-None-Match: *`),
 * 충돌(412)·규칙 거부(422)·비밀 의심은 띠로 보인다. 링크는 서버가 준 범위만 쓴다 — 웹에 링크 패턴·머리말 키·규칙 이름이 없다.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button, ConfirmDialog, useToast } from "@agent-console/ui";
import { KNOWN_ISSUE_CODES } from "@agent-console/contracts/constants";
import { DocumentEditor, type DocumentEditorHandle, type EditorViewMode } from "@agent-console/markdown-doc";
import { HistoryDiff, PageView, WIKI_LINK_HREF_PREFIX, linkMarks, linkifySource, wikiUrlTransform, type HistoryDiffBase, type PageViewHandle, type TreeTitleMode } from "@agent-console/wiki-view";
import type { Issue } from "@agent-console/contracts";
import type { WikiChange, WikiLink, WikiPageVersion, WikiPageView } from "@agent-console/contracts/wiki";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useStorage } from "../../app/StorageContext";
import { useNow } from "../../app/useNow";
import { getAt } from "../../lib/jsonPointer";
import { formatDateTime, formatRelative } from "../../lib/format";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { DEFAULT_ROUTES, routeServing } from "../../shell/routeConfig";
import { useRoutesOn } from "../library";
import { Bands, type BandItem } from "./Bands";
import { LinkPicker } from "./LinkPicker";
import { DeletePageDialog, MovePageDialog, RestoreDialog } from "./PageDialogs";
import { EditStatus, PageHeaderBlock, RuleChip, ViewToolbar } from "./PageMain";
import { SidePane } from "./SidePane";
import { TreePane } from "./TreePane";
import { ListSkeleton } from "./parts";
import { ownWriteKey, usePage, usePageHistory, usePageList, usePageVersion, useWikiChanges, useWikiSpace, useWikiSyntax, wikiKeys } from "./useWikiApi";
import { usePagePreview } from "./usePagePreview";
import { usePageSaver } from "./usePageSave";
import { VIEW_MODES, WIKI_LIMITS, WIKI_PARAMS, WIKI_STORAGE, SIDE_TAB_DEFS, type PageViewMode } from "./wikiConfig";
import { classifyWikiError, failureDetail } from "./wikiErrors";
import { wikiPagePath, runPath } from "./wikiPaths";
import { useWikiShortcuts } from "./wikiShortcuts";
import type { WikiTabProps } from "./wikiTabs";
import { editorMessages, wikiMessages as m } from "./messages";

const P = WIKI_PARAMS;
const EMPTY: readonly never[] = [];

type Draft = { text: string; baseHash: string | undefined };

function readSet(raw: string | null): ReadonlySet<string> {
  if (raw === null) return new Set();
  try {
    const v: unknown = JSON.parse(raw);
    return new Set(Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
  } catch {
    return new Set();
  }
}

/** 비밀 의심 띠를 이 세션에서 닫았는가(`sessionStorage`, 못 쓰면 항상 아니오). */
function secretDismissed(key: string): boolean {
  try {
    return globalThis.sessionStorage?.getItem(key) === "1";
  } catch {
    return false;
  }
}
function dismissSecret(key: string): void {
  try {
    globalThis.sessionStorage?.setItem(key, "1");
  } catch {
    // 저장할 수 없으면 이번 화면에서만 닫는다
  }
}

const lastSegment = (path: string): string => path.split("/").pop() ?? path;
const linesText = (lines: readonly number[]): string => lines.join(", ");
const issueLines = (issues: readonly Issue[]): number[] => issues.flatMap((i) => { const line = (i as unknown as { line?: number | null }).line; return typeof line === "number" ? [line] : []; });

export function PageTab(props: WikiTabProps) {
  const { wikiId, view, ctx, display, params, setParams, ownWrites, refresh, reportDirty, openNewPage, hasTab, goTab } = props;
  const storage = useStorage();
  const toast = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const space = useWikiSpace();
  const now = useNow(true, 60_000);
  const routeOn = useRoutesOn();
  const narrow = useMediaQuery(`(max-width: ${WIKI_LIMITS.drawerBelow - 1}px)`);
  const wide = useMediaQuery(`(min-width: ${WIKI_LIMITS.splitViewportMin}px)`);
  const editorRef = useRef<DocumentEditorHandle>(null);
  const viewRef = useRef<PageViewHandle>(null);
  const treeFilterRef = useRef<HTMLInputElement>(null);

  // ---- 선택·모드(주소가 진실) ---------------------------------------------------------------
  const home = view.wiki.home ?? "";
  const pathParam = params.get(P.path);
  const path = pathParam !== null && pathParam !== "" ? pathParam : home !== "" ? home : null;
  const rawMode = params.get(P.mode);
  const wantedMode: PageViewMode = VIEW_MODES.find((x) => x === rawMode) ?? "view";
  const readOnly = ctx.readOnly;
  const mode: PageViewMode = readOnly ? "view" : wantedMode === "split" && !wide ? "edit" : wantedMode;
  const editing = mode !== "view";
  const sideParam = params.get(P.side);
  const sideTab = SIDE_TAB_DEFS.find((t) => t.id === sideParam)?.id ?? SIDE_TAB_DEFS[0]?.id ?? "";
  const anchorParam = params.get(P.anchor);
  const lineParam = Number(params.get(P.line));
  const initialLine = Number.isInteger(lineParam) && lineParam > 0 ? lineParam : undefined;
  const compareParam = Number(params.get(P.version));
  const compareVersion = Number.isInteger(compareParam) && compareParam > 0 ? compareParam : null;
  const writeBlock = readOnly ? ctx.readOnlyReason : undefined;

  const update = useCallback(
    (patch: Readonly<Record<string, string | null>>, options?: { replace?: boolean }) => {
      const next = new URLSearchParams(params);
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === "") next.delete(k);
        else next.set(k, v);
      }
      setParams(next, options);
    },
    [params, setParams],
  );
  const openPath = useCallback((p: string, anchor: string | null = null) => update({ [P.path]: p, [P.line]: null, [P.anchor]: anchor, [P.version]: null }), [update]);

  // ---- 데이터 ---------------------------------------------------------------------------------
  const pagesQ = usePageList(wikiId);
  const pages = useMemo(() => pagesQ.data?.items ?? EMPTY, [pagesQ.data]);
  const pageQ = usePage(wikiId, path);
  const syntaxQ = useWikiSyntax(wikiId);
  const history = ctx.capabilities.history;
  const historyQ = usePageHistory(wikiId, path, history);
  const historyUnavailable = !history || classifyWikiError(historyQ.error, "").kind === "historyUnavailable";
  const page = pageQ.data?.value;
  const serverHash = pageQ.data?.version_hash ?? page?.content_hash;
  const titles = useMemo(() => new Map(pages.map((p) => [p.path, p.title ?? ""])), [pages]);
  const titleOf = useCallback((p: string): string | undefined => {
    const t = titles.get(p);
    return t === undefined || t === "" ? undefined : t;
  }, [titles]);
  const links = syntaxQ.data?.syntax?.links;
  const noSyntax = syntaxQ.data !== undefined && (links ?? []).length === 0;
  const insertAvailable = (links ?? []).some((l) => typeof l.insert === "string" && l.insert !== "");

  // ---- 초안·저장 ------------------------------------------------------------------------------
  const [drafts, setDrafts] = useState<Readonly<Record<string, Draft | undefined>>>({});
  const [conflicts, setConflicts] = useState<Readonly<Record<string, true | undefined>>>({});
  const draft = path === null ? undefined : drafts[path];
  const dirty = draft !== undefined;
  const value = draft?.text ?? page?.content ?? "";
  const valueBytes = useMemo(() => new TextEncoder().encode(value).length, [value]);
  const dirtyPaths = useMemo(() => new Set(Object.entries(drafts).filter(([, d]) => d !== undefined).map(([p]) => p)), [drafts]);
  const anyDirty = dirtyPaths.size > 0;
  useEffect(() => {
    reportDirty("page", anyDirty);
    return () => reportDirty("page", false);
  }, [anyDirty, reportDirty]);
  const externalChange = dirty && serverHash !== undefined && draft.baseHash !== undefined && serverHash !== draft.baseHash;
  const conflict = path !== null && (conflicts[path] === true || externalChange);
  const setDraft = (p: string, next: Draft | undefined) => setDrafts((prev) => ({ ...prev, [p]: next }));
  const markWritten = useCallback(
    (paths: readonly string[]) => {
      const at = Date.now();
      for (const p of paths) ownWrites.current.set(ownWriteKey(wikiId, p), at);
    },
    [ownWrites, wikiId],
  );
  const saver = usePageSaver(wikiId, ownWrites, () => void refresh());
  const [reloadedNote, setReloadedNote] = useState(false);
  const [confirm, setConfirm] = useState<"reload" | "overwrite" | "close" | null>(null);

  // 저장 안 됨이 아닐 때 다른 곳에서 바뀌면 자동으로 다시 불러온 것을 3초 알린다(자기 저장은 제외)
  const lastHash = useRef<{ path: string | null; hash: string | undefined }>({ path: null, hash: undefined });
  useEffect(() => {
    const prev = lastHash.current;
    lastHash.current = { path, hash: serverHash };
    if (prev.path !== path || prev.hash === undefined || serverHash === undefined || prev.hash === serverHash || dirty) return;
    const own = path !== null && ownWrites.current.get(ownWriteKey(wikiId, path));
    if (typeof own === "number" && Date.now() - own < WIKI_LIMITS.ownWriteTtlMs) return;
    const on = setTimeout(() => setReloadedNote(true), 0);
    const off = setTimeout(() => setReloadedNote(false), 3000);
    return () => {
      clearTimeout(on);
      clearTimeout(off);
    };
  }, [path, serverHash, dirty, ownWrites, wikiId]);

  const onChange = (text: string) => {
    if (path === null) return;
    if (page !== undefined && text === page.content && !dirty) return;
    setDraft(path, { text, baseHash: draft?.baseHash ?? serverHash });
  };
  const save = async (expected: string | undefined) => {
    if (path === null || page === undefined) return;
    const result = await saver.save(path, value, expected);
    if (result.saved !== null) {
      setDraft(path, undefined);
      setConflicts((c) => ({ ...c, [path]: undefined }));
    } else if (result.failure.kind === "conflict") {
      // 비교에 쓸 서버 본문을 최신으로 읽는다
      setConflicts((c) => ({ ...c, [path]: true }));
      void pageQ.refetch();
    }
  };

  const reload = async () => {
    if (path === null) return;
    setDraft(path, undefined);
    setConflicts((c) => ({ ...c, [path]: undefined }));
    saver.clearFailure();
    await pageQ.refetch();
  };
  const overwrite = async () => {
    const fresh = await pageQ.refetch();
    await save(fresh.data?.version_hash ?? serverHash);
  };
  const copyMine = () => {
    const clip = typeof navigator === "undefined" ? undefined : navigator.clipboard;
    if (clip === undefined) toast({ tone: "danger", text: m.editor.copyFailed });
    else void clip.writeText(value).then(() => toast({ tone: "success", text: m.editor.copyMine }), () => toast({ tone: "danger", text: m.editor.copyFailed }));
  };

  // ---- 저장 전 시험·링크 장식 -------------------------------------------------------------------
  const preview = usePagePreview(wikiId, path, value, editing && page !== undefined && !conflict);
  const [applied, setApplied] = useState<{ key: string; content: string; links: readonly WikiLink[] } | null>(null);
  const fresh = preview.result !== null && preview.result.content === value ? preview.result : null;
  const candidate = !editing || path === null ? null : fresh !== null ? { key: `${path}|p|${fresh.content.length}|${fresh.preview.links?.length ?? 0}|${fresh.preview.page.bytes ?? 0}`, content: fresh.content, links: fresh.preview.links ?? EMPTY } : page !== undefined && value === page.content ? { key: `${path}|s|${page.content_hash}`, content: page.content, links: page.links ?? EMPTY } : null;
  if (candidate !== null && candidate.key !== applied?.key) setApplied(candidate);
  const marks = useMemo(() => (applied === null || !editing ? undefined : linkMarks(applied.content, applied.links)), [applied, editing]);
  const previewLinks = applied?.links ?? null;
  const brokenCount = (previewLinks ?? []).filter((l) => l.broken === true).length;

  // ---- 편집 진입·종료 ---------------------------------------------------------------------------
  const [previewOnly, setPreviewOnly] = useState(false);
  const startEdit = useCallback(
    (next?: PageViewMode) => {
      if (readOnly) return;
      const stored = storage.get(WIKI_STORAGE.pageView);
      const pick: PageViewMode = next ?? (stored === "edit" || stored === "split" ? stored : wide ? "split" : "edit");
      setPreviewOnly(false);
      update({ [P.mode]: pick === "view" ? null : pick }, { replace: true });
    },
    [readOnly, storage, wide, update],
  );
  const closeEdit = () => {
    if (dirty) setConfirm("close");
    else update({ [P.mode]: null }, { replace: true });
  };
  const discardAndClose = () => {
    if (path !== null) setDraft(path, undefined);
    setConflicts((c) => (path === null ? c : { ...c, [path]: undefined }));
    saver.clearFailure();
    update({ [P.mode]: null }, { replace: true });
  };
  const editorMode: EditorViewMode = previewOnly ? "preview" : mode === "split" ? "split" : "edit";
  const changeEditorMode = (next: EditorViewMode) => {
    if (next === "preview") {
      setPreviewOnly(true);
      return;
    }
    setPreviewOnly(false);
    if (next === "split" && !wide) return;
    storage.set(WIKI_STORAGE.pageView, next);
    update({ [P.mode]: next }, { replace: true });
  };

  // ---- 트리·패널 ---------------------------------------------------------------------------------
  const [expanded, setExpandedState] = useState<ReadonlySet<string>>(() => readSet(storage.get(WIKI_STORAGE.tree(wikiId))));
  const setExpanded = (next: ReadonlySet<string>) => {
    setExpandedState(next);
    storage.set(WIKI_STORAGE.tree(wikiId), JSON.stringify([...next]));
  };
  const [titleMode, setTitleModeState] = useState<TreeTitleMode>(() => (storage.get(WIKI_STORAGE.treeTitleMode) === "path" ? "path" : "title"));
  const setTitleMode = (next: TreeTitleMode) => {
    setTitleModeState(next);
    storage.set(WIKI_STORAGE.treeTitleMode, next);
  };
  const [recentShown, setRecentShown] = useState(false);
  const changesQ = useWikiChanges(wikiId, recentShown);
  const changeItems = useMemo(() => (changesQ.data?.pages ?? []).flatMap((p) => p.items ?? []), [changesQ.data]);
  const [panelPick, setPanelPick] = useState<boolean | null>(null);
  const panelOpen = panelPick ?? (!narrow && !editing);
  const [hoverStart, setHoverStart] = useState<number | null>(null);
  const [viewingVersion, setViewingVersion] = useState<number | null>(null);

  // ---- 대화상자 -----------------------------------------------------------------------------------
  const [moveFor, setMoveFor] = useState<string | null>(null);
  const [deleteFor, setDeleteFor] = useState<string | null>(null);
  const [restoreFor, setRestoreFor] = useState<WikiPageVersion | null>(null);
  const [picker, setPicker] = useState(false);
  const deleteTitle = deleteFor === null ? "" : titleOf(deleteFor) ?? lastSegment(deleteFor);
  const deleteBacklinks = deleteFor !== null && deleteFor === path ? page?.backlinks ?? EMPTY : EMPTY;

  const copyPath = (p: string) => {
    void navigator.clipboard?.writeText(p);
    toast({ tone: "success", text: m.copied });
  };

  const restoreVersion = async (p: string, version: number) => {
    const result = await saver.restore(p, version);
    if (result.saved !== null) {
      toast({ tone: "success", text: m.history.restored(version), durationMs: 5000 });
      openPath(p);
      setViewingVersion(null);
      void refresh();
    }
  };
  /** 지운 페이지를 되돌린다: 기록에서 지우기 직전(`delete` 이전)의 가장 최근 버전. */
  const restoreDeleted = async (p: string) => {
    try {
      const h = await space.client.getWikiPageHistory(wikiId, p);
      const items = h.items ?? EMPTY;
      const del = items.findIndex((v) => v.op === "delete");
      const target = items.slice(del < 0 ? 0 : del + 1).find((v) => v.op !== "delete");
      if (target === undefined) throw new Error(m.history.restoreFailed);
      await restoreVersion(p, target.version);
    } catch (e) {
      toast({ tone: "danger", text: e instanceof Error && e.message !== "" ? e.message : m.history.restoreFailed });
    }
  };
  const doDelete = async (p: string) => {
    setDeleteFor(null);
    let lastVersion: number | null = null;
    if (history) {
      try {
        lastVersion = (await space.client.getWikiPageHistory(wikiId, p, 1)).items?.[0]?.version ?? null;
      } catch {
        lastVersion = null;
      }
    }
    try {
      await space.client.deleteWikiPage(wikiId, p, p === path ? serverHash : undefined);
    } catch (e) {
      toast({ tone: "danger", text: e instanceof Error && e.message !== "" ? e.message : m.delete.failed });
      return;
    }
    setDraft(p, undefined);
    const index = pages.findIndex((x) => x.path === p);
    const next = pages[index + 1] ?? pages[index - 1];
    ownWrites.current.set(ownWriteKey(wikiId, p), Date.now());
    qc.removeQueries({ queryKey: wikiKeys.page(space.key, wikiId, p) });
    await refresh();
    if (p === path) update({ [P.path]: next?.path ?? null, [P.mode]: null, [P.line]: null, [P.anchor]: null, [P.version]: null });
    const undo = lastVersion !== null && history && !ctx.recordsUnwritable ? lastVersion : null;
    toast({ tone: "success", text: m.delete.done, durationMs: WIKI_LIMITS.restoreToastMs, ...(undo === null ? {} : { action: { label: m.delete.undo, onClick: () => void restoreVersion(p, undo) } }) });
  };

  // ---- 링크 동작 -----------------------------------------------------------------------------------
  const schemeHref = (link: WikiLink): string | undefined => {
    const t = link.scheme_target;
    if (t === undefined || t === null) return undefined;
    const base = routeServing(DEFAULT_ROUTES, t.role)?.path;
    if (base === undefined || !routeOn(t.role)) return undefined;
    const raw = t.id_from.startsWith("/") ? getAt(link, t.id_from) : (link as unknown as Record<string, unknown>)[t.id_from];
    const id = typeof raw === "string" && raw !== "" ? raw : link.target ?? "";
    if (id === "") return base;
    const q = t.query === undefined || t.query === null || t.query === "" ? "" : `?${t.query.replace(/\{value\}/g, encodeURIComponent(id))}`;
    return `${base}/${encodeURIComponent(id)}${q}`;
  };
  const createFromLink = (link: WikiLink, suggested?: string) => {
    const target = suggested ?? link.suggested_path ?? link.target ?? "";
    openNewPage({ path: target, ...(link.label !== undefined && link.label !== "" ? { title: link.label } : {}) });
  };
  const locateLink = (link: WikiLink) => {
    if (editing) editorRef.current?.goToOffset(link.start);
    else viewRef.current?.scrollToLink(link.start);
  };
  const openRun = ctx.capabilities.runs && runPath("x") !== undefined ? (runId: string, rootRunId: string | null) => void navigate(runPath(rootRunId ?? runId) ?? "/") : undefined;
  const pagePathOf = (p: string, anchor: string | null) => wikiPagePath(wikiId, p, anchor === null ? {} : { [P.anchor]: anchor });

  // ---- 링크 넣기 -------------------------------------------------------------------------------------
  const insertLink = async (target: string) => {
    setPicker(false);
    if (path === null) return;
    try {
      const r = await space.client.getWikiLinkText(wikiId, { from_page: path, target });
      editorRef.current?.insertAtCursor(r.text);
    } catch {
      toast({ tone: "danger", text: m.editor.insertLinkFailed });
    }
  };

  // ---- 단축키 ------------------------------------------------------------------------------------------
  const pathIndex = path === null ? -1 : pages.findIndex((p) => p.path === path);
  const step = (delta: number) => {
    const next = pages[pathIndex + delta];
    if (next !== undefined) openPath(next.path);
  };
  useWikiShortcuts({
    edit: path !== null && page !== undefined && !editing && !readOnly ? () => startEdit() : undefined,
    modeEdit: !readOnly && page !== undefined ? () => startEdit("edit") : undefined,
    modeView: () => (dirty ? setConfirm("close") : update({ [P.mode]: null }, { replace: true })),
    modeSplit: !readOnly && wide && page !== undefined ? () => startEdit("split") : undefined,
    panel: () => setPanelPick(!panelOpen),
    tree: () => treeFilterRef.current?.focus(),
    prevPage: () => step(-1),
    nextPage: () => step(1),
    insertLink: editing && insertAvailable ? () => setPicker(true) : undefined,
  });

  // ---- 띠 -------------------------------------------------------------------------------------------------
  const secretKey = path === null ? "" : WIKI_STORAGE.secretDismissed(wikiId, path);
  const [secretHidden, setSecretHidden] = useState(false);
  const allIssues: readonly Issue[] = useMemo(() => [...(page?.issues ?? EMPTY), ...saver.warnings], [page, saver.warnings]);
  const secretIssues = allIssues.filter((i) => i.code === KNOWN_ISSUE_CODES.WIKI_SECRET_SUSPECT);
  const ruleWarnings = saver.warnings.filter((i) => i.code !== KNOWN_ISSUE_CODES.WIKI_SECRET_SUSPECT);
  const parseIssues = (page?.issues ?? EMPTY).filter((i) => i.code === KNOWN_ISSUE_CODES.WIKI_FRONT_MATTER_INVALID || i.code === KNOWN_ISSUE_CODES.WIKI_PARSE_TIMEOUT);
  const gotoLine = (line: number) => {
    if (!editing) update({ [P.mode]: "edit", [P.line]: String(line) }, { replace: true });
    else editorRef.current?.goToLine(line);
  };
  const bands: BandItem[] = [];
  const f = saver.failure;
  if (f !== null && f.kind !== "conflict") {
    if (f.kind === "ruleRejected") {
      bands.push({
        id: "rule-rejected",
        tone: "danger",
        content: <>{m.band.ruleRejected(f.ruleId, f.message)}{f.lines.length > 0 ? ` ${m.band.lines(linesText(f.lines))}` : ""}</>,
        actions: f.lines.length > 0 ? <Button size="sm" onClick={() => gotoLine(f.lines[0] as number)}>{m.band.gotoLine}</Button> : undefined,
      });
    } else if (f.kind === "secretRejected") {
      bands.push({ id: "secret-rejected", tone: "danger", content: m.band.secretRejected(linesText(f.lines)), actions: f.lines.length > 0 ? <Button size="sm" onClick={() => gotoLine(f.lines[0] as number)}>{m.band.gotoLine}</Button> : undefined });
    } else if (f.kind === "tooLarge") {
      bands.push({ id: "too-large", tone: "danger", content: f.message !== "" ? f.message : m.band.tooLarge(f.limit === null ? "" : (f.limit / 1024).toFixed(0)) });
    } else if (f.kind === "versionNotFound") {
      bands.push({ id: "version-missing", tone: "info", content: f.message !== "" ? f.message : m.band.versionNotFound });
    } else {
      const detail = failureDetail(f);
      if (detail !== undefined) bands.push({ id: "save-failed", tone: "danger", content: detail });
    }
  }
  if (ruleWarnings.length > 0) {
    bands.push({
      id: "rule-warn",
      tone: "warning",
      content: m.band.ruleWarn(ruleWarnings.length),
      rows: ruleWarnings.map((i, n) => ({ key: `${i.code}:${n}`, id: (i as { rule_id?: string | null }).rule_id ?? null, message: i.message })),
      actions: <Button size="sm" onClick={saver.clearWarnings}>{m.band.dismiss}</Button>,
    });
  }
  if (secretIssues.length > 0 && !secretHidden && !secretDismissed(secretKey)) {
    const lines = issueLines(secretIssues);
    bands.push({
      id: "secret-suspect",
      tone: "info",
      content: m.band.secretSuspect(secretIssues.length, linesText(lines)),
      actions: (
        <>
          {lines.length > 0 ? <Button size="sm" onClick={() => gotoLine(lines[0] as number)}>{m.band.gotoLine}</Button> : null}
          <Button size="sm" onClick={() => { dismissSecret(secretKey); setSecretHidden(true); }}>{m.band.dismiss}</Button>
        </>
      ),
    });
  }
  for (const i of parseIssues) {
    const line = (i as { line?: number | null }).line;
    bands.push({
      id: `parse-${i.code}`,
      tone: "warning",
      content: i.code === KNOWN_ISSUE_CODES.WIKI_PARSE_TIMEOUT ? m.band.parseTimeout : m.band.frontMatter(typeof line === "number" ? String(line) : ""),
      actions: typeof line === "number" ? <Button size="sm" onClick={() => gotoLine(line)}>{m.band.gotoLine}</Button> : undefined,
    });
  }
  if (wantedMode !== "view" && readOnly) bands.push({ id: "readonly-edit", tone: "warning", content: m.band.readOnlyEdit });
  if (ctx.recordsUnwritable || !history) bands.push({ id: "records", tone: "info", content: m.records.notWritten });

  // ---- 본문 영역 -------------------------------------------------------------------------------------------
  const pageError = pageQ.isError ? classifyWikiError(pageQ.error, m.page.readFailed) : null;
  const tree = (
    <TreePane
      pages={pages}
      truncated={pagesQ.data?.truncated === true}
      total={pagesQ.data?.total ?? null}
      maxPages={ctx.limits?.max_pages ?? null}
      selectedPath={path}
      dirtyPaths={dirtyPaths}
      expanded={expanded}
      onExpandedChange={setExpanded}
      titleMode={titleMode}
      onTitleModeChange={setTitleMode}
      display={display}
      onSelect={openPath}
      onRename={(p) => (dirtyPaths.has(p) ? toast({ tone: "warning", text: m.move.dirty }) : setMoveFor(p))}
      onDelete={setDeleteFor}
      onNewHere={(folder) => openNewPage({ path: `${folder}/` })}
      onCopyPath={copyPath}
      blockedReason={writeBlock}
      changes={{ items: changeItems, hasMore: changesQ.hasNextPage, loading: changesQ.isPending, failed: changesQ.isError, loadMore: () => void changesQ.fetchNextPage() }}
      recentShown={recentShown}
      onShowRecent={setRecentShown}
      onRestoreDeleted={history && !readOnly && !ctx.recordsUnwritable ? (c: WikiChange) => void restoreDeleted(c.path) : undefined}
      onOpenRun={openRun}
      now={now}
      filterRef={treeFilterRef}
    />
  );

  const versionQ = usePageVersion(wikiId, path, viewingVersion ?? compareVersion);
  const versions = historyQ.data?.items ?? EMPTY;
  const compareIndex = compareVersion === null ? -1 : versions.findIndex((v) => v.version === compareVersion);
  const previousVersion = compareIndex < 0 ? null : versions[compareIndex + 1]?.version ?? null;
  const previousQ = usePageVersion(wikiId, path, previousVersion);
  const [diffBase, setDiffBase] = useState<HistoryDiffBase | undefined>(undefined);

  let center: React.ReactNode;
  if (pagesQ.isPending && path === null) {
    center = <ListSkeleton rows={8} />;
  } else if (path === null) {
    center = pages.length === 0 && !pagesQ.isPending ? (
      <div className="wiki-state" data-testid="wiki-page-empty">
        <h2 className="wiki-state-title">{m.page.emptyTitle}</h2>
        <p className="app-muted">{m.page.emptyBody}</p>
        {home === "" ? <p className="app-muted wiki-hint">{m.page.firstSteps}</p> : null}
      </div>
    ) : (
      <div className="wiki-state" data-testid="wiki-page-none">
        <h2 className="wiki-state-title">{m.page.noneTitle}</h2>
        <p className="app-muted">{m.page.noneBody}</p>
        <RecentPages pages={pages} now={now} display={display} onOpen={openPath} />
      </div>
    );
  } else if (pageQ.isPending) {
    center = <ListSkeleton rows={8} />;
  } else if (pageError !== null && pageError.kind === "pageNotFound") {
    center = (
      <div className="wiki-state" data-testid="wiki-page-missing">
        <ErrorBlock title={m.page.missingTitle(path)}>
          {!readOnly ? <Button size="sm" variant="primary" onClick={() => openNewPage({ path })}>{m.page.createThis}</Button> : null}
          {pageError.hasHistory ? <Button size="sm" onClick={() => update({ [P.side]: "history" })}>{m.page.missingHistory}</Button> : null}
          <Button size="sm" onClick={() => treeFilterRef.current?.focus()}>{m.page.missingTree}</Button>
        </ErrorBlock>
      </div>
    );
  } else if (pageError !== null || page === undefined) {
    center = <ErrorBlock title={m.page.readFailed} message={pageError === null ? undefined : failureDetail(pageError)} onRetry={() => void pageQ.refetch()} retryLabel={m.retry} />;
  } else if (compareVersion !== null) {
    center = (
      <div className="wiki-compare">
        {versionQ.isPending ? <ListSkeleton rows={6} /> : versionQ.isError ? <Bands items={[{ id: "version-missing", tone: "info", content: classifyWikiError(versionQ.error, m.band.versionNotFound).kind === "versionNotFound" ? (versionQ.error as Error).message : m.history.versionBody }]} /> : (
          <HistoryDiff
            version={compareVersion}
            content={versionQ.data?.value ?? ""}
            previousContent={previousVersion === null ? null : previousQ.data?.value ?? null}
            currentContent={value}
            {...(diffBase === undefined ? {} : { base: diffBase, onBaseChange: setDiffBase })}
            onClose={() => update({ [P.version]: null })}
          />
        )}
      </div>
    );
  } else if (viewingVersion !== null) {
    const viewed: WikiPageView = { page: page.page, content: versionQ.data?.value ?? "", content_hash: versionQ.data?.version_hash ?? "", links: [], backlinks: [], issues: [] };
    center = (
      <div className="wiki-version-view">
        <Bands items={[{ id: "viewing", tone: "info", content: m.band.viewingVersion(viewingVersion), actions: <Button size="sm" onClick={() => setViewingVersion(null)}>{m.band.backToCurrent}</Button> }]} />
        {versionQ.isPending ? <ListSkeleton rows={6} /> : versionQ.isError ? <p className="app-field-error" role="alert">{m.history.versionBody}</p> : <PageView page={viewed} display={display} readOnly readOnlyReason={m.band.viewingVersion(viewingVersion)} />}
      </div>
    );
  } else if (editing) {
    center = (
      <div
        className="wiki-edit-wrap"
        onKeyDown={(e) => {
          if (e.key === "Escape" && !e.nativeEvent.isComposing && !e.defaultPrevented) closeEdit();
        }}
      >
        <DocumentEditor
          key={path}
          document={{ id: path, title: page.page.title !== undefined && page.page.title !== "" ? page.page.title : lastSegment(path), file: path }}
          value={value}
          onChange={onChange}
          onSave={() => void save(draft?.baseHash ?? serverHash)}
          dirty={dirty}
          saving={saver.saving}
          readOnly={readOnly}
          {...(ctx.readOnlyReason === undefined ? {} : { readOnlyReason: ctx.readOnlyReason })}
          conflict={path !== null && conflicts[path] === true}
          externalChange={externalChange && conflicts[path] !== true}
          onReload={() => setConfirm("reload")}
          onOverwrite={() => setConfirm("overwrite")}
          onCopyMine={copyMine}
          {...(page === undefined || !dirty ? {} : { compare: { before: page.content, beforeLabel: conflict ? m.editor.server : m.editor.saved2 } })}
          {...(initialLine === undefined ? {} : { initialLine })}
          mode={editorMode}
          onModeChange={changeEditorMode}
          handleRef={editorRef}
          issues={secretIssues}
          {...(typeof ctx.limits?.max_page_bytes === "number" ? { maxBytes: ctx.limits.max_page_bytes } : {})}
          {...(marks === undefined ? {} : { marks })}
          messages={editorMessages}
          banners={<Bands items={bands} />}
          statusBar={
            <EditStatus
              bytes={valueBytes}
              maxBytes={ctx.limits?.max_page_bytes ?? null}
              links={previewLinks === null || noSyntax ? null : previewLinks.length}
              brokenLinks={brokenCount}
              issues={(preview.result?.preview.issues ?? EMPTY).length}
              large={ctx.limits !== undefined && valueBytes > ctx.limits.max_page_bytes / 2}
            />
          }
          toolbarExtra={
            <>
              <span className="wiki-save-state" role="status" data-testid="wiki-save-state">
                {saver.saving ? m.editor.saving : dirty ? m.editor.dirty : reloadedNote ? m.band.reloaded : m.editor.saved}
              </span>
              {preview.available && preview.result !== null ? <RuleChip preview={preview.result.preview} onGoto={gotoLine} /> : null}
              <Button size="sm" aria-disabled={!insertAvailable || undefined} title={insertAvailable ? undefined : m.editor.insertLinkOff} onClick={() => { if (insertAvailable) setPicker(true); }}>{m.editor.insertLink}</Button>
              <Button size="sm" onClick={closeEdit}>{m.editor.close}</Button>
            </>
          }
          previewHooks={{
            transformSource: (text: string) => linkifySource(text, applied !== null && applied.content === text ? applied.links : EMPTY),
            urlTransform: wikiUrlTransform,
            renderLink: (href: string | undefined, children: React.ReactNode) =>
              href?.startsWith(WIKI_LINK_HREF_PREFIX) === true ? <span className="wiki-preview-link">{children}</span> : <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
          }}
        />
      </div>
    );
  } else {
    center = (
      <div className="wiki-view-wrap">
        <PageHeaderBlock page={page} onCopyPath={() => copyPath(page.page.path)} />
        <ViewToolbar
          blockedReason={writeBlock}
          onEdit={() => startEdit()}
          onRename={() => (dirty ? toast({ tone: "warning", text: m.move.dirty }) : setMoveFor(page.page.path))}
          onDelete={() => setDeleteFor(page.page.path)}
          onCopyPath={() => copyPath(page.page.path)}
          onOpenHistory={() => update({ [P.side]: "history" })}
          onReload={() => void pageQ.refetch()}
          panelOpen={panelOpen}
          onTogglePanel={() => setPanelPick(!panelOpen)}
          backlinkCount={(page.backlinks ?? EMPTY).length}
          panelControls="wiki-side-panel"
        />
        <Bands items={bands} />
        {dirty ? <Bands items={[{ id: "draft", tone: "info", content: m.editor.dirty, actions: <Button size="sm" onClick={() => startEdit()}>{m.page.edit}</Button> }]} /> : null}
        <div className="wiki-prose-wrap">
          <PageView
            page={page}
            display={display}
            titleOf={titleOf}
            onOpenPage={(p, anchor) => openPath(p, anchor)}
            hrefOfPage={pagePathOf}
            onCreatePage={createFromLink}
            onOpenScheme={(l) => {
              const href = schemeHref(l);
              if (href !== undefined) void navigate(href);
            }}
            canOpenScheme={(l) => schemeHref(l) !== undefined}
            readOnly={readOnly}
            {...(writeBlock === undefined ? {} : { readOnlyReason: writeBlock })}
            highlightStart={hoverStart}
            anchor={anchorParam}
            onAnchorMissing={(a) => toast({ tone: "info", text: m.page.anchorMissing(a), durationMs: 3000 })}
            handleRef={viewRef}
          />
        </div>
        <span className="ac-sr-only" role="status">{m.page.pageLabel(page.page.title ?? lastSegment(page.page.path))}</span>
      </div>
    );
  }

  const side = (
    <SidePane
      tab={sideTab}
      onTab={(id) => update({ [P.side]: id }, { replace: true })}
      page={page}
      noSyntax={noSyntax}
      onOpenRules={hasTab("rules") ? () => goTab("rules") : undefined}
      display={display}
      titleOf={titleOf}
      onOpenPage={openPath}
      onHoverLink={(l) => setHoverStart(l === null ? null : l.start)}
      onLocateLink={locateLink}
      onOpenLinkTarget={(l) => {
        if (l.resolved !== undefined && l.resolved !== null) openPath(l.resolved, l.anchor ?? null);
        else {
          const href = schemeHref(l);
          if (href !== undefined) void navigate(href);
        }
      }}
      onCreateFromLink={(l) => createFromLink(l)}
      readOnly={readOnly}
      readOnlyReason={writeBlock}
      history={{ data: historyQ.data, unavailable: historyUnavailable, failed: historyQ.isError, loading: historyQ.isPending && history }}
      currentVersion={versions.find((v) => page !== undefined && v.sha256 === page.content_hash)?.version ?? null}
      selectedVersion={viewingVersion ?? compareVersion}
      onSelectVersion={(v) => {
        if (dirty && editing) toast({ tone: "warning", text: m.move.dirty });
        else {
          setViewingVersion(v.version);
          update({ [P.mode]: null, [P.version]: null }, { replace: true });
        }
      }}
      onCompareVersion={(v) => {
        setViewingVersion(null);
        update({ [P.version]: String(v.version) });
      }}
      onRestoreVersion={setRestoreFor}
      onOpenRun={openRun}
      restoreDisabledReason={readOnly ? writeBlock : dirty ? m.move.dirty : ctx.recordsUnwritable ? m.records.notWritten : undefined}
      now={now}
    />
  );

  const restoreAuthor = restoreFor === null ? "" : restoreFor.author.label ?? restoreFor.author.agent_id ?? display.authorKinds?.[restoreFor.author.kind]?.label ?? restoreFor.author.kind;

  return (
    <div className="wiki-page-tab" data-panel={panelOpen ? "open" : "closed"} data-drawer={narrow || undefined} data-editing={editing || undefined} data-testid="wiki-page-tab">
      <aside className="wiki-tree-col" aria-label={m.tree.toggle}>{tree}</aside>
      <section className="wiki-center-col" aria-label={m.tabs["page"]}>{center}</section>
      {panelOpen ? <aside className="wiki-side-col" id="wiki-side-region">{side}</aside> : null}
      {moveFor === null ? null : (
        <MovePageDialog
          wikiId={wikiId}
          from={moveFor}
          open
          onClose={() => setMoveFor(null)}
          blockedReason={dirtyPaths.has(moveFor) ? m.move.dirty : undefined}
          readOnly={readOnly}
          readOnlyReason={writeBlock}
          onWritten={markWritten}
          onOpenPage={(p) => { setMoveFor(null); openPath(p); }}
          onMoved={(to, n) => {
            qc.removeQueries({ queryKey: wikiKeys.page(space.key, wikiId, moveFor) });
            void refresh();
            if (path === moveFor || path === null) openPath(to);
            toast({ tone: "success", text: m.move.done(n) });
          }}
        />
      )}
      <DeletePageDialog
        open={deleteFor !== null}
        title={deleteTitle}
        backlinks={deleteBacklinks}
        recoverable={history && !ctx.recordsUnwritable}
        onConfirm={() => deleteFor !== null && void doDelete(deleteFor)}
        onCancel={() => setDeleteFor(null)}
      />
      <RestoreDialog
        open={restoreFor !== null}
        path={path ?? ""}
        version={restoreFor}
        authorText={restoreAuthor}
        timeText={restoreFor === null ? "" : formatDateTime(restoreFor.at)}
        onConfirm={() => {
          const v = restoreFor;
          setRestoreFor(null);
          if (v !== null && path !== null) void restoreVersion(path, v.version);
        }}
        onCancel={() => setRestoreFor(null)}
      />
      <LinkPicker open={picker} pages={pages} currentPath={path} onPick={(p) => void insertLink(p)} onClose={() => setPicker(false)} />
      <ConfirmDialog
        open={confirm !== null}
        title={confirm === "overwrite" ? m.editor.overwriteTitle : confirm === "close" ? m.editor.discardTitle : m.editor.reloadTitle}
        confirmLabel={confirm === "overwrite" ? m.editor.overwriteOk : confirm === "close" ? m.editor.discardOk : m.editor.reloadOk}
        cancelLabel={confirm === "close" ? m.editor.keepEditing : m.cancel}
        danger
        onConfirm={() => {
          const which = confirm;
          setConfirm(null);
          if (which === "overwrite") void overwrite();
          else if (which === "reload") void reload();
          else if (which === "close") discardAndClose();
        }}
        onCancel={() => setConfirm(null)}
      >
        {confirm === "overwrite" ? m.editor.overwriteBody : confirm === "close" ? m.editor.discardBody : m.editor.reloadBody}
      </ConfirmDialog>
    </div>
  );
}

function RecentPages({ pages, now, display, onOpen }: { pages: readonly { path: string; title?: string; updated_at?: number | null }[]; now: number; display: unknown; onOpen: (path: string) => void }) {
  void display;
  const recent = [...pages].filter((p) => typeof p.updated_at === "number").sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0)).slice(0, WIKI_LIMITS.recentPages);
  if (recent.length === 0) return null;
  return (
    <div className="wiki-recent-pages">
      <strong>{m.page.noneRecent}</strong>
      <ul>
        {recent.map((p) => (
          <li key={p.path}>
            <button type="button" className="app-link-btn" onClick={() => onOpen(p.path)}>{p.title !== undefined && p.title !== "" ? p.title : lastSegment(p.path)}</button>{" "}
            <span className="app-muted">{formatRelative(p.updated_at, now)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
