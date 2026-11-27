import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";
/** 내보내기 다이얼로그 문구(한 곳). 형식·정의 종류 이름은 서버가 준 값을 그대로 보이며 여기에는 없다. */
/** 이 화면의 문구를 만든다(번역 함수 `t`는 `exports` 묶음). */
export function createExportMessages(t: Translate) {
  return {
    menu: t("menu"),
    title: t("title"),
    close: t("close"),
    steps: {
      exporter: t("steps.exporter"),
      items: t("steps.items"),
      preview: t("steps.preview"),
      destination: t("steps.destination"),
    },
    stepsLabel: t("stepsLabel"),
    prev: t("prev"),
    next: t("next"),
    doExport: t("doExport"),
    saveFirst: t("saveFirst"),
    unsavedInfo: t("unsavedInfo"),
    warningsToggle: (n: number) => t("warningsToggle", { n, count: n }),
    warningsRegion: t("warningsRegion"),
    exporter: {
      label: t("exporter.label"),
      loading: t("exporter.loading"),
      empty: t("exporter.empty"),
      emptyLink: t("exporter.emptyLink"),
      failed: t("exporter.failed"),
      retry: t("exporter.retry"),
      kindsLabel: t("exporter.kindsLabel"),
    },
    items: {
      title: t("items.title"),
      add: t("items.add"),
      remove: t("items.remove"),
      none: t("items.none"),
      unsupported: t("items.unsupported"),
      exclude: t("items.exclude"),
      pickerTitle: t("items.pickerTitle"),
      pickerSearch: t("items.pickerSearch"),
      pickerKind: t("items.pickerKind"),
      pickerEmpty: t("items.pickerEmpty"),
      pickerFailed: t("items.pickerFailed"),
      pickerClose: t("items.pickerClose"),
      pickerAdded: t("items.pickerAdded"),
      kindLabels: {
        Graph: t("items.kindLabels.Graph"),
        Agent: t("items.kindLabels.Agent"),
        Resource: t("items.kindLabels.Resource"),
      } as Record<string, string>,
    },
    options: {
      title: t("options.title"),
      none: t("options.none"),
      failed: t("options.failed"),
      unset: t("options.unset"),
      hint: t("options.hint"),
    },
    preview: {
      summary: (n: number, size: string) => t("preview.summary", { n, size, count: n }),
      byAction: {
        create: t("preview.byAction.create"),
        overwrite: t("preview.byAction.overwrite"),
        skip: t("preview.byAction.skip"),
        conflict: t("preview.byAction.conflict"),
      } as Record<string, string>,
      loading: t("preview.loading"),
      refreshing: t("preview.refreshing"),
      empty: t("preview.empty"),
      failed: t("preview.failed"),
      retry: t("preview.retry"),
      treeView: t("preview.treeView"),
      flatView: t("preview.flatView"),
      viewLabel: t("preview.viewLabel"),
      files: t("preview.files"),
      blocked: t("preview.blocked"),
      toOptions: t("preview.toOptions"),
      routedBack: t("preview.routedBack"),
    },
    dest: {
      group: t("dest.group"),
      archive: t("dest.archive"),
      archiveHint: t("dest.archiveHint"),
      folder: t("dest.folder"),
      root: t("dest.root"),
      subdir: t("dest.subdir"),
      subdirHint: t("dest.subdirHint"),
      problems: {
        absolute: t("dest.problems.absolute"),
        dotdot: t("dest.problems.dotdot"),
        empty_segment: t("dest.problems.empty_segment"),
        forbidden_char: t("dest.problems.forbidden_char"),
      } as Record<string, string>,
      onConflict: t("dest.onConflict"),
      conflictOptions: {
        skip: {
          title: t("dest.conflictOptions.skip.title"),
          hint: t("dest.conflictOptions.skip.hint"),
        },
        overwrite: {
          title: t("dest.conflictOptions.overwrite.title"),
          hint: t("dest.conflictOptions.overwrite.hint"),
        },
        fail: {
          title: t("dest.conflictOptions.fail.title"),
          hint: t("dest.conflictOptions.fail.hint"),
        },
      } as Record<string, { title: string; hint: string }>,
      conflictsNow: (n: number) => t("dest.conflictsNow", { n, count: n }),
      rootsLoading: t("dest.rootsLoading"),
      rootPath: t("dest.rootPath"),
      exporting: t("dest.exporting"),
      failed: t("dest.failed"),
      conflictFailed: t("dest.conflictFailed"),
      conflictPaths: t("dest.conflictPaths"),
    },
    overwrite: {
      title: t("overwrite.title"),
      body: (n: number) => t("overwrite.body", { n, count: n }),
      confirm: t("overwrite.confirm"),
      cancel: t("overwrite.cancel"),
    },
    result: {
      title: t("result.title"),
      archiveDone: (name: string, size: string) => t("result.archiveDone", { name, size }),
      summary: (written: number, skipped: number) => t("result.summary", { written, skipped }),
      failedFiles: t("result.failedFiles"),
      where: t("result.where"),
      copyPath: t("result.copyPath"),
      copied: t("result.copied"),
      again: t("result.again"),
      announce: t("result.announce"),
      files: t("result.files"),
    },
    severity: { error: t("severity.error"), warning: t("severity.warning"), info: t("severity.info") } as Record<string, string>,
    action: {
      unknown: (value: string) => value,
    },
  };
}
export type ExportMessages = ReturnType<typeof createExportMessages>;

/** 현재 언어의 문구(렌더 때 만든다). */
export function useExportMessages(): ExportMessages {
  return useMessageTable("exports", createExportMessages);
}
