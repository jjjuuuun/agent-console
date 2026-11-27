import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";
/**
 * 프로젝트 UI 문구 표. 프로젝트 이름·종류 이름·모듈 id는 여기에 없다(서버 데이터).
 */
/** 이 화면의 문구를 만든다(번역 함수 `t`는 `projectsApp` 묶음). */
export function createProjectMessages(t: Translate) {
  return {
    switcher: {
      region: t("switcher.region"),
      label: t("switcher.label"),
      all: t("switcher.all"),
      allHint: t("switcher.allHint"),
      search: t("switcher.search"),
      searchPlaceholder: t("switcher.searchPlaceholder"),
      noMatch: t("switcher.noMatch"),
      listLabel: t("switcher.listLabel"),
      newProject: t("switcher.newProject"),
      manage: t("switcher.manage"),
      createFirst: t("switcher.createFirst"),
      createFirstHint: t("switcher.createFirstHint"),
      tileTitle: (name: string) => t("switcher.tileTitle", { name }),
      current: t("switcher.current"),
      unknownName: (id: string) => id,
      triggerLabel: (name: string, hint?: string) => (hint === undefined ? t("switcher.triggerLabel", { name }) : t("switcher.triggerLabelHint", { name, hint })),
      switchedToast: (name: string) => t("switcher.switchedToast", { name }),
      adoptedToast: (name: string) => t("switcher.adoptedToast", { name }),
      switchedAllToast: t("switcher.switchedAllToast"),
      shortcutTitle: t("switcher.shortcutTitle"),
    },
    region: {
      label: t("region.label"),
      toggleLabel: t("region.toggleLabel"),
      collapse: t("region.collapse"),
      expand: t("region.expand"),
      count: (n: number) => t("region.count", { n }),
      listLabel: t("region.listLabel"),
      add: t("region.add"),
      addLabel: t("region.addLabel"),
      empty: t("region.empty"),
      loadFailed: t("region.loadFailed"),
      retry: t("region.retry"),
      folderUnset: t("region.folderUnset"),
      railLabel: (name?: string) => (name === undefined ? t("region.railLabel") : t("region.railLabelNamed", { name })),
      railMenuLabel: t("region.railMenuLabel"),
      menuLabel: (name: string) => t("region.menuLabel", { name }),
      rowTitle: (name: string, path: string) => (path === "" ? name : `${name}\n${path}`),
    },
    create: {
      title: t("create.title"),
      submit: t("create.submit"),
      name: t("create.name"),
      description: t("create.description"),
      failed: t("create.failed"),
      created: (name: string) => t("create.created", { name }),
      guideAction: t("create.guideAction"),
    },
    move: {
      menu: t("move.menu"),
      selectMode: t("move.selectMode"),
      selectModeOff: t("move.selectModeOff"),
      selectAll: t("move.selectAll"),
      selected: (n: number) => t("move.selected", { n }),
      selectRow: (name: string) => t("move.selectRow", { name }),
      clearSelection: t("move.clearSelection"),
    },
    copyReserved: {
      noCopy: t("copyReserved.noCopy"),
    },
    manage: {
      title: t("manage.title"),
      empty: t("manage.empty"),
      emptyBody: t("manage.emptyBody"),
      create: t("manage.create"),
      listLabel: t("manage.listLabel"),
      loadFailed: t("manage.loadFailed"),
      retry: t("manage.retry"),
      select: t("manage.select"),
      switchTo: t("manage.switchTo"),
      isCurrent: t("manage.isCurrent"),
      name: t("manage.name"),
      description: t("manage.description"),
      logProjects: t("manage.logProjects"),
      logProjectsHint: t("manage.logProjectsHint"),
      save: t("manage.save"),
      saved: t("manage.saved"),
      saveFailed: t("manage.saveFailed"),
      conflict: t("manage.conflict"),
      reload: t("manage.reload"),
      delete: t("manage.delete"),
      deleteTitle: (name: string) => t("manage.deleteTitle", { name }),
      deleteBody: (n: number) => (n === 0 ? t("manage.deleteBodyNone") : t("manage.deleteBody", { n, count: n })),
      deleteItems: t("manage.deleteItems"),
      deleteConfirm: t("manage.deleteConfirm"),
      deleteFailed: t("manage.deleteFailed"),
      deleted: (name: string) => t("manage.deleted", { name }),
      cancel: t("manage.cancel"),
      close: t("manage.close"),
    },
    usage: {
      accountWide: t("usage.accountWide"),
      accountWideTitle: t("usage.accountWideTitle"),
    },
  };
}
export type ProjectMessages = ReturnType<typeof createProjectMessages>;

/** 현재 언어의 문구(렌더 때 만든다). */
export function useProjectMessages(): ProjectMessages {
  return useMessageTable("projectsApp", createProjectMessages);
}
