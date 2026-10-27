import { useCallback, useMemo } from "react";
import { getContractSchema } from "@agent-console/contracts";
import { SchemaForm, type FormError, type SchemaFormFieldProps, type SchemaFormWidgetProps, type UiSchema } from "@agent-console/schema-form";
import { Switch } from "@agent-console/ui";
import { useApi } from "../../app/ApiContext";
import { useApiQuery } from "../../app/queries";
import { ProfilesPanel, type ProfilesPanelProps } from "./ProfilesPanel";
import { archSettingsMessages as t, ORIGIN } from "./messages";
import { buildRows, type ProfilesMap } from "./profileLogic";

/** 위젯 이름(계약 `x-ui.widget`). 스키마가 이 이름을 달고 있으면 프로필 목록·편집기로 그린다. */
export const PROFILES_WIDGET = "architecture-profiles";
const SWITCH_WIDGET = "ac-boolean-switch";
const PROFILE_SELECT_WIDGET = "ac-profile-select";

const archKeys = { profiles: () => ["architecture", "profiles"] as const };

type Obj = Record<string, unknown>;
const asObj = (v: unknown): Obj => (typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Obj) : {});

export interface ArchitectureSettingsEditorProps {
  /** 설정 문서의 `architecture` 값(편집 중 초안, 생략 가능) */
  value: unknown;
  /** 저장된 `architecture` 값(저장 전 변경 표시·지우기 방식) */
  saved: unknown;
  onChange: (next: Obj) => void;
  errors?: FormError[];
  disabled?: boolean;
  /** 편집기 검사 지연(ms) */
  checkDelayMs?: number;
}

type FieldCtx = Omit<ProfilesPanelProps, "profiles" | "saved" | "onChange" | "disabled" | "checkDelayMs">;

function ProfilesField({ value, onChange, options, disabled }: SchemaFormFieldProps) {
  const ctx = options["ctx"] as FieldCtx;
  const saved = options["saved"] as ProfilesMap;
  const delay = options["delay"] as number | undefined;
  return <ProfilesPanel {...ctx} profiles={asObj(value)} saved={saved} onChange={(n) => onChange(n)} disabled={disabled} {...(delay === undefined ? {} : { checkDelayMs: delay })} />;
}

function SwitchWidget({ id, value, onChange, label, disabled, readonly }: SchemaFormWidgetProps) {
  return <Switch checked={value === true} onChange={onChange} ariaLabel={label} onText="켜짐" offText="꺼짐" disabled={disabled || readonly} className={id} />;
}

interface Choice {
  value: string;
  label: string;
}

function ProfileSelectWidget({ id, value, onChange, onBlur, label, disabled, readonly, options }: SchemaFormWidgetProps) {
  const choices = (options["choices"] as Choice[] | undefined) ?? [];
  const current = typeof value === "string" ? value : "";
  const missing = current !== "" && !choices.some((c) => c.value === current);
  return (
    <span className="arch-settings-select">
      <select id={id} aria-label={label} value={current} disabled={disabled || readonly} onBlur={onBlur} onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}>
        <option value="">{t.defaultProfile.first}</option>
        {missing ? <option value={current}>{current}</option> : null}
        {choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
      </select>
      {missing ? <span className="arch-settings-chip">{t.defaultProfile.missing}</span> : null}
    </span>
  );
}

const WIDGETS = { [SWITCH_WIDGET]: SwitchWidget, [PROFILE_SELECT_WIDGET]: ProfileSelectWidget };
const FIELDS = { [PROFILES_WIDGET]: ProfilesField };

/** 스키마 속성 중 `x-ui.widget`이 등록된 필드는 그 필드로, 불리언은 스위치로, 기본 프로필 값은 목록 선택으로 그린다. */
function buildUi(schema: Obj, ctx: FieldCtx, saved: ProfilesMap, choices: Choice[], delay: number | undefined): UiSchema {
  const props = asObj(schema["properties"]);
  const ui: Obj = {};
  for (const [key, raw] of Object.entries(props)) {
    const node = asObj(raw);
    const widget = asObj(node["x-ui"])["widget"];
    if (typeof widget === "string" && widget in FIELDS) ui[key] = { "ui:field": widget, "ui:options": { ctx, saved, delay } };
    else if (node["type"] === "boolean") ui[key] = { "ui:widget": SWITCH_WIDGET };
    else if (key === "default_profile") ui[key] = { "ui:widget": PROFILE_SELECT_WIDGET, "ui:options": { choices } };
  }
  return ui as UiSchema;
}

