import { defaultUiMessages, ShortcutProvider, type ShortcutProviderProps } from "@agent-console/ui";
import { useLibMessages, type MessageTree } from "@agent-console/i18n";
import { useOptionalI18n } from "./AppI18n";

function I18nShortcutProvider(props: ShortcutProviderProps) {
  const messages = useLibMessages("ui", defaultUiMessages as unknown as MessageTree);
  return <ShortcutProvider messages={messages} {...props} />;
}

/**
 * 현재 화면 언어의 `ui` 라이브러리 문구를 건네는 `ShortcutProvider`. 공급자가 없으면(단독 테스트 등) 그냥 `ShortcutProvider`다.
 * 호출자가 `messages`를 주면 그 값이 이긴다.
 */
export function AppShortcutProvider(props: ShortcutProviderProps) {
  return useOptionalI18n() === null ? <ShortcutProvider {...props} /> : <I18nShortcutProvider {...props} />;
}
