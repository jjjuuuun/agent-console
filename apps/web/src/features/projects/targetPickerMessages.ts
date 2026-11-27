import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";
/**
 * 시작 대상 고르기(`ProjectTargetPicker`)와 시작 오류 배너의 문구 표(screen-projects §5.4).
 * 구성 종류·프로젝트 이름은 값으로 받는다(코드에 고정하지 않는다).
 */
/** 이 화면의 문구를 만든다(번역 함수 `t`는 `projectsTarget` 묶음). */
export function createTargetPickerMessages(t: Translate) {
  return {
    folder: {
      label: t("folder.label"),
      change: t("folder.change"),
      changeLabel: t("folder.changeLabel"),
      willSwitch: (name: string) => t("folder.willSwitch", { name }),
      repath: t("folder.repath"),
      problem: (status: string) => t("folder.problem", { status }),
    },
    config: {
      label: t("config.label"),
      search: t("config.search"),
      searchPlaceholder: t("config.searchPlaceholder"),
      list: t("config.list"),
      loading: t("config.loading"),
      loadFailed: t("config.loadFailed"),
      retry: t("config.retry"),
      noMatches: t("config.noMatches"),
      import: t("config.import"),
      emptyTitle: t("config.emptyTitle"),
      importPrimary: t("config.importPrimary"),
      createHere: t("config.createHere"),
      editConfig: t("config.editConfig"),
      showIssues: t("config.showIssues"),
      hideIssues: t("config.hideIssues"),
      blockedChip: (n: number) => t("config.blockedChip", { n, count: n }),
      warnChip: (n: number) => t("config.warnChip", { n, count: n }),
      nodes: (n: number) => t("config.nodes", { n }),
      lastUsed: (rel: string) => t("config.lastUsed", { rel }),
      notSelectable: t("config.notSelectable"),
    },
    start: {
      newChatTitle: t("start.newChatTitle"),
      startChat: t("start.startChat"),
      titleLabel: t("start.titleLabel"),
      titleHelp: t("start.titleHelp"),
      cancel: t("start.cancel"),
      creating: t("start.creating"),
    },
    blocked: {
      noConfig: t("blocked.noConfig"),
      signedOut: t("blocked.signedOut"),
      signIn: t("blocked.signIn"),
    },
    error: {
      required: t("error.required"),
      pickProject: t("error.pickProject"),
      notImportedInLibrary: (name: string) => t("error.notImportedInLibrary", { name }),
      importAndRun: t("error.importAndRun"),
      notImportedMissing: (name: string) => t("error.notImportedMissing", { name }),
      toLibrary: t("error.toLibrary"),
      folderUnusable: t("error.folderUnusable"),
      repath: t("error.repath"),
      manifestInvalid: t("error.manifestInvalid"),
      checkInHome: t("error.checkInHome"),
      recordsReadonly: t("error.recordsReadonly"),
      recordsFolderMissing: t("error.recordsFolderMissing"),
      recordsNewer: t("error.recordsNewer"),
      recordsBroken: t("error.recordsBroken"),
      recordsBusy: t("error.recordsBusy"),
      retry: t("error.retry"),
      configReadonly: t("error.configReadonly"),
      outsideFolderAt: (nodePath: string) => t("error.outsideFolderAt", { nodePath }),
      outsideFolder: (path: string, layer: string) => (layer === "" ? t("error.outsideFolder", { path }) : t("error.outsideFolderLayer", { path, layer })),
      openSettings: t("error.openSettings"),
      dismiss: t("error.dismiss"),
    },
  };
}
export type TargetPickerMessages = ReturnType<typeof createTargetPickerMessages>;

/** 현재 언어의 문구(렌더 때 만든다). */
export function useTargetPickerMessages(): TargetPickerMessages {
  return useMessageTable("projectsTarget", createTargetPickerMessages);
}
