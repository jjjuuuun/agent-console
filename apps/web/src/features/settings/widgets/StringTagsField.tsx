import { useId, useState } from "react";
import { Button } from "@agent-console/ui";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { messages as m } from "../../../app/messages";
import { useImeGuard } from "../../../lib/ime";

/** `ui:field` 이름. */
export const STRING_TAGS_FIELD = "string-tags";

export interface StringTagsOptions {
  /** 입력 자동완성 후보(데이터). 목록에 없는 값도 입력할 수 있다 */
  suggestions?: readonly string[];
  /** 목록이 비었을 때 필드 아래 안내 */
  emptyNote?: string;
  addLabel?: string;
  addButtonLabel?: string;
  removeLabel?: (value: string) => string;
}

/** 문자열 목록 편집기(태그). 값은 `string[]`이며 중복은 무시한다. Enter 또는 [추가]로 확정(IME 조합 중 Enter 제외). */
export function StringTagsField({ id, value, onChange, label, disabled, readonly, options }: SchemaFormFieldProps) {
  const opts = options as StringTagsOptions;
  const listId = useId();
  const ime = useImeGuard();
  const [draft, setDraft] = useState("");
  const items = Array.isArray(value) ? (value as string[]) : [];
  const locked = disabled || readonly;
  const commit = () => {
    const v = draft.trim();
    setDraft("");
    if (v !== "" && !items.includes(v)) onChange([...items, v]);
  };
  return (
    <div className="app-tags" role="group" aria-label={label}>
      {opts.suggestions === undefined ? null : (
        <datalist id={listId}>
          {opts.suggestions.filter((s) => !items.includes(s)).map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      )}
      {items.length === 0 ? null : (
        <ul className="app-tags-list" aria-label={label}>
          {items.map((t) => (
            <li key={t} className="app-tag">
              <code>{t}</code>
              <button type="button" className="app-tag-remove" disabled={locked} aria-label={(opts.removeLabel ?? m.notifications.eventsRemove)(t)} onClick={() => onChange(items.filter((x) => x !== t))}>
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="app-tags-add">
        <input
          id={id}
          type="text"
          list={opts.suggestions === undefined ? undefined : listId}
          value={draft}
          disabled={locked}
          aria-label={opts.addLabel ?? m.notifications.eventsAdd}
          {...ime.handlers}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== "Enter" || ime.isIme(e)) return;
            e.preventDefault();
            commit();
          }}
        />
        <Button size="sm" onClick={commit} disabled={locked || draft.trim() === ""}>
          {opts.addButtonLabel ?? m.notifications.eventsAddButton}
        </Button>
      </div>
      {items.length === 0 && opts.emptyNote !== undefined ? <p className="app-muted">{opts.emptyNote}</p> : null}
    </div>
  );
}
