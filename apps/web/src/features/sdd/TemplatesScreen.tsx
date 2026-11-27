/**
 * 공용 구성 › 문서 틀 화면(`/spec-templates`, screen-sdd §11): 왼쪽 목록(검색·행 보조 버튼) + 오른쪽 편집기(`TemplateEditor`).
 * 공간은 주소의 `?prj=`가 정한다: 없으면 공용(또는 단독 루트), 있으면 그 프로젝트의 사본(`SpaceScope`). 선택·탭·섹션은 주소가 진실이다.
 * 틀 이름·문서 이름은 서버 데이터이고, 정의 종류 이름은 코드에 없다(틀 원문의 `kind`에서 읽는다).
 */
import "@agent-console/sdd-view/styles.css";
import { useCallback, useMemo, useState } from "react";
import { useBlocker, useSearchParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, ConfirmDialog, EmptyState, Icon, PageHeader, useToast } from "@agent-console/ui";
import type { SpecTemplateCreateRequest, SpecTemplateSummary } from "@agent-console/contracts/sdd";
import { useReportUnsaved } from "../../definition/unsaved";
import { usePageTitle } from "../../shell/titles";
import { SpaceChip, SpaceNote, SpaceScope, useConfigTransfer } from "../projects";
import { NewTemplateDialog } from "./NewTemplateDialog";
import { FailureBlock, GuardedButton, ListSkeleton, SearchBox } from "./parts";
import { TEMPLATE_PARAMS } from "./templateConfig";
import { TemplateEditor } from "./TemplateEditor";
import { useTemplateKind, useTemplateSpace } from "./useTemplateApi";
import { sddKeys, useInvalidateSdd } from "./useSddApi";
import "./sdd.css";
import "./templates.css";
import { useT } from "@agent-console/i18n";
import { useCollator } from "../../i18n";
import { SddToast } from "./SddToast";

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
  const collator = useCollator();
  const t = useT("sdd");
  usePageTitle(t("templates.title"));
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
  const items = useMemo(() => [...(list.data ?? [])].sort((a, b) => collator.compare(nameOf(a), nameOf(b))), [list.data, collator]);
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
    toast({ tone: "success", text: <SddToast render={(t) => t("template.toast.created", { name: made.value.name || made.value.id })} /> });
    apply(made.value.id);
  };

  let body;
  if (space.infoQuery.isPending || (templatesOn && list.isPending)) body = <ListSkeleton />;
  else if (space.infoQuery.isError) body = <FailureBlock error={space.infoQuery.error} title={t("templates.loadFailed")} onRetry={() => void space.infoQuery.refetch()} />;
  else if (!templatesOn) body = <div className="sdd-state" data-testid="sdd-templates-off"><EmptyState title={t("templates.off.title")} description={t("templates.off.body")} /></div>;
  else if (list.isError) body = <FailureBlock error={list.error} title={t("templates.loadFailed")} onRetry={() => void list.refetch()} />;
  else if (items.length === 0) {
    body = (
      // 목록 패널은 그대로 두고(항목 0개) 오른쪽 상세 자리에 빈 상태를 보인다: 문서 틀이 생기면 같은 틀로 이어진다
      <div className="sdd-templates">
        <div className="sdd-templates-list">
          <p className="app-muted sdd-templates-count" role="status">{t("template.list.count", { count: 0 })}</p>
        </div>
        <div className="sdd-templates-detail">
          <div className="sdd-state" data-testid="sdd-templates-empty">
            <EmptyState icon={<Icon name="spec" size={40} />} title={t("template.empty.title")} description={`${t("template.empty.body")} ${t("template.empty.hint")}`} />
          </div>
        </div>
      </div>
    );
  } else {
    body = (
      <div className="sdd-templates">
        <div className="sdd-templates-list">
          <SearchBox value={q} onCommit={setQ} label={t("templates.searchLabel")} />
          <ul aria-label={t("templates.title")}>
            {shown.map((x) => {
              const action = transfer.menuItem(x);
              return (
                <li key={x.id} className="sdd-template-item">
                  <button type="button" className="sdd-template-row" aria-current={x.id === picked ? "true" : undefined} onClick={() => select(x.id)}>
                    <span className="ac-ellipsis"><strong>{nameOf(x)}</strong></span>
                    <span className="app-muted">{t("templates.meta", { docs: (x.documents ?? []).length, profiles: (x.run_profiles ?? []).length })}</span>
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
          {selected === undefined ? <p className="app-muted">{t("template.picked")}</p> : (
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
                toast({ tone: "success", text: <SddToast render={(t) => t("template.toast.deleted", { name })} /> });
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
        title={t("templates.title")}
        status={<SpaceChip />}
        actions={templatesOn ? <GuardedButton variant="primary" blockedReason={writeBlock} onClick={() => setCreating(true)}>{t("template.newTemplate")}</GuardedButton> : undefined}
      />
      <SpaceNote />
      <div className="sdd-screen-body">{body}</div>
      {creating ? <NewTemplateDialog open reservedIds={space.info?.reserved_template_ids} onClose={() => setCreating(false)} onSubmit={create} /> : null}
      {transfer.dialog}
      <ConfirmDialog open={blocker.state === "blocked"} title={t("leave.title")} confirmLabel={t("leave.leave")} cancelLabel={t("leave.stay")} danger onConfirm={() => blocker.state === "blocked" && blocker.proceed()} onCancel={() => blocker.state === "blocked" && blocker.reset()}>{t("leave.body")}</ConfirmDialog>
      <ConfirmDialog
        open={pending !== undefined}
        title={t("leave.title")}
        confirmLabel={t("leave.leave")}
        cancelLabel={t("leave.stay")}
        danger
        onConfirm={() => {
          const id = pending;
          setPending(undefined);
          setDirty(false);
          if (id !== undefined) apply(id);
        }}
        onCancel={() => setPending(undefined)}
      >
        {t("leave.body")}
      </ConfirmDialog>
    </div>
  );
}
