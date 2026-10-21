import { useId, useState, type KeyboardEvent } from "react";
import { useImeGuard } from "../../lib/ime";
import type { ConditionOperatorDescriptor } from "./conditions";
import { guessFreeKind, valueKindOf } from "./conditions";
import { delegationMessages } from "./messages";

type M = typeof delegationMessages.condition;
type FreeKind = "string" | "number" | "boolean" | "json";

export interface ValueEditorProps {
  /** 현재 값(없으면 undefined) */
  value: unknown;
  onChange(next: unknown): void;
  /** 고른 연산자. 없으면(자유 입력·아직 안 고름) 형식 선택을 보인다 */
  operator: Pick<ConditionOperatorDescriptor, "value_schema"> | undefined;
  disabled?: boolean | undefined;
  /** 이 입력의 접근성 이름 */
  label: string;
  /** 오류 줄(서버 이슈) */
  error?: string | undefined;
  messages?: M;
  id: string;
}

const stringify = (v: unknown): string => {
  try {
    return v === undefined ? "" : (JSON.stringify(v, null, 2) ?? "");
  } catch {
    return String(v);
  }
};

/**
 * 조건 값 입력. 연산자 `value_schema`의 `type`으로 모양을 정한다(문자열·숫자·불리언·배열 칩·객체 JSON·값 없음).
 * 스키마가 비었거나 연산자가 없으면 형식 선택 `[문자열|숫자|참거짓|JSON]`을 앞에 붙인다. 한글 조합 중에는 Enter를 처리하지 않는다.
 */
export function ValueEditor({ value, onChange, operator, disabled, label, error, messages = delegationMessages.condition, id }: ValueEditorProps) {
  const kind = operator === undefined ? undefined : valueKindOf(operator.value_schema);
  const [free, setFree] = useState<FreeKind>(() => guessFreeKind(value));
  const m = messages;
  if (kind === "none") {
    return (
      <div className="dlg-value" data-kind="none">
        <input className="ac-input" disabled aria-label={label} placeholder={m.valueNone} />
        <span className="app-muted dlg-note">{m.valueNone}</span>
      </div>
    );
  }
  const effective: FreeKind | "array" = kind === undefined ? free : kind === "array" ? "array" : kind === "json" ? "json" : kind;
  const input = (() => {
    switch (effective) {
      case "number":
        return <NumberInput id={id} value={value} onChange={onChange} disabled={disabled} label={label} />;
      case "boolean":
        return (
          <label className="app-check">
            <input id={id} type="checkbox" checked={value === true} disabled={disabled} aria-label={label} onChange={(e) => onChange(e.target.checked)} />
            {m.valueTrue}
          </label>
        );
      case "array":
        return <ArrayInput id={id} value={value} onChange={onChange} disabled={disabled} label={label} messages={m} itemsSchema={itemsOf(operator)} />;
      case "json":
        return <JsonInput id={id} value={value} onChange={onChange} disabled={disabled} label={label} messages={m} />;
      default:
        return <TextInput id={id} value={value} onChange={onChange} disabled={disabled} label={label} />;
    }
  })();
  return (
    <div className="dlg-value" data-kind={effective}>
      {kind === undefined ? (
        <select
          className="dlg-value-kind"
          aria-label={`${label} — ${m.valueType.label}`}
          value={free}
          disabled={disabled}
          onChange={(e) => {
            const next = e.target.value as FreeKind;
            setFree(next);
            onChange(convertFree(value, next));
          }}
        >
          <option value="string">{m.valueType.string}</option>
          <option value="number">{m.valueType.number}</option>
          <option value="boolean">{m.valueType.boolean}</option>
          <option value="json">{m.valueType.json}</option>
        </select>
      ) : null}
      {input}
      {error ? <span className="lib-field-error" role="alert">{error}</span> : null}
    </div>
  );
}

function itemsOf(op: Pick<ConditionOperatorDescriptor, "value_schema"> | undefined): "number" | "string" {
  const items = (op?.value_schema as { items?: { type?: unknown } } | undefined)?.items;
  const t = items?.type;
  return t === "number" || t === "integer" ? "number" : "string";
}

/** 자유 입력에서 형식을 바꿀 때 값을 새 형식으로 옮긴다(옮길 수 없으면 비운다). */
export function convertFree(value: unknown, to: FreeKind): unknown {
  if (value === undefined) return to === "boolean" ? false : undefined;
  switch (to) {
    case "string":
      return typeof value === "string" ? value : typeof value === "number" || typeof value === "boolean" ? String(value) : stringify(value);
    case "number": {
      const n = typeof value === "number" ? value : Number(typeof value === "string" ? value : NaN);
      return Number.isFinite(n) ? n : undefined;
    }
    case "boolean":
      return value === true || value === "true";
    default:
      return value;
  }
}

