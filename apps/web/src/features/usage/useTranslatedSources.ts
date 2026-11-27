import { useMemo } from "react";
import type { UsageSourceInfo } from "@agent-console/contracts";
import { useServerTranslate } from "../../i18n";
import { translateUsageSources } from "./usageLib";

/** 출처 목록(`GET /usage/sources`)의 서버 원문을 현재 화면 언어로 바꾼 목록. 데이터가 같고 언어가 같으면 같은 배열을 돌려준다. */
export function useTranslatedSources(data: readonly UsageSourceInfo[] | undefined): readonly UsageSourceInfo[] | undefined {
  const tr = useServerTranslate();
  return useMemo(() => (data === undefined ? undefined : translateUsageSources(data, tr)), [data, tr]);
}
