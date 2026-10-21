import type { ComponentType, ReactNode } from "react";
import type { Interaction, InteractionKindDescriptor } from "@agent-console/contracts";
import type { InteractionMessages } from "./messages";

export type { Interaction, InteractionKindDescriptor };

/** 422 필드 오류. `path`는 응답 JSON의 위치. */
export interface FieldError {
  path: string;
  message: string;
}

/** 큰 텍스트 편집기를 앱이 주입하는 슬롯(예: text-editor 패키지). 없으면 `<textarea>`. */
export type RenderEditor = (args: { value: string; onChange: (v: string) => void; language: "json" | "markdown"; label: string; disabled?: boolean }) => ReactNode;

/** 모든 렌더러가 받는 props. 렌더러는 `response_schema`에 맞는 응답 객체를 만들어 `onSubmit`으로 넘긴다. */
export interface RendererProps {
  interaction: Interaction;
  descriptor: InteractionKindDescriptor | undefined;
  onSubmit: (response: unknown) => void;
  submitting: boolean;
  errors: readonly FieldError[];
  disabled: boolean;
  /** 읽기 전용(답함·만료·끊김 등). `interaction.response`가 있으면 보여 준다. */
  readOnly: boolean;
  messages: InteractionMessages;
  renderEditor?: RenderEditor;
}

/** `summarize`가 있으면 접힌 줄의 요약("답함: …")에 쓴다. */
export type RendererComponent = ComponentType<RendererProps> & {
  summarize?: (interaction: Interaction, messages: InteractionMessages, descriptor: InteractionKindDescriptor | undefined) => string;
};

export interface FallbackArgs {
  interaction: Interaction;
  descriptor: InteractionKindDescriptor | undefined;
  onSubmit: (response: unknown) => void;
  submitting: boolean;
  errors: readonly FieldError[];
  disabled: boolean;
  readOnly: boolean;
}
