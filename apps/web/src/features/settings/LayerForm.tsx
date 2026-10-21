import { useMemo } from "react";
import { getDefaultValue, SchemaForm, type FormError, type JsonSchema, type ProvenanceLayer, type SchemaFormFieldProps, type SchemaFormWidgetProps, type UiSchema } from "@agent-console/schema-form";
import { ProvenanceBadge } from "@agent-console/ui";
import type { ComponentType } from "react";
import { flashFocused } from "../../app/fix";
import { deepMerge } from "../../lib/jsonPointer";
import { inheritAt, overrideAt } from "../../lib/layerEdit";
import { AttachmentsField, ATTACHMENTS_FIELD } from "./widgets/AttachmentsField";
import { CHOICE_SELECT_WIDGET, ChoiceSelectWidget } from "./widgets/ChoiceSelectWidget";
import { KEY_VALUE_MAP_FIELD, KeyValueMapField } from "./widgets/KeyValueMapField";
import { NULLABLE_NUMBER_WIDGET, NullableNumberWidget } from "./widgets/NullableNumberWidget";
import { RADIO_CARDS_WIDGET, RadioCardsWidget } from "./widgets/RadioCardsWidget";

/** 설정 화면 위젯 묶음(위젯 이름은 `userSettingsUi`가 uiSchema에 쓴다). */
export const SETTINGS_WIDGETS: Record<string, ComponentType<SchemaFormWidgetProps>> = {
  [RADIO_CARDS_WIDGET]: RadioCardsWidget,
  [CHOICE_SELECT_WIDGET]: ChoiceSelectWidget,
  [NULLABLE_NUMBER_WIDGET]: NullableNumberWidget,
};
export const SETTINGS_FIELDS: Record<string, ComponentType<SchemaFormFieldProps>> = {
  [KEY_VALUE_MAP_FIELD]: KeyValueMapField,
  [ATTACHMENTS_FIELD]: AttachmentsField,
};

export interface LayerFormProps {
  schema: Record<string, unknown>;
  uiSchema?: UiSchema;
  /** 이 층의 값(지정한 키만) */
  value: unknown;
  onChange: (next: unknown) => void;
  /** 낮은 우선순위가 앞인 층 목록(서버 데이터 또는 호출자가 정한 라벨) */
  layers: ProvenanceLayer[];
  editLayerId: string;
  /** 위 층에서 상속되는 값(없으면 스키마 기본값). 이 층 값이 이 위에 덮어 보인다 */
  baseValue?: unknown;
  /** 위 층 값의 출처(JSON Pointer → 층 id) */
  provenance?: Record<string, string>;
  layerValues?: Record<string, unknown>;
  errors?: FormError[];
  disabled?: boolean;
  idPrefix?: string;
  /** 고급 영역 펼침 상태를 기억하는 폼 종류 키(없으면 `idPrefix`). 호출자가 폼 종류별로 정한다 */
  formKey?: string;
  fieldWarnings?: Record<string, string>;
  mergeNotes?: Record<string, string>;
  disabledPaths?: Record<string, string>;
  /** 출처 팝오버의 층 줄을 눌렀을 때(그 층 편집 화면으로 이동). 없으면 줄은 버튼이 아니다 */
  onOpenLayer?: (layerId: string) => void;
  /** 설정 화면 기본 묶음에 더할 위젯·필드(예: 에이전트 화면의 모델 선택). 이름이 같으면 이 값이 이긴다 */
  extraWidgets?: Record<string, ComponentType<SchemaFormWidgetProps>>;
  extraFields?: Record<string, ComponentType<SchemaFormFieldProps>>;
  /** 이 JSON Pointer의 필드로 스크롤·포커스하고 2초 강조한다(해결 버튼으로 열렸을 때). 고급 접힘은 폼이 펼친다 */
  focusPath?: string | null;
}

/**
 * 한 층(공통·팀 구성 등)의 값을 출처 표시 폼으로 편집한다. [이 층에서 덮어쓰기]/[상속으로 되돌리기]를 처리하며,
 * 서버·화면을 모른다(값과 콜백만). 설정 화면과 팀 구성 화면이 같은 컴포넌트를 쓴다.
 */
export function LayerForm(props: LayerFormProps) {
  const { schema, uiSchema, value, onChange, layers, editLayerId, baseValue, provenance, layerValues, errors, disabled, idPrefix } = props;
  const inherited = useMemo(() => baseValue ?? getDefaultValue(schema as JsonSchema), [baseValue, schema]);
  const effective = useMemo(() => deepMerge(inherited, value), [inherited, value]);
  return (
    <SchemaForm
      schema={schema}
      {...(uiSchema ? { uiSchema } : {})}
      value={value}
      onChange={onChange}
      layers={layers}
      editLayerId={editLayerId}
      provenance={provenance ?? {}}
      effectiveValue={inherited}
      {...(layerValues ? { layerValues } : {})}
      onOverride={(path) => onChange(overrideAt(value ?? {}, effective, path))}
      onInherit={(path) => onChange(inheritAt(value ?? {}, path))}
      customWidgets={props.extraWidgets ? { ...SETTINGS_WIDGETS, ...props.extraWidgets } : SETTINGS_WIDGETS}
      customFields={props.extraFields ? { ...SETTINGS_FIELDS, ...props.extraFields } : SETTINGS_FIELDS}
      onFocusReached={() => flashFocused()}
      rawJsonToggle={false}
      {...(props.focusPath ? { focusPath: props.focusPath } : {})}
      compactProvenance
      {...(props.formKey ?? idPrefix ? { advancedStorageKey: props.formKey ?? idPrefix } : {})}
      {...(errors ? { errors } : {})}
      {...(disabled === undefined ? {} : { disabled })}
      {...(idPrefix ? { idPrefix } : {})}
      {...(props.fieldWarnings ? { fieldWarnings: props.fieldWarnings } : {})}
      {...(props.mergeNotes ? { mergeNotes: props.mergeNotes } : {})}
      {...(props.disabledPaths ? { disabledPaths: props.disabledPaths } : {})}
      {...(props.onOpenLayer ? { onOpenLayer: props.onOpenLayer } : {})}
      renderProvenanceBadge={(info) => (
        <ProvenanceBadge
          layer={info.layer ?? { id: "default", label: info.text, index: 0 }}
          variant={info.variant}
          label={info.text}
          {...(info.count === undefined ? {} : { count: info.count })}
          onClick={info.onClick}
        />
      )}
    />
  );
}
