import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import type { Agent } from "@agent-console/contracts";
import { Banner, Button, Dialog, Tabs, useShortcuts, useToast } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { ErrorBlock, errorDetails } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { messages as m } from "../../app/messages";
import { useApiQuery } from "../../app/queries";
import { ConflictBanner } from "../../definition/ConflictBanner";
import { SaveStatus } from "../../definition/SaveStatus";
import { UnsavedGuard } from "../../definition/unsaved";
import { useDefinitionEditor } from "../../definition/useDefinitionEditor";
import { usePageTitle } from "../../shell/titles";
import { Skeleton } from "../settings";
import { ActionMenu, useAgentList, useInvalidateLists, DeleteDialog, DEFINITION_KINDS, definitionKey, NewDefinitionDialog, libraryMessages as lm, type DetailRequest } from "../library";
import { useExportAction, exportMessages } from "../exports";
import { DefinitionVersionsTab, versionMessages } from "../versions";
import { AgentActivityTab, AgentResourcesTab, AgentUsagesTab } from "./AgentTabs";
import { AgentEditorForm } from "./AgentEditorForm";
import { loadAgent, saveAgent } from "./agentLogic";
import { NAME_INPUT_SELECTOR } from "./ids";
import { agentMessages as t } from "./messages";

const TAB_IDS = ["settings", "resources", "usages", "activity", "versions"] as const;
type TabId = (typeof TAB_IDS)[number];

export interface AgentDetailProps {
  id: string;
  request?: DetailRequest;
  /** 목록 화면 경로(삭제·복제 뒤 이동) */
  basePath: string;
}

