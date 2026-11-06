import { useMemo } from "react";
import type { LogTaxonomyView } from "@agent-console/log-view";
import type { FilterOptionsData } from "./LogFilters";
import { useLogSources } from "./useLogsApi";

/** 필터 막대의 선택지 데이터: 출처(서버 목록) · 범주(분류 체계 순서 + 데이터에 나온 것). */
export function useFilterOptions(taxonomy: LogTaxonomyView, seenCategories: readonly string[]): FilterOptionsData {
  const sources = useLogSources();
  return useMemo(() => {
    const ids = [...taxonomy.order];
    for (const c of seenCategories) if (!ids.includes(c)) ids.push(c);
    return {
      sources: sources.data,
      categoryIds: ids,
      categoryName: (id) => taxonomy.get(id).name,
    };
  }, [sources.data, taxonomy, seenCategories]);
}
