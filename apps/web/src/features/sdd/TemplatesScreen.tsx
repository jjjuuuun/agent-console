/**
 * 공용 구성 › 문서 틀 화면(`/spec-templates`, screen-sdd §11): 왼쪽 목록(검색·행 보조 버튼) + 오른쪽 편집기(`TemplateEditor`).
 * 공간은 주소의 `?prj=`가 정한다: 없으면 공용(또는 단독 루트), 있으면 그 프로젝트의 사본(`SpaceScope`). 선택·탭·섹션은 주소가 진실이다.
 * 틀 이름·문서 이름은 서버 데이터이고, 정의 종류 이름은 코드에 없다(틀 원문의 `kind`에서 읽는다).
 */
import "@agent-console/sdd-view/styles.css";
import { useCallback, useMemo, useState } from "react";
import { useBlocker, useSearchParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, ConfirmDialog, EmptyState, PageHeader, useToast } from "@agent-console/ui";
import type { SpecTemplateCreateRequest, SpecTemplateSummary } from "@agent-console/contracts/sdd";
import { useReportUnsaved } from "../../definition/unsaved";
import { usePageTitle } from "../../shell/titles";
import { SpaceChip, SpaceNote, SpaceScope, useConfigTransfer } from "../projects";
import { NewTemplateDialog } from "./NewTemplateDialog";
import { FailureBlock, GuardedButton, ListSkeleton, SearchBox } from "./parts";
import { TEMPLATE_PARAMS } from "./templateConfig";
import { TemplateEditor } from "./TemplateEditor";
import { templateMessages as t } from "./templateMessages";
import { useTemplateKind, useTemplateSpace } from "./useTemplateApi";
import { sddKeys, useInvalidateSdd } from "./useSddApi";
import { sddMessages as m } from "./messages";
import "./sdd.css";
import "./templates.css";

const P = TEMPLATE_PARAMS;
const nameOf = (x: SpecTemplateSummary) => (x.name !== undefined && x.name !== "" ? x.name : x.id);
const idOf = (x: SpecTemplateSummary) => x.id;

export function TemplatesScreen() {
  return (
    <SpaceScope>
      <TemplatesBody />
    </SpaceScope>
  );
}

