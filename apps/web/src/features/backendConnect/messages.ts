import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";

/**
 * 백엔드 연결 바로가기(도구줄 단추·모달·명령·사용량 칩) 문구. 묶음: `backendConnect`.
 * 백엔드 이름·모델 이름은 사용자 데이터라 여기에 없다(번역하지 않는다). 개수가 든 문구는 `count`로 단·복수를 고른다.
 */
export const createBackendConnectMessages = (t: Translate) => ({
  /** 단추·화면 이름 */
  buttonName: t("buttonName"),
  /** 단추 툴팁이자 `aria-label` */
  tip: (name: string, summary: string) => t("tip", { name, summary }),
  tipChecking: t("tipChecking"),
  tipUnavailable: t("tipUnavailable"),
  chipLabel: t("chipLabel"),
  chipChecking: t("chipChecking"),
  command: { title: t("command.title"), keywords: t("command.keywords"), hint: (tone: string) => t("command.hint", { tone }) },
  dialog: { title: t("dialog.title"), lead: t("dialog.lead"), loading: t("dialog.loading"), off: t("dialog.off") },
  default: t("default"),
  defaultTip: t("defaultTip"),
  moreInSettings: t("moreInSettings"),
  models: {
    fetching: t("models.fetching"),
    okForm: (count: number, when: string) => t("models.okForm", { count, when }),
    okDialog: (count: number, when: string) => t("models.okDialog", { count, when }),
    none: t("models.none"),
    stale: (count: number, when: string) => t("models.stale", { count, when }),
    failed: t("models.failed"),
    disabled: t("models.disabled"),
    unsupported: t("models.unsupported"),
    refresh: t("models.refresh"),
    check: t("models.check"),
    fetched: (count: number) => t("models.fetched", { count }),
    moreActions: t("models.moreActions"),
  },
  source: { config: t("source.config"), configTip: t("source.configTip"), discovered: t("source.discovered"), discoveredTip: t("source.discoveredTip") },
});

export type BackendConnectMessages = ReturnType<typeof createBackendConnectMessages>;

/** 현재 화면 언어의 백엔드 연결 문구 표. */
export function useBackendConnectMessages(): BackendConnectMessages {
  return useMessageTable("backendConnect", createBackendConnectMessages);
}
