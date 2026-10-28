import { useState } from "react";
import { Btn } from "../shared/Button";
import { s } from "../shared/styles";
import type { InteractionMessages } from "./messages";
import type { FallbackArgs } from "./types";
import { onModEnter, parseJson, prettyJson } from "./util";

/**
 * 내장 폴백: 요청 내용을 보여 주고 JSON으로 응답을 쓴다.
 * 앱이 `renderFallback`으로 SchemaForm을 주입하면 그쪽이 우선한다.
 */
export function FallbackRenderer({ interaction, onSubmit, submitting, disabled, readOnly, readOnlyInput = false, messages }: FallbackArgs & { readOnlyInput?: boolean; messages: InteractionMessages }) {
  const mf = messages.fallback;
  const [text, setText] = useState(() => (readOnly && interaction.response ? prettyJson(interaction.response) : "{}"));
  const parsed = parseJson(text);
  const locked = disabled || readOnly || submitting;
  const submit = () => {
    if (parsed.ok && !locked) onSubmit(parsed.value);
  };
  return (
    <div style={s.col("var(--ac-space-2)")} onKeyDown={(e) => onModEnter(e, submit)}>
      {interaction.payload ? (
        <details>
          <summary style={s.muted}>{mf.payload}</summary>
          <pre style={s.code}>{prettyJson(interaction.payload)}</pre>
        </details>
      ) : null}
      {readOnlyInput ? null : (
        <label style={s.col("var(--ac-space-1)")}>
          <span style={s.muted}>{mf.responseLabel}</span>
          <textarea value={text} rows={5} disabled={locked} aria-invalid={!parsed.ok} style={{ ...s.input, fontFamily: "var(--ac-font-mono)" }} onChange={(e) => setText(e.target.value)} />
        </label>
      )}
      {!parsed.ok && !readOnlyInput ? <span role="alert" style={{ color: "var(--ac-danger)", fontSize: "var(--ac-text-xs, 12px)" }}>{mf.invalidJson}</span> : null}
      {readOnly || readOnlyInput ? null : (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Btn variant="primary" disabled={!parsed.ok || locked} loading={submitting} onClick={submit}>
            {mf.submit}
          </Btn>
        </div>
      )}
    </div>
  );
}
