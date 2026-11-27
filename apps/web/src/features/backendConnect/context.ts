import { createContext, useContext } from "react";

/** 바로가기 한 곳(도구줄·사용량·명령)에 보일 상태. 문구는 이미 화면 언어로 바뀐 것이다. */
export interface BackendConnectSummary {
  tone: "ok" | "warn" | "error" | "unknown" | "checking" | "unavailable";
  /** 짧은 상태(서버가 준 `short_summary`, 없으면 요약·"알 수 없음"). 확인 중이면 "확인 중…" */
  summary: string;
  /** 톤 이름(준비됨·주의·문제·알 수 없음·확인 중) */
  label: string;
  /** 툴팁이자 `aria-label`: "백엔드 연결: {이름} — {요약}" */
  tip: string;
}

export interface OpenBackendConnectOptions {
  /** 이 백엔드가 맨 위로 오게 연다(모델 칸의 [연결 확인…]이 쓴다) */
  focusBackend?: string;
}

export type OpenBackendConnect = (options?: OpenBackendConnectOptions) => void;

/** 판정 전에는 자리만 잡고(`loading`), 숨김이면 아무것도 그리지 않는다(`hidden`). */
export type BackendConnectPhase = "loading" | "hidden" | "ready";

export interface BackendConnectValue {
  phase: BackendConnectPhase;
  summary: BackendConnectSummary | undefined;
  open: OpenBackendConnect;
}

/** 공급자 밖(예: 사용량 화면 단독 사용)의 값: 숨김. */
export const BackendConnectContext = createContext<BackendConnectValue>({ phase: "hidden", summary: undefined, open: () => {} });

/** 모달을 여는 함수. 공급자가 없거나 바로가기가 숨김이면 `undefined`(그리지 않는다). */
export function useOpenBackendConnect(): OpenBackendConnect | undefined {
  const value = useContext(BackendConnectContext);
  return value.phase === "ready" ? value.open : undefined;
}

/** 지금 상태 요약. 공급자가 없거나 바로가기가 숨김이면 `undefined`. */
export function useBackendConnectSummary(): BackendConnectSummary | undefined {
  const value = useContext(BackendConnectContext);
  return value.phase === "ready" ? value.summary : undefined;
}

/** 도구줄 자리 예약용: 판정 전인지·보이는지·숨김인지. */
export function useBackendConnectPhase(): BackendConnectPhase {
  return useContext(BackendConnectContext).phase;
}
