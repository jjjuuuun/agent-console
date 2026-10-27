import type { ResourceSummary } from "@agent-console/contracts";
import { defaultContentRef } from "./resourceLogic";
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { EmptyState, Icon, PageHeader } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { messages as m } from "../../app/messages";
import { useRegisterCommands } from "../../shell/commands";
import { useResourceList, useResourceTypes } from "../settings";
import { DEFINITION_KINDS, useInvalidateLists, type DetailRequest } from "../library";
import { useScopedList } from "../projects";
import { CreateResourceDialog } from "./CreateResourceDialog";
import { ImportDialog } from "./ImportDialog";
import { ResourceDetail } from "./ResourceDetail";
import { ResourceList } from "./ResourceList";
import { resourceMessages as t } from "./messages";
const scopeOfResource = (r: ResourceSummary) => r.project;
const idOfResource = (r: ResourceSummary) => r.id;
const nameOfResource = (r: ResourceSummary) => r.name;

export interface ResourcesScreenProps {
  /** 이 화면의 경로(라우트 설정 데이터). 상세는 `{basePath}/{id}` */
  basePath: string;
}

interface CreateState {
  typeId?: string | undefined;
}

/** 리소스 라이브러리 화면(`/resources`, `/resources/:id`): 종류별 목록 + 상세 + `.claude` 가져오기. */
export function ResourcesScreen({ basePath }: ResourcesScreenProps) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const { rest } = useApi();
  const resources = useResourceList();
  const types = useResourceTypes();
  const invalidate = useInvalidateLists();
  // 다른 화면의 "새 리소스 만들기 →" 링크(`?new=1`)로 들어오면 만들기 창을 연다
  const [creating, setCreating] = useState<CreateState | null>(search.get("new") !== null ? {} : null);
  const [importing, setImporting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [request, setRequest] = useState<DetailRequest | undefined>(undefined);
  const [onlyIds, setOnlyIds] = useState<ReadonlySet<string> | null>(null);
  const scoped = useScopedList(resources.data, { scopeOf: scopeOfResource, kind: DEFINITION_KINDS.resource, idOf: idOfResource, nameOf: nameOfResource });

  if (search.get("new") !== null) {
    const next = new URLSearchParams(search);
    next.delete("new");
    setSearch(next, { replace: true });
  }

  useRegisterCommands([{ id: "resources.new", titleKey: "palette.actions.libResourceNew", run: () => { setError(null); setCreating({}); } }]);
  const go = (rid: string) => void navigate(`${basePath}/${encodeURIComponent(rid)}`);
  const ask = (target: string, action: DetailRequest["action"]) => {
    setRequest({ id: target, action, token: (request?.token ?? 0) + 1 });
    if (target !== id) go(target);
  };
  const existing = new Set((resources.data ?? []).map((r) => r.id));

  const create = async (typeId: string, v: { name: string; id: string; description: string }, scope: { project?: string }) => {
    setBusy(true);
    setError(null);
    try {
      const content = defaultContentRef(types.data?.find((x) => x.id === typeId), v.id);
      await rest.createResource({ id: v.id, type: typeId, name: v.name, ...(v.description ? { description: v.description } : {}), ...(content ? { content } : {}), ...scope });
      await invalidate();
      setCreating(null);
      go(v.id);
    } catch (e) {
      setError(describeError(e, t.create.failed).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-screen-frame" data-screen="resources">
      <PageHeader title={m.nav.resources} />
      <div className="lib-split">
        <ResourceList
          resources={scoped.items}
          scopeBar={scoped.parts.filter}
          selectTool={scoped.parts.select}
          rowExtra={scoped.rowExtra}
          types={types.data}
          typesFailed={types.isError}
          loading={resources.isLoading}
          error={resources.isError ? resources.error : null}
          onRetry={() => void resources.refetch()}
          selectedId={id}
          onSelect={(target) => { if (!scoped.intercept(target)) go(target); }}
          onNew={(typeId) => { setError(null); setCreating({ typeId }); }}
          onImport={() => setImporting(true)}
          onRename={(target) => ask(target, "rename")}
          onDelete={(target) => ask(target, "delete")}
          onlyIds={onlyIds}
          onClearOnlyIds={() => setOnlyIds(null)}
        />
        <div className="lib-split-detail">
          {id === undefined ? (
            <EmptyState icon={<Icon name="resources" size={24} />} title={t.pick.title} description={t.pick.body} />
          ) : (
            <ResourceDetail key={id} id={id} basePath={basePath} {...(request?.id === id ? { request } : {})} />
          )}
        </div>
      </div>
      {creating === null ? null : (
        <CreateResourceDialog
          types={types.data ?? []}
          existingIds={existing}
          initialTypeId={creating.typeId}
          busy={busy}
          error={error}
          onClose={() => setCreating(null)}
          onCreate={(typeId, v, scope) => void create(typeId, v, scope)}
        />
      )}
      {scoped.dialog}
      {importing ? <ImportDialog onClose={() => setImporting(false)} onShowImported={(ids) => setOnlyIds(new Set(ids))} /> : null}
    </div>
  );
}
