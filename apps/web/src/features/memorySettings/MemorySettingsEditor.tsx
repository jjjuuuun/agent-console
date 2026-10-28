import { useCallback, useEffect, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ConditionSpec, Issue } from "@agent-console/contracts";
import { getContractSchema } from "@agent-console/contracts";
import { SchemaForm, getDefaultValue, type FormError, type UiSchema } from "@agent-console/schema-form";
import { scopeLabel } from "@agent-console/memory-view";
import type { MemoryScopeRef } from "@agent-console/contracts/memory";
import { useApi } from "../../app/ApiContext";
import { useApiQuery } from "../../app/queries";
import { formatInterval } from "./formatInterval";
import { memorySettingsMessages } from "./messages";
import { useModule } from "../../modules";
import { sameValue } from "../architectureSettings";
import { summarizeConditions, useConditionOperators } from "../delegation";
import { ROUTE_ROLES, routePath, useRouteOn } from "../library";
import { IMPORTED_AUTHOR_KIND, MEMORY_PARAMS, MEMORY_ROLE, memoryKeys, useMemoryContext, useMemoryKinds, useMemoryScopes } from "../memory";
import { LimitsBlock } from "./LimitsBlock";
import { conditionFieldOf } from "./RuleEditorDialog";
import { RetentionPanel } from "./RetentionPanel";
import { ScopeKindsPanel } from "./ScopeKindsPanel";
import { CHOICE_CARDS_WIDGET, ChoiceCardsWidget, SWITCH_WIDGET, SwitchWidget } from "./SchemaWidgets";
import { buildKindRows, entriesByKind } from "./kindRows";
import { LIMITS, SETTINGS_KEYS, WIDGETS } from "./memorySettingsConfig";
import { useDebouncedCheck } from "./useDebouncedCheck";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const asObj = (v: unknown): Obj => (isObj(v) ? v : {});
const asList = (v: unknown): Obj[] => (Array.isArray(v) ? v.filter(isObj) : []);
const escapePointer = (s: string) => s.replace(/~/g, "~0").replace(/\//g, "~1");

export interface MemorySettingsEditorProps {
  /** 설정 문서의 `memory` 값(편집 중 초안, 생략 가능) */
  value: unknown;
  /** 저장된 `memory` 값 */
  saved: unknown;
  /** 설정 문서에 저장하지 않은 변경이 있다(정리 적용을 막는다) */
  dirty: boolean;
  onChange: (next: Obj) => void;
  errors?: FormError[];
  disabled?: boolean;
  /** 검사 지연(ms, 테스트에서 줄인다) */
  checkDelayMs?: number;
}

interface Ctx {
  kinds: React.ComponentProps<typeof ScopeKindsPanel>;
  retention: React.ComponentProps<typeof RetentionPanel>;
}

/** 스키마 속성이 가리키는 위젯 이름(`x-ui.widget`, 계약 `MemorySettings`가 준다) */
function widgetOf(node: Obj): string | undefined {
  const widget = asObj(node["x-ui"])["widget"];
  return typeof widget === "string" ? widget : undefined;
}


const WIDGET_TABLE = { [SWITCH_WIDGET]: SwitchWidget, [CHOICE_CARDS_WIDGET]: ChoiceCardsWidget };

/** 표·목록 위젯이 그리는 속성 키(폼 엔진이 값을 건드리지 않게 폼 스키마에서 뺀다) */
function panelKeys(schema: Obj): { kinds: string[]; retention: string[] } {
  const out = { kinds: [] as string[], retention: [] as string[] };
  for (const [key, raw] of Object.entries(asObj(schema["properties"]))) {
    const widget = widgetOf(asObj(raw));
    if (widget === WIDGETS.scopeKinds) out.kinds.push(key);
    else if (widget === WIDGETS.retentionRules) out.retention.push(key);
  }
  return out;
}

/**
 * 폼 스키마: 위젯이 그리는 속성은 빼고, 남은 단순 속성은 모두 본문에 보인다(이 화면은 접힌 "고급 설정" 없이 한 번에 보여 준다, 명세 §10.2).
 * 서버가 준 tier는 데이터지만 이 섹션은 속성이 몇 개 안 되므로 접지 않는다.
 */
function formSchemaOf(schema: Obj, omit: ReadonlySet<string>): Obj {
  const props: Obj = {};
  for (const [key, raw] of Object.entries(asObj(schema["properties"]))) {
    if (omit.has(key)) continue;
    const node = asObj(raw);
    props[key] = { ...node, "x-ui": { ...asObj(node["x-ui"]), tier: "basic" } };
  }
  return { ...schema, properties: props };
}

function buildUi(schema: Obj): UiSchema {
  const ui: Obj = {};
  for (const [key, raw] of Object.entries(asObj(schema["properties"]))) {
    const node = asObj(raw);
    if (node["type"] === "boolean") ui[key] = { "ui:widget": SWITCH_WIDGET };
    else if (Array.isArray(node["enum"])) ui[key] = { "ui:widget": CHOICE_CARDS_WIDGET };
  }
  return ui as UiSchema;
}

/** 초안에 없던 키가 스키마 기본값과 같으면 걷어 낸다. 이미 초안에 있던 키는 그대로 둔다. */
function withoutFilledDefaults(next: Obj, draft: Obj, defaults: Obj): Obj {
  const out: Obj = { ...next };
  for (const key of Object.keys(out)) {
    if (key in draft) continue;
    if (JSON.stringify(out[key]) === JSON.stringify(defaults[key])) delete out[key];
  }
  return out;
}

/** 모듈 옵션(설치자 한도). 모듈은 역할로 찾는다(코드에 모듈 id가 없다). */
function useInstallerOptions() {
  const lookup = useModule(MEMORY_ROLE);
  const moduleId = lookup.modules[0]?.id ?? "";
  const q = useApiQuery(["memory", "settings", "options", moduleId], (rest) => rest.getModuleOptions(moduleId), { enabled: moduleId !== "", retry: false, staleTime: 60_000, meta: { silentBackgroundError: true } });
  return q.data;
}

/**
 * 설정 › 메모리 본문: 계약 `MemorySettings` 스키마 폼(스위치·비밀 처리·버전 보관 수) + 범위 종류 표 + 정리 규칙 + 설치자 한도.
 * 범위 종류·규칙은 서버가 병합한 목록과 사용자 데이터이며 이름은 코드에 없다. 설정 문서 전체와 저장은 이 컴포넌트가 모른다(값·콜백만).
 */
export function MemorySettingsEditor({ value, saved, dirty, onChange, errors, disabled, checkDelayMs }: MemorySettingsEditorProps) {
  const { rest } = useApi();
  const qc = useQueryClient();
  const draft = asObj(value);
  const savedObj = asObj(saved);
  const kindsQ = useMemoryKinds();
  const scopesQ = useMemoryScopes();
  const options = useInstallerOptions();
  const ctxData = useMemoryContext();
  const memoryOn = useRouteOn(ROUTE_ROLES.memory);
  const operators = useConditionOperators();

  // 저장된 설정이 바뀌면(저장·되돌리기) 서버 병합 목록을 다시 읽는다.
  const savedKey = JSON.stringify(savedObj);
  useEffect(() => {
    void qc.invalidateQueries({ queryKey: memoryKeys.root });
  }, [savedKey, qc]);

  const includeDefaults = draft[SETTINGS_KEYS.includeDefaults] !== false;
  const kindsMap = asObj(draft[SETTINGS_KEYS.scopeKinds]);
  const savedKinds = asObj(savedObj[SETTINGS_KEYS.scopeKinds]);
  const counts = useMemo(() => entriesByKind(scopesQ.data), [scopesQ.data]);
  const { rows, disabled: disabledRows } = buildKindRows(kindsQ.data?.kinds, kindsMap, savedKinds, includeDefaults, counts, sameValue);

  const schema = useMemo(() => {
    const full = { ...(getContractSchema("MemorySettings") as unknown as Obj) };
    delete full["title"];
    delete full["description"];
    return full;
  }, []);
  // 폼이 마운트 때 채우는 스키마 기본값(사용자가 건드리지 않은 키)은 초안에 넣지 않는다(열기만 해도 "저장되지 않은 변경"이 되지 않게).
  const defaults = useMemo(() => asObj(getDefaultValue(schema as never)), [schema]);
  const kindSpecSchema = useMemo(() => asObj(getContractSchema("MemoryScopeKindSpec") as unknown), []);
  const ruleSchema = useMemo(() => {
    const rules = asObj(asObj(asObj(getContractSchema("MemoryRetentionSettings") as unknown)["properties"])[SETTINGS_KEYS.rules]);
    const items = asObj(rules["items"]);
    const ref = typeof items["$ref"] === "string" ? items["$ref"].split("/").pop() : undefined;
    return ref === undefined ? asObj(getContractSchema("MemoryRetentionRule") as unknown) : asObj(getContractSchema(ref) as unknown);
  }, []);
  const templateExamples = useMemo(() => {
    const node = asObj(asObj(kindSpecSchema["properties"])["id"]);
    const list = Array.isArray(node["examples"]) ? node["examples"].filter((v): v is string => typeof v === "string") : [];
    const one = asObj(node["x-ui"])["example"];
    return list.length > 0 ? list : typeof one === "string" ? [one] : [];
  }, [kindSpecSchema]);

  // 설정 섹션 전체 검사(문제 수 표시): 멈춘 뒤 한 번.
  const whole = useDebouncedCheck(JSON.stringify(draft), () => rest.checkMemorySettings(draft), true, checkDelayMs ?? LIMITS.checkDelayMs);
  const problemCounts = (() => {
    const out = new Map<string, number>();
    for (const r of [...rows, ...disabledRows]) {
      const needle = `/${SETTINGS_KEYS.scopeKinds}/${escapePointer(r.id)}`;
      const n = whole.issues.filter((i: Issue) => i.path != null && (i.path.includes(`${needle}/`) || i.path.endsWith(needle))).length;
      if (n > 0) out.set(r.id, n);
    }
    return out;
  })();

  const retention = asObj(draft[SETTINGS_KEYS.retention]);
  const interval = options?.values?.["retention_interval_seconds"];
  const everyText = typeof interval === "number" && interval > 0 ? formatInterval(interval, memorySettingsMessages.retention.unit) : null;
  const scopeText = useCallback(
    (scope: MemoryScopeRef) => {
      const kinds = kindsQ.data?.kinds ?? [];
      const kind = kinds.find((k) => k.kind === scope.kind);
      return scopeLabel(scope, kind, ctxData.resolvers, kind !== undefined).text;
    },
    [kindsQ.data, ctxData.resolvers],
  );
  const whenKey = conditionFieldOf(ruleSchema);
  const checkWith = (patch: Obj) => rest.checkMemorySettings({ ...draft, ...patch });
  const kindsCtx: Ctx["kinds"] = {
    kinds: kindsMap,
    saved: savedKinds,
    onChange: (next) => onChange({ ...draft, [SETTINGS_KEYS.scopeKinds]: next }),
    rows,
    disabledRows,
    includeDefaults,
    onEnableDefaults: () => onChange({ ...draft, [SETTINGS_KEYS.includeDefaults]: true }),
    status: kindsQ.isPending ? "loading" : kindsQ.isError ? "error" : "ready",
    error: kindsQ.error,
    onRetry: () => void kindsQ.refetch(),
    defaultsPending: kindsQ.data !== undefined && kindsQ.data.include_defaults !== undefined && kindsQ.data.include_defaults !== includeDefaults,
    examples: templateExamples,
    problemCounts,
    check: (id, spec) => checkWith({ [SETTINGS_KEYS.scopeKinds]: { ...kindsMap, [id]: spec } }),
    ...(disabled === undefined ? {} : { disabled }),
    ...(checkDelayMs === undefined ? {} : { checkDelayMs }),
  };
  const retentionCtx: Ctx["retention"] = {
    rules: asList(retention[SETTINGS_KEYS.rules]),
    savedRules: asList(asObj(savedObj[SETTINGS_KEYS.retention])[SETTINGS_KEYS.rules]),
    onChange: () => undefined,
    ruleSchema,
    dirty,
    everyText,
    summarize: (rule) => {
      const when = whenKey === undefined ? undefined : rule[whenKey];
      const s = summarizeConditions(isObj(when) ? (when as ConditionSpec) : undefined, operators.operators, undefined);
      return s.empty ? "" : s.text;
    },
    check: (rules) => checkWith({ [SETTINGS_KEYS.retention]: { ...retention, [SETTINGS_KEYS.rules]: rules } }),
    plan: (rules) => rest.planMemoryRetention({ rules, limit: LIMITS.planLimit }),
    apply: () => rest.applyMemoryRetention(),
    scopeText,
    resultHref: memoryOn ? `${routePath(ROUTE_ROLES.memory)}?${MEMORY_PARAMS.authorKind}=${encodeURIComponent(IMPORTED_AUTHOR_KIND)}` : null,
    onApplied: () => void qc.invalidateQueries({ queryKey: memoryKeys.root }),
    ...(disabled === undefined ? {} : { disabled }),
    ...(checkDelayMs === undefined ? {} : { checkDelayMs }),
  };
  const panels = useMemo(() => panelKeys(schema), [schema]);
  const formSchema = useMemo(() => formSchemaOf(schema, new Set([...panels.kinds, ...panels.retention])), [schema, panels]);
  const ui = useMemo(() => buildUi(formSchema), [formSchema]);
  const formValue = useMemo(() => Object.fromEntries(Object.entries(draft).filter(([k]) => k in asObj(formSchema["properties"]))), [draft, formSchema]);
  const optionTitles = useMemo(() => {
    const props = asObj(asObj(options?.schema)["properties"]);
    return Object.fromEntries(Object.entries(props).flatMap(([k, v]) => (typeof asObj(v)["title"] === "string" ? [[k, asObj(v)["title"] as string]] : [])));
  }, [options]);
  return (
    <div className="memset" data-testid="memset">
      <SchemaForm
        schema={formSchema as never}
        uiSchema={ui}
        value={formValue}
        onChange={(next) => {
          const merged = { ...draft, ...withoutFilledDefaults(asObj(next), formValue, defaults) };
          for (const k of Object.keys(asObj(formSchema["properties"]))) if (!(k in asObj(next))) delete merged[k];
          if (JSON.stringify(merged) !== JSON.stringify(draft)) onChange(merged);
        }}
        customWidgets={WIDGET_TABLE}
        rawJsonToggle={false}
        idPrefix="memset"
        {...(errors ? { errors } : {})}
        {...(disabled === undefined ? {} : { disabled })}
      />
      {panels.kinds.length > 0 ? <ScopeKindsPanel {...kindsCtx} /> : null}
      {panels.retention.length > 0 ? (
        <RetentionPanel
          {...retentionCtx}
          onChange={(rules) => onChange({ ...draft, [SETTINGS_KEYS.retention]: { ...retention, [SETTINGS_KEYS.rules]: rules } })}
        />
      ) : null}
      <LimitsBlock values={options?.values} titles={optionTitles} />
    </div>
  );
}

