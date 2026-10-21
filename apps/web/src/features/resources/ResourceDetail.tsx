import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import type { Resource } from "@agent-console/contracts";
import { Banner, Button, Dialog, Tabs, Tag, useShortcuts, useToast } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { ErrorBlock, errorDetails } from "../../app/ErrorBlock";
import { describeError } from "../../app/errors";
import { messages as m } from "../../app/messages";
import { ConflictBanner } from "../../definition/ConflictBanner";
import { SaveIssuesBanner } from "../../definition/SaveIssuesBanner";
import { SaveStatus } from "../../definition/SaveStatus";
import { UnsavedGuard } from "../../definition/unsaved";
import { useDefinitionEditor } from "../../definition/useDefinitionEditor";
import { shortId } from "../../lib/format";
import { usePageTitle } from "../../shell/titles";
import { Skeleton, useResourceList, useResourceTypes } from "../settings";
import { ActionMenu, DescriptorIcon, useInvalidateLists, DeleteDialog, DEFINITION_KINDS, definitionKey, NewDefinitionDialog, libraryMessages as lm, type DetailRequest } from "../library";
import { useExportAction, exportMessages } from "../exports";
import { DefinitionVersionsTab, versionMessages } from "../versions";
import { ResourceEditorForm } from "./ResourceEditorForm";
import { ResourceUsagesTab, useResourceUsages } from "./UsagesTab";
import { resourceMessages as t } from "./messages";
import { loadResource, mediaTypeOf, resourceTabIds, saveResource, type ResourceDoc, type ResourceTabId } from "./resourceLogic";

export interface ResourceDetailProps {
  id: string;
  basePath: string;
  request?: DetailRequest;
}

type DialogKind = "rename" | "duplicate" | "delete" | "origin" | null;

/** 리소스 상세 탭: 종류가 정하는 탭 + 모든 종류 공통 [버전] */
type DetailTabId = ResourceTabId | "versions";

function importedFrom(resource: Resource): { path: string; hash: string } | undefined {
  const from = resource.attributes?.["imported_from"];
  if (typeof from !== "object" || from === null) return undefined;
  const rec = from as Record<string, unknown>;
  return typeof rec["path"] === "string" ? { path: rec["path"], hash: typeof rec["sha256"] === "string" ? rec["sha256"] : "" } : undefined;
}