/**
 * 폼이 마운트 때 채우는 스키마 기본값(사용자가 건드리지 않은 키)을 걷어 낸다. 걷지 않으면 열기만 해도 "저장되지 않은 변경"이 된다.
 * 이미 초안에 있던 키는 그대로 둔다.
 */
export function withoutFilledDefaults(next: Obj, draft: Obj, schema: Obj): Obj {
  const props = asObj(schema["properties"]);
  const out: Obj = { ...next };
  for (const [key, raw] of Object.entries(props)) {
    if (key in draft || !(key in out)) continue;
    const node = asObj(raw);
    const def = "default" in node ? node["default"] : null;
    if (JSON.stringify(out[key]) === JSON.stringify(def)) delete out[key];
  }
  return out;
}

/**
 * 설정 › 구조도 본문: 계약 `ArchitectureSettings` 스키마 폼(기본 프로필 사용·기본 프로필 선택) + 프로필 목록·편집기 위젯.
 * 프로필 목록은 서버 병합 응답이고 이름은 모두 데이터다. 설정 문서 전체와 저장은 이 컴포넌트가 모른다(값·콜백만).
 */
export function ArchitectureSettingsEditor({ value, saved, onChange, errors, disabled, checkDelayMs }: ArchitectureSettingsEditorProps) {
  const { rest } = useApi();
  const list = useApiQuery(archKeys.profiles(), (r) => r.listArchitectureProfiles(), { retry: false });
  const draft = asObj(value);
  const savedObj = asObj(saved);
  const includeDefaults = draft["include_defaults"] !== false;
  const profiles = asObj(draft["profiles"]);
  const savedProfiles = asObj(savedObj["profiles"]);
  const { rows, disabled: disabledRows } = useMemo(() => buildRows(list.data, profiles, savedProfiles, includeDefaults, { isDefault: (o) => o === ORIGIN.default, user: ORIGIN.user }), [list.data, profiles, savedProfiles, includeDefaults]);
  const loadBody = useCallback(async (id: string) => (await rest.getArchitectureProfile(id)).profile, [rest]);
  const check = useCallback((body: Parameters<typeof rest.checkArchitectureProfile>[0]) => rest.checkArchitectureProfile(body), [rest]);
  // 폼 머리(제목·설명)는 설정 섹션 머리가 이미 보이므로 뺀다.
  const schema = useMemo(() => {
    const full = { ...(getContractSchema("ArchitectureSettings") as unknown as Obj) };
    delete full["title"];
    delete full["description"];
    return full;
  }, []);
  const ctx = useMemo<FieldCtx>(
    () => ({
      rows,
      disabledRows,
      includeDefaults,
      onEnableDefaults: () => onChange({ ...draft, include_defaults: true }),
      status: list.isPending ? "loading" : list.isError ? "error" : "ready",
      error: list.error,
      onRetry: () => void list.refetch(),
      loadBody,
      check,
      defaultsPending: list.data !== undefined && list.data.include_defaults !== includeDefaults,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rows, disabledRows, includeDefaults, onChange, draft, list.isPending, list.isError, list.error, list.data, loadBody, check],
  );
  const choices = useMemo(() => rows.map((r) => ({ value: r.id, label: `${r.title} (${r.id})` })), [rows]);
  const ui = useMemo(() => buildUi(schema, ctx, savedProfiles, choices, checkDelayMs), [schema, ctx, savedProfiles, choices, checkDelayMs]);
  return (
    <div className="arch-settings" data-testid="arch-settings">
      <SchemaForm
        schema={schema as never}
        uiSchema={ui}
        value={draft}
        onChange={(next) => {
          const merged = withoutFilledDefaults(asObj(next), draft, schema);
          if (JSON.stringify(merged) !== JSON.stringify(draft)) onChange(merged);
        }}
        customWidgets={WIDGETS}
        customFields={FIELDS}
        rawJsonToggle={false}
        idPrefix="arch-settings"
        {...(errors ? { errors } : {})}
        {...(disabled === undefined ? {} : { disabled })}
      />
    </div>
  );
}
