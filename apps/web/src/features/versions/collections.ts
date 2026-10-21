import { definitionBase } from "@agent-console/api-client";
import { contractsSchema } from "@agent-console/contracts";
import type { SchemaNode } from "../../lib/schemaTools";
import { schemaTitleResolver, type ReadablePathOptions } from "./versionsLogic";

/**
 * 버전 경로 표(데이터): 계약 모델 이름 -> REST 컬렉션 경로. 서버 `DEFAULT_VERSIONED_COLLECTIONS`와 같은 표이며,
 * 새 정의 종류는 항목 하나를 더하면 같은 화면(`DefinitionVersionsTab`)이 그대로 동작한다.
 * `singleton`은 id 없는 정의(설정)다.
 */
export const VERSIONED_MODELS: Readonly<Record<string, { collection: string; singleton?: boolean }>> = {
  Agent: { collection: "/agents" },
  Graph: { collection: "/graphs" },
  Resource: { collection: "/resources" },
  WorkspaceSettings: { collection: "/settings", singleton: true },
};

/** 모델 + id -> 정의 경로(`/agents/a1`). 모르는 모델은 undefined. */
export function versionBaseOf(model: string, id?: string): string | undefined {
  const entry = Object.hasOwn(VERSIONED_MODELS, model) ? VERSIONED_MODELS[model] : undefined;
  if (entry === undefined) return undefined;
  return entry.singleton === true ? definitionBase(entry.collection) : id === undefined ? undefined : definitionBase(entry.collection, id);
}

/** 모델의 스키마 title로 비교 표 경로를 읽기 좋게 만드는 옵션. 스키마를 모르면 빈 옵션(원문 경로). */
export function pathOptionsOf(model: string): ReadablePathOptions {
  const def = contractsSchema.$defs[model] as SchemaNode | undefined;
  if (def === undefined) return {};
  const root: SchemaNode = { ...def, $defs: contractsSchema.$defs };
  return { schemaTitles: schemaTitleResolver(root) };
}
