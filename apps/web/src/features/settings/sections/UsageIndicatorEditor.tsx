import { useMemo } from "react";
import { getContractSchema, type UsageIndicatorColorRule, type UsageIndicatorSettings, type UsageSourceInfo, type UsageWindowSnapshot } from "@agent-console/contracts";
import { Button } from "@agent-console/ui";
import {
  INDICATOR_FIELDS,
  INDICATOR_PLACEMENTS,
  INDICATOR_TONES,
  UsageIndicatorPreview,
  resolveIndicatorSettings,
  resolvePlacement,
  splitFields,
  usageIndicatorMessages,
} from "../../usage";
import { changedKeysOnly } from "./NotificationsSection";

const t = usageIndicatorMessages.settings;

type PropSchema = { title?: string; description?: string; minimum?: number; maximum?: number; enum?: string[] };
const props = (): Record<string, PropSchema> => (getContractSchema("UsageIndicatorSettings") as { properties: Record<string, PropSchema> }).properties;

export interface UsageIndicatorEditorProps {
  /** 저장된 값(생략된 키 = 상속) */
  value: UsageIndicatorSettings | undefined;
  onChange: (next: UsageIndicatorSettings) => void;
  disabled?: boolean;
  /** 관측된 창 id(자동완성) */
  windowIds: readonly string[];
  /** 창 id → 표시 이름 */
  labels: Readonly<Record<string, string>>;
  /** 미리보기 데이터 */
  windows: readonly UsageWindowSnapshot[];
  sources: readonly UsageSourceInfo[];
  primaryOrder: readonly string[];
  staleAfterSeconds: number | null;
  nowMs: number;
  usageHref: string;
}

/**
 * 사용량 표시기 설정 편집기. 제목·설명·범위·기본값은 계약 스키마에서 읽고, 배치·요소·색 어휘는 웹의 표(데이터)에서 온다.
 * 저장 값에는 이미 있던 키와 이번에 바꾼 키만 남긴다(생략 = 상속).
 */
