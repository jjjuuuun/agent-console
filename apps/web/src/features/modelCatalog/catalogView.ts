import type { ModelInfo, ModelSource } from "@agent-console/contracts";
import type { BackendModelCatalogResult } from "@agent-console/api-client";

/** 상태 줄이 그리는 상태: 서버의 `discovery.state` + 요청 진행 중 + `signin`(실패 사유가 로그인 없음이라 오류 대신 안내로 보이는 것). */
export type CatalogLineState = "fetching" | "ok" | "stale" | "failed" | "disabled" | "unsupported" | "signin";

/** 모델 한 항목이 어느 출처를 가졌는가(서버가 준 순서 그대로, 빈 목록 = 출처 모름). */
export function modelSources(model: { sources?: readonly ModelSource[] | undefined }): readonly ModelSource[] {
  return model.sources ?? [];
}

/** 계정 조회(`discovered`)에서 온 항목 수 — 합친 목록 길이가 아니라 계정이 말한 수(design BC-7). */
export function discoveredCount(models: readonly ModelInfo[] | undefined): number {
  return (models ?? []).filter((m) => modelSources(m).includes("discovered")).length;
}

/**
 * 상태 줄을 그릴 상태. 카탈로그 경로가 없는 옛 서버(`discovery: null`)와 아직 응답 없음은 `null`(줄 없음)이고,
 * 요청이 진행 중이면(처음 또는 새로 고침) `fetching`이다.
 */
export function lineStateOf(catalog: BackendModelCatalogResult | undefined, fetching: boolean): CatalogLineState | null {
  if (fetching) return "fetching";
  if (catalog === undefined || catalog === null || catalog.discovery === null) return null;
  return catalog.discovery.state;
}
