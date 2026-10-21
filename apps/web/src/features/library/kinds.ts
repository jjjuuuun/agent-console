import { contractsSchema } from "@agent-console/contracts";

/**
 * 계약 모델의 정의 종류 이름(저장소 kind)을 스키마의 `kind` 상수에서 읽는다.
 * 앱 코드에 종류 이름 문자열을 두지 않기 위한 단일 통로다.
 * @param model 계약 모델 이름(예: 에이전트 모델의 이름)
 */
export function kindOfModel(model: string): string | undefined {
  const props = contractsSchema.$defs[model]?.["properties"] as Record<string, { const?: unknown }> | undefined;
  const value = props?.["kind"]?.const;
  return typeof value === "string" ? value : undefined;
}

/** 정의 하나를 편집하는 질의 키(종류 이름은 계약에서 읽은 값을 그대로 쓴다). */
export const definitionKey = (kind: string | undefined, id: string) => ["definition", kind ?? "", id] as const;

/** 정의 종류. 계약 모델 이름 -> 스키마가 정한 kind. */
export const DEFINITION_KINDS = {
  agent: kindOfModel("Agent"),
  graph: kindOfModel("Graph"),
  resource: kindOfModel("Resource"),
} as const;
