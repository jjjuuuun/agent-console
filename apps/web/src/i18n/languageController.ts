import type { I18nInfo } from "@agent-console/contracts/i18n";
import { availableLanguages, resolveLanguage, setLanguage, type Console18n, type FetchCatalog, type SetLanguageResult } from "@agent-console/i18n";
import type { SafeStorage } from "../app/storage";
import { FALLBACK_LANGUAGE, writeStoredLanguage } from "./languageStorage";

/** 화면이 읽는 언어 상태. 값은 바뀔 때마다 새 객체다(`useSyncExternalStore` 스냅샷). */
export interface LanguageState {
  /** 지금 화면에 보이는 실제 언어 */
  language: string;
  /** 설정 문서의 `ui.language`(null = 자동, undefined = 아직 모름) */
  preference: string | null | undefined;
  /** 방금 누른 선택(아직 적용 전). undefined = 없음, null = 자동 */
  pending: string | null | undefined;
  /** 화면은 바뀌었지만 서버에 저장하지 못함 */
  saveFailed: boolean;
  /** 서버 문구 묶음을 못 받아 앱 문구만 바뀜(오류·시간 초과) */
  serverTextFailed: boolean;
  /** 사용자가 직접 바꾼 뒤 스크린 리더에 알릴 문구의 재료. 알릴 때마다 `id`가 늘어난다 */
  announcement: { id: number; language: string } | null;
}

export interface LanguageControllerDeps {
  i18n: Console18n;
  storage: SafeStorage;
  /** `navigator.languages` */
  browser: () => readonly string[];
  /** 앱이 묶어 둔 언어 */
  bundled: readonly string[];
  /** 서버 문구 묶음 가져오기(서버 기능이 없으면 생략) */
  fetchCatalog?: FetchCatalog;
  /** `ui.language`만 저장한다(null = 자동). 설정 문서 기능이 없으면 생략 */
  save?: (value: string | null) => Promise<void>;
  /** `<html lang>` 바꾸기(기본: 문서) */
  setDocumentLanguage?: (language: string) => void;
  /** 연타를 합치는 시간(기본 250ms) */
  debounceMs?: number;
  /** 서버 묶음 대기 상한(기본 5000ms) */
  timeoutMs?: number;
}

export interface LanguageController {
  getState(): LanguageState;
  subscribe(listener: () => void): () => void;
  /** 사용자가 고른 값을 처리한다(§3). `null` = 자동. 같은 값이면 무시 */
  select(next: string | null): void;
  /** 저장 실패 뒤 다시 저장한다 */
  retrySave(): void;
  /** 설정 문서와 서버 언어 목록을 받은 뒤 한 번 맞춘다(§4.1 단계 B). 조용히 바꾼다 */
  sync(input: { preference: string | null | undefined; info: Pick<I18nInfo, "languages" | "default_language"> | null }): void;
  /** 타이머를 정리한다 */
  dispose(): void;
}

const defaultSetDocumentLanguage = (language: string) => {
  if (typeof document !== "undefined") document.documentElement.lang = language;
};

/** 언어 바꾸기·첫 화면 맞추기의 순서 제어. React를 모른다(상태·구독만). */
export function createLanguageController(deps: LanguageControllerDeps): LanguageController {
  const { i18n, storage, browser, bundled, fetchCatalog, save } = deps;
  const debounceMs = deps.debounceMs ?? 250;
  const setDocumentLanguage = deps.setDocumentLanguage ?? defaultSetDocumentLanguage;
  const setOptions = { ...(fetchCatalog ? { fetchCatalog } : {}), ...(deps.timeoutMs === undefined ? {} : { timeoutMs: deps.timeoutMs }) };
  const listeners = new Set<() => void>();
  let state: LanguageState = {
    language: i18n.language,
    preference: undefined,
    pending: undefined,
    saveFailed: false,
    serverTextFailed: false,
    announcement: null,
  };
  let seq = 0; // 가장 최근 선택의 번호(낡은 결과를 버린다)
  let timer: ReturnType<typeof setTimeout> | undefined;
  let chain: Promise<unknown> = Promise.resolve();
  let syncKey = "";
  let info: Pick<I18nInfo, "languages" | "default_language"> | null = null;
  let lastSaved: string | null | undefined;

  const set = (patch: Partial<LanguageState>) => {
    state = { ...state, ...patch };
    listeners.forEach((l) => l());
  };

  const resolveFor = (preference: string | null): string =>
    resolveLanguage({
      preference,
      browser: browser(),
      available: availableLanguages(bundled, info),
      serverDefault: info?.default_language ?? null,
      fallback: FALLBACK_LANGUAGE,
    });

  /** 묶음을 준비해 한 번에 바꾼다. 앞선 작업이 끝난 뒤에 시작하므로 늦게 끝난 낡은 결과가 덮지 않는다. */
  const switchTo = (language: string, isCurrent: () => boolean): Promise<SetLanguageResult | undefined> => {
    const run = chain.then(async () => {
      if (!isCurrent()) return undefined;
      const result = await setLanguage(i18n, language, setOptions);
      if (isCurrent()) {
        writeStoredLanguage(storage, language);
        setDocumentLanguage(language);
      }
      return result;
    });
    chain = run.catch(() => undefined);
    return run;
  };

  const persist = async (value: string | null) => {
    if (save === undefined) return;
    lastSaved = value;
    try {
      await save(value);
      if (lastSaved === value) set({ saveFailed: false });
    } catch {
      if (lastSaved === value) set({ saveFailed: true });
    }
  };

  const apply = async (next: string | null, mine: number) => {
    const language = resolveFor(next);
    syncKey = JSON.stringify([next, language]);
    const result = await switchTo(language, () => mine === seq);
    if (mine !== seq || result === undefined) return;
    set({
      language: i18n.language,
      preference: next,
      pending: undefined,
      serverTextFailed: result.server === "failed",
      announcement: { id: (state.announcement?.id ?? 0) + 1, language: i18n.language },
    });
    void persist(next);
  };

  return {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    select(next) {
      if (next === (state.pending === undefined ? state.preference : state.pending)) return;
      seq += 1;
      const mine = seq;
      set({ pending: next });
      if (timer !== undefined) clearTimeout(timer);
      timer = setTimeout(() => void apply(next, mine), debounceMs);
    },
    retrySave() {
      if (state.preference !== undefined) void persist(state.preference);
    },
    sync(input) {
      // 사용자가 고르는 중이면 그 선택이 이긴다.
      if (state.pending !== undefined) return;
      info = input.info;
      const preference = input.preference ?? null;
      const language = resolveFor(preference);
      const key = JSON.stringify([preference, language]);
      if (key === syncKey) {
        if (state.preference !== input.preference) set({ preference: input.preference });
        return;
      }
      syncKey = key;
      set({ preference: input.preference });
      const mine = seq;
      void switchTo(language, () => mine === seq && state.pending === undefined).then((result) => {
        if (result === undefined) return;
        set({ language: i18n.language, serverTextFailed: result.server === "failed" });
      });
    },
    dispose() {
      if (timer !== undefined) clearTimeout(timer);
      listeners.clear();
    },
  };
}
