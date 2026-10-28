import { Switch } from "@agent-console/ui";
import type { SchemaFormWidgetProps } from "@agent-console/schema-form";
import { memorySettingsMessages as t } from "./messages";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** `ui:widget` 이름 */
export const SWITCH_WIDGET = "ac-boolean-switch";
export const CHOICE_CARDS_WIDGET = "ac-choice-cards";

export function SwitchWidget({ id, value, onChange, label, disabled, readonly }: SchemaFormWidgetProps) {
  return <Switch checked={value === true} onChange={onChange} ariaLabel={label} onText="켜짐" offText="꺼짐" disabled={disabled || readonly} className={id} />;
}

/** 스키마 enum의 선택지 목록(값 + `x-ui.enum_labels` 라벨, 없으면 값 원문). */
export function enumChoices(schema: Obj): { value: string; label: string }[] {
  const list = Array.isArray(schema["enum"]) ? schema["enum"].filter((v): v is string => typeof v === "string") : [];
  const xui = isObj(schema["x-ui"]) ? schema["x-ui"] : {};
  const labels = isObj(xui["enum_labels"]) ? xui["enum_labels"] : {};
  return list.map((value) => ({ value, label: typeof labels[value] === "string" ? (labels[value] as string) : value }));
}

/**
 * enum 값을 카드형 라디오로 그린다(비밀 처리 선택). 선택지는 스키마의 enum이고 값별 설명은 문구 표(`messages`)이며 모르는 값은 라벨만 보인다.
 * 값을 "그대로 저장"하는 선택지는 스키마에 없으므로 그 사실을 한 줄로 알린다.
 */
export function ChoiceCardsWidget({ id, value, onChange, label, disabled, readonly, schema }: SchemaFormWidgetProps) {
  const choices = enumChoices(schema);
  const current = typeof value === "string" ? value : typeof schema["default"] === "string" ? schema["default"] : "";
  const locked = disabled || readonly;
  return (
    <div role="radiogroup" aria-label={label} id={id} className="memset-cards">
      {choices.map((c) => {
        const info = t.secrets.byValue[c.value];
        const checked = current === c.value;
        return (
          <label key={c.value} className="memset-card" data-checked={checked ? "true" : undefined}>
            <input type="radio" name={id} value={c.value} checked={checked} disabled={locked} onChange={() => onChange(c.value)} />
            <span className="memset-card-body">
              <span className="memset-strong">{info?.title ?? c.label}</span>
              {info === undefined ? null : <span className="memset-note app-muted">{info.body}</span>}
            </span>
          </label>
        );
      })}
      <p className="memset-note app-muted">{t.secrets.none}</p>
    </div>
  );
}
