import { useMemo } from "react";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";

export interface ColorSlotPickerProps {
  /** `cat-1`~`cat-8`, `neutral`, undefined = 자동. 이 밖의 값(CSS 색 등)은 선택 없음으로 보이고 그대로 보존된다. */
  value: string | undefined;
  onChange: (next: string | undefined) => void;
  slots?: number;
  messages?: DeepPartial<LogViewMessages>;
  ariaLabel: string;
}

/** 분류 체계 색 슬롯 선택(라디오 그룹). 색 단독이 아니라 번호/이름 텍스트가 함께 있다. */
export function ColorSlotPicker({ value, onChange, slots = 8, messages, ariaLabel }: ColorSlotPickerProps) {
  const m = useMemo(() => mergeMessages(messages), [messages]);
  const options: { id: string | undefined; label: string; css: string }[] = [
    { id: undefined, label: m.colorAuto, css: "transparent" },
    ...Array.from({ length: slots }, (_, i) => ({ id: `cat-${i + 1}`, label: fmt(m.colorSlot, { n: i + 1 }), css: `var(--ac-cat-${i + 1})` })),
    { id: "neutral", label: m.colorNeutral, css: "var(--ac-text-muted)" },
  ];
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="ac-lv-colorpicker">
      {options.map((o) => (
        <label key={o.id ?? "auto"} className="ac-lv-swatch" title={o.label}>
          <input type="radio" name={ariaLabel} checked={value === o.id} onChange={() => onChange(o.id)} />
          <span className="ac-lv-dot" style={{ background: o.css, border: o.id === undefined ? "1px dashed var(--ac-border-strong, currentColor)" : undefined }} aria-hidden="true" />
          <span>{o.id === undefined ? o.label : (o.id.replace("cat-", ""))}</span>
          <span className="ac-lv-sr">{o.label}</span>
        </label>
      ))}
    </div>
  );
}
