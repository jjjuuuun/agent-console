import { useMemo } from "react";
import { getContractSchema } from "@agent-console/contracts";
import type { FormError, ProvenanceLayer } from "@agent-console/schema-form";
import { pickProperties, type SchemaNode } from "../../lib/schemaTools";
import { LayerForm } from "./LayerForm";
import { buildUserSettingsUi, type UserSettingsOptions } from "./userSettingsUi";

export interface UserSettingsFormProps {
  /** 보여 줄 최상위 키(예: `["chat"]`, `["settings_merge"]`). 설정 화면은 섹션마다 나눠 부른다 */
  sections: readonly string[];
  /** 이 층의 값(지정한 키만). 키는 `sections`의 부분집합 */
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  layers: ProvenanceLayer[];
  editLayerId: string;
  /** 위 층에서 상속되는 값(설정 화면: 없음 → 스키마 기본, 팀 패널: 공통 값) */
  baseValue?: Record<string, unknown>;
  provenance?: Record<string, string>;
  options?: UserSettingsOptions;
  errors?: FormError[];
  disabled?: boolean;
  idPrefix?: string;
  /** 사용자 설정 묶음의 JSON Schema(기본: 계약 `WorkspaceSettings`). 다른 스키마로 검사·테스트할 때 주입 */
  rootSchema?: SchemaNode;
  /** 섹션이 하나뿐이고 화면이 이미 그 제목·설명을 보일 때: 폼 안의 같은 제목 접기 단추·설명·"모두 고급" 안내를 숨긴다 */
  flat?: boolean;
}

/**
 * 채팅·편집기·위임·병합 규칙·상호작용·사용량 같은 사용자 설정 묶음 폼(출처 표시).
 * 설정 화면(층 = 공통)과 팀 구성 패널(층 = 팀 구성, 공통 값이 상속으로 보임)이 함께 쓴다.
 * 필드는 스키마에서 그려지고, 위젯 이름만 `userSettingsUi`가 정한다.
 */
export function UserSettingsForm({ sections, value, onChange, layers, editLayerId, baseValue, provenance, options, errors, disabled, idPrefix, rootSchema, flat }: UserSettingsFormProps) {
  const schema = useMemo(() => pickProperties(rootSchema ?? (getContractSchema("WorkspaceSettings") as SchemaNode), sections), [rootSchema, sections]);
  const uiSchema = useMemo(() => buildUserSettingsUi(schema, options), [schema, options]);
  const picked = useMemo(() => Object.fromEntries(sections.filter((k) => value[k] !== undefined).map((k) => [k, value[k]])), [sections, value]);
  const form = (
    <LayerForm
      schema={schema}
      uiSchema={uiSchema}
      value={picked}
      onChange={(next) => {
        const merged: Record<string, unknown> = { ...value };
        for (const key of sections) {
          const v = (next as Record<string, unknown> | null)?.[key];
          if (v === undefined) delete merged[key];
          else merged[key] = v;
        }
        onChange(merged);
      }}
      layers={layers}
      editLayerId={editLayerId}
      {...(baseValue ? { baseValue: Object.fromEntries(sections.filter((k) => baseValue[k] !== undefined).map((k) => [k, baseValue[k]])) } : {})}
      {...(provenance ? { provenance } : {})}
      {...(errors ? { errors } : {})}
      {...(disabled === undefined ? {} : { disabled })}
      idPrefix={idPrefix ?? `us-${sections.join("-")}`}
    />
  );
  return flat === true ? <div className="app-flat-sections">{form}</div> : form;
}
