import { useMemo } from "react";
import { useArrangeMessages } from "../library";
import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";

/** 출처 값(계약 `ArchitectureProfileInfo.origin`의 문서화된 어휘). 화면 문구는 `origin` 묶음. */
export const ORIGIN = { default: "default", user: "user", pluginPrefix: "plugin:" } as const;

/** 구조도 설정(프로필 목록·편집기) 문구. */
export function createArchSettingsMessages(t: Translate) {
  return {
    help: t("help"),
    origin: {
      default: t("origin.default"),
      user: t("origin.user"),
      userOverride: t("origin.userOverride"),
      plugin: (name: string) => t("origin.plugin", { name }),
    },
    defaultProfile: {
      first: t("defaultProfile.first"),
      missing: t("defaultProfile.missing"),
    },
    list: {
      title: (n: number) => t("list.title", { n }),
      label: t("list.label"),
      new: t("list.new"),
      import: t("list.import"),
      issues: (n: number) => t("list.issues", { n }),
      noIssues: t("list.noIssues"),
      counts: (cells: number, edges: number) => t("list.counts", { cells, edges }),
      unsaved: t("list.unsaved"),
      unknownCounts: t("list.unknownCounts"),
      notInList: t("list.notInList"),
      view: t("list.view"),
      edit: t("list.edit"),
      clone: t("list.clone"),
      disable: t("list.disable"),
      enable: t("list.enable"),
      remove: t("list.remove"),
      revert: t("list.revert"),
      disabledTitle: (n: number) => t("list.disabledTitle", { n }),
      empty: t("list.empty"),
      emptyBody: t("list.emptyBody"),
      enableDefaults: t("list.enableDefaults"),
      loadFailed: t("list.loadFailed"),
      retry: t("list.retry"),
      defaultsPending: t("list.defaultsPending"),
      actionsFor: (title: string) => t("list.actionsFor", { title }),
    },
    dialog: {
      cloneTitle: (title: string) => t("dialog.cloneTitle", { title }),
      newTitle: t("dialog.newTitle"),
      importTitle: t("dialog.importTitle"),
      id: t("dialog.id"),
      profileTitle: t("dialog.profileTitle"),
      sameId: t("dialog.sameId"),
      idTaken: t("dialog.idTaken"),
      idEmpty: t("dialog.idEmpty"),
      ok: t("dialog.ok"),
      cancel: t("dialog.cancel"),
      importBody: t("dialog.importBody"),
      importPaste: t("dialog.importPaste"),
      importCheck: t("dialog.importCheck"),
      importToEditor: t("dialog.importToEditor"),
      importParse: t("dialog.importParse"),
      removeTitle: (title: string) => t("dialog.removeTitle", { title }),
      removeBody: t("dialog.removeBody"),
      removeOk: t("dialog.removeOk"),
    },
    editor: {
      title: (title: string, id: string) => t("editor.title", { title, id }),
      viewTitle: (title: string, id: string) => t("editor.viewTitle", { title, id }),
      close: t("editor.close"),
      yaml: t("editor.yaml"),
      yamlLabel: t("editor.yamlLabel"),
      results: t("editor.results"),
      save: t("editor.save"),
      saveNote: t("editor.saveNote"),
      saveBlocked: t("editor.saveBlocked"),
      saveChecking: t("editor.saveChecking"),
      discardTitle: t("editor.discardTitle"),
      discardBody: t("editor.discardBody"),
      discardOk: t("editor.discardOk"),
      checking: t("editor.checking"),
      ok: t("editor.ok"),
      problems: (n: number) => t("editor.problems", { n }),
      line: (n: number) => t("editor.line", { n }),
      checkFailed: t("editor.checkFailed"),
      checkedAt: (time: string) => t("editor.checkedAt", { time }),
      parseError: t("editor.parseError"),
      notMap: t("editor.notMap"),
      readOnly: t("editor.readOnly"),
      loadFailed: t("editor.loadFailed"),
      newCellId: "cell-1",
      severityGlyph: { error: "✕", warning: "▲", info: "ⓘ" } as Record<string, string> as Record<string, string>,
      severity: {
        error: t("editor.severity.error"),
        warning: t("editor.severity.warning"),
        info: t("editor.severity.info"),
      } as Record<string, string>,
    },
    switch: { on: t("switch.on"), off: t("switch.off") },
    /** 이 화면이 공용 목록 보기 문구에 덧붙이는 몫(`useArchSettingsMessages`가 합친다) */
    /** 공용 목록 보기 문구(`useArrangeMessages`)에 덧붙이는 이 화면 몫(`mergeArrange`로 합친다). */
    arrange: {
      groupNames: { "group.origin": t("arrange.groupOrigin") } as Record<string, string>,
      sortNames: { "sort.title": t("arrange.sortTitle"), "sort.issues": t("arrange.sortIssues") } as Record<string, string>,
      sortSummaries: { "sort.title": t("arrange.sortTitleSummary"), "sort.issues": t("arrange.sortIssues") } as Record<string, string>,
    },
  };
}

/** 현재 언어의 `architectureSettings` 문구(렌더 때 만든다). 목록 보기(`arrange`)는 공용 문구에 이 화면 몫을 합친 것이다. */
export function useArchSettingsMessages() {
  const own = useMessageTable("architectureSettings", createArchSettingsMessages);
  const base = useArrangeMessages();
  return useMemo(
    () => ({ ...own, arrange: { ...base, groupNames: { ...base.groupNames, ...own.arrange.groupNames }, sortNames: own.arrange.sortNames, sortSummaries: own.arrange.sortSummaries } }),
    [own, base],
  );
}
export type ArchSettingsMessages = ReturnType<typeof useArchSettingsMessages>;
