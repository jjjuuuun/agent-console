import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";
/** 백엔드 구독 로그인·로그아웃 문구(한 곳). 단계 안내·사유·notice·쓰기 범위는 서버가 준 문장을 그대로 보이며 여기에는 없다. */
export const createLoginMessages = (t: Translate) => ({
  titleFallback: t("titleFallback"),
  writesHeading: t("writesHeading"),
  start: t("start"),
  starting: t("starting"),
  cancel: t("cancel"),
  close: t("close"),
  retry: t("retry"),
  remaining: (mmss: string) => t("remaining", { mmss }),
  stepsLabel: t("stepsLabel"),
  steps: [t("steps.browser"), t("steps.code"), t("steps.confirm")],
  stepState: { done: t("stepState.done"), active: t("stepState.active"), todo: t("stepState.todo") },
  openPage: t("openPage"),
  browserHint: t("browserHint"),
  copyLink: t("copyLink"),
  linkCopied: t("linkCopied"),
  codeLabelFallback: t("codeLabelFallback"),
  codeSend: t("codeSend"),
  codeSending: t("codeSending"),
  codeSendFailed: t("codeSendFailed"),
  screenToggle: t("screenToggle"),
  screenLabel: t("screenLabel"),
  screenEmpty: t("screenEmpty"),
  screenSendLabel: t("screenSendLabel"),
  screenSend: t("screenSend"),
  keyButton: (key: string) => t("keyButton", { key }),
  keyLabels: { enter: "Enter" } as Readonly<Record<string, string>>,
  succeeded: t("succeeded"),
  cancelled: t("cancelled"),
  failedTitle: t("failedTitle"),
  expiredTitle: t("expiredTitle"),
  lost: t("lost"),
  details: t("details"),
  reasonLabel: t("reasonLabel"),
  warnings: t("warnings"),
  startFailed: t("startFailed"),
  busyTitle: t("busyTitle"),
  busyBody: t("busyBody"),
  busyResume: t("busyResume"),
  busyCancelOther: t("busyCancelOther"),
  menuLabel: t("menuLabel"),
  menuTrigger: "…",
  logoutTitle: t("logoutTitle"),
  logoutBody: t("logoutBody"),
  logoutConfirm: t("logoutConfirm"),
  logoutRunning: t("logoutRunning"),
  logoutDone: t("logoutDone"),
  logoutFailed: t("logoutFailed"),
} as const);

export type LoginMessages = ReturnType<typeof createLoginMessages>;

/** 로그인·로그아웃 문구 표(현재 화면 언어). */
export function useLoginMessages(): LoginMessages {
  return useMessageTable("backendLogin", createLoginMessages);
}
