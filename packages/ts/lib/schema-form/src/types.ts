import type { ComponentType, ReactNode } from "react";

/** JSON Schema 문서. 이 패키지는 스키마 내용을 해석하지 않고 그대로 폼 엔진에 전달한다. */
export type JsonSchema = Record<string, unknown> | boolean;

/** 필드 표시 힌트(디스크립터의 `ui_schema`). 키는 `ui:widget` 같은 rjsf 관례를 따른다. */
export type UiSchema = Record<string, unknown>;

/** 서버·상위에서 온 필드 오류. */
export interface FormError {
  /** 폼 값 기준 JSON Pointer. 루트는 빈 문자열. 예: `/model`, `/tags/0` */
  path: string;
  message: string;
  /** 기본 `error` */
  severity?: "error" | "warning";
}

/** 문구 덮어쓰기(부분 지정 가능). 기본값은 한국어. */
export interface SchemaFormMessages {
  /** 값이 남아 있는 `deprecated: true` 필드의 라벨 옆 칩 문구 */
  deprecatedChip: string;
  /** 같은 필드의 설명 아래 안내 문구 */
  deprecatedNote: string;
  addItem: string;
  removeItem: string;
  moveUp: string;
  moveDown: string;
  copyItem: string;
  itemTitle: string;
  emptyArray: string;
  rawJsonToggle: string;
  formViewToggle: string;
  rawJsonLabel: string;
  invalidJson: string;
  emptyObject: string;
  schemaUnusable: string;
  /** 필수 항목 비어 있음 */
  required: string;
  /** 검증 문구 템플릿. `{limit}`, `{multipleOf}`, `{format}`, `{type}` 자리표시자를 쓴다. */
  minimum: string;
  maximum: string;
  exclusiveMinimum: string;
  exclusiveMaximum: string;
  minLength: string;
  maxLength: string;
  minItems: string;
  maxItems: string;
  multipleOf: string;
  pattern: string;
  format: string;
  enumValue: string;
  type: string;
  uniqueItems: string;
  itemAdded: string;
  itemRemoved: string;
  yes: string;
  no: string;
  /** 출처 표시(선택 prop `provenance` 사용 시) */
  overrideHere: string;
  inheritBack: string;
  setHere: string;
  badgeDefault: string;
  /** `{count}` 자리표시자 */
  badgeMixed: string;
  /** `{layer}` 자리표시자 */
  badgeSetHint: string;
  badgeInheritedHint: string;
  popoverTitle: string;
  layerEmpty: string;
  layerApplied: string;
  openLayer: string;
  disabledLock: string;
  /** 필수 칩 */
  requiredChip: string;
  /** 고급 영역 제목. `{count}` = 고급 필드 수 */
  advancedTitle: string;
  /** 고급 제목 옆 칩. `{count}` = 지정된 고급 필드 수 */
  advancedSetCount: string;
  advancedErrorCount: string;
  advancedAllHint: string;
  /** `{value}` 자리표시자 */
  defaultHint: string;
  exampleHint: string;
  whenHint: string;
  /** 상속 출처 한 줄. `{layer}` */
  inheritedFrom: string;
  /** 읽기 전용 값 복사 버튼 */
  copyValue: string;
  copiedValue: string;
  /** 필드 라벨 줄 ⓘ 버튼의 라벨(단축키 안내 포함) */
  helpToggle: string;
  /** ⓘ 팝오버(예시·기본값·바꾸는 때)의 접근성 이름 */
  helpTitle: string;
  /** 값이 비어 있는 읽기 전용 값 */
  emptyValue: string;
}

/** `customWidgets`로 주입하는 위젯이 받는 props. 폼 엔진 타입을 노출하지 않기 위해 이 패키지가 정의한다. */
export interface SchemaFormWidgetProps {
  id: string;
  value: unknown;
  onChange: (value: unknown) => void;
  onBlur: () => void;
  label: string;
  required: boolean;
  disabled: boolean;
  readonly: boolean;
  placeholder?: string;
  schema: Record<string, unknown>;
  /** `ui:options` 객체 */
  options: Record<string, unknown>;
  /** 이 필드의 오류 메시지 */
  errors: string[];
}

/**
 * `customFields`로 주입하는 필드가 받는 props. 값 전체(객체·배열 포함)를 한 컴포넌트가 그린다.
 * 위젯 props와 같은 모양이며 `ui:field` 이름으로 고른다(스키마에 `properties`가 없는 키-값 맵, 첨부 목록 등).
 */
export type SchemaFormFieldProps = SchemaFormWidgetProps;

/** 설정 층 하나. 목록은 낮은 우선순위가 앞이다(서버 `layers`). id·이름은 호출 측이 정한다. */
export interface ProvenanceLayer {
  id: string;
  label: string;
}

