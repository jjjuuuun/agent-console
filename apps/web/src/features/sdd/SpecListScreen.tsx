/**
 * 스펙 목록 화면(`/specs`, screen-sdd §3): 현재 프로젝트의 스펙을 진행·지금 단계·문서 상태·준비 수로 보고, 새 스펙을 만들거나 폴더의 문서를 가져온다.
 * 데이터는 `useSddApi`, 목록 그림은 `@agent-console/sdd-view`의 `SpecList`가 맡고 이 파일은 그것들을 잇는 얇은 조립이다.
 * 문서 상태·스펙 이름은 서버 데이터(라벨)다.
 */
import "@agent-console/sdd-view/styles.css";
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { PageHeader, Switch, useToast } from "@agent-console/ui";
import { SpecList } from "@agent-console/sdd-view";
import type { SpecSummary } from "@agent-console/contracts/sdd";
import { useStorage } from "../../app/StorageContext";
import { usePageTitle } from "../../shell/titles";
import { formatRelative } from "../../lib/format";
import { useNow } from "../../app/useNow";
import { routePath } from "../library";
import { ProjectChip } from "../projects";
import { NewSpecDialog } from "./NewSpecDialog";
import { FailureBlock, GuardedButton, ListSkeleton, SearchBox } from "./parts";
import { SDD_ROLE, SDD_STORAGE } from "./sddConfig";
import { SpecImportDialog } from "./SpecImportDialog";
import { sddMessages as m, viewMessages } from "./messages";
import { useInvalidateSdd, useSddLive, useSddSpace, useSpecList, useSpecTemplates } from "./useSddApi";
import { useSddContext } from "./useSddContext";
import { specTemplatesPath } from "./sddPaths";
import "./sdd.css";

type Dlg = { kind: "new"; name: string } | { kind: "import"; name: string } | null;

/** 목록 거르기·정렬(순수): 이름·id 부분 일치, 문서 상태(하나라도 가진 스펙), 준비된 작업 있음. 기본 정렬은 갱신 시각 내림차순. */
export function filterSpecs(specs: readonly SpecSummary[], q: string, states: ReadonlySet<string>, readyOnly: boolean): SpecSummary[] {
  const needle = q.trim().toLowerCase();
  return specs
    .filter((s) => needle === "" || `${s.name ?? ""} ${s.id}`.toLowerCase().includes(needle))
    .filter((s) => states.size === 0 || (s.documents ?? []).some((d) => d.state !== undefined && d.state !== null && states.has(d.state)))
    .filter((s) => !readyOnly || (s.ready ?? 0) > 0)
    .sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0));
}

export function SpecListScreen() {
  usePageTitle(m.title);
  const navigate = useNavigate();
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
  const specs = useMemo(() => list.data ?? [], [list.data]);
  const stateOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const s of specs) for (const d of s.documents ?? []) if (d.state !== undefined && d.state !== null && !seen.has(d.state)) seen.set(d.state, d.state_label ?? d.state);
    return [...seen.entries()].map(([id, label]) => ({ id, label }));
  }, [specs]);
  const shown = useMemo(() => filterSpecs(specs, q, states, readyOnly), [specs, q, states, readyOnly]);
  const base = routePath(SDD_ROLE);
  const open = (spec: SpecSummary) => void navigate(`${base}/${encodeURIComponent(spec.id)}`);
  const templatesHref = ctx.capabilities.templates ? specTemplatesPath() : undefined;
  const failed = list.isError ? list.error : null;
  const filtering = q.trim() !== "" || states.size > 0 || readyOnly;
  const writeBlock = ctx.readOnly ? ctx.readOnlyReason : undefined;

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
          onSubmit={async (body) => {
            const created = await space.client.createSpec(body);
            setDialog(null);
            goTo(created.value.spec.id);
          }}
        />
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
