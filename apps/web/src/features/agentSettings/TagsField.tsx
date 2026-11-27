import { useId, useState } from "react";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { useImeGuard } from "../../lib/ime";

/** `ui:field` 이름. */
export const TAGS_FIELD = "tags";

export interface TagsOptions {
  /** 자동완성 후보 */
  suggestions?: readonly string[];
  addLabel: string;
  removeLabel: (tag: string) => string;
  placeholder?: string;
}

/** 문자열 목록(또는 null)을 태그로 편집한다. Enter·쉼표로 추가, 항목의 ×로 제거. IME 조합 중 Enter는 무시한다. */
export function TagsField({ id, value, onChange, label, disabled, readonly, options }: SchemaFormFieldProps) {
  const opts = options as unknown as TagsOptions;
  const tags = Array.isArray(value) ? (value as unknown[]).filter((v): v is string => typeof v === "string") : [];
  const [text, setText] = useState("");
  const ime = useImeGuard();
  const listId = useId();
  const locked = disabled || readonly;
  const add = (raw: string) => {
    const parts = raw.split(",").map((s) => s.trim()).filter((s) => s !== "" && !tags.includes(s));
    if (parts.length > 0) onChange([...tags, ...parts]);
    setText("");
  };
  return (
    <div role="group" aria-label={label} className="lib-tags">
      <span className="lib-field-label">{label}</span>
      {tags.map((tag) => (
        <span key={tag} className="lib-tag">
          <span className="ac-ellipsis">{tag}</span>
          {locked ? null : (
            <button type="button" aria-label={opts.removeLabel(tag)} onClick={() => onChange(tags.filter((x) => x !== tag))}>
              ×
            </button>
          )}
        </span>
      ))}
      {locked ? null : (
        <>
          <input
            id={id}
            className="ac-input lib-tags-input"
            value={text}
            list={opts.suggestions && opts.suggestions.length > 0 ? listId : undefined}
            aria-label={opts.addLabel}
            placeholder={opts.placeholder ?? opts.addLabel}
            {...ime.handlers}
            onChange={(e) => setText(e.target.value)}
            onBlur={() => text.trim() !== "" && add(text)}
            onKeyDown={(e) => {
              if (ime.isIme(e)) return;
              if (e.key === "Enter" || e.key === ",") {
                e.preventDefault();
                if (text.trim() !== "") add(text);
              } else if (e.key === "Backspace" && text === "" && tags.length > 0) {
                onChange(tags.slice(0, -1));
              }
            }}
          />
          {opts.suggestions && opts.suggestions.length > 0 ? (
            <datalist id={listId}>
              {opts.suggestions.filter((s) => !tags.includes(s)).map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          ) : null}
        </>
      )}
    </div>
  );
}
