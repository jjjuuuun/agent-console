import { useT } from "@agent-console/i18n";

/** 정의 상세 화면(에이전트·리소스·팀)이 버전 탭 머리에 쓰는 이름. 화면 언어를 따른다. */
export function useVersionLabels(): { tab: string; title: string } {
  const t = useT("versions");
  return { tab: t("tab"), title: t("title") };
}
