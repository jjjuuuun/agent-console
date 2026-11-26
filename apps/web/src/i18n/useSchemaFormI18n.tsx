import { SchemaForm, DEFAULT_MESSAGES, type SchemaFormMessages, type SchemaFormProps } from "@agent-console/schema-form";
import { useLibMessages, useServerText, type MessageTree } from "@agent-console/i18n";
import { useOptionalI18n } from "./AppI18n";

/** `SchemaForm`에 현재 언어 문구(`messages`)와 서버 스키마 글자 번역(`translate`)을 건네는 값. 공급자 안에서만 쓴다. */
export function useSchemaFormI18n(): { messages: SchemaFormMessages; translate: (text: string) => string } {
  const messages = useLibMessages("schema-form", DEFAULT_MESSAGES as unknown as MessageTree) as unknown as SchemaFormMessages;
  const { text } = useServerText();
  return { messages, translate: text };
}

function I18nSchemaForm(props: SchemaFormProps) {
  const { messages, translate } = useSchemaFormI18n();
  return <SchemaForm messages={messages} translate={translate} {...props} />;
}

/**
 * 현재 화면 언어로 그리는 `SchemaForm`. 공급자가 없으면(단독 테스트 등) 그냥 `SchemaForm`이다.
 * 호출자가 `messages`·`translate`를 직접 주면 그 값이 이긴다.
 */
export function AppSchemaForm(props: SchemaFormProps) {
  return useOptionalI18n() === null ? <SchemaForm {...props} /> : <I18nSchemaForm {...props} />;
}
