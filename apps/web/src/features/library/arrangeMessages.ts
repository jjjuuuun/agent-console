import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";
/** 목록 보기(묶기·정렬·접기)·폴더 이동·라벨 편집의 공용 문구. 화면별 기준 이름은 `groupNames` 등에 덧붙여 쓴다(5.2R.62·63). */
/** 목록 보기 공용 문구를 만든다(번역 함수 `t`는 `arrange` 묶음). */
export function createArrangeMessages(t: Translate) {
  return {
    viewLabel: t("viewLabel"),
    groupTitle: t("groupTitle"),
    sortTitle: t("sortTitle"),
    collapseAll: t("collapseAll"),
    expandAll: t("expandAll"),
    none: t("none"),
    groupNames: {
      "group.folder": t("groupNames.groupFolder"),
      "group.labels": t("groupNames.groupLabels"),
      "group.project": t("groupNames.groupProject"),
      "group.type": t("groupNames.groupType"),
      "group.attribute": t("groupNames.groupAttribute"),
    } as Record<string, string>,
    summaryGroup: (name: string) => t("summaryGroup", { name }),
    noneLabels: {
      "group.folder": t("noneLabels.groupFolder"),
      "group.labels": t("noneLabels.groupLabels"),
      "group.project": t("noneLabels.groupProject"),
      "group.type": t("noneLabels.groupType"),
      "group.attribute": t("noneLabels.groupAttribute"),
    } as Record<string, string>,
    sortNames: {
      "sort.name": t("sortNames.sortName"),
      "sort.modified": t("sortNames.sortModified"),
    } as Record<string, string>,
    sortSummaries: {
      "sort.name": t("sortSummaries.sortName"),
      "sort.modified": t("sortSummaries.sortModified"),
    } as Record<string, string>,
    conflict: t("conflict"),
    retry: t("retry"),
    noProjects: t("noProjects"),
    attrKey: t("attrKey"),
    attrKeyPlaceholder: t("attrKeyPlaceholder"),
    move: {
      title: t("move.title"),
      target: (name: string) => t("move.target", { name }),
      search: t("move.search"),
      listLabel: t("move.listLabel"),
      create: (name: string) => t("move.create", { name }),
      clear: t("move.clear"),
      current: t("move.current"),
      cancel: t("move.cancel"),
      done: (name: string, folder: string) => t("move.done", { name, folder }),
      doneClear: (name: string) => t("move.doneClear", { name }),
      undo: t("move.undo"),
      undone: t("move.undone"),
      failed: t("move.failed"),
    },
    labels: {
      title: t("labels.title"),
      target: (name: string) => t("labels.target", { name }),
      input: t("labels.input"),
      remove: (l: string) => t("labels.remove", { l }),
      empty: t("labels.empty"),
      save: t("labels.save"),
      cancel: t("labels.cancel"),
      saved: (name: string) => t("labels.saved", { name }),
      failed: t("labels.failed"),
    },
  };
}
export type ArrangeMessages = ReturnType<typeof createArrangeMessages>;

/** 현재 언어의 목록 보기 공용 문구(렌더 때 만든다). */
export function useArrangeMessages(): ArrangeMessages {
  return useMessageTable("arrange", createArrangeMessages);
}


/** 화면이 덧붙이는 목록 보기 문구: 묶는 기준·정렬 이름 표에 항목을 더하고 그 밖의 문구를 더한다. */
export interface ArrangeExtra {
  groupNames?: Record<string, string>;
  noneLabels?: Record<string, string>;
  sortNames?: Record<string, string>;
  sortSummaries?: Record<string, string>;
}

/**
 * 공용 목록 보기 문구에 화면 몫을 합친다(표는 항목 단위로 덧씌우고, 나머지 문구는 그대로 더한다).
 * @param base 공용 문구.
 * @param extra 화면이 덧붙인 문구(없으면 공용 문구 그대로).
 */
export function mergeArrange<E extends ArrangeExtra>(base: ArrangeMessages, extra?: E): ArrangeMessages & E {
  const merged = { ...base, ...extra } as ArrangeMessages & E;
  for (const key of ["groupNames", "noneLabels", "sortNames", "sortSummaries"] as const) {
    merged[key] = { ...base[key], ...extra?.[key] };
  }
  return merged;
}
