import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { BackendDescriptor } from "@agent-console/contracts";
import type { RestClient } from "@agent-console/api-client";
import { visibleBackends } from "../../app/backendVisibility";
import { useAppMessages } from "../../app/appMessages";
import { queryKeys, useApiQuery, useWorkspaceSettings } from "../../app/queries";
import { useRegisterCommands } from "../../shell/commands";
import { readinessShownBackends, useBackendReadiness } from "../backendReadiness";
import { BACKEND_CONNECT_TRIGGER_ATTR } from "./BackendConnectButton";
import { BackendConnectDialog } from "./BackendConnectDialog";
import { BackendConnectContext, type BackendConnectPhase, type BackendConnectSummary, type BackendConnectValue, type OpenBackendConnectOptions } from "./context";
import { useBackendConnectMessages } from "./messages";
import { pickBackendTone } from "./pickBackendTone";

/** 바로가기 명령 id(`ui.keybindings`에서 사용자가 키를 붙일 수 있는 이름. 기본 단축키는 없다). */
export const BACKEND_CONNECT_COMMAND_ID = "backend.connect.open";

const NO_BACKENDS: readonly BackendDescriptor[] = [];
const loadBackends = (rest: RestClient) => rest.listBackends();

export interface BackendConnectProviderProps {
  /** 모달의 [설정에서 자세히]가 가는 주소(`경로#섹션/앵커`). 없으면 링크를 그리지 않는다 */
  settingsHref?: string | undefined;
  /** 모달 안 카드 맨 아래 자리(모델 줄 등). 연동 대상이 없으면 생략 */
  renderFooter?: ((backend: BackendDescriptor) => ReactNode) | undefined;
  children: ReactNode;
}

/**
 * 백엔드 연결 바로가기의 데이터 연결(앱 셸에 한 번). 백엔드 목록·준비 상태·기본 백엔드를 읽어 한 판정으로
 * 도구줄 단추·사용량 칩·Ctrl+K 명령에 같은 상태를 준다. 모달도 여기서 한 번만 그린다.
 * 보이는 조건은 설정의 준비 상태 섹션과 같은 함수(`readinessShownBackends`)이며 모듈·백엔드 id를 모른다.
 */
export function BackendConnectProvider({ settingsHref, renderFooter, children }: BackendConnectProviderProps) {
  const m = useBackendConnectMessages();
  const app = useAppMessages();
  const backendsQuery = useApiQuery(queryKeys.descriptors("backends"), loadBackends, { meta: { silentBackgroundError: true } });
  const status = useBackendReadiness();
  const settings = useWorkspaceSettings();
  const defaults = settings.data?.value.agent_defaults as Record<string, unknown> | null | undefined;
  const rawDefault = defaults?.["backend"];
  const defaultBackendId = typeof rawDefault === "string" && rawDefault !== "" ? rawDefault : undefined;

  const visible = useMemo(() => visibleBackends(backendsQuery.data ?? NO_BACKENDS), [backendsQuery.data]);
  const shown = useMemo(() => readinessShownBackends(visible, status.readiness), [visible, status.readiness]);
  const statusFailed = status.isError && status.data === undefined;

  let phase: BackendConnectPhase = "ready";
  if (backendsQuery.isPending) phase = "loading";
  else if (backendsQuery.isError || !status.available || shown.length === 0) phase = "hidden";

  const picked = useMemo(
    () => pickBackendTone({ backends: shown, defaultBackendId, readiness: status.readiness, loading: status.isPending, failed: statusFailed }),
    [shown, defaultBackendId, status.readiness, status.isPending, statusFailed],
  );
  const summary = useMemo<BackendConnectSummary>(() => {
    const tone = picked.tone;
    const label = tone === "checking" ? m.chipChecking : app.backendReadiness.toneLabel[tone === "unavailable" ? "unknown" : tone] ?? "";
    const full = picked.readiness?.summary || app.backendReadiness.unknownSummary;
    const short = picked.readiness?.short_summary || full;
    if (tone === "checking") return { tone, summary: m.chipChecking, label, tip: m.tipChecking };
    if (tone === "unavailable") return { tone, summary: label, label, tip: m.tipUnavailable };
    return { tone, summary: short, label, tip: m.tip(picked.backend?.title ?? "", short) };
  }, [picked, m, app.backendReadiness]);

  const [dialog, setDialog] = useState<{ open: boolean; focusBackend: string | undefined }>({ open: false, focusBackend: undefined });
  const refetchStatus = status.refetch;
  const open = useCallback((options?: OpenBackendConnectOptions) => setDialog({ open: true, focusBackend: options?.focusBackend }), []);
  const close = useCallback(() => {
    setDialog((d) => ({ ...d, open: false }));
    void refetchStatus();
  }, [refetchStatus]);

  // 창이 다시 초점을 얻으면 한 번 다시 읽는다(타이머 폴링은 없다: 서버가 값을 캐시한다).
  const phaseRef = useRef(phase);
  useEffect(() => {
    phaseRef.current = phase;
  });
  useEffect(() => {
    const onFocus = () => {
      if (phaseRef.current === "ready") void refetchStatus();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refetchStatus]);

  // 모달이 닫힌 뒤 초점이 갈 곳을 잃었으면(연 요소가 사라짐) 도구줄 단추, 없으면 본문으로 보낸다.
  const wasOpen = useRef(false);
  useEffect(() => {
    if (dialog.open) {
      wasOpen.current = true;
      return;
    }
    if (!wasOpen.current) return;
    wasOpen.current = false;
    const active = document.activeElement;
    if (active !== null && active !== document.body) return;
    const fallback = document.querySelector<HTMLElement>(`[${BACKEND_CONNECT_TRIGGER_ATTR}]`) ?? document.getElementById("app-main");
    fallback?.focus();
  }, [dialog.open]);

  // 화면이 바뀌어 숨김이 되면(모듈 꺼짐) 열린 모달은 안내만 남기고, 다음 판정에서 단추가 사라진다.
  const commands = useMemo(
    () =>
      phase === "ready"
        ? [{ id: BACKEND_CONNECT_COMMAND_ID, titleKey: "", title: m.command.title, hint: m.command.hint(summary.label), keywords: m.command.keywords, run: () => open() }]
        : [],
    [phase, m, summary.label, open],
  );
  useRegisterCommands(commands);

  const value = useMemo<BackendConnectValue>(() => ({ phase, summary: phase === "ready" ? summary : undefined, open }), [phase, summary, open]);
  return (
    <BackendConnectContext.Provider value={value}>
      {children}
      <BackendConnectDialog
        open={dialog.open && phase !== "loading"}
        onClose={close}
        backends={shown}
        defaultBackendId={defaultBackendId}
        focusBackend={dialog.focusBackend}
        off={phase === "hidden"}
        settingsHref={settingsHref}
        footer={renderFooter}
      />
    </BackendConnectContext.Provider>
  );
}