function TextInput({ id, value, onChange, disabled, label }: { id: string; value: unknown; onChange(v: unknown): void; disabled?: boolean | undefined; label: string }) {
  const ime = useImeGuard();
  return (
    <input
      id={id}
      className="ac-input"
      aria-label={label}
      value={typeof value === "string" ? value : value === undefined || value === null ? "" : String(value)}
      disabled={disabled}
      {...ime.handlers}
      onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.preventDefault();
      }}
    />
  );
}

function NumberInput({ id, value, onChange, disabled, label }: { id: string; value: unknown; onChange(v: unknown): void; disabled?: boolean | undefined; label: string }) {
  const [text, setText] = useState(() => (typeof value === "number" ? String(value) : ""));
  const [seen, setSeen] = useState(value);
  if (!Object.is(seen, value)) {
    // 바깥에서 값이 바뀌면(행 이동 등) 입력 문구를 맞춘다. 입력 중인 같은 값은 건드리지 않는다.
    setSeen(value);
    if (typeof value === "number" && Number(text) !== value) setText(String(value));
    else if (value === undefined && text !== "" && Number.isFinite(Number(text))) setText("");
  }
  return (
    <input
      id={id}
      className="ac-input"
      type="number"
      aria-label={label}
      value={text}
      disabled={disabled}
      onChange={(e) => {
        setText(e.target.value);
        const n = e.target.value === "" ? undefined : Number(e.target.value);
        onChange(n !== undefined && Number.isFinite(n) ? n : undefined);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.preventDefault();
      }}
    />
  );
}

function ArrayInput({ id, value, onChange, disabled, label, messages, itemsSchema }: { id: string; value: unknown; onChange(v: unknown): void; disabled?: boolean | undefined; label: string; messages: M; itemsSchema: "number" | "string" }) {
  const items = Array.isArray(value) ? (value as unknown[]) : [];
  const [draft, setDraft] = useState("");
  const ime = useImeGuard();
  const add = () => {
    const text = draft.trim();
    if (text === "") return;
    const item = itemsSchema === "number" ? Number(text) : text;
    if (itemsSchema === "number" && !Number.isFinite(item as number)) return;
    onChange([...items, item]);
    setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    if (ime.isIme(e)) return;
    add();
  };
  return (
    <div className="dlg-chips" role="group" aria-label={label}>
      {items.map((it, i) => (
        <span key={`${i}:${String(it)}`} className="dlg-chip">
          <span className="ac-ellipsis">{String(it)}</span>
          <button type="button" className="app-link-btn" disabled={disabled} aria-label={messages.valueArrayRemove(String(it))} onClick={() => onChange(items.filter((_, j) => j !== i))}>×</button>
        </span>
      ))}
      <input id={id} className="ac-input dlg-chip-input" aria-label={`${label} — ${messages.valueArrayAdd}`} placeholder={messages.valueArrayAdd} value={draft} disabled={disabled} {...ime.handlers} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} />
    </div>
  );
}

function JsonInput({ id, value, onChange, disabled, label, messages }: { id: string; value: unknown; onChange(v: unknown): void; disabled?: boolean | undefined; label: string; messages: M }) {
  const [text, setText] = useState(() => stringify(value));
  const [bad, setBad] = useState(false);
  const [seen, setSeen] = useState(value);
  const errId = useId();
  if (!Object.is(seen, value)) {
    // 바깥 값이 바뀌었는데 입력 문구가 그 값이 아니면 문구를 맞춘다(입력 중인 잘못된 JSON은 건드리지 않는다)
    setSeen(value);
    let parsed: unknown;
    let valid = true;
    try {
      parsed = text.trim() === "" ? undefined : JSON.parse(text);
    } catch {
      valid = false;
    }
    if (valid && JSON.stringify(parsed) !== JSON.stringify(value)) setText(stringify(value));
  }
  return (
    <>
      <textarea
        id={id}
        className="ac-input ac-mono dlg-json"
        rows={2}
        aria-label={label}
        aria-invalid={bad}
        {...(bad ? { "aria-describedby": errId } : {})}
        value={text}
        disabled={disabled}
        onChange={(e) => {
          setText(e.target.value);
          if (e.target.value.trim() === "") {
            setBad(false);
            onChange(undefined);
            return;
          }
          try {
            onChange(JSON.parse(e.target.value));
            setBad(false);
          } catch {
            setBad(true);
          }
        }}
      />
      {bad ? <span id={errId} className="lib-field-error" role="alert">{messages.valueJsonInvalid}</span> : null}
    </>
  );
}
