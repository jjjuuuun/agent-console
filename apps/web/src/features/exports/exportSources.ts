import type { RestClient } from "@agent-console/api-client";
import { kindOfModel } from "../library";
import { exportMessages as t } from "./messages";

/** 항목 고르기에 쓰는 정의 목록 원천(데이터). 새 정의 종류는 항목 하나를 더하면 고를 수 있다. */
export interface ItemSource {
  /** 계약 모델 이름(저장소 kind는 계약에서 읽는다) */
  model: string;
  /** 목록 읽기 -> {id, name} */
  load: (rest: RestClient) => Promise<{ id: string; name: string }[]>;
}

export const ITEM_SOURCES: readonly ItemSource[] = [
  { model: "Graph", load: async (rest) => (await rest.listGraphs({ validate: false })).map((g) => ({ id: g.id, name: g.name })) },
  { model: "Agent", load: async (rest) => (await rest.listAgents()).map((a) => ({ id: a.id, name: a.name })) },
  { model: "Resource", load: async (rest) => (await rest.listResources()).map((r) => ({ id: r.id, name: r.name })) },
];

/** 원천의 저장소 kind(계약에서 읽은 값). */
export function sourceKind(source: ItemSource): string | undefined {
  return kindOfModel(source.model);
}

/** 정의 종류의 표시 이름. 모르는 종류는 서버가 준 문자열 그대로. */
export function kindLabel(kind: string): string {
  const source = ITEM_SOURCES.find((s) => sourceKind(s) === kind);
  const label = source === undefined ? undefined : t.items.kindLabels[source.model];
  return label ?? kind;
}
