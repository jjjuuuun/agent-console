/**
 * 스펙 목록 화면(`/specs`, screen-sdd §3): 현재 프로젝트의 스펙을 진행·지금 단계·문서 상태·준비 수로 보고, 새 스펙을 만들거나 폴더의 문서를 가져온다.
 * 데이터는 `useSddApi`, 목록 그림은 `@agent-console/sdd-view`의 `SpecList`가 맡고 이 파일은 그것들을 잇는 얇은 조립이다.
 * 문서 상태·스펙 이름은 서버 데이터(라벨)다.
 */
import "@agent-console/sdd-view/styles.css";
import { useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { ConfirmDialog, PageHeader, Switch, useToast } from "@agent-console/ui";
import { SpecList, type SpecSortState } from "@agent-console/sdd-view";
import type { SpecSummary } from "@agent-console/contracts/sdd";
import { useStorage } from "../../app/StorageContext";
import { usePageTitle } from "../../shell/titles";
import { formatRelative } from "../../lib/format";
import { useNow } from "../../app/useNow";
import { routePath } from "../library";
import { ProjectChip } from "../projects";
import { NewSpecDialog } from "./NewSpecDialog";
import { FailureBlock, GuardedButton, ListSkeleton, MenuButton, SearchBox } from "./parts";
import { SDD_PARAMS, SDD_ROLE, SDD_STORAGE, SPEC_SORT } from "./sddConfig";
import { SpecExportDialog } from "./SpecExportDialog";
import { SpecImportDialog } from "./SpecImportDialog";
import { SpecRenameDialog } from "./SpecRenameDialog";
import { describeError } from "../../app/errors";
import { sddMessages as m, viewMessages } from "./messages";
import { useInvalidateSdd, useSddLive, useSddSpace, useSpecList, useSpecTemplates } from "./useSddApi";
import { useSddContext } from "./useSddContext";
import { useLibraryTemplateImport } from "./useLibraryTemplateImport";
import { specTemplatesPath } from "./sddPaths";
import "./sdd.css";

type Dlg =
  | { kind: "new"; name: string }
  | { kind: "import"; name: string }
  | { kind: "export" | "rename" | "delete"; spec: SpecSummary }
  | null;

/** 정렬 열 id → 비교 함수. 열 목록·기본 정렬·문구는 `SPEC_SORT` 데이터이고, 새 열은 여기에 비교 함수 하나를 더한다. */
export const SPEC_COMPARATORS: Readonly<Record<string, (a: SpecSummary, b: SpecSummary) => number>> = {
  name: (a, b) => (a.name && a.name !== "" ? a.name : a.id).localeCompare(b.name && b.name !== "" ? b.name : b.id),
  updated: (a, b) => (a.updated_at ?? 0) - (b.updated_at ?? 0),
};

/** 주소 인자 값(`열:방향`)을 정렬 상태로. 모르는 열·방향이면 기본 정렬. */
export function parseSort(raw: string | null): SpecSortState {
  const [id, dir] = (raw ?? "").split(":");
  const known = SPEC_SORT.columns.some((c) => c.id === id) && id !== undefined && SPEC_COMPARATORS[id] !== undefined;
  return known && (dir === "asc" || dir === "desc") ? { id: id as string, direction: dir } : { ...SPEC_SORT.default };
}

/** 목록 거르기·정렬(순수): 이름·id 부분 일치, 문서 상태(하나라도 가진 스펙), 준비된 작업 있음. 정렬은 열 머리(`SPEC_SORT`), 기본은 갱신 시각 내림차순. */
export function filterSpecs(specs: readonly SpecSummary[], q: string, states: ReadonlySet<string>, readyOnly: boolean, sort: SpecSortState = SPEC_SORT.default): SpecSummary[] {
  const needle = q.trim().toLowerCase();
  const compare = SPEC_COMPARATORS[sort.id] ?? SPEC_COMPARATORS[SPEC_SORT.default.id] ?? (() => 0);
  const sign = sort.direction === "asc" ? 1 : -1;
  return specs
    .filter((s) => needle === "" || `${s.name ?? ""} ${s.id}`.toLowerCase().includes(needle))
    .filter((s) => states.size === 0 || (s.documents ?? []).some((d) => d.state !== undefined && d.state !== null && states.has(d.state)))
    .filter((s) => !readyOnly || (s.ready ?? 0) > 0)
    .sort((a, b) => sign * compare(a, b));
}

export function SpecListScreen() {
  usePageTitle(m.title);
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const toast = useToast();
  const storage = useStorage();
  const space = useSddSpace();
  const ctx = useSddContext();
  const list = useSpecList();
  const invalidate = useInvalidateSdd();
  const ownHashes = useRef(new Set<string>());
  useSddLive(ownHashes);
  const now = useNow(true, 60_000);
  const [dialog, setDialog] = useState<Dlg>(null);
  const [q, setQ] = useState("");
  const [states, setStates] = useState<ReadonlySet<string>>(new Set());
  const [readyOnly, setReadyOnly] = useState(false);
  const templates = useSpecTemplates(dialog?.kind === "new");
  const libraryImport = useLibraryTemplateImport(dialog?.kind === "new");
  const specs = useMemo(() => list.data ?? [], [list.data]);
  const stateOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const s of specs) for (const d of s.documents ?? []) if (d.state !== undefined && d.state !== null && !seen.has(d.state)) seen.set(d.state, d.state_label ?? d.state);
    return [...seen.entries()].map(([id, label]) => ({ id, label }));
  }, [specs]);
  const sortRaw = search.get(SDD_PARAMS.sort);
  const sort = useMemo(() => parseSort(sortRaw), [sortRaw]);
  const shown = useMemo(() => filterSpecs(specs, q, states, readyOnly, sort), [specs, q, states, readyOnly, sort]);
  const sortColumns = useMemo(() => SPEC_SORT.columns.map((c) => ({ id: c.id, label: m.list.sortColumns[c.labelKey] ?? c.id })), []);
  /** 같은 열을 다시 누르면 방향을 뒤집고, 다른 열이면 그 열의 처음 방향. 기본 정렬과 같아지면 주소에서 뺀다 */
  const changeSort = (columnId: string) => {
    const col = SPEC_SORT.columns.find((c) => c.id === columnId);
    if (col === undefined) return;
    const direction = sort.id === columnId ? (sort.direction === "asc" ? "desc" : "asc") : col.firstDirection;
    setSearch(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (columnId === SPEC_SORT.default.id && direction === SPEC_SORT.default.direction) next.delete(SDD_PARAMS.sort);
        else next.set(SDD_PARAMS.sort, `${columnId}:${direction}`);
        return next;
      },
      { replace: true },
    );
  };
  const base = routePath(SDD_ROLE);
  const open = (spec: SpecSummary) => void navigate(`${base}/${encodeURIComponent(spec.id)}`);
  const templatesHref = ctx.capabilities.templates ? specTemplatesPath() : undefined;
  const failed = list.isError ? list.error : null;
  const filtering = q.trim() !== "" || states.size > 0 || readyOnly;
  const writeBlock = ctx.readOnly ? ctx.readOnlyReason : undefined;

  const copyPath = (spec: SpecSummary) => {
    void navigator.clipboard?.writeText(spec.directory ?? "");
    toast({ tone: "success", text: m.head.copied });
  };
  const rowMenu = (spec: SpecSummary) => {
    const name = spec.name && spec.name !== "" ? spec.name : spec.id;
    return (
      <MenuButton
        label={<><span aria-hidden="true">⋯</span><span className="ac-sr-only">{m.list.rowMenu(name)}</span></>}
        panelLabel={m.list.actions}
        items={[
          { id: "open", label: m.list.open, onSelect: () => open(spec) },
          ...(ctx.capabilities.import_export ? [{ id: "export", label: m.list.export, disabled: writeBlock !== undefined, onSelect: () => setDialog({ kind: "export", spec }) }] : []),
          { id: "rename", label: m.head.rename, disabled: writeBlock !== undefined, onSelect: () => setDialog({ kind: "rename", spec }) },
          { id: "copy", label: m.list.copyPath, disabled: (spec.directory ?? "") === "", onSelect: () => copyPath(spec) },
          { id: "delete", label: m.list.delete, danger: true, disabled: writeBlock !== undefined, onSelect: () => setDialog({ kind: "delete", spec }) },
        ]}
      />
    );
  };
  /** 이름 바꾸기·삭제는 최신 버전 표시(`version_hash`)가 필요해 그때 읽는다(목록 응답에는 없다) */
  const renameSpec = async (spec: SpecSummary, name: string) => {
    const current = await space.client.getSpec(spec.id);
    const saved = await space.client.putSpec(spec.id, { ...current.value.spec, name }, current.version_hash ?? current.value.version_hash ?? "");
    if (saved.version_hash !== undefined) ownHashes.current.add(saved.version_hash);
    setDialog(null);
    await invalidate();
  };
  const deleteSpec = async (spec: SpecSummary) => {
    try {
      const current = await space.client.getSpec(spec.id);
      await space.client.deleteSpec(spec.id, current.version_hash ?? current.value.version_hash ?? "");
      setDialog(null);
      await invalidate();
    } catch (e) {
      setDialog(null);
      toast({ tone: "danger", text: describeError(e, m.problem.generic).message });
    }
  };

  const goTo = (id: string) => {
    void invalidate();
    void navigate(`${base}/${encodeURIComponent(id)}`);
  };

  return (
    <div className="app-screen-frame sdd-screen">
      <PageHeader
        title={m.title}
        actions={
          failed !== null ? undefined : (
            <>
              <ProjectChip />
              <GuardedButton blockedReason={writeBlock} onClick={() => setDialog({ kind: "import", name: "" })}>{m.list.import}</GuardedButton>
              <GuardedButton variant="primary" blockedReason={writeBlock} onClick={() => setDialog({ kind: "new", name: "" })}>{m.list.new}</GuardedButton>
            </>
          )
        }
      />
      {ctx.readOnly && failed === null ? (
        <div className="sdd-banner-row">
          <div className="sdd-readonly-note" role="status" data-testid="sdd-readonly">
            <strong>{m.readonly.title}</strong> <span>{m.readonly.body}</span>
          </div>
        </div>
      ) : null}
      <div className="sdd-screen-body">
        {failed !== null ? (
          <FailureBlock error={failed} title={m.list.loadFailed} onRetry={() => void list.refetch()} />
        ) : list.isPending ? (
          <ListSkeleton />
        ) : (
          <>
            <div className="sdd-toolbar" role="group" aria-label={m.list.search}>
              <SearchBox value={q} onCommit={setQ} label={m.list.search} />
              {stateOptions.length === 0 ? null : (
                <label className="sdd-filter">
                  <span className="app-muted">{m.list.docState}</span>
                  <select
                    className="sdd-input"
                    value={[...states][0] ?? ""}
                    onChange={(e) => setStates(e.target.value === "" ? new Set() : new Set([e.target.value]))}
                  >
                    <option value="">{m.list.docStateAll}</option>
                    {stateOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </select>
                </label>
              )}
              <Switch checked={readyOnly} onChange={setReadyOnly} label={m.list.readyOnly} onText={m.on} offText={m.off} />
              <span className="sdd-spacer" />
              <span className="app-muted" role="status">{m.list.count(shown.length)}</span>
            </div>
            {specs.length > 0 && shown.length === 0 && filtering ? (
              <div className="sdd-state">
                <p role="status">{m.list.noResult(q.trim())}</p>
                <button type="button" className="app-link-btn" onClick={() => { setQ(""); setStates(new Set()); setReadyOnly(false); }}>{m.list.clearSearch}</button>
              </div>
            ) : (
              <SpecList
                specs={shown}
                onOpen={open}
                sortColumns={sortColumns}
                sort={sort}
                onSortChange={changeSort}
                renderRowMenu={rowMenu}
                formatTime={(t) => formatRelative(t, now)}
                messages={viewMessages}
                emptyActions={<button type="button" className="app-link-btn" onClick={() => setDialog({ kind: "import", name: "" })}>{m.list.import}</button>}
              />
            )}
          </>
        )}
      </div>
      {dialog?.kind === "new" ? (
        <NewSpecDialog
          open
          onClose={() => setDialog(null)}
          folder={ctx.projectName === undefined ? undefined : { name: ctx.projectName, path: ctx.specRoot ?? "" }}
          specRoot={ctx.specRoot}
          templates={templates.data ?? []}
          templatesLoading={templates.isPending}
          initialTemplate={storage.get(SDD_STORAGE.lastTemplate(ctx.projectId))}
          initialName={dialog.name}
          templatesHref={templatesHref}
          blockedReason={writeBlock}
          onTemplateChosen={(id) => (id === null ? storage.remove(SDD_STORAGE.lastTemplate(ctx.projectId)) : storage.set(SDD_STORAGE.lastTemplate(ctx.projectId), id))}
          onImport={(name) => setDialog({ kind: "import", name })}
          onImportFromLibrary={libraryImport.available ? libraryImport.open : undefined}
          onSubmit={async (body) => {
            const created = await space.client.createSpec(body);
            setDialog(null);
            goTo(created.value.spec.id);
          }}
        />
      ) : null}
      {libraryImport.dialog}
      {dialog?.kind === "export" ? (
        <SpecExportDialog open onClose={() => setDialog(null)} blockedReason={writeBlock} loadDirs={(path) => space.client.listImportFiles(path)} onSubmit={(body) => space.client.exportSpec(dialog.spec.id, body)} />
      ) : null}
      {dialog?.kind === "rename" ? (
        <SpecRenameDialog open initialName={dialog.spec.name ?? ""} onClose={() => setDialog(null)} onSubmit={(name) => renameSpec(dialog.spec, name)} />
      ) : null}
      {dialog?.kind === "delete" ? (
        <ConfirmDialog open title={m.delete.title(dialog.spec.name && dialog.spec.name !== "" ? dialog.spec.name : dialog.spec.id)} confirmLabel={m.delete.confirm} cancelLabel={m.cancel} danger onConfirm={() => void deleteSpec(dialog.spec)} onCancel={() => setDialog(null)}>
          {m.delete.body(dialog.spec.directory ?? "")}
        </ConfirmDialog>
      ) : null}
      {dialog?.kind === "import" ? (
        <SpecImportDialog
          open
          onClose={() => setDialog(null)}
          initialName={dialog.name}
          blockedReason={writeBlock}
          loadFiles={(path) => space.client.listImportFiles(path)}
          onSubmit={async (body) => {
            const created = await space.client.importSpec(body);
            setDialog(null);
            toast({ tone: "success", text: m.import.done(body.files.length) });
            goTo(created.value.spec.id);
          }}
        />
      ) : null}
    </div>
  );
}
