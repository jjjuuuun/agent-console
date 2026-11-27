import type { MessageTree, Translate } from "@agent-console/i18n";
import { koT } from "./koText";

const KO = import.meta.glob<MessageTree>("../locales/ko/*.json", { eager: true, import: "default" });

/** 앱 한국어 묶음 한 네임스페이스의 트리(`locales/ko/<namespace>.json`). */
export function koTree(namespace: string): MessageTree {
  const hit = KO[`../locales/ko/${namespace}.json`];
  if (hit === undefined) throw new Error(`ko bundle not found: ${namespace}`);
  return hit;
}

/** 한국어 묶음으로 만든 번역 함수(`koT`와 같다, 빠진 키는 실패). */
export const koTranslate: (namespace: string) => Translate = koT;

/** 한국어 묶음으로 문구 표를 만든다: `koMessages("resources", createResourceMessages)`. */
export function koMessages<M>(namespace: string, create: (t: Translate) => M): M {
  return create(koTranslate(namespace));
}