function TemplatesBody() {
  usePageTitle(m.templates.title);
  const space = useTemplateSpace();
  const toast = useToast();
  const qc = useQueryClient();
  const invalidate = useInvalidateSdd();
  const [params, setParams] = useSearchParams();
  const templatesOn = space.info?.capabilities?.templates === true;
  const list = useQuery({ queryKey: sddKeys.templates(space.key), queryFn: () => space.client.listSpecTemplates(), retry: false, enabled: templatesOn });
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<string | null | undefined>(undefined);
  const items = useMemo(() => [...(list.data ?? [])].sort((a, b) => nameOf(a).localeCompare(nameOf(b), "ko")), [list.data]);
  const kind = useTemplateKind(space.client, space.key, items[0]?.id, items.length > 0);
  const transfer = useConfigTransfer(items, { kind, idOf, nameOf });
  const shown = q.trim() === "" ? items : items.filter((x) => `${nameOf(x)} ${x.id}`.toLowerCase().includes(q.trim().toLowerCase()));
  const picked = params.get(P.template);
  const selected = items.find((x) => x.id === picked);
  const writeBlock = space.readOnly ? space.readOnlyReason : undefined;

  useReportUnsaved(dirty);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);

  const apply = useCallback(
    (id: string | null) => {
      const next = new URLSearchParams(params);
      next.delete(P.tab);
      next.delete(P.section);
      next.delete(P.file);
      if (id === null) next.delete(P.template);
      else next.set(P.template, id);
      setParams(next);
    },
    [params, setParams],
  );
  const select = (id: string) => {
    if (id === picked) return;
    if (dirty) setPending(id);
    else apply(id);
  };
  const onDirtyChange = useCallback((next: boolean) => setDirty(next), []);

  const create = async (body: SpecTemplateCreateRequest) => {
    const made = await space.client.createSpecTemplate(body);
    setCreating(false);
    await invalidate();
    toast({ tone: "success", text: t.toast.created(made.value.name || made.value.id) });
    apply(made.value.id);
  };

  let body;
  if (space.infoQuery.isPending || (templatesOn && list.isPending)) body = <ListSkeleton />;
  else if (space.infoQuery.isError) body = <FailureBlock error={space.infoQuery.error} title={m.templates.loadFailed} onRetry={() => void space.infoQuery.refetch()} />;
  else if (!templatesOn) body = <div className="sdd-state" data-testid="sdd-templates-off"><EmptyState title={m.templates.off.title} description={m.templates.off.body} /></div>;
  else if (list.isError) body = <FailureBlock error={list.error} title={m.templates.loadFailed} onRetry={() => void list.refetch()} />;
  else if (items.length === 0) {
    body = (
      <div className="sdd-state" data-testid="sdd-templates-empty">
        <EmptyState title={t.empty.title} description={`${t.empty.body} ${t.empty.hint}`} />
      </div>
    );
  } else {
    body = (
      <div className="sdd-templates">
        <div className="sdd-templates-list">
          <SearchBox value={q} onCommit={setQ} label={m.templates.searchLabel} />
          <ul aria-label={m.templates.title}>
            {shown.map((x) => {
              const action = transfer.menuItem(x);
              return (
                <li key={x.id} className="sdd-template-item">
                  <button type="button" className="sdd-template-row" aria-current={x.id === picked ? "true" : undefined} onClick={() => select(x.id)}>
                    <span className="ac-ellipsis"><strong>{nameOf(x)}</strong></span>
                    <span className="app-muted">{m.templates.meta((x.documents ?? []).length, (x.run_profiles ?? []).length)}</span>
                  </button>
                  {action === null ? null : (
                    <Button size="sm" aria-disabled={action.disabled === true || undefined} title={action.title} aria-label={`${action.label}: ${nameOf(x)}`} onClick={() => { if (action.disabled !== true) action.onSelect(); }}>
                      {action.label}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
        <div className="sdd-templates-detail">
          {selected === undefined ? <p className="app-muted">{t.picked}</p> : (
            <TemplateEditor
              key={`${space.key}:${selected.id}`}
              space={space}
              id={selected.id}
              params={params}
              setParams={(next, options) => setParams(next, { replace: options?.replace === true })}
              onDirtyChange={onDirtyChange}
              onDeleted={(name) => {
                qc.removeQueries({ queryKey: ["sdd", space.key, "template", selected.id] });
                void invalidate();
                toast({ tone: "success", text: t.toast.deleted(name) });
                setDirty(false);
                apply(null);
              }}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="app-screen-frame sdd-screen">
      <PageHeader
        title={m.templates.title}
        status={<SpaceChip />}
        actions={templatesOn ? <GuardedButton variant="primary" blockedReason={writeBlock} onClick={() => setCreating(true)}>{t.newTemplate}</GuardedButton> : undefined}
      />
      <SpaceNote />
      <div className="sdd-screen-body">{body}</div>
      {creating ? <NewTemplateDialog open onClose={() => setCreating(false)} onSubmit={create} /> : null}
      {transfer.dialog}
      <ConfirmDialog open={blocker.state === "blocked"} title={m.leave.title} confirmLabel={m.leave.leave} cancelLabel={m.leave.stay} danger onConfirm={() => blocker.state === "blocked" && blocker.proceed()} onCancel={() => blocker.state === "blocked" && blocker.reset()}>{m.leave.body}</ConfirmDialog>
      <ConfirmDialog
        open={pending !== undefined}
        title={m.leave.title}
        confirmLabel={m.leave.leave}
        cancelLabel={m.leave.stay}
        danger
        onConfirm={() => {
          const id = pending;
          setPending(undefined);
          setDirty(false);
          if (id !== undefined) apply(id);
        }}
        onCancel={() => setPending(undefined)}
      >
        {m.leave.body}
      </ConfirmDialog>
    </div>
  );
}