/** 리소스 상세(컨테이너): 종류 디스크립터가 탭 구성을 정한다(내용/설정/사용처). 정의 + 본문을 하나의 [저장]으로 저장한다. */
export function ResourceDetail({ id, basePath, request }: ResourceDetailProps) {
  const toast = useToast();
  const navigate = useNavigate();
  const { rest } = useApi();
  const queryClient = useQueryClient();
  const invalidateLists = useInvalidateLists();
  const types = useResourceTypes();
  const list = useResourceList();
  const usages = useResourceUsages(id);
  const descriptors = types.data ?? [];
  const editor = useDefinitionEditor<ResourceDoc>({
    queryKey: definitionKey(DEFINITION_KINDS.resource, id),
    enabled: types.isSuccess || types.isError,
    load: (r) => loadResource(r, id, descriptors),
    save: (r, value, hash) => saveResource(r, value, hash, descriptors),
  });
  const [params] = useSearchParams();
  const [tab, setTab] = useState<DetailTabId | null>(() => (params.get("tab") === "versions" ? "versions" : null));
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const [handled, setHandled] = useState(request?.token ?? 0);
  if (request !== undefined && request.token !== handled) {
    setHandled(request.token);
    setDialogError(null);
    setDialog(request.action === "delete" ? "delete" : "rename");
  }

  const draft = editor.draft;
  usePageTitle(draft?.resource.name ?? null);
  const descriptor = draft === undefined ? undefined : descriptors.find((x) => x.id === draft.resource.type);
  const tabIds: DetailTabId[] = draft === undefined ? [] : [...resourceTabIds(descriptor, draft.resource), "versions"];
  const activeTab: DetailTabId = tab !== null && tabIds.includes(tab) ? tab : (tabIds[0] ?? "usages");

  const save = () => {
    void editor.save().then((ok) => {
      if (ok) {
        toast({ tone: "success", text: t.detail.saved });
        void invalidateLists();
      }
    });
  };
  useShortcuts([
    { id: "resources.save", scope: "resources", keys: "Mod+S", titleKey: "shortcuts.save", modifierRequired: true, run: save },
    ...tabIds.map((tabId, i) => ({ id: `resources.tab${i + 1}`, scope: "resources", keys: `Alt+${i + 1}`, titleKey: "shortcuts.libPanelTab", run: () => setTab(tabId) })),
  ]);

  const exportAction = useExportAction({
    items: DEFINITION_KINDS.resource === undefined ? [] : [{ kind: DEFINITION_KINDS.resource, id }],
    dirty: editor.dirty,
    onSave: save,
  });

  if (editor.status === "loading") return <div className="lib-detail-inner"><Skeleton rows={8} /></div>;
  if (editor.status === "error" || draft === undefined) {
    const notFound = editor.error instanceof ApiError && editor.error.status === 404;
    const view = describeError(editor.error, t.detail.loadFailed);
    return (
      <div className="lib-detail-inner">
        <ErrorBlock
          title={notFound ? t.detail.notFound : t.detail.loadFailed}
          {...(notFound ? {} : { message: view.message, retryLabel: lm.retry, onRetry: editor.reload })}
          details={errorDetails(view)}
          detailsLabel={m.common.details}
        >
          {notFound ? <Button onClick={() => void navigate(basePath)}>{t.detail.toList}</Button> : null}
        </ErrorBlock>
      </div>
    );
  }

  const { resource } = draft;
  const saving = editor.savePhase === "saving";
  const origin = importedFrom(resource);
  const existingIds = new Set((list.data ?? []).map((r) => r.id));
  const mediaType = mediaTypeOf(resource, descriptor);

  const rename = async (v: { name: string; description: string }) => {
    const next = { ...resource, name: v.name } as Record<string, unknown>;
    if (v.description === "") delete next["description"];
    else next["description"] = v.description;
    editor.setDraft({ ...draft, resource: next as unknown as Resource });
    setDialog(null);
  };

  const remove = async () => {
    setBusy(true);
    setDialogError(null);
    try {
      await rest.deleteResource(id, editor.versionHash);
      queryClient.removeQueries({ queryKey: definitionKey(DEFINITION_KINDS.resource, id) });
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
      const copy = { ...resource, id: v.id, name: v.name } as Resource;
      if (v.description) copy.description = v.description;
      const created = await rest.createResource(copy);
      if (draft.text !== null) await rest.putResourceContent(v.id, draft.text, created.version_hash ?? "", mediaType);
      let copyHash = created.version_hash ?? "";
      for (const f of draft.files ?? []) {
        const saved = await rest.putResourceFile(v.id, f.path, f.bytes ?? f.text ?? "", copyHash, f.mediaType);
        copyHash = saved.version_hash ?? copyHash;
      }
      await invalidateLists();
      setDialog(null);
      void navigate(`${basePath}/${encodeURIComponent(v.id)}`);
    } catch (e) {
      setDialogError(describeError(e, lm.delete.failed).message);
    } finally {
      setBusy(false);
    }
  };

  const unknownType = descriptor === undefined && types.isSuccess;
  const tabItems = tabIds.map((tabId) => {
    if (tabId === "content" || tabId === "config") {
      return {
        id: tabId,
        label: tabId === "content" ? t.tabs.content : t.tabs.config,
        content: <ResourceEditorForm part={tabId} descriptor={descriptor} doc={draft} onChange={editor.setDraft} errors={editor.fieldErrors} disabled={tabId === "content" ? saving : false} onSave={save} />,
      };
    }
    if (tabId === "versions") {
      return {
        id: tabId,
        label: versionMessages.tab,
        content: (
          <DefinitionVersionsTab
            model="Resource"
            id={id}
            currentHash={editor.versionHash}
            dirty={editor.dirty}
            onRestored={() => {
              editor.revert();
              void queryClient.invalidateQueries({ queryKey: definitionKey(DEFINITION_KINDS.resource, id) });
              void invalidateLists();
            }}
          />
        ),
      };
    }
    return {
      id: tabId,
      label: usages.data === undefined ? t.tabs.usages : t.usages.tabCount(usages.data.length),
      content: <ResourceUsagesTab id={id} />,
    };
  });

  return (
    <div className="lib-detail-inner" data-wide={activeTab === "content" ? "true" : "false"}>
      <UnsavedGuard dirty={editor.dirty} />
      <div className="lib-detail-head">
        <DescriptorIcon hint={descriptor?.ui_hints?.icon} title={descriptor?.title ?? resource.type} size={24} />
        <div className="lib-detail-title">
          <h2 className="app-block-title ac-ellipsis" title={resource.name}>{resource.name || id}</h2>
          <span className="lib-detail-sub app-muted">
            {t.detail.typeLabel(descriptor?.title ?? resource.type)} · <span className="lib-mono">{id}</span>{" "}
            {origin === undefined ? null : <Tag>{t.detail.imported}</Tag>} {descriptor?.declarative ? <Tag>{t.detail.declarative}</Tag> : null}
          </span>
        </div>
        <SaveStatus dirty={editor.dirty} phase={editor.savePhase} onRetry={save} />
        <Button onClick={editor.revert} disabled={!editor.dirty || saving}>{t.detail.revert}</Button>
        <Button variant="primary" loading={saving} disabled={!editor.dirty || editor.conflict !== null} title="Ctrl+S" onClick={save}>
          {t.detail.save}
        </Button>
        <ActionMenu
          label={t.detail.menu}
          size="md"
          items={[
            { id: "rename", label: t.detail.rename, onSelect: () => { setDialogError(null); setDialog("rename"); } },
            { id: "duplicate", label: t.detail.duplicate, onSelect: () => { setDialogError(null); setDialog("duplicate"); } },
            { id: "export", label: exportMessages.menu, onSelect: exportAction.open },
            { id: "versions", label: versionMessages.title, onSelect: () => setTab("versions") },
            ...(origin === undefined ? [] : [{ id: "origin", label: t.detail.source, onSelect: () => setDialog("origin") }]),
            { id: "delete", label: t.detail.delete, danger: true, onSelect: () => { setDialogError(null); setDialog("delete"); } },
          ]}
        />
      </div>
      {origin === undefined ? null : <p className="app-muted lib-field-note">{t.detail.originOf(origin.path, shortId(origin.hash))} {t.detail.originNote}</p>}
      {unknownType ? <Banner tone="warning">{t.unknownType(resource.type)}</Banner> : null}
      {editor.conflict === null ? null : (
        <ConflictBanner details={editor.conflict} busy={saving} onLoadServer={() => void editor.loadServerVersion()} onOverwrite={() => void editor.overwrite()} />
      )}
      <SaveIssuesBanner issues={editor.saveIssues} />
      {editor.saveError !== null && editor.fieldErrors.length === 0 ? (
        <Banner tone="danger">{editor.saveError}</Banner>
      ) : null}
      <Tabs lazy tabs={tabItems} activeId={activeTab} onChange={(next) => setTab(next as DetailTabId)} ariaLabel={t.detail.tabsLabel} />
      {exportAction.dialog}

      {dialog === "rename" ? (
        <NewDefinitionDialog
          open
          title={t.detail.renameTitle}
          submitLabel={t.detail.renameSubmit}
          existingIds={new Set()}
          fallbackId={id}
          initialName={resource.name}
          initialDescription={resource.description ?? ""}
          hideId
          onClose={() => setDialog(null)}
          onSubmit={(v) => void rename(v)}
        />
      ) : null}
      {dialog === "duplicate" ? (
        <NewDefinitionDialog
          open
          title={t.detail.duplicate}
          submitLabel={t.detail.duplicate}
          existingIds={existingIds}
          fallbackId={`${id}-copy`}
          initialName={`${resource.name} 2`}
          initialDescription={resource.description ?? ""}
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(null)}
          onSubmit={(v) => void duplicate(v)}
        />
      ) : null}
      {dialog === "delete" ? (
        <DeleteDialog
          open
          name={resource.name || id}
          references={(usages.data ?? []).map((u) => u.name ?? u.id)}
          note={(usages.data ?? []).length > 0 ? t.delete.usedNote : undefined}
          busy={busy}
          error={dialogError}
          onCancel={() => setDialog(null)}
          onConfirm={() => void remove()}
        />
      ) : null}
      <Dialog open={dialog === "origin"} title={t.detail.originTitle} onClose={() => setDialog(null)} actions={<Button onClick={() => setDialog(null)}>{lm.close}</Button>}>
        {origin === undefined ? null : (
          <dl className="app-meta">
            <dt>{t.detail.originPath}</dt>
            <dd className="lib-mono app-wrap">{origin.path}</dd>
            <dt>{t.detail.originHash}</dt>
            <dd className="lib-mono app-wrap">{origin.hash}</dd>
          </dl>
        )}
        <p className="app-muted">{t.detail.originNote}</p>
      </Dialog>
    </div>
  );
}
