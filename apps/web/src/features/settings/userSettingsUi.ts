import type { UiSchema } from "@agent-console/schema-form";
import type { BackendDescriptor, MergeStrategyInfo, ResourceSummary, ResourceTypeDescriptor } from "@agent-console/contracts";
import { messages as m, lookupMessage } from "../../app/messages";
import { CHAT_SORT_MODES } from "../../lib/chatSort";
import { formatPointer, parsePointer, setAt } from "../../lib/jsonPointer";
import { enumValues, isNullableNumber, keywordAt, parseEnumDescriptions, resolveRef, schemaAt, schemaPointers, unwrapNullable, type SchemaNode } from "../../lib/schemaTools";
import { ENUM_PREVIEWS } from "./replyDisplayPreviews";
import type { Choice } from "./widgets/ChoiceSelectWidget";
import { CHOICE_SELECT_WIDGET } from "./widgets/ChoiceSelectWidget";
import { ATTACHMENTS_FIELD } from "./widgets/AttachmentsField";
import { KEY_VALUE_MAP_FIELD, type KeyValueMapOptions } from "./widgets/KeyValueMapField";
import { NULLABLE_NUMBER_WIDGET } from "./widgets/NullableNumberWidget";
import { RADIO_CARDS_WIDGET } from "./widgets/RadioCardsWidget";

/** 사용자 설정 폼이 필요로 하는 서버 데이터(디스크립터·목록). 모두 선택이며 없으면 해당 필드는 일반 입력으로 그려진다. */
export interface UserSettingsOptions {
  /** `GET /edge-types` → 선택 목록(값 = 종류 id, 라벨 = 디스크립터 title) */
  edgeKinds?: readonly Choice[];
  /** `GET /merge-strategies` */
  mergeStrategies?: readonly MergeStrategyInfo[];
  /** 병합 규칙의 "스키마 기본" 계산·경로 자동완성에 쓰는 에이전트 설정 스키마(`x-merge` 주석) */
  mergeSchema?: SchemaNode;
  /** 사용량 창 id 후보(`GET /usage` 응답에서 본 창) */
  windowIds?: readonly string[];
}

type Obj = Record<string, unknown>;

