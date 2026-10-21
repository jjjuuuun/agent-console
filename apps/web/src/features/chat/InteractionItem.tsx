import type { ReactNode } from "react";
import { InteractionCard, type FallbackArgs, type RenderEditor } from "@agent-console/chat";
import type { FieldError } from "@agent-console/chat";
import type { Interaction, InteractionKindDescriptor } from "@agent-console/contracts";
import { InteractionSchemaForm } from "../interactions";
import { LazyTextEditor } from "../library";
/** 큰 텍스트 편집기를 카드에 주입한다(`text-editor` 패키지, 지연 로딩). */
export const renderCardEditor: RenderEditor = ({ value, onChange, language, label, disabled }) => (
  <LazyTextEditor value={value} onChange={onChange} language={language} ariaLabel={label} readOnly={disabled === true} height={240} />
);

/** 모르는 renderer용 폴백: 공용 스키마 폼(요청 내용은 접어서 보여 준다). */
export function SchemaFallback(args: FallbackArgs): ReactNode {
  return <InteractionSchemaForm {...args} className="chat-fallback" actionsClassName="chat-fallback-actions" />;
}

export interface InteractionItemProps {
  interaction: Interaction;
  descriptor: InteractionKindDescriptor | undefined;
  /** 현재 시각(epoch 초) */
  now: number;
  actorLabel: string;
  onRespond: (interaction: Interaction, response: unknown) => Promise<void>;
  errors?: readonly FieldError[];
  /** 연결이 끊겨 보낼 수 없음 */
  disabled?: boolean;
  onEscape?: () => void;
  /** 서버 재시작으로 끊긴 대기: 답을 새 메시지로 보내기 */
  onResendAsMessage?: (interaction: Interaction) => void;
  /** 요청자 옆 작은 칩(중첩 팀 안의 요청이면 `중첩 팀`) */
  contextChip?: { text: string; title?: string };
}

/** 상호작용 카드 하나: `InteractionCard`에 응답 호출·폴백·편집기를 연결한다(종류 이름을 모른다). */
export function InteractionItem({ interaction, descriptor, now, actorLabel, onRespond, errors, disabled, onEscape, onResendAsMessage, contextChip }: InteractionItemProps) {
  return (
    <InteractionCard
      interaction={interaction}
      descriptor={descriptor}
      now={now}
      actorLabel={actorLabel}
      {...(contextChip ? { contextChip } : {})}
      onRespond={(response) => onRespond(interaction, response)}
      renderFallback={(args) => <SchemaFallback key={interaction.id} {...args} />}
      renderEditor={renderCardEditor}
      {...(errors ? { errors } : {})}
      {...(disabled ? { disabled } : {})}
      {...(onEscape ? { onEscape } : {})}
      {...(onResendAsMessage ? { serverRestartHint: { onResendAsMessage: () => onResendAsMessage(interaction) } } : {})}
    />
  );
}
