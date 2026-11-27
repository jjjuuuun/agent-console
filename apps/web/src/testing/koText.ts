/**
 * 테스트가 한국어 문구 표를 만들 때 쓰는 번역기(앱 코드에서 import하지 않는다).
 * 모든 언어의 locales 묶음 파일을 읽어(영어 묶음은 대체 언어 사슬용) `koT("chat")("키", { 값 })`처럼 쓴다. 빠진 키는 던진다.
 */
import type { MessageTree, Translate } from "@agent-console/i18n";
import { createTestI18n } from "@agent-console/i18n/testing";

const files = import.meta.glob<MessageTree>("../locales/*/*.json", { eager: true, import: "default" });
const bundled: Record<string, Record<string, MessageTree>> = {};
for (const [path, tree] of Object.entries(files)) {
  const hit = /locales\/([^/]+)\/([^/]+)\.json$/.exec(path);
  if (hit) (bundled[hit[1]!] ??= {})[hit[2]!] = tree;
}

/** 한국어 묶음 전부를 담은 테스트용 i18n(빠진 키는 던진다). 앱 공급자 밖에서 컴포넌트를 그리는 테스트가 `TestI18n`으로 감싼다. */
export const koI18n = createTestI18n({ language: "ko", bundled });
const i18n = koI18n;

/** 한국어 묶음의 번역 함수(네임스페이스별). */
export function koT(namespace: string): Translate {
  return (key, values) => {
    const { count, ...rest } = values ?? {};
    return i18n.t(key, { ns: namespace, ...(typeof count === "number" ? { count } : {}), replace: { ...rest, ...(typeof count === "number" ? { count } : {}) } });
  };
}
