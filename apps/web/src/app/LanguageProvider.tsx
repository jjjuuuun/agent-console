import { useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { RestClient } from "@agent-console/api-client";
import type { I18nInfo } from "@agent-console/contracts/i18n";
import type { Console18n } from "@agent-console/i18n";
import { LanguageAnnouncer, LanguageContext, bundledLanguages, browserLanguages, createLanguageController, saveLanguage } from "../i18n";
import type { LanguageContextValue } from "../i18n";
import { useRequires } from "../modules";
import { useApi } from "./ApiContext";
import { queryKeys, useWorkspaceSettings } from "./queries";
import { DOCUMENT_REQUIRES } from "./requirements";
import type { SafeStorage } from "./storage";

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
  /**
   * 첫 화면 언어(설정 → 브라우저 → en)가 정해지고 서버 문구 묶음이 들어올 때까지 본문을 그리지 않는 최대 시간(ms, 기본 3000).
   * 그 전에 그리면 부팅 언어와 서버 원문이 잠깐 섞여 보인다. 시간이 지나면 있는 그대로(원문) 그린다. 0이면 기다리지 않는다.
   */
  holdMs?: number;
}

/** 첫 언어 맞추기가 끝나기 전 자리: 눈에 보이는 글자 없이 "준비 중"만 알린다(부팅 언어 문구가 깜박이지 않게). */
export const LANGUAGE_HOLD_TEST_ID = "language-hold";
/**
 * 언어 상태 컨테이너: 서버 언어 목록(`GET /i18n`)과 설정의 `ui.language`를 읽어 첫 화면 언어를 한 번 맞추고(§4.1 B),
 * 사용자가 고른 언어를 즉시 반영·저장한다(§3). 서버·설정 기능이 없어도 앱 묶음만으로 동작한다.
 * 스크린 리더 알림 한 곳(`role="status"`)도 여기서 그린다.
 */
export function LanguageProvider({ i18n, storage, children, holdMs = 3000 }: LanguageProviderProps) {
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

  // 첫 맞추기가 끝날 때까지(또는 시간이 지날 때까지) 본문을 잠시 보류한다. 화면 전체를 오래 막지 않는다.
  const [holdExpired, setHoldExpired] = useState(false);
  useEffect(() => {
    if (state.settled || holdMs <= 0) return;
    const id = setTimeout(() => setHoldExpired(true), holdMs);
    return () => clearTimeout(id);
  }, [state.settled, holdMs]);
  const holding = !state.settled && !holdExpired && holdMs > 0;

  const value: LanguageContextValue = { state, infoStatus, info, bundled, browser, select: controller.select, retrySave: controller.retrySave };
  return (
    <LanguageContext.Provider value={value}>
      {holding ? <div aria-busy="true" data-testid={LANGUAGE_HOLD_TEST_ID} /> : children}
      <LanguageAnnouncer announcement={state.announcement} />
    </LanguageContext.Provider>
  );
}

