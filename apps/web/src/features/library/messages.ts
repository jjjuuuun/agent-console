import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";
/** 정의 목록·상세 화면(팀 구성·에이전트·리소스)이 함께 쓰는 문구. */
/** 이 화면의 문구를 만든다(번역 함수 `t`는 `library` 묶음). */
export function createLibraryMessages(t: Translate) {
  return {
    create: t("create"),
    cancel: t("cancel"),
    close: t("close"),
    retry: t("retry"),
    copy: t("copy"),
    copied: t("copied"),
    more: t("more"),
    rowMenu: t("rowMenu"),
    detailMenu: t("detailMenu"),
    search: t("search"),
    loading: t("loading"),
    none: t("none"),
    newDialog: {
      name: t("newDialog.name"),
      id: t("newDialog.id"),
      idHint: t("newDialog.idHint"),
      description: t("newDialog.description"),
      idErrors: {
        empty: t("newDialog.idErrors.empty"),
        pattern: t("newDialog.idErrors.pattern"),
        duplicate: t("newDialog.idErrors.duplicate"),
        reserved: t("newDialog.idErrors.reserved"),
      },
      nameRequired: t("newDialog.nameRequired"),
    },
    delete: {
      title: (name: string) => t("delete.title", { name }),
      body: t("delete.body"),
      action: t("delete.action"),
      usedBy: (n: number) => t("delete.usedBy", { n, count: n }),
      understood: t("delete.understood"),
      checking: t("delete.checking"),
      failed: t("delete.failed"),
    },
    picker: {
      title: t("picker.title"),
      search: t("picker.search"),
      allTypes: t("picker.allTypes"),
      empty: t("picker.empty"),
      noMatch: t("picker.noMatch"),
      createNew: t("picker.createNew"),
      pick: (name: string) => t("picker.pick", { name }),
    },
    attach: {
      moveUp: t("attach.moveUp"),
      moveDown: t("attach.moveDown"),
      remove: t("attach.remove"),
      modeLabel: t("attach.modeLabel"),
      add: t("attach.add"),
      empty: t("attach.empty"),
      readOnly: t("attach.readOnly"),
      missing: t("attach.missing"),
      modes: {
        add: t("attach.modes.add"),
        replace: t("attach.modes.replace"),
        remove: t("attach.modes.remove"),
      } as Record<string, string>,
    },
    usage: {
      kindTeam: t("usage.kindTeam"),
      kindAgent: t("usage.kindAgent"),
      kindResource: t("usage.kindResource"),
      kindCommon: t("usage.kindCommon"),
      nodes: (labels: string) => t("usage.nodes", { labels }),
      layer: t("usage.layer"),
    },
    menu: {
      label: t("menu.label"),
    },
    agentForm: {
      customModel: t("agentForm.customModel"),
      modelsFailed: t("agentForm.modelsFailed"),
      addTag: t("agentForm.addTag"),
      removeTag: (tag: string) => t("agentForm.removeTag", { tag }),
    },
    avatarLabel: (name: string) => t("avatarLabel", { name }),
  };
}
export type LibraryMessages = ReturnType<typeof createLibraryMessages>;

/** 현재 언어의 문구(렌더 때 만든다). */
export function useLibraryMessages(): LibraryMessages {
  return useMessageTable("library", createLibraryMessages);
}

/** 첨부 방식 라벨. 모르는 값은 서버 문자열 그대로. */
export function modeLabel(mode: string, modes: Readonly<Record<string, string>>): string {
  return modes[mode] ?? mode;
}
