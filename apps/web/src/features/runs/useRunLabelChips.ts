import { useMemo } from "react";
import type { LabelDisplay } from "@agent-console/contracts";
import { useModuleList } from "../../modules";
import { DEFAULT_ROUTES, routeServing } from "../../shell/routeConfig";
import { resolveLabelChips, type LabelChips } from "./runLabels";

/** 모든 모듈이 선언한 라벨 표시 규칙을 모은다(`GET /modules`의 `label_display`). 모듈 id는 보지 않는다. */
export function useLabelDisplay(): readonly LabelDisplay[] {
  const modules = useModuleList();
  return useMemo(() => modules.flatMap((m) => m.label_display ?? []), [modules]);
}

/** 실행 라벨 → 머리 칩 모델. 열 화면은 라우트 데이터의 역할로 푼다(그 역할을 맡은 화면이 없으면 링크 없는 칩). */
export function useRunLabelChips(labels: Readonly<Record<string, string>> | undefined): LabelChips {
  const display = useLabelDisplay();
  return useMemo(() => resolveLabelChips(labels, display, (role) => routeServing(DEFAULT_ROUTES, role)?.path), [labels, display]);
}
