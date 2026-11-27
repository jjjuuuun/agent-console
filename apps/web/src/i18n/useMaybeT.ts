import { useCallback } from "react";
import { useT, type Translate } from "@agent-console/i18n";
import { useOptionalI18n } from "./AppI18n";

/** 키가 있으면 번역하고 없으면 undefined를 돌려주는 번역 함수. 서버 데이터가 키가 되는 표(상태·종류 이름)에서 `?? 원문`으로 이어 쓴다. */
export type MaybeTranslate = (key: string, values?: Parameters<Translate>[1]) => string | undefined;

/**
 * 네임스페이스의 `MaybeTranslate`. 언어가 바뀌거나 묶음이 더해지면 새 함수가 되어 화면이 다시 그려진다.
 * 앱 i18n 공급자 밖이면 항상 undefined(호출자의 대체 문구가 보인다).
 */
export function useMaybeT(namespace: string): MaybeTranslate {
  const t = useT(namespace);
  const i18n = useOptionalI18n();
  return useCallback<MaybeTranslate>((key, values) => (i18n?.exists(key, { ns: namespace }) ? t(key, values) : undefined), [i18n, namespace, t]);
}
