/**
 * 범위 고르기(새 항목·옮기기). 선택지 = 지금 있는 범위 + 켜진 범위 종류. 범위 종류 이름은 모르고 서버 목록(`kinds`)만 본다.
 * 범위 id가 필요한 종류(id 틀이 비어 있지 않은 종류)를 고르면 id 입력이 나타나고, 정의 목록 역할이 있으면 이름으로 고르는 보조 선택이 생긴다.
 */
import { useId, useMemo } from "react";
import { templateFields, scopeKey } from "@agent-console/memory-view";
import type { MemoryScopeKindInfo, MemoryScopeRef, MemoryScopeSummary } from "@agent-console/contracts/memory";
import { memoryMessages as t } from "./messages";

export interface ScopePickerState {
  /** `scope:<종류>:<id>`(있는 범위) · `kind:<종류>`(종류만) · ""(고르지 않음) */
  choice: string;
  /** 종류만 골랐을 때의 범위 id */
  id: string;
}

export const EMPTY_PICK: ScopePickerState = { choice: "", id: "" };

const SCOPE = "scope:";
const KIND = "kind:";

/** 선택 상태 → 범위. 아직 정해지지 않았거나 id가 필요한데 비었으면 null. */
export function pickedScope(state: ScopePickerState, kinds: readonly MemoryScopeKindInfo[]): MemoryScopeRef | null {
  if (state.choice.startsWith(SCOPE)) {
    const rest = state.choice.slice(SCOPE.length);
    const at = rest.indexOf(":");
    return at <= 0 ? null : { kind: rest.slice(0, at), id: rest.slice(at + 1) };
  }
  if (state.choice.startsWith(KIND)) {
    const kind = state.choice.slice(KIND.length);
    const info = kinds.find((k) => k.kind === kind);
    if (info === undefined) return null;
    if ((info.id ?? "") === "") return { kind, id: "" };
    return state.id.trim() === "" ? null : { kind, id: state.id.trim() };
  }
  return null;
}

/** 범위 → 선택 상태(있는 범위로). */
export function pickOf(scope: MemoryScopeRef | null): ScopePickerState {
  return scope === null ? EMPTY_PICK : { choice: `${SCOPE}${scope.kind}:${scope.id ?? ""}`, id: "" };
}

export interface ScopePickerProps {
  label: string;
  kinds: readonly MemoryScopeKindInfo[];
  scopes: readonly MemoryScopeSummary[];
  state: ScopePickerState;
  onChange: (next: ScopePickerState) => void;
  labelOf: (scope: MemoryScopeRef) => string;
  /** 맥락 필드 이름 → [id, 이름] 보조 선택지 */
  pickers?: Readonly<Record<string, readonly (readonly [string, string])[]>>;
  /** 이 범위를 고른 채 두는 선택지(예: 옮기기에서 지금 범위). */
  disabled?: boolean;
}

export function ScopePicker({ label, kinds, scopes, state, onChange, labelOf, pickers = {}, disabled = false }: ScopePickerProps) {
  const uid = useId();
  const writable = useMemo(() => kinds.filter((k) => k.disabled !== true && k.id !== null && k.id !== undefined), [kinds]);
  const known = useMemo(() => scopes.filter((s) => s.kind_known !== false && writable.some((k) => k.kind === s.scope.kind)), [scopes, writable]);
  const knownKeys = new Set(known.map((s) => scopeKey(s.scope)));
  // 지금 값이 선택지에 없으면(예: 옮기기에서 현재 범위, 비어 있는 범위) 그 값을 그대로 선택지에 더한다.
  const extra = state.choice.startsWith(SCOPE) && !knownKeys.has(state.choice.slice(SCOPE.length)) ? pickedScope(state, kinds) : null;
  const selectedKind = state.choice.startsWith(KIND) ? kinds.find((k) => k.kind === state.choice.slice(KIND.length)) : undefined;
  const needsId = selectedKind !== undefined && (selectedKind.id ?? "") !== "";
  const template = selectedKind?.id ?? "";
  const fields = templateFields(template);
  const picker = fields.length === 1 ? (pickers[fields[0] as string] ?? null) : null;
  const helpId = `${uid}-help`;
  return (
    <div className="mem-field">
      <label htmlFor={`${uid}-select`} className="mem-label">{label}</label>
      <select id={`${uid}-select`} className="mem-input" value={state.choice} disabled={disabled} onChange={(e) => onChange({ choice: e.target.value, id: "" })}>
        <option value="">{t.newEntry.scopeNone}</option>
        {extra !== null ? <option value={state.choice}>{labelOf(extra)}</option> : null}
        {known.map((s) => (
          <option key={scopeKey(s.scope)} value={`${SCOPE}${scopeKey(s.scope)}`}>{labelOf(s.scope)}</option>
        ))}
        {writable.map((k) => (
          <option key={`kind-${k.kind}`} value={`${KIND}${k.kind}`}>{(k.id ?? "") === "" ? k.label : `${k.label} — ${t.move.other}`}</option>
        ))}
      </select>
      {needsId ? (
        <div className="mem-subfield">
          <label htmlFor={`${uid}-id`} className="mem-label">{t.newEntry.scopeId}</label>
          <input id={`${uid}-id`} className="mem-input mem-mono" value={state.id} aria-describedby={helpId} onChange={(e) => onChange({ ...state, id: e.target.value })} />
          {picker !== null && picker.length > 0 ? (
            <select aria-label={t.newEntry.scopeIdPick} className="mem-input" value="" onChange={(e) => e.target.value !== "" && onChange({ ...state, id: e.target.value })}>
              <option value="">{t.newEntry.scopeIdPick}</option>
              {picker.map(([id, name]) => (
                <option key={id} value={id}>{name}</option>
              ))}
            </select>
          ) : null}
          <span id={helpId} className="mem-help">
            {t.newEntry.scopeIdHelp(template)}
          </span>
        </div>
      ) : null}
    </div>
  );
}
