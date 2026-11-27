import type { BundledCatalogs, LoadBundled, MessageTree, NamespaceBundle } from "@agent-console/i18n";
import { LIB_LOCALES } from "./libLocales";

/** 앱 묶음 파일 경로의 규칙: `locales/<언어>/<네임스페이스>.json`. 언어·네임스페이스 이름은 파일 이름에서 읽는다(코드에 목록 없음). */
// 테스트 캐시 주의: 아래 glob의 파일 목록은 이 파일 내용이 바뀔 때만 다시 계산된다. 묶음 파일을 새로 더한 뒤 문구 키가 그대로 보이면 이 줄의 숫자를 올린다. (캐시 갱신 #3)
const FILE = /locales\/([^/]+)\/([^/]+)\.json$/;

/** 부팅 네임스페이스: 첫 청크에 동기로 싣는다(부팅·연결 실패 화면). */
export const BOOT_NAMESPACE = "boot";

// 부팅 묶음은 모든 언어 것을 첫 청크에 싣고(작다), 나머지는 언어를 바꿀 때 내려받는다.
const bootFiles = import.meta.glob<MessageTree>("../locales/*/boot.json", { eager: true, import: "default" });
const lazyFiles = import.meta.glob<MessageTree>(["../locales/*/*.json", "!../locales/*/boot.json"], { import: "default" });

function parse(path: string): { language: string; namespace: string } | undefined {
  const hit = FILE.exec(path);
  return hit ? { language: hit[1]!, namespace: hit[2]! } : undefined;
}

/** 앱이 묶어 둔 언어(앱 묶음 파일 + 라이브러리 묶음에서 찾은 합집합, 코드순). */
export function bundledLanguages(): string[] {
  const found = new Set<string>();
  for (const path of [...Object.keys(bootFiles), ...Object.keys(lazyFiles)]) {
    const parsed = parse(path);
    if (parsed) found.add(parsed.language);
  }
  return [...found].sort();
}

/** 이미 첫 청크에 들어 있는 부팅 묶음(언어 -> 네임스페이스). */
export function bootBundles(): BundledCatalogs {
  const out: BundledCatalogs = {};
  for (const [path, tree] of Object.entries(bootFiles)) {
    const parsed = parse(path);
    if (parsed) (out[parsed.language] ??= {})[parsed.namespace] = tree;
  }
  return out;
}

/**
 * 한 언어의 나머지 앱 묶음 + 라이브러리 묶음을 내려받는다. 그 언어 파일이 하나도 없으면 undefined.
 * 일부 파일이 실패하면 받은 것만 돌려준다(빠진 키는 대체 언어 사슬이 채운다).
 */
export const loadBundled: LoadBundled = async (language) => {
  const bundle: NamespaceBundle = {};
  const jobs: Promise<void>[] = [];
  for (const [path, load] of Object.entries(lazyFiles)) {
    const parsed = parse(path);
    if (parsed?.language !== language) continue;
    jobs.push(load().then((tree) => void (bundle[parsed.namespace] = tree), () => undefined));
  }
  for (const [namespace, byLanguage] of Object.entries(LIB_LOCALES)) {
    const load = byLanguage[language];
    if (load) jobs.push(load().then((tree) => void (bundle[namespace] = tree), () => undefined));
  }
  await Promise.all(jobs);
  return Object.keys(bundle).length === 0 ? undefined : bundle;
};