/** 스키마 노드의 `x-ui.enum_labels`(값 → 라벨). 없거나 문자열 라벨이 하나도 없으면 undefined. */
function xUiEnumLabels(node: SchemaNode): Record<string, string> | undefined {
  const xui = node["x-ui"];
  const raw = typeof xui === "object" && xui !== null ? (xui as Obj)["enum_labels"] : undefined;
  if (typeof raw !== "object" || raw === null) return undefined;
  const entries = Object.entries(raw as Obj).filter((e): e is [string, string] => typeof e[1] === "string" && e[1].trim() !== "");
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

function put(ui: Obj, pointer: string, spec: Obj): Obj {
  return setAt(ui, pointer, spec) as Obj;
}

/** 규칙 경로(JSON Pointer) 검사: 비었거나 `/`로 시작해야 한다. */
export function validateMergePointer(key: string): string | undefined {
  return key === "" || key.startsWith("/") ? undefined : m.settings.merge.pointerInvalid;
}

/**
 * 스키마에서 사용자 설정 폼의 uiSchema를 만든다. 규칙은 스키마 모양이며 필드 이름이 아니다:
 *  - 문자열 enum → 카드형 라디오(설명은 필드 description의 "값: 설명"에서, 그림은 `ENUM_PREVIEWS`)
 *  - 널 허용 숫자 → "정하지 않음" 체크가 있는 숫자 입력
 * 아래 `BINDINGS`는 의미를 가진 몇 필드의 위젯 이름만 고른다(설정 키 → 위젯 이름 데이터).
 */
export function buildUserSettingsUi(root: SchemaNode, options: UserSettingsOptions = {}): UiSchema {
  let ui: Obj = {};
  const walk = (node: SchemaNode, pointer: string, depth: number) => {
    const { schema } = unwrapNullable(node, root);
    const props = schema["properties"];
    if (typeof props !== "object" || props === null || depth > 4) return;
    for (const [key, raw] of Object.entries(props as Record<string, SchemaNode>)) {
      const child = formatPointer([...parsePointer(pointer), key]);
      const values = enumValues(raw, root);
      const resolved = resolveRef(raw, root);
      if (values.length > 0) {
        const descriptions = parseEnumDescriptions(typeof resolved["description"] === "string" ? resolved["description"] : undefined, values);
        const labels = xUiEnumLabels(raw) ?? xUiEnumLabels(resolved);
        ui = put(ui, child, { "ui:widget": RADIO_CARDS_WIDGET, "ui:options": { descriptions, previews: ENUM_PREVIEWS[child] ?? {}, ...(labels ? { labels } : {}) } });
      } else if (isNullableNumber(raw, root)) {
        ui = put(ui, child, { "ui:widget": NULLABLE_NUMBER_WIDGET });
      } else {
        walk(raw, child, depth + 1);
      }
    }
  };
  walk(root, "", 0);

  for (const binding of BINDINGS) {
    const spec = binding.spec(options);
    if (spec !== undefined && schemaAt(root, binding.pointer) !== undefined) {
      ui = put(ui, binding.pointer, spec);
    }
  }
  return ui as UiSchema;
}

interface Binding {
  pointer: string;
  spec: (options: UserSettingsOptions) => Obj | undefined;
}

/** 설정 키 → 위젯/필드 이름. 필드의 의미를 아는 유일한 곳이며, 값 어휘는 모두 서버 데이터로 채운다. */
const BINDINGS: readonly Binding[] = [
  {
    pointer: "/editor/default_edge_kind",
    spec: (o) => ({ "ui:widget": CHOICE_SELECT_WIDGET, "ui:options": { choices: o.edgeKinds ?? [], emptyLabel: m.settings.edgeKind.first } }),
  },
  {
    pointer: "/chat/list_sort",
    spec: () => ({
      "ui:widget": CHOICE_SELECT_WIDGET,
      "ui:options": { choices: CHAT_SORT_MODES.map((s) => ({ value: s.id, label: `${lookupMessage(s.titleKey)} — ${lookupMessage(s.descriptionKey)}` })), emptyLabel: m.settings.chatSort.empty },
    }),
  },
  {
    pointer: "/settings_merge",
    spec: (o) => {
      const mergeOptions: KeyValueMapOptions = {
        keyLabel: m.settings.merge.path,
        valueLabel: m.settings.merge.strategy,
        addLabel: m.settings.merge.add,
        keySuggestions: o.mergeSchema === undefined ? [] : schemaPointers(o.mergeSchema),
        valueChoices: (o.mergeStrategies ?? []).map((s) => ({ value: s.id, label: s.id, ...(s.description ? { hint: s.description } : {}) })),
        validateKey: validateMergePointer,
        rowNote: (key) => {
          const base = o.mergeSchema === undefined ? undefined : keywordAt(o.mergeSchema, key, "x-merge");
          return `${typeof base === "string" ? m.settings.merge.schemaDefault(base) : m.settings.merge.noSchemaDefault} · ${m.settings.merge.widenWarning}`;
        },
      };
      return { "ui:field": KEY_VALUE_MAP_FIELD, "ui:options": mergeOptions };
    },
  },
  {
    pointer: "/usage/window_labels",
    spec: (o) => ({
      "ui:field": KEY_VALUE_MAP_FIELD,
      "ui:options": {
        keyLabel: m.settings.usage.windowKey,
        valueLabel: m.settings.usage.windowValue,
        addLabel: m.settings.usage.windowAdd,
        keySuggestions: o.windowIds ?? [],
      } satisfies KeyValueMapOptions,
    }),
  },
];

/** 에이전트 공통 설정 폼에 필요한 서버 데이터. */
export interface AgentDefaultsOptions {
  backends?: readonly BackendDescriptor[];
  resources?: readonly ResourceSummary[];
  resourceTypes?: readonly ResourceTypeDescriptor[];
  /** 첨부 방식 선택지(계약 enum에서 읽은 값) */
  attachmentModes?: readonly string[];
  layerLabel: string;
  /** 백엔드 select의 "비움" 항목 이름(기본 `(지정 안 함)`). 공통 설정은 "첫 실행 때 묻기" */
  backendEmptyLabel?: string;
  /** 첨부 번호 -> 서버 오류 메시지 */
  attachmentErrors?: Readonly<Record<number, readonly string[]>>;
}

/**
 * 에이전트 설정(`AgentSettings`) 스키마를 폼용으로 다듬는다:
 * 고른 백엔드의 `config_schema`가 있으면 `backend_options`의 스키마를 그것으로 바꾼다(백엔드를 바꾸면 영역이 다시 그려진다).
 */
export function agentSchemaForBackend(schema: SchemaNode, backends: readonly BackendDescriptor[], backendId: string | null | undefined): SchemaNode {
  const config = backends.find((b) => b.id === backendId)?.config_schema;
  const props = schema["properties"];
  if (config === undefined || typeof props !== "object" || props === null || !("backend_options" in props)) return schema;
  const prev = (props as Record<string, SchemaNode>)["backend_options"] ?? {};
  const { title, description } = prev as { title?: unknown; description?: unknown };
  // 백엔드 스키마의 `$ref`(#/$defs/…)가 풀리도록 그 `$defs`를 루트로 옮긴다(이름이 겹치면 기존 루트 정의가 이긴다).
  const { $defs: backendDefs, ...configBody } = config as Record<string, unknown>;
  const rootDefs = (schema["$defs"] ?? {}) as Obj;
  return {
    ...schema,
    ...(backendDefs === undefined ? {} : { $defs: { ...(backendDefs as Obj), ...rootDefs } }),
    properties: { ...(props as Obj), backend_options: { ...configBody, ...(typeof title === "string" ? { title } : {}), ...(typeof description === "string" && configBody["description"] === undefined ? { description } : {}) } },
  };
}

export function buildAgentDefaultsUi(root: SchemaNode, options: AgentDefaultsOptions): UiSchema {
  let ui = buildUserSettingsUi(root) as Obj;
  const props = (root["properties"] ?? {}) as Obj;
  if ("backend" in props) {
    ui = put(ui, "/backend", {
      "ui:widget": CHOICE_SELECT_WIDGET,
      "ui:options": { choices: (options.backends ?? []).map((b) => ({ value: b.id, label: b.title })), emptyLabel: options.backendEmptyLabel ?? m.settings.unset },
    });
  }
  if ("resources" in props) {
    ui = put(ui, "/resources", {
      "ui:field": ATTACHMENTS_FIELD,
      "ui:options": {
        resources: options.resources ?? [],
        types: options.resourceTypes ?? [],
        modes: options.attachmentModes ?? [],
        layerLabel: options.layerLabel,
        warning: m.settings.commonResourcesWarning,
        ...(options.attachmentErrors ? { errors: options.attachmentErrors } : {}),
      },
    });
  }
  return ui as UiSchema;
}
