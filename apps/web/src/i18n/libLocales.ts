import type { MessageTree } from "@agent-console/i18n";

/**
 * 라이브러리 패키지가 내보내는 문구 묶음(`@agent-console/<패키지>/locales/<언어>`)의 지연 로더.
 * 네임스페이스 이름 = 패키지 이름. 앱은 이것을 i18next 묶음에 올려 서버 묶음이 덮을 수 있게 한다.
 * 라이브러리가 새 언어 묶음을 내보내면 이 표에 한 줄을 더한다(언어 목록은 이 표와 앱 묶음 파일에서 읽는다).
 */
type Loader = () => Promise<MessageTree>;

/** 묶음 모듈이 내보낼 수 있는 모양: 나무(`tree`, 평면 표를 default로 두는 패키지) 또는 default가 곧 나무인 패키지. */
interface LocaleModule {
  default: unknown;
  tree?: unknown;
}

/**
 * 점 표기 평면 표(`{ "a.b": "x" }`)를 나무(`{ a: { b: "x" } }`)로 바꾼다. 이미 나무인 값은 그대로 둔다.
 * 평면 표를 default로 내보내는 패키지(folder-picker)를 i18next 묶음에 올리려고 쓴다.
 */
export function nestFlatKeys(flat: unknown): MessageTree {
  const out: MessageTree = {};
  if (typeof flat !== "object" || flat === null) return out;
  for (const [key, value] of Object.entries(flat as Record<string, unknown>)) {
    const path = key.split(".");
    let node = out;
    for (const part of path.slice(0, -1)) {
      const next = node[part];
      if (typeof next === "object") node = next;
      else node = node[part] = {};
    }
    const last = path[path.length - 1] as string;
    if (typeof value === "string") node[last] = value;
    else if (typeof value === "object" && value !== null) node[last] = nestFlatKeys(value);
  }
  return out;
}

/** 묶음 모듈에서 나무를 꺼낸다: named `tree`가 있으면 그것, 없으면 default(점 표기 평면 표면 나무로 바꾼다). */
export const pick = (mod: LocaleModule): MessageTree => {
  if (mod.tree !== undefined) return mod.tree as MessageTree;
  const flat = typeof mod.default === "object" && mod.default !== null && Object.keys(mod.default).some((key) => key.includes("."));
  return flat ? nestFlatKeys(mod.default) : (mod.default as MessageTree);
};

/** 패키지 이름 -> 언어 -> 로더. 새 패키지는 한 줄을 더한다. */
function both(ko: () => Promise<LocaleModule>, en: () => Promise<LocaleModule>): Readonly<Record<string, Loader>> {
  return { ko: () => ko().then(pick), en: () => en().then(pick) };
}

export const LIB_LOCALES: Readonly<Record<string, Readonly<Record<string, Loader>>>> = {
  ui: both(() => import("@agent-console/ui/locales/ko"), () => import("@agent-console/ui/locales/en")),
  "schema-form": both(() => import("@agent-console/schema-form/locales/ko"), () => import("@agent-console/schema-form/locales/en")),
  "graph-editor": both(() => import("@agent-console/graph-editor/locales/ko"), () => import("@agent-console/graph-editor/locales/en")),
  chat: both(() => import("@agent-console/chat/locales/ko"), () => import("@agent-console/chat/locales/en")),
  "log-view": both(() => import("@agent-console/log-view/locales/ko"), () => import("@agent-console/log-view/locales/en")),
  "trace-view": both(() => import("@agent-console/trace-view/locales/ko"), () => import("@agent-console/trace-view/locales/en")),
  "arch-view": both(() => import("@agent-console/arch-view/locales/ko"), () => import("@agent-console/arch-view/locales/en")),
  "folder-picker": both(() => import("@agent-console/folder-picker/locales/ko"), () => import("@agent-console/folder-picker/locales/en")),
  "markdown-doc": both(() => import("@agent-console/markdown-doc/locales/ko"), () => import("@agent-console/markdown-doc/locales/en")),
  "memory-view": both(() => import("@agent-console/memory-view/locales/ko"), () => import("@agent-console/memory-view/locales/en")),
  "wiki-view": both(() => import("@agent-console/wiki-view/locales/ko"), () => import("@agent-console/wiki-view/locales/en")),
  "sdd-view": both(() => import("@agent-console/sdd-view/locales/ko"), () => import("@agent-console/sdd-view/locales/en")),
  projects: both(() => import("@agent-console/projects/locales/ko"), () => import("@agent-console/projects/locales/en")),
};
