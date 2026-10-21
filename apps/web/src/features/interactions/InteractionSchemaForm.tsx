import { useState } from "react";
import type { FallbackArgs } from "@agent-console/chat";
import { getDefaultValue, SchemaForm, type JsonSchema } from "@agent-console/schema-form";
import { Button } from "@agent-console/ui";
import { interactionMessages, type InteractionMessages } from "./messages";

export interface InteractionSchemaFormProps extends FallbackArgs {
  /** 문구를 덮어쓴다(`payload`, `send`) */
  messages?: Partial<Pick<InteractionMessages, "payload" | "send">>;
  /** 바깥·버튼 줄에 붙일 클래스(화면 스타일은 호출 측이 정한다) */
  className?: string;
  actionsClassName?: string;
}

/**
 * 모르는 renderer의 상호작용을 스키마 폼으로 받는다(`InteractionCard`의 `renderFallback`). 새 상호작용 종류가
 * 플러그인만으로 화면에 나타나는 경로이며 채팅과 실행 상세가 같이 쓴다.
 * 스키마는 요청의 `response_schema` -> 종류 디스크립터의 `response_schema` 순서로 쓰고, 둘 다 없으면 JSON 직접 입력.
 * 요청 내용(`payload`)은 접어서 보여 주고, Ctrl/Cmd+Enter로 보낸다.
 */
export function InteractionSchemaForm({ interaction, descriptor, onSubmit, submitting, errors, disabled, readOnly, messages, className, actionsClassName }: InteractionSchemaFormProps) {
  const text = { ...interactionMessages, ...messages };
  const schema = (interaction.response_schema ?? descriptor?.response_schema ?? { type: "object" }) as JsonSchema;
  const [value, setValue] = useState<unknown>(() => (readOnly && interaction.response !== undefined ? interaction.response : getDefaultValue(schema)));
  const locked = disabled || readOnly || submitting;
  return (
    <div
      {...(className ? { className } : {})}
      onKeyDown={(e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !locked) onSubmit(value);
      }}
    >
      {interaction.payload ? (
        <details>
          <summary className="app-muted">{text.payload}</summary>
          <pre className="ac-pre app-json">{JSON.stringify(interaction.payload, null, 2)}</pre>
        </details>
      ) : null}
      <SchemaForm
        schema={schema}
        value={value}
        onChange={setValue}
        errors={errors.map((e) => ({ path: e.path, message: e.message }))}
        disabled={locked}
        readonly={readOnly}
        idPrefix={`ix-${interaction.id}`}
        advancedStorageKey="interaction"
      />
      {readOnly ? null : (
        <div {...(actionsClassName ? { className: actionsClassName } : {})}>
          <Button variant="primary" loading={submitting} disabled={locked} onClick={() => onSubmit(value)}>
            {text.send}
          </Button>
        </div>
      )}
    </div>
  );
}
