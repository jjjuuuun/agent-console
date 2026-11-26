import { createContext, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { RestClient } from "@agent-console/api-client";
import type { I18nInfo } from "@agent-console/contracts/i18n";
import { languageName, useT, type Console18n } from "@agent-console/i18n";
import { useApi } from "../app/ApiContext";
import { DOCUMENT_REQUIRES } from "../app/requirements";
import { queryKeys, useWorkspaceSettings } from "../app/queries";
import type { SafeStorage } from "../app/storage";
import { useRequires } from "../modules";
import { bundledLanguages } from "./bundles";
import { browserLanguages } from "./createAppI18n";
import { createLanguageController, type LanguageController, type LanguageState } from "./languageController";
import { saveLanguage } from "./saveLanguage";

/** 언어 고르기 화면이 읽는 값. 서버 언어 목록 상태와 앱이 묶어 둔 언어를 함께 준다. */
export interface LanguageContextValue {
  state: LanguageState;
  /** 서버 언어 목록: `loading` 응답 전, `ready` 받음, `unavailable` 서버에 이 기능이 없거나 실패 */
  infoStatus: "loading" | "ready" | "unavailable";
  info: I18nInfo | null;
  bundled: readonly string[];
  /** 브라우저 언어 */
  browser: readonly string[];
  select: LanguageController["select"];
  retrySave: LanguageController["retrySave"];
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

/** 언어 상태를 읽는다. 공급자 밖이면 null(설정 화면이 서버 없이 쓰일 때를 위해 오류로 만들지 않는다). */
export function useLanguage(): LanguageContextValue | null {
  return useContext(LanguageContext);
}

/** 값 하나를 들고 있다가 렌더 밖에서 최신 값을 읽게 하는 보관함. */
function createLatest<T>(initial: T) {
  let value = initial;
  return {
    set(next: T): void {
      value = next;
    },
    get(): T {
      return value;
    },
  };
}

/** 컨트롤러가 부르는 서버 호출 둘. 렌더가 바뀌어도 컨트롤러는 그대로이므로 최신 값을 보관함에서 읽는다. */
function latestCalls(latest: { get(): { rest: RestClient; save: (value: string | null) => Promise<void> } }) {
  return {
    fetchCatalog: (language: string, signal: AbortSignal) =>
      Promise.resolve()
        .then(() => latest.get().rest.getI18nCatalog(language, { signal }))
        .then((v) => v ?? null),
    save: (value: string | null) => latest.get().save(value),
  };
}

export interface LanguageProviderProps {
  i18n: Console18n;
  storage: SafeStorage;
  children: ReactNode;
}

/**
 * 언어 상태 컨테이너: 서버 언어 목록(`GET /i18n`)과 설정의 `ui.language`를 읽어 첫 화면 언어를 한 번 맞추고(§4.1 B),
 * 사용자가 고른 언어를 즉시 반영·저장한다(§3). 서버·설정 기능이 없어도 앱 묶음만으로 동작한다.
 * 스크린 리더 알림 한 곳(`role="status"`)도 여기서 그린다.
 */
export function LanguageProvider({ i18n, storage, children }: LanguageProviderProps) {
  const { rest } = useApi();
  const queryClient = useQueryClient();
  const settings = useWorkspaceSettings();
  const documentPhase = useRequires(DOCUMENT_REQUIRES).phase;
  const documentOn = documentPhase === "met";
  const bundled = useMemo(() => bundledLanguages(), []);
  const browser = useMemo(() => browserLanguages(), []);

  // 컨트롤러·질의가 렌더 밖(비동기)에서 부르는 최신 값 보관함
  const [latest] = useState(() => createLatest<{ rest: RestClient; save: (value: string | null) => Promise<void> }>({ rest, save: () => Promise.resolve() }));
  useEffect(() => latest.set({ ...latest.get(), rest }), [latest, rest]);

  const infoQuery = useQuery<I18nInfo | null, Error>({
    queryKey: ["i18n", "info"],
    // 서버에 이 기능이 없거나(404) 실패해도 오류 화면이 아니다. 앱 묶음만으로 동작한다.
    queryFn: () => Promise.resolve().then(() => latest.get().rest.getI18nInfo()).then((v) => v ?? null, () => null),
    staleTime: 60_000,
    retry: false,
    meta: { silentBackgroundError: true },
  });
  const info = infoQuery.data ?? null;
  const infoStatus = infoQuery.isPending ? "loading" : info === null ? "unavailable" : "ready";

  useEffect(
    () =>
      latest.set({
        ...latest.get(),
        save: documentOn
          ? async (value) => {
              const saved = await saveLanguage(latest.get().rest, value);
              queryClient.setQueryData(queryKeys.settings(), saved);
            }
          : () => Promise.resolve(),
      }),
    [latest, documentOn, queryClient],
  );

  const [controller] = useState(() => createLanguageController({ i18n, storage, browser: () => browser, bundled, ...latestCalls(latest) }));
  useEffect(() => () => controller.dispose(), [controller]);
  const state = useSyncExternalStore(controller.subscribe, controller.getState, controller.getState);

  // 설정 문서와 언어 목록이 확정되면 한 번 맞춘다(문서 기능이 꺼졌으면 설정값 없이 자동으로).
  const settingsSettled = documentPhase === "unmet" || (documentOn && !settings.isPending);
  const preference = settings.data?.value.ui?.language;
  const infoReady = !infoQuery.isPending;
  useEffect(() => {
    if (settingsSettled && infoReady) controller.sync({ preference, info });
  }, [controller, settingsSettled, infoReady, preference, info]);

  const value: LanguageContextValue = { state, infoStatus, info, bundled, browser, select: controller.select, retrySave: controller.retrySave };
  return (
    <LanguageContext.Provider value={value}>
      {children}
      <LanguageAnnouncer announcement={state.announcement} />
    </LanguageContext.Provider>
  );
}

/** 사용자가 언어를 바꾼 뒤 새 언어 문구로 한 번 알린다(토스트 없음, §3-8). 부팅 때 자동으로 바뀐 것은 알리지 않는다. */
function LanguageAnnouncer({ announcement }: { announcement: LanguageState["announcement"] }) {
  const t = useT("settings");
  return (
    <div role="status" aria-live="polite" className="ac-sr-only" data-testid="language-announcer">
      {announcement === null ? "" : t("language.changed", { name: languageName(announcement.language) })}
    </div>
  );
}