/** 에이전트 상세(컨테이너): 정의 편집 상태(`useDefinitionEditor`) + 탭. 이름·역할 등은 탭 표현 컴포넌트에 props로 넘긴다. */
export function AgentDetail({ id, basePath, request }: AgentDetailProps) {
  const toast = useToast();
  const navigate = useNavigate();
  const { rest } = useApi();
  const queryClient = useQueryClient();
  const invalidateLists = useInvalidateLists();
  const editor = useDefinitionEditor<Agent>({
    queryKey: definitionKey(DEFINITION_KINDS.agent, id),
    load: (r) => loadAgent(r, id),
    save: (r, value, hash) => saveAgent(r, value, hash),
  });
  const effective = useApiQuery(["list", "agent-effective", id], (r) => r.getAgentEffectiveSettings(id));
  // 사용처 패널은 정의-팀 연동이 켜져 있을 때만 있다(꺼졌으면 탭도 조회도 없다).
  const usagePart = useLinkPart(LINK_PART_IDS.agentsUsagesPanel);
  const usages = useApiQuery(["list", "agent-usages", id], (r) => r.listAgentUsages(id), { enabled: usagePart.visible });
  const agents = useAgentList();
  const [params] = useSearchParams();
  const [tab, setTab] = useState<TabId>(() => TAB_IDS.find((x) => x === params.get("tab")) ?? "settings");
  const [dialog, setDialog] = useState<"duplicate" | "delete" | "json" | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);

  // 목록 단축키 요청(렌더 중 상태 조정 패턴: 같은 요청을 두 번 처리하지 않는다)
  const [handled, setHandled] = useState(request?.token ?? 0);
  if (request !== undefined && request.token !== handled) {
    setHandled(request.token);
    if (request.action === "delete") setDialog("delete");
    else {
      setTab("settings");
      setTimeout(() => document.querySelector<HTMLElement>(NAME_INPUT_SELECTOR)?.focus(), 0);
    }
  }

  const draft = editor.draft;
  usePageTitle(draft?.name ?? null);

  const save = () => {
    void editor.save().then((ok) => {
      if (!ok) return;
      toast({ tone: "success", text: t.detail.saved });
      void invalidateLists();
    });
  };
  useShortcuts([
    { id: "agents.save", scope: "agents", keys: "Mod+S", titleKey: "shortcuts.save", modifierRequired: true, run: save },
    ...TAB_IDS.filter((tabId) => tabId !== "usages" || usagePart.visible).map((tabId, i) => ({ id: `agents.tab${i + 1}`, scope: "agents", keys: `Alt+${i + 1}`, titleKey: "shortcuts.libPanelTab", run: () => setTab(tabId) })),
  ]);

  const exportAction = useExportAction({
    items: DEFINITION_KINDS.agent === undefined ? [] : [{ kind: DEFINITION_KINDS.agent, id }],
    dirty: editor.dirty,
    onSave: save,
  });

  if (editor.status === "loading") {
    return <div className="lib-detail-inner"><Skeleton rows={8} /></div>;
  }
  if (editor.status === "error" || draft === undefined) {
    const notFound = editor.error instanceof ApiError && editor.error.status === 404;
    const view = describeError(editor.error, t.detail.loadFailed);
    return (
      <div className="lib-detail-inner">
        <ErrorBlock
          title={notFound ? t.detail.notFound : t.detail.loadFailed}
          message={notFound ? undefined : view.message}
          details={errorDetails(view)}
          detailsLabel={m.common.details}
          {...(notFound ? {} : { retryLabel: lm.retry, onRetry: editor.reload })}
        >
          {notFound ? <Button onClick={() => void navigate(basePath)}>{t.detail.toList}</Button> : null}
        </ErrorBlock>
      </div>
    );
  }

  const saving = editor.savePhase === "saving";
  const nameEmpty = draft.name.trim() === "";
  const existingIds = new Set((agents.data ?? []).map((a) => a.id));

  const remove = async () => {
    setBusy(true);
    setDialogError(null);
    try {
      await rest.deleteAgent(id, editor.versionHash);
      queryClient.removeQueries({ queryKey: definitionKey(DEFINITION_KINDS.agent, id) });
      await invalidateLists();
      setDialog(null);
      void navigate(basePath);
    } catch (e) {
      setDialogError(describeError(e, t.delete.failed).message);
    } finally {
      setBusy(false);
    }
  };

  const duplicate = async (v: { name: string; id: string; description: string }) => {
    setBusy(true);
    setDialogError(null);
    try {
      const copy = { ...draft, id: v.id, name: v.name } as Agent;
      if (v.description !== "") copy.description = v.description;
      await rest.createAgent(copy);
      await invalidateLists();
      setDialog(null);
      void navigate(`${basePath}/${encodeURIComponent(v.id)}`);
    } catch (e) {
      setDialogError(describeError(e, lm.delete.failed).message);
    } finally {
      setBusy(false);
    }
  };

  const items = [
    {
      id: "settings",
      label: t.tabs.settings,
      content: (
        <AgentEditorForm agent={draft} onChange={editor.setDraft} effective={effective.data} effectiveError={effective.error} effectiveLoading={effective.isLoading} errors={editor.fieldErrors} disabled={false} />
      ),
    },
    { id: "resources", label: t.tabs.resources, content: <AgentResourcesTab agent={draft} onChange={editor.setDraft} effective={effective.data} errors={editor.fieldErrors} disabled={false} /> },
    ...(usagePart.visible
      ? [
          {
            id: "usages",
            label: usages.data === undefined ? t.tabs.usages : `${t.tabs.usages} ${usages.data.length}`,
            content: <AgentUsagesTab agentId={id} />,
          },
        ]
      : []),
    { id: "activity", label: t.tabs.activity, content: <AgentActivityTab agentId={id} /> },
    {
      id: "versions",
      label: versionMessages.tab,
      content: (
        <DefinitionVersionsTab
          model="Agent"
          id={id}
          currentHash={editor.versionHash}
          dirty={editor.dirty}
          onRestored={() => {
            editor.revert();
            void queryClient.invalidateQueries({ queryKey: definitionKey(DEFINITION_KINDS.agent, id) });
            void invalidateLists();
          }}
        />
      ),
    },
  ];

  return (
    <div className="lib-detail-inner">
      <UnsavedGuard dirty={editor.dirty} />
      <div className="lib-detail-head">
        <div className="lib-detail-title">
          <h2 className="app-block-title ac-ellipsis" title={draft.name}>{draft.name || id}</h2>
          <span className="lib-detail-sub app-muted">
            {t.detail.id}: <span className="lib-mono">{id}</span>{" "}
            <button type="button" className="app-link-btn" onClick={() => void navigator.clipboard?.writeText(id).then(() => toast({ tone: "success", text: lm.copied }))}>
              {lm.copy}
            </button>
          </span>
        </div>
        <SaveStatus dirty={editor.dirty} phase={editor.savePhase} onRetry={save} />
        <Button onClick={editor.revert} disabled={!editor.dirty || saving}>{t.detail.revert}</Button>
        <Button variant="primary" loading={saving} disabled={!editor.dirty || nameEmpty || editor.conflict !== null} title="Ctrl+S" onClick={save}>
          {t.detail.save}
        </Button>
        <ActionMenu
          label={t.detail.menu}
          size="md"
          items={[
            { id: "duplicate", label: t.detail.duplicate, onSelect: () => { setDialogError(null); setDialog("duplicate"); } },
            { id: "export", label: exportMessages.menu, onSelect: exportAction.open },
            { id: "versions", label: versionMessages.title, onSelect: () => setTab("versions") },
            { id: "json", label: t.detail.viewJson, onSelect: () => setDialog("json") },
            { id: "delete", label: t.detail.delete, danger: true, onSelect: () => { setDialogError(null); setDialog("delete"); } },
          ]}
        />
      </div>
      {editor.conflict === null ? null : (
        <ConflictBanner details={editor.conflict} busy={saving} onLoadServer={() => void editor.loadServerVersion()} onOverwrite={() => void editor.overwrite()} />
      )}
      {editor.saveError !== null && editor.fieldErrors.length === 0 ? <Banner tone="danger">{editor.saveError}</Banner> : null}
      <Tabs lazy tabs={items} activeId={tab === "usages" && !usagePart.visible ? "settings" : tab} onChange={(next) => setTab(next as TabId)} ariaLabel={t.detail.tabsLabel} />
      {exportAction.dialog}
      {dialog === "duplicate" ? (
        <NewDefinitionDialog
          open
          title={t.detail.duplicate}
          submitLabel={t.detail.duplicate}
          existingIds={existingIds}
          fallbackId={`${id}-copy`}
          initialName={`${draft.name} 2`}
          initialDescription={draft.description ?? ""}
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(null)}
          onSubmit={(v) => void duplicate(v)}
        />
      ) : null}
      {dialog === "delete" ? (
        <DeleteDialog
          open
          name={draft.name || id}
          references={(usages.data ?? []).map((u) => u.name ?? u.id)}
          note={(usages.data ?? []).length > 0 ? t.delete.usedNote : undefined}
          busy={busy}
          error={dialogError}
          onCancel={() => setDialog(null)}
          onConfirm={() => void remove()}
        />
      ) : null}
      <Dialog open={dialog === "json"} title={t.detail.jsonTitle} onClose={() => setDialog(null)} wide actions={<Button onClick={() => setDialog(null)}>{lm.close}</Button>}>
        <pre className="ac-pre app-json">{JSON.stringify(draft, null, 2)}</pre>
      </Dialog>
    </div>
  );
}
