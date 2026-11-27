import { useMemo } from "react";
import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";
import { mergeArrange, useArrangeMessages } from "../library";
/** 에이전트 화면 문구. 에이전트·백엔드·모델 이름은 서버 데이터이므로 여기에 없다. */
/** 이 화면의 문구를 만든다(번역 함수 `t`는 `agents` 묶음). 목록 보기 공용 문구는 `arrange` 묶음이고 `useAgentMessages`가 합친다. */
export function createAgentMessages(t: Translate) {
  return {
    title: t("title"),
    list: {
      label: t("list.label"),
      search: t("list.search"),
      searchPlaceholder: t("list.searchPlaceholder"),
      new: t("list.new"),
      filterAll: t("list.filterAll"),
      filterUsed: t("list.filterUsed"),
      filterUnused: t("list.filterUnused"),
      filterLabel: t("list.filterLabel"),
      empty: t("list.empty"),
      emptyBody: t("list.emptyBody"),
      noMatch: t("list.noMatch"),
      loadFailed: t("list.loadFailed"),
      usedBy: (n: number) => t("list.usedBy", { n, count: n }),
      usageText: (n: number): string => (n === 0 ? t("list.usageNone") : n >= 2 ? t("list.usageMany", { n }) : ""),
    },
    arrange: {
      groupNames: {
        "group.role": t("arrange.groupNames.groupRole"),
        "group.backend": t("arrange.groupNames.groupBackend"),
        "group.model": t("arrange.groupNames.groupModel"),
      } as Record<string, string>,
      noneLabels: {
        "group.role": t("arrange.noneLabels.groupRole"),
        "group.backend": t("arrange.noneLabels.groupBackend"),
        "group.model": t("arrange.noneLabels.groupModel"),
      } as Record<string, string>,
      sortNames: {
        "sort.usage": t("arrange.sortNames.sortUsage"),
      } as Record<string, string>,
      sortSummaries: {
        "sort.usage": t("arrange.sortSummaries.sortUsage"),
      } as Record<string, string>,
      roleDistinct: t("arrange.roleDistinct"),
    },
    pick: {
      title: t("pick.title"),
      body: t("pick.body"),
    },
    create: {
      fallbackId: t("create.fallbackId"),
      title: t("create.title"),
      submit: t("create.submit"),
      role: t("create.role"),
      roleHint: t("create.roleHint"),
      failed: t("create.failed"),
      resourcesTitle: t("create.resourcesTitle"),
    },
    detail: {
      notFound: t("detail.notFound"),
      toList: t("detail.toList"),
      loadFailed: t("detail.loadFailed"),
      id: t("detail.id"),
      save: t("detail.save"),
      saved: t("detail.saved"),
      revert: t("detail.revert"),
      menu: t("detail.menu"),
      duplicate: t("detail.duplicate"),
      delete: t("detail.delete"),
      viewJson: t("detail.viewJson"),
      jsonTitle: t("detail.jsonTitle"),
      tabsLabel: t("detail.tabsLabel"),
    },
    tabs: {
      settings: t("tabs.settings"),
      resources: t("tabs.resources"),
      usages: t("tabs.usages"),
      activity: t("tabs.activity"),
    },
    identity: {
      title: t("identity.title"),
      name: t("identity.name"),
      role: t("identity.role"),
      description: t("identity.description"),
      descriptionHint: t("identity.descriptionHint"),
      nameRequired: t("identity.nameRequired"),
    },
    display: {
      title: t("display.title"),
      icon: t("display.icon"),
      iconHint: t("display.iconHint"),
      iconInvalid: t("display.iconInvalid"),
      color: t("display.color"),
      colorHint: t("display.colorHint"),
      colorInvalid: t("display.colorInvalid"),
      colorOption: (n: string) => t("display.colorOption", { n }),
      preview: t("display.preview"),
    },
    settings: {
      title: t("settings.title"),
      hint: t("settings.hint"),
      effectiveFailed: t("settings.effectiveFailed"),
      loading: t("settings.loading"),
    },
    resources: {
      footer: t("resources.footer"),
      layerFallback: t("resources.layerFallback"),
      commonFailed: t("resources.commonFailed"),
    },
    usages: {
      empty: t("usages.empty"),
      toTeams: t("usages.toTeams"),
      team: t("usages.team"),
      nodes: t("usages.nodes"),
      failed: t("usages.failed"),
      nodeIds: (ids: readonly string[]) => (ids.length === 0 ? t("usages.nodeIdsNone") : ids.join(", ")),
    },
    activity: {
      empty: t("activity.empty"),
      failed: t("activity.failed"),
      started: t("activity.started"),
      run: t("activity.run"),
      events: t("activity.events"),
      last: t("activity.last"),
      more: t("activity.more"),
      open: t("activity.open"),
    },
    delete: {
      usedNote: t("delete.usedNote"),
      failed: t("delete.failed"),
    },
  };
}

/** 현재 언어의 문구(렌더 때 만든다). 목록 보기(`arrange`)는 공용 묶음에 이 화면 몫을 덧붙인 것이다. */
export function useAgentMessages() {
  const own = useMessageTable("agents", createAgentMessages);
  const arrange = useArrangeMessages();
  return useMemo(() => ({ ...own, arrange: mergeArrange(arrange, own.arrange) }), [own, arrange]);
}
export type AgentMessages = ReturnType<typeof useAgentMessages>;
/** 목록 보기(`arrange`)를 합치기 전의 이 화면 문구. 화면 밖 순수 함수가 받는다. */
export type AgentTexts = ReturnType<typeof createAgentMessages>;
