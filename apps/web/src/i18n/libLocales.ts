import type { MessageTree } from "@agent-console/i18n";

/**
 * 라이브러리 패키지가 내보내는 문구 묶음(`@agent-console/<패키지>/locales/<언어>`)의 지연 로더.
 * 네임스페이스 이름 = 패키지 이름. 앱은 이것을 i18next 묶음에 올려 서버 묶음이 덮을 수 있게 한다.
 * 라이브러리가 새 언어 묶음을 내보내면 이 표에 한 줄을 더한다(언어 목록은 이 표와 앱 묶음 파일에서 읽는다).
 */
type Loader = () => Promise<MessageTree>;

const pick = (mod: { default: unknown }): MessageTree => mod.default as MessageTree;

export const LIB_LOCALES: Readonly<Record<string, Readonly<Record<string, Loader>>>> = {
  ui: { ko: () => import("@agent-console/ui/locales/ko").then(pick), en: () => import("@agent-console/ui/locales/en").then(pick) },
  "schema-form": {
    ko: () => import("@agent-console/schema-form/locales/ko").then(pick),
    en: () => import("@agent-console/schema-form/locales/en").then(pick),
  },
  "graph-editor": {
    ko: () => import("@agent-console/graph-editor/locales/ko").then(pick),
    en: () => import("@agent-console/graph-editor/locales/en").then(pick),
  },
  chat: { ko: () => import("@agent-console/chat/locales/ko").then(pick), en: () => import("@agent-console/chat/locales/en").then(pick) },
  "log-view": {
    ko: () => import("@agent-console/log-view/locales/ko").then(pick),
    en: () => import("@agent-console/log-view/locales/en").then(pick),
  },
  "trace-view": {
    ko: () => import("@agent-console/trace-view/locales/ko").then(pick),
    en: () => import("@agent-console/trace-view/locales/en").then(pick),
  },
  "arch-view": {
    ko: () => import("@agent-console/arch-view/locales/ko").then(pick),
    en: () => import("@agent-console/arch-view/locales/en").then(pick),
  },
};