/** 출처 배지 한 개를 그리는 데 필요한 정보. `renderProvenanceBadge`로 다른 배지 컴포넌트를 주입할 때 받는다. */
export interface ProvenanceBadgeInfo {
  /** `set` 이 층에서 지정, `inherited` 위 층에서 상속, `default` 어느 층에도 없음, `mixed` 하위 값의 출처가 여러 층 */
  variant: "set" | "inherited" | "default" | "mixed";
  /** set·inherited일 때 출처 층. `index`는 `layers` 안 위치(색 선택용) */
  layer?: { id: string; label: string; index: number };
  /** mixed일 때 층 수 */
  count?: number;
  /** 화면에 보일 텍스트 라벨(색 단독 금지) */
  text: string;
  /** 스크린리더·툴팁용 설명 */
  description: string;
  /** 클릭 시 "값이 정해지는 과정" 팝오버를 연다. 팝오버는 이 패키지가 그린다. */
  onClick: () => void;
  expanded: boolean;
  /** 팝오버 요소 id(`aria-controls`) */
  popoverId: string;
}

export interface SchemaFormProps {
  /** JSON Schema (object 권장). */
  schema: JsonSchema;
  uiSchema?: UiSchema;
  /** 현재 값(제어형). */
  value?: unknown;
  /** 사용자가 편집했을 때만 호출된다(마운트 시 기본값 채움으로는 호출하지 않음). */
  onChange?: (value: unknown) => void;
  /** 서버/상위 오류. 필드별로 매핑해 표시한다. */
  errors?: FormError[];
  disabled?: boolean;
  readonly?: boolean;
  /** 같은 화면의 폼 id 충돌 방지. 기본 `root`. */
  idPrefix?: string;
  /** 이 JSON Pointer의 필드로 포커스를 옮긴다. */
  focusPath?: string | null;
  /** focusPath 필드가 처음 포커스를 받았을 때(필드가 늦게 그려져도 한 번 부른다). 강조 표시 등에 쓴다 */
  onFocusReached?: (el: HTMLElement) => void;
  /** focusPath 필드가 생기기를 기다리는 최대 시간(ms, 기본 5000) */
  focusTimeoutMs?: number;
  /** `ui:widget` 이름으로 추가 위젯 주입. */
  customWidgets?: Record<string, ComponentType<SchemaFormWidgetProps>>;
  /** `ui:field` 이름으로 필드 통째 주입(객체·배열 값을 한 컴포넌트가 그린다). 출처 표시 행 안에서도 동작한다. */
  customFields?: Record<string, ComponentType<SchemaFormFieldProps>>;
  /** 클라이언트 검증 시점. 기본 `blur`. `submit`이면 클라이언트 검증을 표시하지 않는다(서버 `errors`만). */
  validateOn?: "blur" | "change" | "submit";
  /** `{ } JSON` 전환 토글 표시. 기본 true. */
  rawJsonToggle?: boolean;
  messages?: Partial<SchemaFormMessages>;
  className?: string;

  // --- 스키마 `x-ui` 렌더(모두 선택) ---
  /** `x-ui`·tier 규칙으로 그린다(필수 칩·설명·예시·기본값·고급 접힘). 기본 true. false면 rjsf 기본 모양. */
  xui?: boolean;
  /** 고급 영역 펼침 상태를 localStorage에 `ac.form.advanced.<키>`로 기억한다(폼 종류별 키). 없으면 기억하지 않는다. */
  advancedStorageKey?: string;
  /** 출처 표시 간소화: 지정된 필드만 배지와 [상속으로 되돌리기] 아이콘, 나머지는 입력을 바로 편집(건드리면 이 층에서 지정). 기본 false. */
  compactProvenance?: boolean;

  // --- 출처 표시(R12.3, 모두 선택). `provenance`·`disabledPaths`가 없으면 기존 동작 그대로 ---
  /** 층 목록(낮은 우선순위가 앞). 배지 색 순서와 팝오버 순서를 정한다. */
  layers?: ProvenanceLayer[];
  /** 지금 편집 중인 층 id. `value`는 이 층의 값(지정한 키만)이다. */
  editLayerId?: string;
  /** 잎 값마다의 출처: JSON Pointer -> 층 id. 있으면 출처 표시 모드. */
  provenance?: Record<string, string>;
  /** 유효 값(상속 값 표시용). 없으면 `value`만 보여 준다. */
  effectiveValue?: unknown;
  /** 층별 원본 값(팝오버 "값이 정해지는 과정"용). */
  layerValues?: Record<string, unknown>;
  /** [이 층에서 덮어쓰기]·[이 층에서 지정]. 앱이 `value`에 유효 값을 복사해 돌려준다. */
  onOverride?: (path: string) => void;
  /** [상속으로 되돌리기]. 앱이 `value`에서 해당 키를 지운다. 입력을 비워도 호출하지 않는다. */
  onInherit?: (path: string) => void;
  /** 적용되지 않는 필드: JSON Pointer -> 사유. 하위 경로까지 회색+자물쇠로 비활성. */
  disabledPaths?: Record<string, string>;
  /** 필드 아래 경고 문구(예: 범위를 넓힘). 앱이 문구를 정한다. */
  fieldWarnings?: Record<string, string>;
  /** 라벨 옆 칩 문구(예: 병합 규칙 이름). 앱이 문구를 정한다. */
  mergeNotes?: Record<string, string>;
  /** 팝오버의 층 줄을 눌렀을 때(편집 화면 이동). 없으면 줄은 버튼이 아니다. */
  onOpenLayer?: (layerId: string) => void;
  /** 출처 배지 렌더 주입(예: `@agent-console/ui`의 `ProvenanceBadge`). 없으면 내장 배지. */
  renderProvenanceBadge?: (info: ProvenanceBadgeInfo) => ReactNode;
}
