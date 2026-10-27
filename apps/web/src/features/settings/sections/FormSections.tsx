import { useMemo } from "react";
import { contractsSchema, getContractSchema, type WorkspaceSettings } from "@agent-console/contracts";
import type { FormError } from "@agent-console/schema-form";
import { Banner, Button } from "@agent-console/ui";
import { describeError } from "../../../app/errors";
import { messages as m } from "../../../app/messages";
import { attachmentErrorsAt } from "../../../lib/attachmentProblems";
import { Skeleton } from "../Skeleton";
import { agentSchemaForBackend, buildAgentDefaultsUi } from "../userSettingsUi";
import { LayerForm } from "../LayerForm";
import { UserSettingsForm } from "../UserSettingsForm";
import { BackendReadinessSection } from "../../backendReadiness";
import { useBackends, useDelegationStrategies, useEdgeTypes, useMergeStrategies, useResourceList, useResourceTypes } from "../settingsData";
import type { SchemaNode } from "../../../lib/schemaTools";
import { enumValues } from "../../../lib/schemaTools";

/** 설정 섹션이 공유하는 편집 props. */
export interface SectionEditProps {
  value: WorkspaceSettings;
  onChange: (next: WorkspaceSettings) => void;
  errors?: FormError[];
  disabled?: boolean;
  /** 이 섹션 폼에서 포커스할 필드(JSON Pointer) */
  focusPath?: string | null;
}

/** 공통 층 하나만 있는 설정 화면의 층 목록. 스키마 기본값은 "어느 층에도 없음"(기본값 배지)이다. */
export const COMMON_LAYER_ID = "common";
const useLayers = () => useMemo(() => [{ id: COMMON_LAYER_ID, label: m.settings.layerCommon }], []);

function QueryNote({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <Banner tone="warning" actions={<Button size="sm" onClick={onRetry}>{m.common.retry}</Button>}>
      {m.settings.optionsFailed} <span className="app-muted">{describeError(error, "").message}</span>
    </Banner>
  );
}

/** ① 공통 설정(`agent_defaults`): 에이전트 기본값 스키마(`AgentDefaults`, 필드는 에이전트 설정과 같고 분류만 다름), 백엔드·첨부 목록은 서버 데이터로. */
export function CommonSection({ value, onChange, errors, disabled, focusPath }: SectionEditProps) {
  const layers = useLayers();
  const backends = useBackends();
  const resources = useResourceList();
  const types = useResourceTypes();
  const defaults = (value.agent_defaults ?? {}) as Record<string, unknown>;
  const backendId = typeof defaults["backend"] === "string" ? (defaults["backend"] as string) : null;
  const schema = useMemo(() => agentSchemaForBackend(getContractSchema("AgentDefaults") as SchemaNode, backends.data ?? [], backendId), [backends.data, backendId]);
  const modes = useMemo(() => {
    const def = contractsSchema.$defs["AttachmentMode"];
    return def === undefined ? [] : enumValues(def, contractsSchema);
  }, []);
  const attachmentErrors = useMemo(() => attachmentErrorsAt(errors, "/resources"), [errors]);
  const ui = useMemo(
    () => buildAgentDefaultsUi(schema, { backends: backends.data ?? [], resources: resources.data ?? [], resourceTypes: types.data ?? [], attachmentModes: modes, layerLabel: m.settings.layerCommon, backendEmptyLabel: m.settings.backendUnset, attachmentErrors }),
    [schema, backends.data, resources.data, types.data, modes, attachmentErrors],
  );
  const failed = backends.error ?? resources.error ?? types.error;
  return (
    <>
      {failed ? <QueryNote error={failed} onRetry={() => void Promise.all([backends.refetch(), resources.refetch(), types.refetch()])} /> : null}
      <p className="app-muted">
        {m.settings.editingLayer}: <strong>{m.settings.layerCommon}</strong>
      </p>
      {backends.data !== undefined && backends.data.length === 0 ? <Banner tone="warning">{m.settings.backendNone}</Banner> : <p className="app-muted">{m.settings.backendUnsetNote}</p>}
      <BackendReadinessSection backends={backends.data ?? []} />
      <LayerForm
        schema={schema}
        uiSchema={ui}
        value={defaults}
        {...(focusPath ? { focusPath } : {})}
        onChange={(next) => onChange({ ...value, agent_defaults: next as WorkspaceSettings["agent_defaults"] })}
        layers={layers}
        editLayerId={COMMON_LAYER_ID}
        {...(errors ? { errors } : {})}
        {...(disabled === undefined ? {} : { disabled })}
        idPrefix="agent-defaults"
      />
    </>
  );
}

/** 값 한 묶음(`sections`)을 사용자 설정 폼으로. 채팅·편집기·위임·병합 규칙·상호작용이 같은 경로를 쓴다. */
export function UserSection({ sections, value, onChange, errors, disabled }: SectionEditProps & { sections: readonly string[] }) {
  const layers = useLayers();
  const edgeTypes = useEdgeTypes();
  const strategies = useMergeStrategies();
  const options = useMemo(
    () => ({
      edgeKinds: (edgeTypes.data ?? []).filter((e) => e.ui_hints?.hidden !== true).map((e) => ({ value: e.id, label: e.title })),
      mergeStrategies: strategies.data ?? [],
      mergeSchema: getContractSchema("AgentSettings") as SchemaNode,
    }),
    [edgeTypes.data, strategies.data],
  );
  const failed = edgeTypes.error ?? strategies.error;
  return (
    <>
      {failed ? <QueryNote error={failed} onRetry={() => void Promise.all([edgeTypes.refetch(), strategies.refetch()])} /> : null}
      <UserSettingsForm
        sections={sections}
        flat={sections.length === 1}
        value={value as Record<string, unknown>}
        onChange={(next) => onChange(next as WorkspaceSettings)}
        layers={layers}
        editLayerId={COMMON_LAYER_ID}
        options={options}
        {...(errors ? { errors } : {})}
        {...(disabled === undefined ? {} : { disabled })}
      />
      <p className="app-muted app-overridable">{m.settings.overridable}</p>
    </>
  );
}

/** 위임 방식 표(읽기 전용, `GET /delegation-strategies`). 제약이 무엇인지 확인하는 용도. */
export function DelegationTable() {
  const q = useDelegationStrategies();
  if (q.isLoading) return <Skeleton rows={2} />;
  if (q.error) return <QueryNote error={q.error} onRetry={() => void q.refetch()} />;
  const rows = q.data ?? [];
  const t = m.settings.delegationTable;
  if (rows.length === 0) return <p className="app-muted">{t.empty}</p>;
  return (
    <table className="app-table" aria-label={t.title}>
      <thead>
        <tr>
          <th>{t.name}</th>
          <th>{t.maxDepth}</th>
          <th>{t.downstream}</th>
          <th>{t.fields}</th>
          <th>{t.interactions}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
            <td title={r.description || undefined}>{r.title}</td>
            <td>{r.max_depth ?? t.unlimited}</td>
            <td>{r.allows_outgoing_flow ? t.allowed : t.denied}</td>
            <td className="app-wrap">{r.member_fields.length === 0 ? t.anyField : r.member_fields.join(", ")}</td>
            <td className="app-wrap">{r.member_interaction_kinds == null ? t.unlimited : r.member_interaction_kinds.join(", ") || m.common.none}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

