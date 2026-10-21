import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { RouterProvider, type createBrowserRouter } from "react-router";
import { IconRegistryProvider, THEME_CYCLE, ThemeProvider, ToastProvider, useToast, type ThemeChoice } from "@agent-console/ui";
import { ApiProvider } from "./ApiContext";
import { DEFAULT_LINK_PARTS } from "../links";
import { LinkPartsProvider, ModulesProvider, type LinkPartDef } from "../modules";
import type { ApiClients, FeatureSignal } from "./apiClients";
import { AppStatusProvider } from "./AppStatus";
import { BootError } from "./boot";
import { ErrorBlock, errorDetails, LoadingBlock } from "./ErrorBlock";
import { describeError } from "./errors";
import { appIcons } from "./icons";
import { messages as m } from "./messages";
import { createAppQueryClient } from "./queries";
import { appStorage, type SafeStorage } from "./storage";
import { StorageProvider } from "./StorageContext";
import { ThemeColorSync } from "./themeColor";
import { useDelayed } from "./useDelayed";

export const THEME_STORAGE_KEY = "agent-console.theme";

/** 저장값을 읽는다. 없거나 알 수 없는 값이면 "system"(OS 설정을 따름). */
export function readTheme(storage: SafeStorage): ThemeChoice {
  const raw = storage.get(THEME_STORAGE_KEY);
  return THEME_CYCLE.find((t) => t === raw) ?? "system";
}

/** 클라이언트를 만들 때 앱이 주는 콜백. `onAuthRejected`는 인증 거부(401/403) 때, `onFeatureSignal`은 기능 REST의 404·409 `feature_unavailable` 때 부른다. */
export interface ClientHooks {
  onAuthRejected: () => void;
  onFeatureSignal?: (signal: FeatureSignal) => void;
}

export interface AppRootProps {
  /** 서버 클라이언트를 만든다(설정 파일·부트스트랩 포함). 인증 거부 시 `onAuthRejected`를 불러야 한다 */
  createClients: (hooks: ClientHooks) => Promise<ApiClients>;
  /** 연동 부분 등록 데이터(기본: `links/linkParts`) */
  linkParts?: readonly LinkPartDef[];
  router: ReturnType<typeof createBrowserRouter>;
  storage?: SafeStorage;
  /** 새로고침 동작(테스트 주입) */
  onReload?: () => void;
  /** 질의 클라이언트(테스트 주입). 생략하면 앱 기본 */
  queryClient?: QueryClient;
}

type Boot =
  | { attempt: number; status: "ready"; clients: ApiClients }
  | { attempt: number; status: "error"; error: unknown };

const BACKGROUND_ERROR = "background-error";

/** 갱신 실패를 한 번만 토스트로 알린다(데이터가 있을 때의 백그라운드 갱신 오류). */
function BackgroundErrorBridge({ bus }: { bus: EventTarget }) {
  const toast = useToast();
  useEffect(() => {
    const onError = () => toast({ tone: "danger", text: m.common.refreshFailed });
    bus.addEventListener(BACKGROUND_ERROR, onError);
    return () => bus.removeEventListener(BACKGROUND_ERROR, onError);
  }, [bus, toast]);
  return null;
}

/** 기능 신호를 구독자에게 전하는 아주 작은 버스(클라이언트 생성이 먼저라 구독자는 나중에 붙는다). */
function createSignalBus() {
  const listeners = new Set<(signal: FeatureSignal) => void>();
  return {
    emit: (signal: FeatureSignal) => listeners.forEach((l) => l(signal)),
    subscribe: (listener: (signal: FeatureSignal) => void) => {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
  };
}

/** 앱 부팅(주소·토큰 획득) -> 테마·질의·토스트·API 컨텍스트 -> 라우터. */
export function AppRoot({ createClients, router, storage = appStorage, onReload = () => window.location.reload(), queryClient, linkParts = DEFAULT_LINK_PARTS }: AppRootProps) {
  const [attempt, setAttempt] = useState(0);
  const [boot, setBoot] = useState<Boot | null>(null);
  const [authRejected, setAuthRejected] = useState(false);
  const [theme, setTheme] = useState<ThemeChoice>(() => readTheme(storage));
  const [bus] = useState(() => new EventTarget());
  const [signals] = useState(() => createSignalBus());
  const client = useMemo(() => queryClient ?? createAppQueryClient({ onBackgroundError: () => bus.dispatchEvent(new Event(BACKGROUND_ERROR)) }), [queryClient, bus]);

  useEffect(() => {
    let cancelled = false;
    let created: ApiClients | undefined;
    createClients({ onAuthRejected: () => setAuthRejected(true), onFeatureSignal: signals.emit }).then(
      (clients) => {
        created = clients;
        if (cancelled) clients.ws.close();
        else setBoot({ attempt, status: "ready", clients });
      },
      (error: unknown) => {
        if (!cancelled) setBoot({ attempt, status: "error", error });
      },
    );
    return () => {
      cancelled = true;
      created?.ws.close();
    };
  }, [createClients, attempt, signals]);

  const booting = boot === null || boot.attempt !== attempt;
  const showSpinner = useDelayed(booting);
  const onThemeChange = useCallback(
    (next: ThemeChoice) => {
      setTheme(next);
      storage.set(THEME_STORAGE_KEY, next);
    },
    [storage],
  );
  const status = useMemo(() => ({ authRejected, reload: onReload }), [authRejected, onReload]);

  const themed = (children: ReactNode) => (
    <ThemeProvider theme={theme} onThemeChange={onThemeChange}>
      <ThemeColorSync />
      <IconRegistryProvider icons={appIcons}>
        <StorageProvider storage={storage}>{children}</StorageProvider>
      </IconRegistryProvider>
    </ThemeProvider>
  );

  if (booting) {
    return themed(<div className="app-boot">{showSpinner ? <LoadingBlock label={m.app.booting} /> : null}</div>);
  }
  if (boot.status === "error") {
    const bootError = boot.error instanceof BootError ? boot.error : undefined;
    const cause = bootError?.cause ?? boot.error;
    const view = describeError(cause, m.boot.failedTitle);
    const address = bootError?.baseUrl ?? "";
    const details = errorDetails(view, address === "" ? undefined : `${m.boot.requestAddress}: ${address}`);
    return themed(
      <div className="app-boot">
        <ErrorBlock
          title={m.boot.failedTitle}
          message={m.boot.failedBody(address === "" ? "?" : address)}
          details={details}
          detailsLabel={m.common.details}
          retryLabel={m.boot.retry}
          onRetry={() => setAttempt((a) => a + 1)}
        >
          {bootError?.corsSuspected ? <p className="ac-text app-wrap">{m.boot.corsHint}</p> : null}
        </ErrorBlock>
      </div>,
    );
  }
  return themed(
    <ApiProvider clients={boot.clients}>
      <QueryClientProvider client={client}>
        <ToastProvider regionLabel={m.common.notifications}>
          <BackgroundErrorBridge bus={bus} />
          <ModulesProvider subscribeSignals={signals.subscribe}>
            <LinkPartsProvider parts={linkParts}>
              <AppStatusProvider value={status}>
                <RouterProvider router={router} />
              </AppStatusProvider>
            </LinkPartsProvider>
          </ModulesProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ApiProvider>,
  );
}
