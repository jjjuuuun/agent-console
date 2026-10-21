import { useMemo } from "react";
import { contractsSchema, getContractSchema } from "@agent-console/contracts";
import type { FormError, ProvenanceLayer, UiSchema } from "@agent-console/schema-form";
import { messages as m } from "../../app/messages";
import { useApiQuery } from "../../app/queries";
import { setAt } from "../../lib/jsonPointer";
import { enumValues, pickProperties, type SchemaNode } from "../../lib/schemaTools";
import { LayerForm, useBackends, useResourceList, useResourceTypes, agentSchemaForBackend, buildAgentDefaultsUi } from "../settings";
import { libraryMessages as t } from "./messages";
import { MODEL_WIDGET, ModelWidget, type ModelOptions } from "./ModelWidget";
import { TAGS_FIELD, TagsField, type TagsOptions } from "./TagsField";

const EXTRA_WIDGETS = { [MODEL_WIDGET]: ModelWidget };
const EXTRA_FIELDS = { [TAGS_FIELD]: TagsField };
const NO_KEYS: readonly string[] = [];

export interface AgentSettingsFormProps {
  /** 이 층의 값(지정한 키만) */
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  layers: ProvenanceLayer[];
  editLayerId: string;
  /** 아래 층에서 상속되는 값(서버 유효 설정에서 이 층을 뺀 값) */
  baseValue?: unknown;
  provenance?: Record<string, string>;
  /** 모델 목록·`backend_options` 스키마를 고르는 유효 백엔드 id */
  backendId: string | null;
  /** 폼에서 뺄 최상위 키(다른 곳에서 편집하는 필드) */
  hideKeys?: readonly string[];
  errors?: FormError[];
  disabled?: boolean;
  idPrefix?: string;
  /** 고급 영역 열림을 기억하는 폼 종류 키 */
  formKey?: string;
  disabledPaths?: Record<string, string>;
  fieldWarnings?: Record<string, string>;
  mergeNotes?: Record<string, string>;
  onOpenLayer?: (layerId: string) => void;
  /** 이 필드(JSON Pointer)로 포커스한다(해결 버튼) */
  focusPath?: string | null;
}

/** 첨부 방식 선택지: 계약 `AttachmentMode` enum에서 읽는다. */
export function attachmentModes(): string[] {
  const def = contractsSchema.$defs["AttachmentMode"];
  return def === undefined ? [] : enumValues(def, contractsSchema);
}

/** 첨부 방식 선택지(모듈 로드 시 한 번 읽는다). */
export const ATTACHMENT_MODES: readonly string[] = attachmentModes();

/** 백엔드가 알려 주는 모델 목록. 백엔드를 아직 못 정했으면 질의하지 않는다. */
export function useBackendModels(backendId: string | null) {
  return useApiQuery(["descriptors", "backend-models", backendId ?? ""], (rest) => rest.listBackendModels(backendId ?? ""), { enabled: backendId !== null && backendId !== "" });
}

/**
 * 에이전트 설정(`AgentSettings`) 한 층의 출처 표시 폼. 에이전트 화면·팀 구성의 노드 설정·팀 설정이 같은 폼을 쓴다.
 * 필드는 스키마에서 오고, 모델·백엔드·도구 위젯만 서버 데이터(백엔드 목록·모델 목록)로 채운다.
 */
export function AgentSettingsForm(props: AgentSettingsFormProps) {
  const { value, onChange, layers, editLayerId, backendId, hideKeys = NO_KEYS, ...rest } = props;
  const backends = useBackends();
  const resources = useResourceList();
  const types = useResourceTypes();
  const models = useBackendModels(backendId);
  const modes = ATTACHMENT_MODES;

  const schema = useMemo(() => {
    const base = getContractSchema("AgentSettings") as SchemaNode;
    const keys = Object.keys((base["properties"] ?? {}) as object).filter((k) => !hideKeys.includes(k));
    return agentSchemaForBackend(pickProperties(base, keys), backends.data ?? [], backendId);
  }, [backends.data, backendId, hideKeys]);

  const ui = useMemo(() => {
    let out = buildAgentDefaultsUi(schema, {
      backends: backends.data ?? [],
      resources: resources.data ?? [],
      resourceTypes: types.data ?? [],
      attachmentModes: modes,
      layerLabel: layers.find((l) => l.id === editLayerId)?.label ?? "",
    }) as Record<string, unknown>;
    const props = (schema["properties"] ?? {}) as Record<string, unknown>;
    if ("model" in props) {
      const options: ModelOptions = { models: models.data ?? [], failed: models.isError, emptyLabel: m.settings.unset, customLabel: t.agentForm.customModel, failedNote: t.agentForm.modelsFailed };
      out = setAt(out, "/model", { "ui:widget": MODEL_WIDGET, "ui:options": options }) as Record<string, unknown>;
    }
    const tags: TagsOptions = { addLabel: t.agentForm.addTag, removeLabel: t.agentForm.removeTag };
    for (const key of ["tools", "disallowed_tools"]) {
      if (key in props) out = setAt(out, `/${key}`, { "ui:field": TAGS_FIELD, "ui:options": tags }) as Record<string, unknown>;
    }
    return out as UiSchema;
  }, [schema, backends.data, resources.data, types.data, modes, models.data, models.isError, layers, editLayerId]);

  // 숨긴 키는 폼 값에서도 빼서 다시 합칠 때 잃지 않게 한다.
  const shown = useMemo(() => Object.fromEntries(Object.entries(value).filter(([k]) => !hideKeys.includes(k))), [value, hideKeys]);
  const hidden = useMemo(() => Object.fromEntries(Object.entries(value).filter(([k]) => hideKeys.includes(k))), [value, hideKeys]);

  return (
    <LayerForm
      schema={schema}
      uiSchema={ui}
      value={shown}
      onChange={(next) => onChange({ ...hidden, ...((next ?? {}) as Record<string, unknown>) })}
      layers={layers}
      editLayerId={editLayerId}
      extraWidgets={EXTRA_WIDGETS}
      extraFields={EXTRA_FIELDS}
      {...rest}
    />
  );
}