export function UsageIndicatorEditor(p: UsageIndicatorEditorProps) {
  const schema = useMemo(() => props(), []);
  const eff = resolveIndicatorSettings(p.value);
  const set = (patch: Partial<UsageIndicatorSettings>) => p.onChange(changedKeysOnly<UsageIndicatorSettings>(p.value, { ...eff }, { ...eff, ...patch }));
  const off = p.disabled === true || !eff.enabled;
  const { known: placementKnown } = resolvePlacement(eff.placement);
  const { known, unknown } = splitFields(eff.fields);
  const orderedFields = [...known, ...INDICATOR_FIELDS.filter((f) => !known.includes(f))];
  const toggleField = (f: string, on: boolean) => set({ fields: on ? [...eff.fields, f] : eff.fields.filter((x) => x !== f) });
  const moveField = (f: string, d: number) => {
    const list = [...known];
    const i = list.indexOf(f);
    const j = i + d;
    if (i < 0 || j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j]!, list[i]!];
    set({ fields: [...list, ...unknown] });
  };
  const nameOf = (id: string) => p.labels[id] ?? id;
  const addable = p.windowIds.filter((id) => !eff.windows.includes(id));
  const rules = eff.color_rules;
  const setRule = (i: number, patch: Partial<UsageIndicatorColorRule>) => set({ color_rules: rules.map((r, k) => (k === i ? { ...r, ...patch } : r)) });
  const dup = (i: number) => rules.some((r, k) => k !== i && r.at === rules[i]!.at);

  return (
    <div className="usage-ind-editor" data-disabled={eff.enabled ? undefined : "true"}>
      <h3 className="app-block-subtitle">{t.group}</h3>
      <label className="app-check">
        <input type="checkbox" checked={eff.enabled} disabled={p.disabled} onChange={(e) => set({ enabled: e.target.checked })} />
        <strong>{schema["enabled"]?.title}</strong>
      </label>
      <p className="app-muted">{schema["enabled"]?.description}</p>
      <p className="app-muted">{t.pollNotice}</p>
      {eff.enabled ? null : <p className="app-muted">{t.enabledOffNote}</p>}
      <div className="usage-ind-editor-body">
        <fieldset disabled={off}>
          <legend>{schema["placement"]?.title}</legend>
          <select className="ac-input" aria-label={schema["placement"]?.title} value={eff.placement} onChange={(e) => set({ placement: e.target.value })}>
            {placementKnown ? null : <option value={eff.placement}>{eff.placement}</option>}
            {INDICATOR_PLACEMENTS.map((pl) => <option key={pl.id} value={pl.id}>{t.placements[pl.id] ?? pl.id}</option>)}
          </select>
          {placementKnown ? null : <p className="app-field-error" role="alert">{t.placementUnknown(eff.placement)}</p>}
          <p className="app-muted">{t.placementHelp}</p>
        </fieldset>

        <fieldset disabled={off}>
          <legend>{schema["windows"]?.title}</legend>
          <div className="usage-ind-chips">
            {eff.windows.map((id) => (
              <span key={id} className="app-check">
                <strong>{nameOf(id)}</strong>
                {p.windowIds.includes(id) ? null : <span className="app-muted">({t.windowMissing})</span>}
                <Button size="sm" aria-label={t.windowRemove(nameOf(id))} onClick={() => set({ windows: eff.windows.filter((x) => x !== id) })}>×</Button>
              </span>
            ))}
            <select className="ac-input" aria-label={t.windowAdd} value="" onChange={(e) => e.target.value !== "" && set({ windows: [...eff.windows, e.target.value] })}>
              <option value="">{t.windowAddPlaceholder}</option>
              {addable.map((id) => <option key={id} value={id}>{nameOf(id)}</option>)}
            </select>
          </div>
          <p className="app-muted">{eff.windows.length === 0 ? t.windowsEmpty : schema["windows"]?.description}</p>
          <label className="app-check">
            {schema["max_items"]?.title}
            <input
              type="number"
              className="ac-input"
              min={schema["max_items"]?.minimum}
              max={schema["max_items"]?.maximum}
              value={eff.max_items}
              onChange={(e) => {
                const n = Math.round(Number(e.target.value));
                if (Number.isFinite(n)) set({ max_items: Math.min(schema["max_items"]?.maximum ?? 6, Math.max(schema["max_items"]?.minimum ?? 1, n)) });
              }}
            />
          </label>
        </fieldset>

        <fieldset disabled={off}>
          <legend>{schema["fields"]?.title}</legend>
          <ol className="app-order">
            {orderedFields.map((f) => {
              const on = known.includes(f);
              const label = t.fields[f] ?? f;
              const i = known.indexOf(f);
              return (
                <li key={f} className="app-order-row">
                  <label className="app-check">
                    <input type="checkbox" checked={on} onChange={(e) => toggleField(f, e.target.checked)} />
                    {label}
                  </label>
                  <Button size="sm" disabled={!on || i === 0} aria-label={t.fieldUp(label)} onClick={() => moveField(f, -1)}>↑</Button>
                  <Button size="sm" disabled={!on || i === known.length - 1} aria-label={t.fieldDown(label)} onClick={() => moveField(f, 1)}>↓</Button>
                </li>
              );
            })}
          </ol>
          {unknown.map((f) => <p key={f} className="app-field-error">{t.fieldUnknown(f)}</p>)}
        </fieldset>

        <fieldset disabled={off}>
          <legend>{schema["value_mode"]?.title}</legend>
          <div className="usage-ind-chips" role="radiogroup" aria-label={schema["value_mode"]?.title}>
            {(schema["value_mode"]?.enum ?? []).map((m) => (
              <label key={m} className="app-check">
                <input type="radio" name="usage-ind-mode" checked={eff.value_mode === m} onChange={() => set({ value_mode: m as "remaining" | "used" })} />
                {t.modes[m] ?? m}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset disabled={off}>
          <legend>{schema["color_rules"]?.title}</legend>
          {rules.map((r, i) => (
            <div key={i} className="usage-ind-rule-row">
              <label className="app-check">
                {t.ruleAt}
                <input
                  type="number"
                  className="ac-input"
                  min={0}
                  max={100}
                  value={Math.round(r.at * 100)}
                  aria-invalid={dup(i) ? "true" : undefined}
                  onChange={(e) => {
                    const n = Number(e.target.value);
                    if (Number.isFinite(n)) setRule(i, { at: Math.min(100, Math.max(0, Math.round(n))) / 100 });
                  }}
                />
              </label>
              <select className="ac-input" aria-label={t.ruleTone} value={r.tone} onChange={(e) => setRule(i, { tone: e.target.value })}>
                {r.tone in INDICATOR_TONES ? null : <option value={r.tone}>{r.tone}</option>}
                {Object.keys(INDICATOR_TONES).map((id) => <option key={id} value={id}>{usageIndicatorMessages.tones[id] ?? id}</option>)}
              </select>
              <Button size="sm" aria-label={t.ruleRemove} onClick={() => set({ color_rules: rules.filter((_, k) => k !== i) })}>🗑</Button>
              {dup(i) ? <span className="app-field-error" role="alert">{t.ruleDuplicate}</span> : null}
              {r.tone in INDICATOR_TONES ? null : <span className="app-field-error">{t.ruleToneUnknown(r.tone)}</span>}
            </div>
          ))}
          <div>
            <Button size="sm" onClick={() => set({ color_rules: [...rules, { at: 0.8, tone: Object.keys(INDICATOR_TONES)[0] ?? "" }] })}>{t.ruleAdd}</Button>
          </div>
          <p className="app-muted usage-ind-pop-line">{rules.length === 0 ? schema["color_rules"]?.description : t.ruleNote}</p>
        </fieldset>

        <label className="app-check">
          <input type="checkbox" checked={eff.hide_when_empty} disabled={off} onChange={(e) => set({ hide_when_empty: e.target.checked })} />
          {schema["hide_when_empty"]?.title}
        </label>
        <label className="app-check">
          <input type="checkbox" checked={eff.also_in_title} disabled={off} onChange={(e) => set({ also_in_title: e.target.checked })} />
          {schema["also_in_title"]?.title}
        </label>
      </div>
      <h4 className="app-block-subtitle">{t.preview}</h4>
      <UsageIndicatorPreview
        settings={eff}
        windows={p.windows}
        sources={p.sources}
        labels={p.labels}
        primaryOrder={p.primaryOrder}
        staleAfterSeconds={p.staleAfterSeconds}
        nowMs={p.nowMs}
        href={p.usageHref}
      />
    </div>
  );
}
